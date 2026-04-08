#!/bin/bash
cd "$(dirname "$0")"

if lsof -ti:5050 >/dev/null 2>&1; then
  lsof -ti:5050 | xargs kill -9
  rm -f .server.pid
  echo "Сервер остановлен"
else
  echo "Сервер не запущен"
fi
