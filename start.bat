@echo off
chcp 65001 >nul
title Discord Role Sync Bot

echo ========================================
echo  Discord Role Sync Bot
echo ========================================
echo.

REM Проверка виртуального окружения
if exist "venv\Scripts\activate.bat" (
    echo Активация виртуального окружения...
    call venv\Scripts\activate.bat
) else (
    echo ВНИМАНИЕ: Виртуальное окружение не найдено
    echo Рекомендуется создать: python -m venv venv
    echo.
)

REM Проверка зависимостей
echo Проверка зависимостей...
python -c "import discord" 2>nul
if errorlevel 1 (
    echo ОШИБКА: discord.py не установлен
    echo Установите зависимости: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Проверка .env файла
if not exist ".env" (
    echo ОШИБКА: .env файл не найден
    echo Создайте .env файл на основе .env.example
    pause
    exit /b 1
)

echo.
echo Запуск бота...
echo Для остановки нажмите Ctrl+C
echo.
echo ========================================
echo.

python run.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo ОШИБКА: Бот завершился с ошибкой
    echo Проверьте логи в logs/bot.log
    echo ========================================
    pause
)
