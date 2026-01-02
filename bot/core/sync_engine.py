"""
Движок синхронизации ролей - основная логика
"""

import discord
import asyncio
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from datetime import datetime

from bot.core.role_mapper import RoleMapper
from bot.core.permissions import can_manage_role, get_manageable_roles
from bot.database.operations import DatabaseOperations
from bot.config import Config
from bot.utils.logger import get_logger
from bot.utils.errors import SyncError, UserNotFoundError

logger = get_logger("core.sync_engine")


@dataclass
class SyncResult:
    """Результат синхронизации"""
    success: bool
    user_id: int
    roles_added: List[int]
    roles_removed: List[int]
    errors: List[str]
    timestamp: datetime
    source_servers: List[int]
    # Диагностическая информация
    source_roles_found: Optional[Dict[int, List[int]]] = None  # {server_id: [role_ids]}
    target_roles_calculated: Optional[List[int]] = None  # Целевые роли которые должны быть
    current_roles: Optional[List[int]] = None  # Текущие роли на главном сервере

    def __post_init__(self):
        """Установить timestamp если не задан"""
        if not self.timestamp:
            self.timestamp = datetime.now()

    @property
    def total_changes(self) -> int:
        """Общее количество изменений"""
        return len(self.roles_added) + len(self.roles_removed)

    @property
    def has_errors(self) -> bool:
        """Есть ли ошибки"""
        return len(self.errors) > 0


