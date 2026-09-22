"""Хранилище: помнит, что уже видели и что уже отправили."""
import sqlite3, hashlib, datetime as dt
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DB_PATH = Path(__file__).parent / "data" / "state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid         TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    source_name TEXT NOT NULL,
    grp         TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    summary     TEXT,
    published   TEXT,
    found_at    TEXT NOT NULL,
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_unsent ON items(sent_at) WHERE sent_at IS NULL;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS seeded (source_id TEXT PRIMARY KEY, at TEXT);
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def canonical(url: str) -> str:
    """Убираем utm-мусор и хвостовой слэш, чтобы одна статья не пришла дважды."""
    p = urlsplit(url.strip())
    q = "&".join(
        kv for kv in p.query.split("&")
        if kv and not kv.split("=")[0].lower().startswith(("utm_", "fbclid", "yclid", "gclid"))
    )
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, q, ""))


def make_uid(source_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{canonical(url)}".encode()).hexdigest()[:20]


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- дедупликация ---
    def is_known(self, uid: str) -> bool:
        return self.db.execute("SELECT 1 FROM items WHERE uid=?", (uid,)).fetchone() is not None

    def add(self, item, sent: bool = False) -> bool:
        """Возвращает True, если запись новая. sent=True — записать как уже отправленную (сидирование).

        INSERT OR IGNORE, а не проверка + вставка: обход может идти сразу в двух
        процессах (демон и ручной запуск), и гонка иначе валит вставку.
        """
        uid = make_uid(item.source_id, item.url)
        cur = self.db.execute(
            "INSERT OR IGNORE INTO items(uid,source_id,source_name,grp,title,url,summary,published,found_at,sent_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (uid, item.source_id, item.source_name, item.group, item.title, item.url,
             item.summary, item.published, now_iso(), now_iso() if sent else None),
        )
        self.db.commit()
        return cur.rowcount > 0

    # --- сидирование: первый обход источника не должен присылать весь архив ---
    def is_seeded(self, source_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM seeded WHERE source_id=?", (source_id,)).fetchone() is not None

    def mark_seeded(self, source_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO seeded VALUES(?,?)", (source_id, now_iso()))
        self.db.commit()

    # --- дайджест ---
    def pending(self, limit: int = 100):
        return self.db.execute(
            "SELECT * FROM items WHERE sent_at IS NULL ORDER BY grp, source_name, found_at LIMIT ?",
            (limit,),
        ).fetchall()

    def mark_sent(self, uids) -> None:
        self.db.executemany("UPDATE items SET sent_at=? WHERE uid=?", [(now_iso(), u) for u in uids])
        self.db.commit()

    # --- служебное ---
    def get_meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, str(value)))
        self.db.commit()

    def stats(self):
        total = self.db.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
        unsent = self.db.execute("SELECT COUNT(*) c FROM items WHERE sent_at IS NULL").fetchone()["c"]
        return total, unsent
