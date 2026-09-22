#!/bin/bash
LABEL="com.designdigest.bot"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null && echo "Автозапуск снят." || echo "Не был установлен."
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
