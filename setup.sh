#!/bin/bash
# Ставит окружение и зависимости. Запускать из папки проекта: bash setup.sh
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    V=$("$c" -c 'import sys; print(sys.version_info >= (3,11))' 2>/dev/null || echo False)
    [ "$V" = "True" ] && { PY="$c"; break; }
  fi
done
[ -z "$PY" ] && { echo "Нужен Python 3.11 или новее. Установите и повторите."; exit 1; }
echo "Python: $($PY --version)"

"$PY" -m venv .venv
./.venv/bin/pip -q install --upgrade pip
./.venv/bin/pip -q install -r requirements.txt
mkdir -p data logs

echo
echo "Готово. Дальше:"
echo "  1. cp .env.example .env   и впишите BOT_TOKEN от @BotFather"
echo "  2. .venv/bin/python run.py whoami   — узнать свой CHAT_ID"
echo "  3. .venv/bin/python run.py now      — проверить"
echo "  4. bash deploy/install-macos.sh     — автозапуск (macOS)"
