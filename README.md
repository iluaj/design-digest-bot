# Дайджест дизайна в Telegram

Бот обходит блоги, сайты студий, Telegram- и YouTube-каналы, копит новые
публикации за день и вечером присылает их одним сообщением — сгруппированными
по разделам.

Из коробки — **162 проверенных источника** с упором на дизайн интерфейсов:
продуктовые блоги, UX-издания, галереи интерфейсов, студии, каналы.

```
📅 Дайджест за 22 сентября — 34 публикации

🖥 Интерфейсы и продуктовый дизайн

Nielsen Norman Group
• Designing AI Products and Features: Study Guide

Дайджест продуктового дизайна
• Как мы переизобрели навигацию в мобильном приложении

⚙️ Вёрстка, доступность, дизайн-системы

Josh W Comeau
• Getting Started with Anchor Positioning

🗂 Галереи интерфейсов

siteInspire
• Visual (Archives) Society
```

Повторы не приходят: каждая публикация запоминается по адресу.
Первый обход источника уходит в архив молча — вечером не прилетит весь его бэклог.

---

## Что внутри

**162 источника в семи разделах.** Порядок разделов настраивается, интерфейсы
стоят первыми.

| Раздел | Сколько | Примеры |
|---|---|---|
| 🖥 Интерфейсы и продуктовый дизайн | 55 | Nielsen Norman Group, UX Collective, Figma, Linear, дизайн-команды Airbnb, Spotify, Ozon, Авито |
| ⚙️ Вёрстка, доступность, дизайн-системы | 27 | Smashing, Josh Comeau, Brad Frost, A11Y Project, Adrian Roselli |
| 🗂 Галереи интерфейсов | 10 | siteInspire, Httpster, Awwwards, Land-book, Page Flows |
| 🎨 Студии и агентства | 13 | Pentagram, COLLINS, Wolff Olins, Studio Dumbar, ONY, Depot |
| 📰 Издания и блоги | 13 | Brand New, It's Nice That, Dezeen, Fonts In Use |
| ✈️ Telegram | 26 | каналы студий, дизайнеров и профильных медиа |
| ▶️ YouTube | 18 | Figma, NN/g, Malewicz, Бюро Горбунова |

Каждая ссылка проверена живым запросом. Мёртвые, закрывшиеся и захваченные
сквоттерами источники в список не попали.

**Четыре типа источников:**

- `rss` — RSS/Atom-лента. Сюда же YouTube: у каждого канала есть фид.
- `html` — сайт без ленты. Следим за страницей со списком работ и ловим новые ссылки.
- `telegram` — канал. Режим `web` читает публичное превью без авторизации,
  режим `api` — через Telethon, любой канал, на который вы подписаны.

---

## Запуск

Нужен Python 3.11 или новее.

### 1. Поставить

```bash
git clone https://github.com/USER/design-digest-bot.git
cd design-digest-bot
bash setup.sh
```

### 2. Создать бота

Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → придумайте имя.
Он выдаст токен вида `123456:AAF...`.

```bash
cp .env.example .env
# впишите BOT_TOKEN, CHAT_ID пока оставьте пустым
```

### 3. Узнать свой CHAT_ID

```bash
.venv/bin/python run.py whoami
```

Напишите боту в Telegram любое слово — команда покажет ваш ID.
Впишите его в `.env`.

### 4. Проверить

```bash
.venv/bin/python run.py now
```

Соберёт и пришлёт дайджест прямо сейчас.

### 5. Поставить на автозапуск

**macOS:**
```bash
bash deploy/install-macos.sh
```

**Linux (systemd):**
```bash
sudo cp deploy/design-digest.service /etc/systemd/system/
sudo systemctl enable --now design-digest
```

Бот стартует при загрузке, поднимается после сбоя, обходит источники каждые
3 часа и в 18:00 присылает дайджест.

---

## Команды

**В чате с ботом**

| Команда | Что делает |
|---|---|
| `/now` | собрать и прислать прямо сейчас |
| `/pending` | сколько публикаций накопилось к вечеру |
| `/sources` | список подключённых источников |
| `/stats` | статистика базы |
| `/when` | когда следующий дайджест |

**В терминале**

```bash
.venv/bin/python run.py check          # проверить все источники на доступность
.venv/bin/python run.py test pentagram # посмотреть, что отдаёт один источник
.venv/bin/python run.py collect        # только собрать, не отправлять
.venv/bin/python run.py digest         # только отправить накопленное
.venv/bin/python run.py stats          # что в базе
tail -f logs/bot.log                   # логи
```

