#!/usr/bin/env python3
"""Дайджест дизайн-публикаций в Telegram.

  python run.py collect          обойти источники и сложить новое в базу
  python run.py digest           отправить накопленное одним сообщением
  python run.py now              collect + digest сразу (для проверки)
  python run.py daemon           постоянный режим: расписание + команды бота
  python run.py test <id>        проверить один источник, ничего не сохраняя
  python run.py check            проверить все источники на доступность
  python run.py whoami           узнать свой CHAT_ID
  python run.py auth             разовый вход в Telegram для mode: api
  python run.py discover <текст> найти публичные каналы по названию
  python run.py stats            что в базе
  python run.py export-state     выгрузить состояние в текстовые файлы
  python run.py import-state     собрать базу из текстовых файлов
"""
import sys, os, time, logging, datetime as dt, threading
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

import storage, digest as digest_mod, fetchers
from bot import Bot

LOG_FILE = ROOT / "logs" / "bot.log"
LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("digest")


def chat_id() -> str:
    cid = os.getenv("CHAT_ID")
    if not cid:
        raise RuntimeError("не задан CHAT_ID — узнай его командой: python run.py whoami")
    return cid


def load_config() -> dict:
    with open(ROOT / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def active_sources(cfg) -> list:
    return [s for s in cfg["sources"] if s.get("enabled", True)]


def tz_of(cfg) -> ZoneInfo:
    return ZoneInfo(cfg["settings"].get("timezone", "Europe/Moscow"))


# ---------------------------------------------------------------- collect
def collect(cfg=None, store=None) -> int:
    cfg = cfg or load_config()
    store = store or storage.Store()
    settings = cfg["settings"]
    total_new, failed = 0, []

    for i, src in enumerate(active_sources(cfg)):
        if i:
            time.sleep(settings.get("pause_between_sources", 2))
        first_time = not store.is_seeded(src["id"])
        src.setdefault("limit", 500 if first_time else settings.get("max_items_per_source", 12))
        try:
            items = fetchers.fetch(src, store, seed=first_time)
        except Exception as e:
            failed.append((src["id"], f"{type(e).__name__}: {str(e)[:90]}"))
            log.warning("  ✗ %-18s %s: %s", src["id"], type(e).__name__, str(e)[:90])
            continue

        # первый обход источника: запоминаем архив как «уже видели», но не шлём
        added = sum(store.add(it, sent=first_time) for it in items)
        if first_time:
            store.mark_seeded(src["id"])
            log.info("  ⚑ %-18s первый обход, в архив: %d", src["id"], added)
        else:
            total_new += added
            log.info("  %s %-18s новых: %d", "✓" if added else "·", src["id"], added)

    store.set_meta("last_collect", storage.now_iso())
    log.info("Собрано новых: %d | источников с ошибкой: %d", total_new, len(failed))
    return total_new


# ---------------------------------------------------------------- digest
def _cap_per_source(rows, cap: int):
    """Не больше cap публикаций от одного источника — иначе болтливая лента
    вытеснит из дайджеста всех остальных. Остаток дождётся следующего раза."""
    if cap <= 0:
        return list(rows)
    kept, count = [], {}
    for r in rows:
        sid = r["source_id"]
        if count.get(sid, 0) >= cap:
            continue
        count[sid] = count.get(sid, 0) + 1
        kept.append(r)
    return kept

def send_digest(cfg=None, store=None, force: bool = False) -> int:
    cfg = cfg or load_config()
    store = store or storage.Store()
    settings = cfg["settings"]
    tz = tz_of(cfg)

    rows = store.pending(limit=settings.get("digest_max_items", 120) * 3)
    rows = _cap_per_source(rows, settings.get("max_per_source_in_digest", 4))
    rows = rows[: settings.get("digest_max_items", 120)]
    if not rows:
        if settings.get("send_empty_digest") or force:
            Bot().send(chat_id(), "📭 Сегодня новых публикаций не было.")
        log.info("Дайджест: нечего отправлять")
        return 0

    messages = digest_mod.build(rows, cfg["groups"], dt.datetime.now(tz).date())
    bot = Bot()
    bot.send_long(chat_id(), messages)
    store.mark_sent([r["uid"] for r in rows])
    store.set_meta("last_digest", storage.now_iso())
    log.info("Дайджест отправлен: %d публикаций в %d сообщ.", len(rows), len(messages))
    return len(rows)


# ---------------------------------------------------------------- daemon
class Daemon:
    def __init__(self):
        self.cfg = load_config()
        self.store = storage.Store()
        self.bot = Bot()
        self.tz = tz_of(self.cfg)
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def _last_digest_day(self):
        """Когда дайджест уходил в последний раз — из базы, переживает перезапуск."""
        raw = self.store.get_meta("last_digest_day")
        if raw:
            try:
                return dt.date.fromisoformat(raw)
            except ValueError:
                pass
        raw = self.store.get_meta("last_digest")
        if raw:
            try:
                return dt.datetime.fromisoformat(raw).astimezone(self.tz).date()
            except ValueError:
                pass
        return None

    # --- команды в чате ---
    def handle(self, chat_id, text: str):
        cmd, _, arg = text.strip().partition(" ")
        cmd = cmd.lower().lstrip("/").split("@")[0]

        if cmd == "start":
            self.bot.send(chat_id,
                "Привет! Я собираю новые публикации студий и изданий.\n\n"
                f"Твой CHAT_ID: <code>{chat_id}</code>\n\n"
                "<b>Команды</b>\n"
                "/now — собрать и прислать прямо сейчас\n"
                "/pending — что накопилось к вечеру\n"
                "/sources — список источников\n"
                "/stats — статистика\n"
                "/when — когда следующий дайджест")
        elif cmd == "now":
            self.bot.send(chat_id, "Иду по источникам, это займёт минуту-другую…")
            with self.lock:
                n = collect(self.cfg, self.store)
                sent = send_digest(self.cfg, self.store, force=True)
            if not sent:
                self.bot.send(chat_id, f"Новых публикаций нет (проверено источников: {len(active_sources(self.cfg))}).")
        elif cmd == "pending":
            rows = self.store.pending(limit=200)
            self.bot.send(chat_id, f"В очереди на вечер: <b>{len(rows)}</b>")
        elif cmd == "sources":
            lines = [f"Активных источников: <b>{len(active_sources(self.cfg))}</b>\n"]
            for grp, label in self.cfg["groups"].items():
                names = [s["name"] for s in active_sources(self.cfg) if s["group"] == grp]
                if names:
                    lines.append(f"<b>{label}</b>\n" + "\n".join(f"• {n}" for n in names))
            self.bot.send(chat_id, "\n\n".join(lines))
        elif cmd == "stats":
            total, unsent = self.store.stats()
            self.bot.send(chat_id,
                f"Всего в базе: <b>{total}</b>\nЖдут отправки: <b>{unsent}</b>\n"
                f"Последний обход: {self.store.get_meta('last_collect', '—')}\n"
                f"Последний дайджест: {self.store.get_meta('last_digest', '—')}")
        elif cmd == "when":
            self.bot.send(chat_id, f"Дайджест в {self.cfg['settings']['digest_time']} "
                                   f"({self.cfg['settings']['timezone']}), "
                                   f"обход каждые {self.cfg['settings']['collect_every_hours']} ч.")
        else:
            self.bot.send(chat_id, "Не знаю такой команды. /start — список.")

    def poll_commands(self):
        offset = None
        while not self.stop.is_set():
            try:
                for upd in self.bot.get_updates(offset=offset, timeout=25):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    text = msg.get("text")
                    if text:
                        try:
                            self.handle(msg["chat"]["id"], text)
                        except Exception as e:
                            log.exception("команда %r упала: %s", text, e)
            except Exception as e:
                log.warning("polling: %s", e)
                self.stop.wait(15)

    # --- расписание ---
    def loop(self):
        threading.Thread(target=self.poll_commands, daemon=True).start()
        settings = self.cfg["settings"]
        every = dt.timedelta(hours=settings.get("collect_every_hours", 3))
        hh, mm = (int(x) for x in settings["digest_time"].split(":"))
        next_collect = dt.datetime.now(self.tz)
        # дату последней отправки держим в базе, а не только в памяти: иначе
        # перезапуск демона вечером шлёт второй дайджест за тот же день
        last_digest_day = self._last_digest_day()

        log.info("Демон запущен. Дайджест в %s %s, обход каждые %s ч.",
                 settings["digest_time"], settings["timezone"], settings["collect_every_hours"])
        while not self.stop.is_set():
            now = dt.datetime.now(self.tz)
            if now >= next_collect:
                with self.lock:
                    try:
                        collect(self.cfg, self.store)
                    except Exception:
                        log.exception("обход источников упал")
                next_collect = now + every
            if (now.hour, now.minute) >= (hh, mm) and last_digest_day != now.date():
                with self.lock:
                    try:
                        collect(self.cfg, self.store)
                        send_digest(self.cfg, self.store)
                        last_digest_day = now.date()
                        self.store.set_meta("last_digest_day", last_digest_day.isoformat())
                    except Exception:
                        log.exception("отправка дайджеста упала")
            self.stop.wait(30)


# ---------------------------------------------------------------- утилиты
def cmd_test(source_id: str):
    cfg = load_config()
    src = next((s for s in cfg["sources"] if s["id"] == source_id), None)
    if not src:
        sys.exit(f"нет источника с id={source_id!r}")
    src.setdefault("limit", 5)
    items = fetchers.fetch(src, None)
    print(f"{src['name']}: получено {len(items)}\n")
    for it in items[:5]:
        print(f"  • {it.title}\n    {it.url}\n    {it.summary[:100]}\n")


def cmd_check():
    cfg = load_config()
    import concurrent.futures as cf

    def one(src):
        # у RSS фильтр по ключевым словам может отсеять первые записи,
        # поэтому лимит берём боевой; у html/telegram он дорогой — урезаем
        src = dict(src, limit=cfg["settings"].get("max_items_per_source", 12)
                   if src["type"] == "rss" else 3)
        try:
            n = len(fetchers.fetch(src, None))
            return f"{'OK ' if n else 'ПУСТО'} | {src['id']:20} | {n} шт."
        except Exception as e:
            return f"ОШИБКА | {src['id']:20} | {type(e).__name__}: {str(e)[:60]}"

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for line in sorted(ex.map(one, active_sources(cfg))):
            print(line)


def cmd_whoami():
    bot = Bot()
    print(f"Бот: @{bot.me()['username']}\nНапиши ему что-нибудь в Telegram, жду…")
    offset = None
    for _ in range(24):
        for upd in bot.get_updates(offset=offset, timeout=10):
            offset = upd["update_id"] + 1
            chat = (upd.get("message") or {}).get("chat")
            if chat:
                print(f"\nТвой CHAT_ID = {chat['id']}  ({chat.get('first_name','')})")
                print("Впиши его в .env  ->  CHAT_ID=" + str(chat["id"]))
                return
    print("Сообщений не было.")


def cmd_auth():
    from telethon.sync import TelegramClient
    from fetchers.telegram import SESSION_FILE
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not api_id or not api_hash:
        sys.exit("впиши TG_API_ID и TG_API_HASH в .env (берутся на my.telegram.org)")
    with TelegramClient(SESSION_FILE, int(api_id), api_hash) as c:
        me = c.get_me()
        print(f"Готово, вошли как {me.first_name} (@{me.username}). Сессия: {SESSION_FILE}.session")


def cmd_discover(query: str):
    """Ищет публичные каналы по названию — чтобы не угадывать юзернеймы руками."""
    from telethon.sync import TelegramClient
    from telethon.tl.functions.contacts import SearchRequest
    from fetchers.telegram import SESSION_FILE
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not api_id or not api_hash:
        sys.exit("для поиска нужны TG_API_ID и TG_API_HASH в .env, затем: python run.py auth")
    with TelegramClient(SESSION_FILE, int(api_id), api_hash) as c:
        res = c(SearchRequest(q=query, limit=20))
        rows = []
        for ch in res.chats:
            if getattr(ch, "username", None) and getattr(ch, "broadcast", False):
                full = c(__import__("telethon.tl.functions.channels", fromlist=["GetFullChannelRequest"])
                         .GetFullChannelRequest(ch))
                rows.append((full.full_chat.participants_count or 0, ch.username, ch.title))
        for n, u, t in sorted(rows, reverse=True):
            print(f"{n:>9,} подп. | @{u:24} | {t}")
        if not rows:
            print("Каналов не найдено.")


SEEN_FILE   = ROOT / "data" / "seen.txt"
SEEDED_FILE = ROOT / "data" / "seeded.txt"


def cmd_export_state():
    """Выгружаем состояние в текстовые файлы.

    В облаке базу между запусками держать негде, а класть в репозиторий
    SQLite нельзя — это мегабайты двоичных данных на каждый коммит. Отпечатки
    отправленных записей и список освоенных источников занимают на два порядка
    меньше, и git дописывает их построчно.
    """
    store = storage.Store()
    seen = [r[0] for r in store.db.execute(
        "SELECT uid FROM items WHERE sent_at IS NOT NULL ORDER BY uid")]
    seeded = [r[0] for r in store.db.execute("SELECT source_id FROM seeded ORDER BY source_id")]
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text("\n".join(seen) + "\n", encoding="utf-8")
    SEEDED_FILE.write_text("\n".join(seeded) + "\n", encoding="utf-8")
    log.info("Выгружено: %d отпечатков, %d освоенных источников (%.0f КБ)",
             len(seen), len(seeded), SEEN_FILE.stat().st_size / 1024)


def cmd_import_state():
    """Собираем базу обратно из текстовых файлов — первый шаг облачного запуска."""
    store = storage.Store()
    if not SEEN_FILE.exists():
        log.info("Файла состояния нет — источники будут освоены с нуля")
        return
    seen = [l.strip() for l in SEEN_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    seeded = []
    if SEEDED_FILE.exists():
        seeded = [l.strip() for l in SEEDED_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    now = storage.now_iso()
    store.db.executemany(
        "INSERT OR IGNORE INTO items(uid,source_id,source_name,grp,title,url,summary,"
        "published,found_at,sent_at) VALUES(?,'','','','','','','',?,?)",
        [(u, now, now) for u in seen])
    store.db.executemany("INSERT OR REPLACE INTO seeded VALUES(?,?)", [(s, now) for s in seeded])
    store.db.commit()
    log.info("Загружено: %d отпечатков, %d освоенных источников", len(seen), len(seeded))


def cmd_stats():
    store = storage.Store()
    total, unsent = store.stats()
    print(f"Всего записей: {total}\nЖдут отправки: {unsent}")
    print(f"Последний обход:    {store.get_meta('last_collect', '—')}")
    print(f"Последний дайджест: {store.get_meta('last_digest', '—')}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "collect":
        collect()
    elif cmd == "digest":
        send_digest()
    elif cmd == "now":
        collect(); send_digest(force=True)
    elif cmd == "daemon":
        Daemon().loop()
    elif cmd == "test":
        cmd_test(arg or sys.exit("укажи id источника"))
    elif cmd == "check":
        cmd_check()
    elif cmd == "whoami":
        cmd_whoami()
    elif cmd == "auth":
        cmd_auth()
    elif cmd == "discover":
        cmd_discover(arg or sys.exit("укажи, что искать"))
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "export-state":
        cmd_export_state()
    elif cmd == "import-state":
        cmd_import_state()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
