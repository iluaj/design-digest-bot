"""Тонкий клиент Telegram Bot API. Без лишних зависимостей — только requests."""
import os, requests

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000          # лимит Telegram 4096, оставляем запас


class Bot:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("BOT_TOKEN")
        if not self.token:
            raise RuntimeError("не задан BOT_TOKEN — скопируй .env.example в .env и впиши токен")

    def _call(self, method: str, **params):
        r = requests.post(API.format(token=self.token, method=method), json=params, timeout=60)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method}: {data.get('description')}")
        return data["result"]

    def send(self, chat_id, text: str, preview: bool = False):
        return self._call("sendMessage", chat_id=chat_id, text=text,
                          parse_mode="HTML",
                          link_preview_options={"is_disabled": not preview})

    def send_long(self, chat_id, chunks: list[str], preview: bool = False):
        return [self.send(chat_id, c, preview) for c in chunks]

    def get_updates(self, offset=None, timeout=25):
        return self._call("getUpdates", offset=offset, timeout=timeout,
                          allowed_updates=["message"])

    def me(self):
        return self._call("getMe")
