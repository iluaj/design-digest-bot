"""RSS/Atom — самый простой и надёжный тип источника."""
import feedparser
from .base import Item, session, clean_text, passes_keywords, TIMEOUT


def fetch_rss(source: dict, store=None):
    limit = source.get("limit", 12)
    r = session().get(source["url"], timeout=TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)

    items = []
    for e in feed.entries[: limit * 3]:
        url = (e.get("link") or "").strip()
        title = clean_text(e.get("title") or "", 200)
        if not url or not title:
            continue
        summary = clean_text(e.get("summary") or e.get("description") or "")
        if not passes_keywords(source, title, summary):
            continue
        items.append(Item(
            source_id=source["id"], source_name=source["name"], group=source["group"],
            title=title, url=url, summary=summary,
            published=e.get("published") or e.get("updated") or "",
        ))
        if len(items) >= limit:
            break
    return items
