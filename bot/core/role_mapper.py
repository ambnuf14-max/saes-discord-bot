"""
Система маппинга ролей между серверами
"""

from typing import List, Optional, Tuple, Dict
from bot.config import Config, RoleMapping
from bot.database.operations import DatabaseOperations
from bot.utils.logger import get_logger
from bot.utils.errors import RoleMappingError

logger = get_logger("core.role_mapper")


class RoleMapper:
    """Класс для управления маппингом ролей между серверами"""

    def __init__(self, config: Config, db: DatabaseOperations):
        """
        Инициализация RoleMapper

        Args:
            config: Объект конфигурации
            db: Объект для работы с БД
        """
        self.config = config
        self.db = db
        self._mapping_cache: Dict[Tuple[int, int], int] = {}
        self._initialized = False

    async def initialize(self):
        """Инициализация - загрузка маппингов в кеш"""
        if self._initialized:
            return

        logger.info("Инициализация RoleMapper...")
        await self.load_mappings()
        self._initialized = True
        logger.info("RoleMapper инициализирован")

    async def load_mappings(self):
        """Загрузить маппинги из базы данных в память"""
        try:
            # Получаем все маппинги из БД
            mappings = await self.db.get_all_mappings()

            # Очищаем старый кеш
            self._mapping_cache.clear()

            # Загружаем в кеш только активные маппинги
            for mapping in mappings:
                if mapping['enabled']:
                    # Преобразуем ID в int для корректного сравнения
                    source_server_id = int(mapping['source_server_id'])
                    source_role_id = int(mapping['source_role_id'])
                    target_role_id = int(mapping['target_role_id'])

                    key = (source_server_id, source_role_id)
                    self._mapping_cache[key] = target_role_id

                    # Детальное логирование только в DEBUG режиме
                    logger.debug(
                        f"Маппинг загружен: сервер {source_server_id}, "
                        f"роль {source_role_id} -> целевая роль {target_role_id}"
                    )

            logger.info(f"Загружено {len(self._mapping_cache)} активных маппингов в кеш")

        except Exception as e:
            logger.error(f"Ошибка загрузки маппингов: {e}", exc_info=True)
            raise RoleMappingError(f"Не удалось загрузить маппинги: {e}")

    async def reload_mappings(self):
        """Перезагрузить маппинги из конфигурации и обновить БД"""
        try:
            logger.info("Перезагрузка маппингов из конфигурации...")

            # Перезагружаем конфигурацию
            self.config.reload_mappings()

            # Очищаем кеш в БД
            await self.db.clear_mapping_cache()

            # Загружаем маппинги из конфига в БД
            mappings = self.config.get_all_role_mappings()
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

            # Перезагружаем в память
            await self.load_mappings()

            logger.info("Маппинги успешно перезагружены")

        except Exception as e:
            logger.error(f"Ошибка перезагрузки маппингов: {e}", exc_info=True)
            raise RoleMappingError(f"Не удалось перезагрузить маппинги: {e}")

    def get_target_role(self, source_server_id: int, source_role_id: int) -> Optional[int]:
        """
        Получить целевую роль для данной исходной роли

        Args:
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли

        Returns:
            ID целевой роли или None если маппинг не найден
        """
        key = (source_server_id, source_role_id)
        target_role_id = self._mapping_cache.get(key)

        if target_role_id:
            logger.debug(
                f"Найден маппинг: сервер {source_server_id}, "
                f"роль {source_role_id} -> {target_role_id}"
            )

        return target_role_id

    def get_all_target_roles(
        self,
        source_roles: List[Tuple[int, int]]
    ) -> List[int]:
        """
        Получить все целевые роли для списка исходных ролей

        Args:
            source_roles: Список кортежей (server_id, role_id)

        Returns:
            Список ID целевых ролей (без дубликатов)
        """
        target_roles = set()

        for server_id, role_id in source_roles:
            target_role = self.get_target_role(server_id, role_id)
            if target_role:
                target_roles.add(target_role)

        result = list(target_roles)
        logger.debug(
            f"Из {len(source_roles)} исходных ролей найдено "
            f"{len(result)} уникальных целевых ролей"
        )

        return result

    def has_mapping(self, source_server_id: int, source_role_id: int) -> bool:
        """
        Проверить существует ли маппинг для данной роли

        Args:
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли

        Returns:
            True если маппинг существует
        """
        key = (source_server_id, source_role_id)
        return key in self._mapping_cache

    async def add_mapping(
        self,
        mapping_id: str,
        source_server_id: int,
        source_role_id: int,
        target_server_id: int,
        target_role_id: int,
        description: str = "",
        enabled: bool = True
    ) -> bool:
        """
        Добавить новый маппинг роли

        Args:
            mapping_id: Уникальный ID маппинга
            source_server_id: ID исходного сервера
            source_role_id: ID исходной роли
            target_server_id: ID целевого сервера
            target_role_id: ID целевой роли
            description: Описание маппинга
            enabled: Включен ли маппинг

        Returns:
            True если добавлен успешно
        """
        try:
            # Создаем объект маппинга
            mapping = RoleMapping(
                id=mapping_id,
                source_server_id=source_server_id,
                source_role_id=source_role_id,
                target_server_id=target_server_id,
                target_role_id=target_role_id,
                description=description,
                enabled=enabled
            )

            # Добавляем в конфиг
            self.config.add_role_mapping(mapping)

            # Добавляем в БД
            await self.db.cache_role_mapping(
                mapping_id=mapping_id,
                source_server_id=source_server_id,
                source_role_id=source_role_id,
                target_server_id=target_server_id,
                target_role_id=target_role_id,
                enabled=enabled,
                description=description
            )

            # Обновляем кеш в памяти
            if enabled:
                key = (source_server_id, source_role_id)
                self._mapping_cache[key] = target_role_id

            logger.info(f"Добавлен новый маппинг: {mapping_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления маппинга: {e}", exc_info=True)
            raise RoleMappingError(f"Не удалось добавить маппинг: {e}")

    async def remove_mapping(self, mapping_id: str) -> bool:
        """
        Удалить маппинг роли

        Args:
            mapping_id: ID маппинга для удаления

        Returns:
            True если удален успешно
        """
        try:
            # Получаем маппинг перед удалением
            mapping = self.config.get_mapping_by_id(mapping_id)
            if not mapping:
                logger.warning(f"Маппинг {mapping_id} не найден")
                return False

            # Удаляем из конфига
            self.config.remove_role_mapping(mapping_id)

            # Удаляем из БД
            await self.db.remove_mapping(mapping_id)

            # Удаляем из кеша в памяти
            key = (mapping.source_server_id, mapping.source_role_id)
            self._mapping_cache.pop(key, None)

            logger.info(f"Удален маппинг: {mapping_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления маппинга: {e}", exc_info=True)
            raise RoleMappingError(f"Не удалось удалить маппинг: {e}")

    async def update_mapping(
        self,
        mapping_id: str,
        enabled: Optional[bool] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        Обновить существующий маппинг

        Args:
            mapping_id: ID маппинга
            enabled: Новое состояние (опционально)
            description: Новое описание (опционально)

        Returns:
            True если обновлен успешно
        """
        try:
            # Получаем текущий маппинг
            mapping = self.config.get_mapping_by_id(mapping_id)
            if not mapping:
                logger.warning(f"Маппинг {mapping_id} не найден")
                return False

            # Обновляем поля
            if enabled is not None:
                mapping.enabled = enabled
            if description is not None:
                mapping.description = description

            # Обновляем в конфиге
            self.config.update_role_mapping(mapping)

            # Обновляем в БД
            await self.db.cache_role_mapping(
                mapping_id=mapping.id,
                source_server_id=mapping.source_server_id,
                source_role_id=mapping.source_role_id,
                target_server_id=mapping.target_server_id,
                target_role_id=mapping.target_role_id,
                enabled=mapping.enabled,
                description=mapping.description
            )

            # Обновляем кеш в памяти
            key = (mapping.source_server_id, mapping.source_role_id)
            if mapping.enabled:
                self._mapping_cache[key] = mapping.target_role_id
            else:
                self._mapping_cache.pop(key, None)

            logger.info(f"Обновлен маппинг: {mapping_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления маппинга: {e}", exc_info=True)
            raise RoleMappingError(f"Не удалось обновить маппинг: {e}")

    def get_mappings_for_server(self, source_server_id: int) -> List[Dict]:
        """
        Получить все маппинги для конкретного сервера

        Args:
            source_server_id: ID исходного сервера

        Returns:
            Список маппингов в виде словарей
        """
        result = []
        for (server_id, role_id), target_role_id in self._mapping_cache.items():
            if server_id == source_server_id:
                result.append({
                    'source_server_id': server_id,
                    'source_role_id': role_id,
                    'target_role_id': target_role_id
                })

        return result

    def get_stats(self) -> Dict[str, int]:
        """
        Получить статистику по маппингам

        Returns:
            Словарь со статистикой
        """
        all_mappings = self.config.get_all_role_mappings()
        enabled_count = len(self._mapping_cache)
        total_count = len(all_mappings)

        # Подсчитываем количество уникальных серверов
        unique_servers = set(key[0] for key in self._mapping_cache.keys())

        return {
            'total_mappings': total_count,
            'enabled_mappings': enabled_count,
            'disabled_mappings': total_count - enabled_count,
            'unique_source_servers': len(unique_servers)
        }
