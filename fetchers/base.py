"""Общее для всех фетчеров: модель публикации и HTTP-сессия."""
import re, html as htmllib
from dataclasses import dataclass, field
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

TIMEOUT = 25


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


@dataclass
class Item:
    source_id: str
    source_name: str
    group: str
    title: str
    url: str
    summary: str = ""
    published: str = ""


def clean_text(raw: str, limit: int = 220) -> str:
    """Выкидываем теги и схлопываем пробелы — для короткого описания в дайджесте."""
    if not raw:
        return ""
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = htmllib.unescape(txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:limit].rstrip() + ("…" if len(txt) > limit else "")


BOILERPLATE = (
    "your browser does not support the video tag",
    "javascript is required", "enable javascript", "loading…", "loading...",
)


def tidy_title(raw: str, limit: int = 72) -> str:
    """Приводим заголовок к виду «название проекта».

    Многие сайты не отдают внятный заголовок, и в него попадает текст карточки
    целиком: список услуг, подпись под видео, повторяющиеся теги. Режем это.
    """
    if not raw:
        return ""
    txt = re.sub(r"\s+", " ", raw).strip()

    low = txt.lower()
    for b in BOILERPLATE:                       # служебные подписи в начале
        if low.startswith(b):
            txt = txt[len(b):].lstrip(" .,:;–—-")
            low = txt.lower()

    # «Branding Branding Brandbook … Branding Branding Brandbook …» — повтор блока
    words = txt.split()
    for size in range(1, min(9, len(words) // 2 + 1)):
        if words[:size] == words[size:size * 2]:
            half = len(words) // 2
            if words[:half] == words[half:half * 2]:
                txt = " ".join(words[:half])
                break

    # подряд идущие одинаковые слова
    txt = re.sub(r"\b(\w[\w'-]*)(\s+\1\b)+", r"\1", txt, flags=re.I)

    if len(txt) <= limit:
        return txt.strip(" .,:;–—-|")

    # длинный — обрезаем по первому осмысленному разделителю
    for sep in (". ", " — ", " – ", " | ", " ↳ ", " · ", ": "):
        head = txt.split(sep, 1)[0]
        if 8 <= len(head) <= limit:
            return head.strip(" .,:;–—-|")

    cut = txt[:limit].rsplit(" ", 1)[0]
    return cut.strip(" .,:;–—-|") + "…"


def apply_title_regex(source: dict, title: str) -> str:
    """title_regex из sources.yaml: вытащить из заголовка только нужную часть."""
    pattern = source.get("title_regex")
    if not pattern or not title:
        return title
    m = re.search(pattern, title)
    if not m:
        return title
    return (m.group(1) if m.groups() else m.group(0)).strip()


def passes_keywords(source: dict, *texts: str) -> bool:
    """include_keywords / exclude_keywords из sources.yaml."""
    inc = [k.lower() for k in source.get("include_keywords", [])]
    exc = [k.lower() for k in source.get("exclude_keywords", [])]
    blob = " ".join(t.lower() for t in texts if t)
    if exc and any(k in blob for k in exc):
        return False
    if inc and not any(k in blob for k in inc):
        return False
    return True
