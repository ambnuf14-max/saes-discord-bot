"""
CRUD операции для работы с базой данных
"""

import aiosqlite
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from bot.utils.logger import get_logger
from bot.utils.errors import DatabaseError

logger = get_logger("database.operations")


class DatabaseOperations:
    """Класс для выполнения операций с базой данных"""

    def __init__(self, db_path: str):
        """
        Инициализация

        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path = db_path

    async def _execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """
        Выполнить SQL запрос

        Args:
            query: SQL запрос
            params: Параметры запроса

        Returns:
            Cursor объект
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query, params)
                await db.commit()
                return cursor
        except Exception as e:
            logger.error(f"Ошибка выполнения запроса: {e}", exc_info=True)
            raise DatabaseError(f"Database error: {e}")

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        """Выполнить запрос и вернуть одну строку"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple = ()) -> List[aiosqlite.Row]:
        """Выполнить запрос и вернуть все строки"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    # ============ Sync State Operations ============

    async def update_sync_state(self, user_id: int, main_server_id: int) -> None:
        """
        Обновить состояние синхронизации пользователя

        Args:
            user_id: ID пользователя
            main_server_id: ID главного сервера
        """
        query = """
        INSERT INTO sync_state (user_id, main_server_id, last_sync_timestamp, sync_count)
        VALUES (?, ?, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(user_id, main_server_id) DO UPDATE SET
            last_sync_timestamp = CURRENT_TIMESTAMP,
            sync_count = sync_count + 1
        """
        await self._execute(query, (user_id, main_server_id))
        logger.debug(f"Обновлено состояние синхронизации для пользователя {user_id}")

    async def get_sync_state(self, user_id: int, main_server_id: int) -> Optional[Dict]:
        """Получить состояние синхронизации пользователя"""
        query = """
        SELECT * FROM sync_state
        WHERE user_id = ? AND main_server_id = ?
        """
        row = await self._fetchone(query, (user_id, main_server_id))
        return dict(row) if row else None

    # ============ Role Assignment Operations ============

    async def record_role_assignment(
        self,
        user_id: int,
        source_server_id: int,
        source_role_id: int,
        target_server_id: int,
        target_role_id: int,
        assignment_type: str
    ) -> None:
        """
        Записать назначение роли

        Args:
            user_id: ID пользователя
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли
            target_server_id: ID целевого сервера
            target_role_id: ID целевой роли
            assignment_type: Тип назначения (button/auto/manual)
        """
        query = """
        INSERT INTO role_assignments (
            user_id, source_server_id, source_role_id,
            target_server_id, target_role_id, assignment_type
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        await self._execute(query, (
            user_id, source_server_id, source_role_id,
            target_server_id, target_role_id, assignment_type
        ))
        logger.debug(f"Записано назначение роли для пользователя {user_id}")

    async def get_user_role_assignments(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Dict]:
        """
        Получить историю назначения ролей пользователя

        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей

        Returns:
            Список назначений ролей
        """
        query = """
        SELECT * FROM role_assignments
        WHERE user_id = ?
        ORDER BY assigned_timestamp DESC
        LIMIT ?
        """
        rows = await self._fetchall(query, (user_id, limit))
        return [dict(row) for row in rows]

    # ============ Sync Logs Operations ============

    async def log_sync_event(
        self,
        user_id: int,
        action_type: str,
        trigger_type: str,
        success: bool,
        source_server_id: Optional[int] = None,
        source_role_id: Optional[int] = None,
        target_server_id: Optional[int] = None,
        target_role_id: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Записать событие синхронизации в логи

        Args:
            user_id: ID пользователя
            action_type: Тип действия
            trigger_type: Триггер синхронизации
            success: Успешно ли выполнено
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли
            target_server_id: ID целевого сервера
            target_role_id: ID целевой роли
            error_message: Сообщение об ошибке
        """
        query = """
        INSERT INTO sync_logs (
            user_id, action_type, trigger_type, success,
            source_server_id, source_role_id,
            target_server_id, target_role_id, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self._execute(query, (
            user_id, action_type, trigger_type, success,
            source_server_id, source_role_id,
            target_server_id, target_role_id, error_message
        ))

    async def get_recent_logs(
        self,
        limit: int = 100,
        user_id: Optional[int] = None,
        action_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Получить недавние логи

        Args:
            limit: Максимальное количество записей
            user_id: Фильтр по ID пользователя
            action_type: Фильтр по типу действия

        Returns:
            Список логов
        """
        query = "SELECT * FROM sync_logs WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self._fetchall(query, tuple(params))
        return [dict(row) for row in rows]

    # ============ Statistics Operations ============

    async def update_statistics(
        self,
        trigger_type: str,
        success: bool,
        roles_assigned: int,
        user_id: int
    ) -> None:
        """
        Обновить статистику за сегодня

        Args:
            trigger_type: Тип триггера синхронизации
            success: Успешно ли выполнено
            roles_assigned: Количество назначенных ролей
            user_id: ID пользователя
        """
        today = date.today().isoformat()

        # Создаем или обновляем запись за сегодня
        query = """
        INSERT INTO statistics (
            stat_date, total_syncs, button_syncs, auto_syncs, manual_syncs,
            successful_syncs, failed_syncs, unique_users_synced, total_roles_assigned
        ) VALUES (?, 1, 0, 0, 0, 0, 0, 0, ?)
        ON CONFLICT(stat_date) DO UPDATE SET
            total_syncs = total_syncs + 1,
            total_roles_assigned = total_roles_assigned + ?
        """
        await self._execute(query, (today, roles_assigned, roles_assigned))

        # Обновляем счетчики в зависимости от типа триггера
        if trigger_type == "button":
            await self._execute(
                "UPDATE statistics SET button_syncs = button_syncs + 1 WHERE stat_date = ?",
                (today,)
            )
        elif trigger_type == "auto":
            await self._execute(
                "UPDATE statistics SET auto_syncs = auto_syncs + 1 WHERE stat_date = ?",
                (today,)
            )
        elif trigger_type == "manual":
            await self._execute(
                "UPDATE statistics SET manual_syncs = manual_syncs + 1 WHERE stat_date = ?",
                (today,)
            )

        # Обновляем счетчик успешных/неуспешных синхронизаций
        if success:
            await self._execute(
                "UPDATE statistics SET successful_syncs = successful_syncs + 1 WHERE stat_date = ?",
                (today,)
            )
        else:
            await self._execute(
                "UPDATE statistics SET failed_syncs = failed_syncs + 1 WHERE stat_date = ?",
                (today,)
            )

    async def get_statistics_summary(self, days: int = 30) -> Dict:
        """
        Получить сводную статистику за период

        Args:
            days: Количество дней

        Returns:
            Словарь со статистикой
        """
        query = """
        SELECT
            SUM(total_syncs) as total_syncs,
            SUM(button_syncs) as button_syncs,
            SUM(auto_syncs) as auto_syncs,
            SUM(manual_syncs) as manual_syncs,
            SUM(successful_syncs) as successful_syncs,
            SUM(failed_syncs) as failed_syncs,
            SUM(total_roles_assigned) as total_roles_assigned
        FROM statistics
        WHERE stat_date >= date('now', ?)
        """
        row = await self._fetchone(query, (f'-{days} days',))
        return dict(row) if row else {}

    async def get_daily_statistics(self, days: int = 7) -> List[Dict]:
        """
        Получить ежедневную статистику

        Args:
            days: Количество дней

        Returns:
            Список статистики по дням
        """
        query = """
        SELECT * FROM statistics
        WHERE stat_date >= date('now', ?)
        ORDER BY stat_date DESC
        """
        rows = await self._fetchall(query, (f'-{days} days',))
        return [dict(row) for row in rows]

    # ============ Role Mapping Cache Operations ============

    async def cache_role_mapping(
        self,
        mapping_id: str,
        source_server_id: int,
        source_role_id: int,
        target_server_id: int,
        target_role_id: int,
        enabled: bool = True,
        description: str = ""
    ) -> None:
        """
        Кешировать маппинг роли

        Args:
            mapping_id: ID маппинга
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли
            target_server_id: ID целевого сервера
            target_role_id: ID целевой роли
            enabled: Включен ли маппинг
            description: Описание
        """
        query = """
        INSERT INTO role_mapping_cache (
            mapping_id, source_server_id, source_role_id,
            target_server_id, target_role_id, enabled, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mapping_id) DO UPDATE SET
            source_server_id = ?,
            source_role_id = ?,
            target_server_id = ?,
            target_role_id = ?,
            enabled = ?,
            description = ?,
            last_updated = CURRENT_TIMESTAMP
        """
        await self._execute(query, (
            mapping_id, source_server_id, source_role_id,
            target_server_id, target_role_id, enabled, description,
            source_server_id, source_role_id, target_server_id,
            target_role_id, enabled, description
        ))

    async def get_target_role(
        self,
        source_server_id: int,
        source_role_id: int
    ) -> Optional[int]:
        """
        Получить целевую роль для данной исходной роли

        Args:
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли

        Returns:
            ID целевой роли или None
        """
        query = """
        SELECT target_role_id FROM role_mapping_cache
        WHERE source_server_id = ? AND source_role_id = ? AND enabled = 1
        """
        row = await self._fetchone(query, (source_server_id, source_role_id))
        return row['target_role_id'] if row else None

    async def get_all_mappings(self) -> List[Dict]:
        """
        Получить все маппинги ролей

        Returns:
            Список всех маппингов
        """
        query = "SELECT * FROM role_mapping_cache ORDER BY mapping_id"
        rows = await self._fetchall(query)
        return [dict(row) for row in rows]

    async def remove_mapping(self, mapping_id: str) -> bool:
        """
        Удалить маппинг роли

        Args:
            mapping_id: ID маппинга

        Returns:
            True если удален успешно
        """
        query = "DELETE FROM role_mapping_cache WHERE mapping_id = ?"
        await self._execute(query, (mapping_id,))
        logger.info(f"Удален маппинг {mapping_id}")
        return True

    async def clear_mapping_cache(self) -> None:
        """Очистить весь кеш маппингов"""
        query = "DELETE FROM role_mapping_cache"
        await self._execute(query)
        logger.info("Кеш маппингов очищен")
