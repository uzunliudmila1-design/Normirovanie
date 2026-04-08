#!/bin/bash
cd "$(dirname "$0")"
export LANG=ru_RU.UTF-8

# Если порт уже занят — сообщаем
if lsof -ti:5050 >/dev/null 2>&1; then
  echo "Сервер уже запущен на порту 5050"
  echo "http://localhost:5050"
  exit 0
fi

echo "Запуск сервера на http://localhost:5050 ..."
python3 app.py &
echo $! > .server.pid
echo "PID: $(cat .server.pid)"
