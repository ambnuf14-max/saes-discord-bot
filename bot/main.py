"""
Главный модуль бота - инициализация и настройка
"""

import discord
from discord.ext import commands
import asyncio
from pathlib import Path

from bot.config import Config
from bot.database.models import initialize_database
from bot.database.operations import DatabaseOperations
from bot.utils.logger import get_logger
from bot.utils.errors import ConfigurationError

logger = get_logger("main")


class RoleSyncBot(commands.Bot):
    """Основной класс Discord бота для синхронизации ролей"""

    def __init__(self):
        """Инициализация бота"""

        # Настраиваем intents (необходимые разрешения для бота)
        intents = discord.Intents.default()
        intents.guilds = True  # Доступ к серверам
        intents.members = True  # Доступ к информации о участниках
        intents.message_content = True  # Доступ к содержимому сообщений

        # Загружаем конфигурацию
        try:
            self.config = Config()
            logger.info("Конфигурация успешно загружена")
        except ConfigurationError as e:
            logger.critical(f"Ошибка загрузки конфигурации: {e}")
            raise

        # Инициализируем бота с префиксом команд
        super().__init__(
            command_prefix=self.config.get_command_prefix(),
            intents=intents,
            help_command=None  # Отключаем стандартную команду help
        )

        # Инициализируем database operations
        self.db = None

        # Флаг готовности
        self.is_ready = False

    async def setup_hook(self):
        """
        Этот метод вызывается при инициализации бота перед подключением к Discord.
        Здесь мы инициализируем БД и загружаем cogs.
        """
        logger.info("Инициализация бота...")

        # Инициализируем базу данных
        try:
            db_path = self.config.get_database_path()
            await initialize_database(db_path)
            self.db = DatabaseOperations(db_path)
            logger.info("База данных инициализирована")

            # Кешируем маппинги ролей в БД
            await self._cache_role_mappings()

        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}", exc_info=True)
            raise

        # Загрузка cogs
        await self.load_extension("bot.cogs.sync_button")
        await self.load_extension("bot.cogs.role_monitor")
        await self.load_extension("bot.cogs.admin_commands")
        await self.load_extension("bot.cogs.stats_commands")
        logger.info("Все cogs загружены успешно")

        logger.info("Setup hook завершен")

    async def _cache_role_mappings(self):
        """Кешировать маппинги ролей в базе данных"""
        try:
            # Очищаем старый кеш
            await self.db.clear_mapping_cache()

            # Загружаем маппинги из конфигурации
            mappings = self.config.get_role_mappings()

            # Кешируем каждый маппинг
            for mapping in mappings:
                await self.db.cache_role_mapping(
                    mapping_id=mapping.id,
                    source_server_id=mapping.source_server_id,
                    source_role_id=mapping.source_role_id,
                    target_server_id=mapping.target_server_id,
                    target_role_id=mapping.target_role_id,
                    enabled=mapping.enabled,
                    description=mapping.description
                )

            logger.info(f"Закешировано {len(mappings)} маппингов ролей")

        except Exception as e:
            logger.error(f"Ошибка кеширования маппингов: {e}", exc_info=True)

    async def on_ready(self):
        """Событие: бот подключился к Discord и готов к работе"""
        if self.is_ready:
            return

        self.is_ready = True

        logger.info("=" * 50)
        logger.info(f"Бот подключен как: {self.user.name} (ID: {self.user.id})")
        logger.info(f"Discord.py версия: {discord.__version__}")
        logger.info(f"Серверов: {len(self.guilds)}")
        logger.info("=" * 50)

        # Выводим список серверов
        for guild in self.guilds:
            logger.info(f"  - {guild.name} (ID: {guild.id}, участников: {guild.member_count})")

        # Проверяем наличие главного сервера
        main_server_id = self.config.get_main_server_id()
        main_guild = self.get_guild(main_server_id)

        if main_guild:
            logger.info(f"Главный сервер найден: {main_guild.name}")
        else:
            logger.warning(f"ВНИМАНИЕ: Главный сервер (ID: {main_server_id}) не найден!")
            logger.warning("Проверьте настройки main_server_id в config.yaml")

        # Синхронизация slash команд только для главного сервера
        try:
            guild = discord.Object(id=main_server_id)

            # Копируем все команды в главный сервер
            self.tree.copy_global_to(guild=guild)

            # Синхронизируем команды только с главным сервером (мгновенно)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"✅ Синхронизировано {len(synced)} команд для главного сервера")

            # Очищаем глобальные команды (выполняется один раз для удаления старых)
            # После первого запуска это будет просто синхронизация пустого списка
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            logger.info("🌍 Глобальные команды очищены")

        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации команд: {e}")

        logger.info("Бот полностью готов к работе!")

    async def on_guild_join(self, guild: discord.Guild):
        """Событие: бот присоединился к новому серверу"""
        logger.info(f"Присоединились к новому серверу: {guild.name} (ID: {guild.id})")

    async def on_guild_remove(self, guild: discord.Guild):
        """Событие: бот покинул сервер"""
        logger.info(f"Покинули сервер: {guild.name} (ID: {guild.id})")

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Обработка ошибок команд"""
        if isinstance(error, commands.CommandNotFound):
            return  # Игнорируем несуществующие команды

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("У вас нет прав для использования этой команды.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Отсутствует обязательный аргумент: {error.param.name}")
            return

        # Логируем неожиданные ошибки
        logger.error(f"Ошибка при выполнении команды {ctx.command}: {error}", exc_info=True)
        await ctx.send("Произошла ошибка при выполнении команды. Проверьте логи.")

    async def close(self):
        """Корректное закрытие бота"""
        logger.info("Закрытие бота...")

        # Закрываем соединение с БД
        if self.db:
            try:
                await self.db.close()
                logger.info("База данных закрыта")
            except Exception as e:
                logger.error(f"Ошибка закрытия БД: {e}", exc_info=True)

        # Закрываем Discord соединение
        await super().close()
        logger.info("Бот остановлен")