---

## Настройка

Всё правится в `sources.yaml`, код трогать не нужно.

### Расписание

```yaml
settings:
  timezone: Europe/Moscow
  digest_time: "18:00"          # во сколько присылать
  collect_every_hours: 3        # как часто обходить источники
  max_items_per_source: 8       # новинок с источника за обход
  digest_max_items: 120         # потолок публикаций в дайджесте
  max_per_source_in_digest: 4   # чтобы одна лента не забила дайджест
```

### Добавить источник

**RSS-лента:**
```yaml
  - id: myfeed
    name: 'Название'
    group: ui_product
    type: rss
    url: https://example.com/feed/
```

**YouTube-канал** — та же `rss`, адрес фида:
```yaml
    url: https://www.youtube.com/feeds/videos.xml?channel_id=UCxxxxxxxxxxxxxxxxxxxxxx
```

**Сайт без RSS:**
```yaml
  - id: mystudio
    name: 'Студия'
    group: studios
    type: html
    url: https://example.com/work     # страница со списком работ
    link_pattern: '/work/'            # что общего у ссылок на проекты
```

**Telegram-канал:**
```yaml
  - id: tg_channel
    name: 'Канал'
    group: telegram
    type: telegram
    channel: username                 # без @
    mode: web
```

Проверить после добавления: `.venv/bin/python run.py test myfeed`

### Необязательные поля

```yaml
    enabled: false                          # временно отключить
    limit: 5                                # максимум новинок за обход
    include_keywords: ['дизайн', 'брендинг'] # брать только с этими словами
    exclude_keywords: ['вакансия']           # выкидывать с этими
    title_regex: '^Work — (.+?) —'           # вырезать из заголовка нужное
```

### Проверить пачку источников разом

```bash
.venv/bin/python verify.py my_candidates.tsv
```

Формат TSV: `название · адрес · тег · заметка`. Адресом может быть ссылка на
ленту, `@канал` или YouTube `channel_id`. Живые попадут в `*_verified.tsv`.

---

## Закрытые Telegram-каналы

Режим `web` читает публичное превью и не требует авторизации. Если у канала
превью выключено, нужен вход под своим аккаунтом:

1. Получите `api_id` и `api_hash` на [my.telegram.org](https://my.telegram.org)
   → API development tools, впишите в `.env`.
2. `.venv/bin/python run.py auth` — разовый вход по коду из Telegram.
3. У источника поставьте `mode: api`.

После авторизации работает поиск каналов по названию:

```bash
.venv/bin/python run.py discover "брендинг"
```

---

## Запуск без своего компьютера

В `.github/workflows/digest.yml` лежит готовый сценарий для GitHub Actions:
приватный форк, секреты `BOT_TOKEN` и `CHAT_ID`, запуск по расписанию.
Работает бесплатно.

Учтите: расписание GitHub Actions может плавать на 5–15 минут, а состояние
(`data/state.db`) коммитится обратно в репозиторий.

---

## Известные ограничения

**Behance и Dribbble** закрыты Cloudflare — на обычный запрос отвечают 403 и 202.
Лежат в `sources.yaml` с `enabled: false`. Чтобы заработали, нужен
headless-браузер.

**Сайты на SPA** (Curated.design, Dark Mode Design, Screensdesign, Логомашина)
отдают пустой HTML — статический парсер их не видит.

**Instagram** не поддерживается сознательно: требует авторизации и грозит
блокировкой аккаунта. У большинства студий есть Telegram-канал с тем же
содержимым.

---

## Как это устроено

```
run.py            запуск: демон, разовый сбор, отправка, утилиты
sources.yaml      список источников и расписание
fetchers/         rss.py · html_list.py · telegram.py
storage.py        SQLite: что видели и что отправили
digest.py         сборка сообщения
bot.py            клиент Telegram Bot API
verify.py         массовая проверка кандидатов в источники
deploy/           автозапуск для macOS и Linux
```

Логика обхода: собрали ссылки → отсеяли известные по адресу → новое положили в
базу → вечером отправили и пометили отправленным. Первый обход источника
целиком уходит в архив, чтобы не завалить первым же дайджестом.

---

## Лицензия

MIT — делайте что хотите.
