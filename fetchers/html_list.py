"""Сайты без RSS: берём страницу со списком работ и следим за новыми ссылками.

Логика: собрали все ссылки, подходящие под link_pattern -> новые (которых ещё
нет в базе) догружаем по одной, чтобы вытащить настоящий заголовок и описание.
"""
from collections import Counter
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from .base import Item, session, clean_text, passes_keywords, apply_title_regex, TIMEOUT

SKIP_TAILS = {"", "work", "projects", "portfolio", "cases", "case-studies", "all-work"}
# служебные разделы: архивы по тегам, категориям, пагинация. Это не проекты,
# но по шаблону ссылки они неотличимы от кейсов — отсекаем по сегменту пути.
SKIP_SEGMENTS = {"tag", "tags", "category", "categories", "filter", "filters",
                 "author", "page", "search", "label", "topic", "topics",
                 "sector", "sectors", "industry", "industries", "service",
                 "services", "discipline", "disciplines", "type", "types"}
# некоторые сайты отдают мусор в og:title — тогда берём название из адреса
BAD_TITLES = {"undefined", "null", "none", "untitled", "home", "index"}


def _from_slug(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = slug.split("?")[0].replace("-", " ").replace("_", " ").strip()
    return slug.title() if slug else ""


def _collect_links(soup, base_url: str, pattern: str):
    """Все внутренние ссылки, подходящие под шаблон. Порядок сохраняем."""
    seen, out = set(), []
    host = urlsplit(base_url).netloc
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if pattern not in href:
            continue
        absolute = urljoin(base_url, href)
        parts = urlsplit(absolute)
        if parts.netloc != host:
            continue
        # отсекаем саму страницу-раздел, пагинацию и архивы по тегам
        segments = [s.lower() for s in parts.path.strip("/").split("/") if s]
        if any(s in SKIP_SEGMENTS for s in segments):
            continue
        tail = segments[-1] if segments else ""
        if tail in SKIP_TAILS or tail.isdigit():
            continue
        clean = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
        if clean in seen:
            continue
        seen.add(clean)
        anchor = clean_text(a.get_text(" "), 150)
        if not anchor:
            img = a.find("img")
            anchor = clean_text(img.get("alt", ""), 150) if img else ""
        out.append((clean, anchor))
    return out


def _page_details(sess, url: str):
    """Заголовок и описание со страницы проекта. Тихо падаем в пустое при ошибке."""
    try:
        r = sess.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return "", ""
        s = BeautifulSoup(r.content, "lxml")
        title = ""
        og = s.find("meta", property="og:title")
        if og and og.get("content"):
            title = clean_text(og["content"], 200)
        if not title and s.title:
            title = clean_text(s.title.get_text(), 200)
        if not title:
            h1 = s.find("h1")
            title = clean_text(h1.get_text(" "), 200) if h1 else ""
        desc = ""
        for sel in (("meta", {"property": "og:description"}), ("meta", {"name": "description"})):
            m = s.find(*sel[:1], **{"attrs": sel[1]})
            if m and m.get("content"):
                desc = clean_text(m["content"])
                break
        return title, desc
    except Exception:
        return "", ""


def _tidy(title: str, source_name: str) -> str:
    """Убираем '| Pentagram', '— Studio Dumbar' и прочие хвосты из <title>."""
    for sep in ("|", "—", "–", "·", " - "):
        if sep in title:
            head, _, tail = title.partition(sep)
            if source_name.lower() in tail.lower() and len(head.strip()) > 3:
                title = head
    return title.strip(" |—–·-")


def fetch_html(source: dict, store=None, seed: bool = False):
    # при первом обходе забираем всю страницу целиком, иначе следующий обход
    # примет нижнюю часть архива за новые публикации
    limit = 500 if seed else source.get("limit", 12)
    sess = session()
    r = sess.get(source["url"], timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    links = _collect_links(soup, r.url, source.get("link_pattern", "/"))

    # Заголовок самой страницы-списка = общий заголовок сайта. Если страница
    # проекта отдаёт такой же (Shuka, часть Webflow-сайтов), он бесполезен.
    site_title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        site_title = _tidy(clean_text(og["content"], 200), source["name"]).lower()
    elif soup.title:
        site_title = _tidy(clean_text(soup.title.get_text(), 200), source["name"]).lower()

    # догружаем детали только у тех, что ещё не в базе — экономим запросы
    fresh = []
    for url, anchor in links:
        if store is not None:
            from storage import make_uid
            if store.is_known(make_uid(source["id"], url)):
                continue
        fresh.append((url, anchor))
        if len(fresh) >= limit:
            break

    items = []
    for url, anchor in fresh:
        title, desc = ("", "") if seed else _page_details(sess, url)
        def bad(s: str) -> bool:
            s = s.strip().lower()
            return not s or s in BAD_TITLES or (bool(site_title) and s == site_title)

        title = _tidy(title, source["name"])
        if bad(title):
            title = ""
        anchor = _tidy(anchor, source["name"])
        if bad(anchor):
            anchor = ""
        title = apply_title_regex(source, title or anchor) or _from_slug(url)
        if not title:
            continue
        if not passes_keywords(source, title, desc):
            continue
        items.append(Item(
            source_id=source["id"], source_name=source["name"], group=source["group"],
            title=title, url=url, summary=desc,
        ))

    return _dedupe_titles(items)


def _dedupe_titles(items):
    """Один и тот же заголовок у нескольких проектов = это заголовок сайта,
    а не работы (типично для SPA). Берём название из адреса."""
    counts = Counter(i.title.lower() for i in items)
    for it in items:
        if counts[it.title.lower()] > 1:
            slug = _from_slug(it.url)
            if slug:
                it.title = slug
    return items
