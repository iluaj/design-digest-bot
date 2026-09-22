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
