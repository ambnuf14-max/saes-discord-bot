"""
Утилиты для валидации входных данных
"""

import re
from typing import Optional


def is_valid_snowflake(snowflake: str) -> bool:
    """
    Проверка валидности Discord snowflake ID

    Args:
        snowflake: Строка с ID

    Returns:
        True если валидный snowflake
    """
    if not isinstance(snowflake, str):
        return False
    return snowflake.isdigit() and len(snowflake) >= 17 and len(snowflake) <= 20


def validate_server_id(server_id: int) -> bool:
    """
    Валидация ID сервера Discord

    Args:
        server_id: ID сервера

    Returns:
        True если валидный
    """
    return isinstance(server_id, int) and server_id > 0


def validate_role_id(role_id: int) -> bool:
    """
    Валидация ID роли Discord

    Args:
        role_id: ID роли

    Returns:
        True если валидный
    """
    return isinstance(role_id, int) and role_id > 0


def sanitize_input(text: str, max_length: int = 200) -> str:
    """
    Очистка пользовательского ввода

    Args:
        text: Входной текст
        max_length: Максимальная длина

    Returns:
        Очищенный текст
    """
    if not isinstance(text, str):
        return ""

    # Удаляем управляющие символы
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

    # Обрезаем до максимальной длины
    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()
