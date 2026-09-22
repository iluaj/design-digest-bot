#!/bin/bash
# Ставит бота в автозапуск на macOS. Запускать из папки проекта: bash deploy/install-macos.sh
set -e
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.designdigest.bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PROJECT/.env" ]; then
  echo "Нет файла .env — скопируй .env.example в .env и впиши BOT_TOKEN и CHAT_ID."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT/logs"
sed "s|__PROJECT__|$PROJECT|g" "$PROJECT/deploy/com.designdigest.bot.plist" > "$PLIST"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/$LABEL"

echo "Готово. Бот в автозапуске."
echo "  статус:    launchctl print gui/$UID/$LABEL | head -20"
echo "  логи:      tail -f $PROJECT/logs/bot.log"
echo "  выключить: launchctl bootout gui/$UID/$LABEL"
