"""Сборка дайджеста: сгруппированный список одним сообщением."""
import html, datetime as dt
from collections import OrderedDict

MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MAX_LEN = 4000


def _plural(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "публикаций"
    return {1: "публикация", 2: "публикации", 3: "публикации", 4: "публикации"}.get(n % 10, "публикаций")


def _date_ru(d: dt.date) -> str:
    return f"{d.day} {MONTHS_RU[d.month - 1]}"


def build(rows, groups: dict, today: dt.date) -> list[str]:
    """rows — строки из БД. Возвращает список сообщений (обычно одно)."""
    if not rows:
        return []

    by_group = OrderedDict((g, OrderedDict()) for g in groups)
    for r in rows:
        by_group.setdefault(r["grp"], OrderedDict()).setdefault(r["source_name"], []).append(r)

    header = f"📅 <b>Дайджест за {_date_ru(today)}</b> — {len(rows)} {_plural(len(rows))}\n"

    blocks = []
    for grp, sources in by_group.items():
        if not sources:
            continue
        lines = [f"\n<b>{html.escape(groups.get(grp, grp))}</b>"]
        for source_name, items in sources.items():
            lines.append(f"\n<u>{html.escape(source_name)}</u>")
            for it in items:
                title = html.escape(it["title"])
                lines.append(f'• <a href="{html.escape(it["url"], quote=True)}">{title}</a>')
        blocks.append("\n".join(lines))

    # склеиваем в сообщения, не разрывая блок группы посередине
    messages, current = [], header
    for b in blocks:
        if len(current) + len(b) + 1 > MAX_LEN:
            if current.strip():
                messages.append(current.rstrip())
            current = b.lstrip("\n")
        else:
            current += "\n" + b
    if current.strip():
        messages.append(current.rstrip())
    return messages
