"""
Кастомные исключения для Discord Role Sync Bot
"""


class SyncBotException(Exception):
    """Базовое исключение для бота синхронизации ролей"""
    pass


class ConfigurationError(SyncBotException):
    """Ошибки загрузки или валидации конфигурации"""
    pass


class PermissionError(SyncBotException):
    """Боту не хватает необходимых прав"""
    pass


class UserNotFoundError(SyncBotException):
    """Пользователь не найден на сервере"""
    pass


class RoleMappingError(SyncBotException):
    """Ошибки разрешения маппинга ролей"""
    pass


class DatabaseError(SyncBotException):
    """Ошибки операций с базой данных"""
    pass


class SyncError(SyncBotException):
    """Ошибки процесса синхронизации"""
    pass
