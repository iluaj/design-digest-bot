#!/usr/bin/env python3
"""Массовая проверка кандидатов в источники.

    python verify.py staging/feeds_candidates.tsv

Формат входа — TSV: название, адрес, тег, заметка. Строки с # игнорируются.
Тип определяется по адресу: youtube channel_id, t.me-канал, всё прочее — RSS.
Результат: staging/<имя>_verified.tsv только с живыми источниками.
"""
import sys, re, concurrent.futures as cf
from pathlib import Path
import feedparser
from bs4 import BeautifulSoup
from fetchers.base import session, clean_text, TIMEOUT

YT = re.compile(r"^UC[\w-]{22}$")


def probe_rss(url):
    r = session().get(url, timeout=TIMEOUT, allow_redirects=True)
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    f = feedparser.parse(r.content)
    if not f.entries:
        return None, "лента без записей"
    e = f.entries[0]
    when = e.get("published", e.get("updated", ""))[:16]
    return (len(f.entries), clean_text(e.get("title", ""), 60), when), None


def probe_telegram(name):
    r = session().get(f"https://t.me/s/{name}", timeout=TIMEOUT)
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    s = BeautifulSoup(r.content, "lxml")
    msgs = s.select(".tgme_widget_message")
    title = s.select_one(".tgme_channel_info_header_title")
    subs = s.select_one(".tgme_channel_info_counter .counter_value")
    if not msgs:
        return None, "нет постов или превью выключено"
    return (len(msgs), (title.get_text(strip=True) if title else "")[:40],
            subs.get_text(strip=True) if subs else "?"), None


def probe(row):
    name, url, tag, note = row
    try:
        if YT.match(url):
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={url}"
            got, err = probe_rss(url)
        elif url.startswith("@") or "t.me/" in url:
            ch = url.split("t.me/")[-1].lstrip("@s/").strip("/")
            got, err = probe_telegram(ch)
            url = f"https://t.me/{ch}"
        else:
            got, err = probe_rss(url)
    except Exception as e:
        return False, name, url, tag, note, f"{type(e).__name__}: {str(e)[:50]}"
    if err:
        return False, name, url, tag, note, err
    return True, name, url, tag, note, " | ".join(str(x) for x in got)


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "staging/feeds_candidates.tsv")
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = (line.split("\t") + ["", "", ""])[:4]
        rows.append(parts)

    print(f"Проверяю {len(rows)} кандидатов…\n")
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(probe, rows))

    ok = [r for r in res if r[0]]
    bad = [r for r in res if not r[0]]
    for r in sorted(bad, key=lambda x: x[1]):
        print(f"  ✗ {r[1][:32]:32} {r[5]}")
    print(f"\nЖивых: {len(ok)} из {len(rows)} | отпало: {len(bad)}")

    out = src.with_name(src.stem.replace("_candidates", "") + "_verified.tsv")
    out.write_text("\n".join("\t".join(r[1:5]) for r in ok) + "\n", encoding="utf-8")
    print(f"Живые записаны: {out}")


if __name__ == "__main__":
    main()
