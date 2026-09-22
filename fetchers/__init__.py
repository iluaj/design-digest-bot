from .base import Item, HEADERS, session
from .rss import fetch_rss
from .html_list import fetch_html
from .telegram import fetch_telegram

FETCHERS = {"rss": fetch_rss, "html": fetch_html, "telegram": fetch_telegram}


def fetch(source: dict, store=None, seed: bool = False):
    """seed=True — первый обход источника: забираем всё, что видно, и не тратим
    время на подгрузку описаний (эти записи всё равно уходят сразу в архив)."""
    fn = FETCHERS.get(source.get("type"))
    if fn is None:
        raise ValueError(f"неизвестный тип источника: {source.get('type')!r}")
    if fn is fetch_html:
        return fn(source, store, seed=seed)
    return fn(source, store)
