#!/bin/bash

# Discord Role Sync Bot - Startup Script

echo "========================================"
echo "  Discord Role Sync Bot"
echo "========================================"
echo ""

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка виртуального окружения
if [ -f "venv/bin/activate" ]; then
    echo "Активация виртуального окружения..."
    source venv/bin/activate
else
    echo -e "${YELLOW}ВНИМАНИЕ: Виртуальное окружение не найдено${NC}"
    echo "Рекомендуется создать: python3 -m venv venv"
    echo ""
fi

# Проверка Python версии
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python версия: $python_version"

# Проверка зависимостей
echo "Проверка зависимостей..."
if ! python3 -c "import discord" 2>/dev/null; then
    echo -e "${RED}ОШИБКА: discord.py не установлен${NC}"
    echo "Установите зависимости: pip install -r requirements.txt"
    exit 1
fi

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo -e "${RED}ОШИБКА: .env файл не найден${NC}"
    echo "Создайте .env файл на основе .env.example"
    exit 1
fi

echo ""
echo "Запуск бота..."
echo "Для остановки нажмите Ctrl+C"
echo ""
echo "========================================"
echo ""

# Запуск бота
python3 run.py

# Проверка кода выхода
if [ $? -ne 0 ]; then
    echo ""
    echo "========================================"
    echo -e "${RED}ОШИБКА: Бот завершился с ошибкой${NC}"
    echo "Проверьте логи в logs/bot.log"
    echo "========================================"
    exit 1
fi
