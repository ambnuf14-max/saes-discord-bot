"""
Точка входа для Discord Role Sync Bot
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Добавляем текущую директорию в Python path
sys.path.insert(0, str(Path(__file__).parent))

from bot.utils.logger import setup_logging
from bot.main import RoleSyncBot


async def async_main():
    """Асинхронная главная функция запуска бота"""

    # Загружаем переменные окружения из .env файла
    load_dotenv()

    # Получаем токен бота
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    if not bot_token:
        print("ОШИБКА: DISCORD_BOT_TOKEN не найден в переменных окружения!")
        print("Создайте файл .env на основе .env.example и укажите токен бота.")
        sys.exit(1)

    # Настраиваем логирование
    try:
        logger = setup_logging()
        logger.info("=" * 50)
        logger.info("Discord Role Sync Bot запускается...")
        logger.info("=" * 50)
    except Exception as e:
        print(f"ОШИБКА настройки логирования: {e}")
        sys.exit(1)

    # Создаем и запускаем бота
    bot = None
    try:
        bot = RoleSyncBot()
        async with bot:
            await bot.start(bot_token)

    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")

    except Exception as e:
        logger.critical(f"Критическая ошибка бота: {e}", exc_info=True)
        raise

    finally:
        if bot:
            logger.info("Завершение работы бота...")


def main():
    """Главная функция запуска бота"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        # Игнорируем, уже обработано в async_main
        pass
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