class SyncEngine:
    """Движок для синхронизации ролей между серверами"""

    def __init__(
        self,
        bot: discord.Client,
        config: Config,
        db: DatabaseOperations,
        role_mapper: RoleMapper
    ):
        """
        Инициализация SyncEngine

        Args:
            bot: Объект Discord бота
            config: Объект конфигурации
            db: Объект для работы с БД
            role_mapper: Объект для маппинга ролей
        """
        self.bot = bot
        self.config = config
        self.db = db
        self.role_mapper = role_mapper

    async def sync_user_roles(
        self,
        user_id: int,
        trigger_type: str = "manual"
    ) -> SyncResult:
        """
        Синхронизировать роли пользователя

        Args:
            user_id: ID пользователя Discord
            trigger_type: Тип триггера (button/auto/manual)

        Returns:
            Объект SyncResult с результатами синхронизации
        """
        logger.info(f"Начало синхронизации для пользователя {user_id} (триггер: {trigger_type})")

        result = SyncResult(
            success=False,
            user_id=user_id,
            roles_added=[],
            roles_removed=[],
            errors=[],
            timestamp=datetime.now(),
            source_servers=[]
        )

        try:
            # 1. Получаем главный сервер
            main_server_id = self.config.get_main_server_id()
            main_guild = self.bot.get_guild(main_server_id)

            if not main_guild:
                error_msg = f"Главный сервер {main_server_id} не найден"
                logger.error(error_msg)
                result.errors.append(error_msg)
                await self._log_sync_event(user_id, "sync_failed", trigger_type, False, error_message=error_msg)
                return result

            # 2. Получаем пользователя на главном сервере
            try:
                main_member = await main_guild.fetch_member(user_id)
            except discord.NotFound:
                error_msg = f"Пользователь {user_id} не найден на главном сервере"
                logger.warning(error_msg)
                result.errors.append(error_msg)
                await self._log_sync_event(user_id, "sync_failed", trigger_type, False, error_message=error_msg)
                raise UserNotFoundError(error_msg)

            # 3. Получаем все сервера и роли пользователя (один параллельный запрос)
            mutual_guilds, user_roles_map = await self.get_user_roles_from_all_guilds(user_id)
            logger.info(f"Пользователь найден на {len(mutual_guilds)} общих серверах")

            if not mutual_guilds:
                logger.info(f"Пользователь {user_id} не найден ни на одном из мониторимых серверов")
                result.success = True
                await self._log_sync_event(user_id, "sync_success", trigger_type, True)
                return result

            # 4. Роли уже собраны в предыдущем шаге
            result.source_servers = list(user_roles_map.keys())
            result.source_roles_found = user_roles_map  # Сохраняем диагностическую информацию

            # 5. Вычисляем какие целевые роли должны быть
            target_role_ids = await self.calculate_target_roles(user_roles_map)
            result.target_roles_calculated = target_role_ids  # Сохраняем диагностическую информацию
            logger.info(f"Рассчитано {len(target_role_ids)} целевых ролей для назначения")

            # Сохраняем текущие роли пользователя на главном сервере
            result.current_roles = [role.id for role in main_member.roles if not role.is_default()]

            # 6. Определяем какие роли нужно добавить/удалить
            roles_to_add, roles_to_remove = await self.calculate_role_changes(
                main_member,
                target_role_ids
            )

            # 7. Применяем изменения
            success = await self.apply_role_changes(
                main_member,
                roles_to_add,
                roles_to_remove,
                trigger_type,
                user_roles_map
            )

            result.success = success
            result.roles_added = [r.id for r in roles_to_add]
            result.roles_removed = [r.id for r in roles_to_remove]

            # 8. Логируем результат
            if success:
                await self._log_sync_event(user_id, "sync_success", trigger_type, True)
                await self.db.update_sync_state(user_id, main_server_id)
                await self.db.update_statistics(
                    trigger_type=trigger_type,
                    success=True,
                    roles_assigned=len(roles_to_add),
                    user_id=user_id
                )
            else:
                await self._log_sync_event(user_id, "sync_failed", trigger_type, False)

            logger.info(
                f"Синхронизация завершена для {user_id}: "
                f"+{len(roles_to_add)} ролей, -{len(roles_to_remove)} ролей"
            )

        except UserNotFoundError:
            # Уже залогировано
            pass
        except Exception as e:
            error_msg = f"Ошибка синхронизации: {e}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            await self._log_sync_event(user_id, "sync_failed", trigger_type, False, error_message=str(e))

        return result

    async def _fetch_member_safe(
        self,
        guild: discord.Guild,
        user_id: int
    ) -> Optional[discord.Member]:
        """
        Безопасно получить участника сервера

        Args:
            guild: Сервер
            user_id: ID пользователя

        Returns:
            Member или None если не найден
        """
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
        except Exception as e:
            logger.warning(f"Ошибка получения участника на сервере {guild.name}: {e}")
            return None

    async def get_user_roles_from_all_guilds(
        self,
        user_id: int
    ) -> Tuple[List[discord.Guild], Dict[int, List[int]]]:
        """
        Получить роли пользователя со всех серверов (параллельно)

        Args:
            user_id: ID пользователя

        Returns:
            Кортеж (список серверов где найден, словарь {server_id: [role_ids]})
        """
        main_server_id = self.config.get_main_server_id()

        # Фильтруем сервера (исключаем главный)
        guilds_to_check = [g for g in self.bot.guilds if g.id != main_server_id]

        if not guilds_to_check:
            return [], {}

        # Параллельно запрашиваем всех участников
        tasks = [self._fetch_member_safe(guild, user_id) for guild in guilds_to_check]
        results = await asyncio.gather(*tasks)

        mutual_guilds = []
        user_roles_map = {}

        for guild, member in zip(guilds_to_check, results):
            if member is not None:
                mutual_guilds.append(guild)
                # Получаем все роли кроме @everyone
                role_ids = [role.id for role in member.roles if not role.is_default()]
                if role_ids:
                    user_roles_map[guild.id] = role_ids
                    logger.debug(
                        f"Пользователь имеет {len(role_ids)} ролей на сервере {guild.name}"
                    )

        logger.debug(f"Пользователь найден на {len(mutual_guilds)} серверах (параллельный запрос)")
        return mutual_guilds, user_roles_map

    async def get_user_mutual_guilds(self, user_id: int) -> List[discord.Guild]:
        """
        Получить все сервера где есть и пользователь, и бот

        Args:
            user_id: ID пользователя

        Returns:
            Список объектов Guild
        """
        mutual_guilds, _ = await self.get_user_roles_from_all_guilds(user_id)
        return mutual_guilds

    async def get_user_roles_from_guilds(
        self,
        user_id: int,
        guilds: List[discord.Guild]
    ) -> Dict[int, List[int]]:
        """
        Получить роли пользователя со всех указанных серверов (параллельно)

        Args:
            user_id: ID пользователя
            guilds: Список серверов

        Returns:
            Словарь {server_id: [role_id1, role_id2, ...]}
        """
        if not guilds:
            return {}

        # Параллельно запрашиваем всех участников
        tasks = [self._fetch_member_safe(guild, user_id) for guild in guilds]
        results = await asyncio.gather(*tasks)

        user_roles_map = {}

        for guild, member in zip(guilds, results):
            if member is not None:
                role_ids = [role.id for role in member.roles if not role.is_default()]
                if role_ids:
                    user_roles_map[guild.id] = role_ids
                    logger.debug(
                        f"Пользователь имеет {len(role_ids)} ролей на сервере {guild.name}"
                    )

        return user_roles_map

    async def calculate_target_roles(
        self,
        user_roles_map: Dict[int, List[int]]
    ) -> List[int]:
        """
        Вычислить какие целевые роли должны быть назначены

        Args:
            user_roles_map: Словарь {server_id: [role_ids]}

        Returns:
            Список ID целевых ролей
        """
        # Собираем все пары (server_id, role_id)
        source_roles = []
        for server_id, role_ids in user_roles_map.items():
            for role_id in role_ids:
                source_roles.append((server_id, role_id))

        # Получаем все целевые роли через RoleMapper
        target_role_ids = self.role_mapper.get_all_target_roles(source_roles)

        return target_role_ids

    async def calculate_role_changes(
        self,
        member: discord.Member,
        target_role_ids: List[int]
    ) -> Tuple[List[discord.Role], List[discord.Role]]:
        """
        Определить какие роли нужно добавить/удалить

        Args:
            member: Объект участника на главном сервере
            target_role_ids: Список ID целевых ролей

        Returns:
            Кортеж (роли_для_добавления, роли_для_удаления)
        """
        # Получаем текущие роли пользователя (только управляемые ботом)
        current_role_ids = set(role.id for role in member.roles if not role.is_default())

        # Целевые роли
        target_role_ids_set = set(target_role_ids)

        # Вычисляем разницу
        roles_to_add_ids = target_role_ids_set - current_role_ids
        roles_to_remove_ids = current_role_ids - target_role_ids_set

        # Преобразуем ID в объекты ролей
        roles_to_add = []
        roles_to_remove = []

        # Получаем управляемые роли для добавления
        if roles_to_add_ids:
            manageable_add, unmanageable_add = await get_manageable_roles(
                member.guild,
                list(roles_to_add_ids)
            )
            roles_to_add = manageable_add

            if unmanageable_add:
                logger.warning(
                    f"Не удалось добавить {len(unmanageable_add)} ролей "
                    f"(нет прав или роли не найдены)"
                )

        # Получаем управляемые роли для удаления
        # ВАЖНО: удаляем только те роли, которые были добавлены через синхронизацию
        # Используем обратный индекс для O(1) проверки
        if roles_to_remove_ids:
            # Фильтруем только роли, которые есть в наших маппингах (O(1) через is_target_role)
            mapped_role_ids = [
                role_id for role_id in roles_to_remove_ids
                if self.role_mapper.is_target_role(role_id)
            ]

            if mapped_role_ids:
                manageable_remove, _ = await get_manageable_roles(
                    member.guild,
                    mapped_role_ids
                )
                roles_to_remove = manageable_remove

        logger.debug(
            f"Изменения ролей: +{len(roles_to_add)}, -{len(roles_to_remove)}"
        )

        return roles_to_add, roles_to_remove

    async def apply_role_changes(
        self,
        member: discord.Member,
        roles_to_add: List[discord.Role],
        roles_to_remove: List[discord.Role],
        trigger_type: str,
        user_roles_map: Dict[int, List[int]]
    ) -> bool:
        """
        Применить изменения ролей к пользователю

        Args:
            member: Объект участника
            roles_to_add: Роли для добавления
            roles_to_remove: Роли для удаления
            trigger_type: Тип триггера
            user_roles_map: Карта ролей пользователя на других серверах

        Returns:
            True если все изменения применены успешно
        """
        success = True

        # Добавляем роли
        for role in roles_to_add:
            try:
                await member.add_roles(role, reason=f"Role sync ({trigger_type})")
                logger.info(f"Добавлена роль {role.name} пользователю {member.id}")

                # Логируем в БД
                await self.db.log_sync_event(
                    user_id=member.id,
                    action_type="role_added",
                    trigger_type=trigger_type,
                    success=True,
                    target_server_id=member.guild.id,
                    target_role_id=role.id
                )

                # Записываем назначение роли
                # Находим исходный сервер и роль
                for source_server_id, source_role_ids in user_roles_map.items():
                    for source_role_id in source_role_ids:
                        target_role = self.role_mapper.get_target_role(
                            source_server_id,
                            source_role_id
                        )
                        if target_role == role.id:
                            await self.db.record_role_assignment(
                                user_id=member.id,
                                source_server_id=source_server_id,
                                source_role_id=source_role_id,
                                target_server_id=member.guild.id,
                                target_role_id=role.id,
                                assignment_type=trigger_type
                            )
                            break

            except discord.Forbidden:
                error_msg = f"Нет прав для добавления роли {role.name}"
                logger.error(error_msg)
                success = False
                await self.db.log_sync_event(
                    user_id=member.id,
                    action_type="role_added",
                    trigger_type=trigger_type,
                    success=False,
                    target_role_id=role.id,
                    error_message=error_msg
                )
            except Exception as e:
                error_msg = f"Ошибка добавления роли {role.name}: {e}"
                logger.error(error_msg, exc_info=True)
                success = False

        # Удаляем роли
        for role in roles_to_remove:
            try:
                await member.remove_roles(role, reason=f"Role sync cleanup ({trigger_type})")
                logger.info(f"Удалена роль {role.name} у пользователя {member.id}")

                # Логируем в БД
                await self.db.log_sync_event(
                    user_id=member.id,
                    action_type="role_removed",
                    trigger_type=trigger_type,
                    success=True,
                    target_server_id=member.guild.id,
                    target_role_id=role.id
                )

            except discord.Forbidden:
                error_msg = f"Нет прав для удаления роли {role.name}"
                logger.error(error_msg)
                success = False
            except Exception as e:
                error_msg = f"Ошибка удаления роли {role.name}: {e}"
                logger.error(error_msg, exc_info=True)
                success = False

        return success

    async def sync_all_users(self, guild_id: Optional[int] = None) -> Dict[str, int]:
        """
        Синхронизировать всех пользователей на сервере

        Args:
            guild_id: ID сервера (None = главный сервер)

        Returns:
            Словарь со статистикой синхронизации
        """
        if guild_id is None:
            guild_id = self.config.get_main_server_id()

        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Сервер {guild_id} не найден")
            return {"error": 1}

        logger.info(f"Начало массовой синхронизации на сервере {guild.name}")

        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }

        for member in guild.members:
            if member.bot:
                stats["skipped"] += 1
                continue

            stats["total"] += 1

            try:
                result = await self.sync_user_roles(member.id, trigger_type="manual")
                if result.success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

                # Небольшая задержка чтобы не превысить rate limit
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Ошибка синхронизации пользователя {member.id}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Массовая синхронизация завершена: "
            f"{stats['success']} успешно, {stats['failed']} ошибок, "
            f"{stats['skipped']} пропущено"
        )

        return stats

    async def _log_sync_event(
        self,
        user_id: int,
        action_type: str,
        trigger_type: str,
        success: bool,
        error_message: Optional[str] = None
    ):
        """Вспомогательный метод для логирования событий синхронизации"""
        try:
            await self.db.log_sync_event(
                user_id=user_id,
                action_type=action_type,
                trigger_type=trigger_type,
                success=success,
                error_message=error_message
            )
        except Exception as e:
            logger.error(f"Ошибка логирования события: {e}", exc_info=True)
