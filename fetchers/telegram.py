"""Telegram-каналы.

mode: web  — парсим публичное превью t.me/s/<channel>. Авторизация не нужна,
             но работает только для каналов с включённым веб-превью.
mode: api  — Telethon от твоего аккаунта: читает любой канал, на который ты
             подписан. Нужны TG_API_ID / TG_API_HASH и разовый вход по коду.
"""
import os, re
from pathlib import Path
from bs4 import BeautifulSoup
from .base import Item, session, clean_text, passes_keywords, tidy_title, TIMEOUT

SESSION_FILE = str(Path(__file__).parent.parent / "data" / "user_session")


def _title_and_summary(text: str):
    """Первая осмысленная строка — заголовок, остальное — описание."""
    text = re.sub(r"\s*\n\s*", "\n", text.strip())
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return "", ""
    title = clean_text(lines[0], 150)
    rest = clean_text(" ".join(lines[1:]), 200)
    if len(title) < 15 and rest:            # первая строка — эмодзи/рубрика
        title = clean_text(f"{title} {rest}", 150)
    return tidy_title(title), rest


def _fetch_web(source: dict, limit: int):
    ch = source["channel"]
    r = session().get(f"https://t.me/s/{ch}", timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    items = []
    for msg in reversed(soup.select(".tgme_widget_message")):
        link = msg.get("data-post")
        if not link:
            continue
        url = f"https://t.me/{link}"
        body = msg.select_one(".tgme_widget_message_text")
        text = body.get_text("\n") if body else ""
        title, summary = _title_and_summary(text)
        if not title:
            continue
        if not passes_keywords(source, title, summary):
            continue
        time_tag = msg.select_one("time")
        items.append(Item(
            source_id=source["id"], source_name=source["name"], group=source["group"],
            title=title, url=url, summary=summary,
            published=time_tag.get("datetime", "") if time_tag else "",
        ))
        if len(items) >= limit:
            break
    return items


def _fetch_api(source: dict, limit: int):
    from telethon.sync import TelegramClient
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("для mode: api нужны TG_API_ID и TG_API_HASH в .env")

    items = []
    with TelegramClient(SESSION_FILE, int(api_id), api_hash) as client:
        entity = client.get_entity(source["channel"])
        for msg in client.iter_messages(entity, limit=limit * 2):
            if not msg.text:
                continue
            title, summary = _title_and_summary(msg.text)
            if not title or not passes_keywords(source, title, summary):
                continue
            items.append(Item(
                source_id=source["id"], source_name=source["name"], group=source["group"],
                title=title, url=f"https://t.me/{source['channel']}/{msg.id}",
                summary=summary,
                published=msg.date.isoformat() if msg.date else "",
            ))
            if len(items) >= limit:
                break
    return list(reversed(items))


def fetch_telegram(source: dict, store=None):
    limit = source.get("limit", 12)
    mode = source.get("mode", "web")
    if mode == "api":
        return _fetch_api(source, limit)
    try:
        return _fetch_web(source, limit)
    except Exception:
        # превью выключено — пробуем через API, если он настроен
        if os.getenv("TG_API_ID") and os.getenv("TG_API_HASH"):
            return _fetch_api(source, limit)
        raise
