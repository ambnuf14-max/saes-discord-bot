"""
Утилиты для проверки прав бота на серверах
"""

import discord
from typing import List, Tuple, Dict, Optional
from bot.utils.logger import get_logger

logger = get_logger("core.permissions")


async def check_bot_permissions(
    guild: discord.Guild,
    required_permissions: List[str]
) -> Tuple[bool, List[str]]:
    """
    Проверить наличие необходимых прав у бота на сервере

    Args:
        guild: Объект сервера Discord
        required_permissions: Список названий требуемых прав

    Returns:
        Кортеж (все_права_есть, список_отсутствующих_прав)
    """
    try:
        bot_member = guild.me
        if not bot_member:
            logger.warning(f"Бот не найден на сервере {guild.name}")
            return False, required_permissions

        permissions = bot_member.guild_permissions
        missing_permissions = []

        # Проверяем каждое требуемое право
        for perm_name in required_permissions:
            if not getattr(permissions, perm_name, False):
                missing_permissions.append(perm_name)

        has_all = len(missing_permissions) == 0

        if not has_all:
            logger.warning(
                f"На сервере {guild.name} отсутствуют права: {', '.join(missing_permissions)}"
            )

        return has_all, missing_permissions

    except Exception as e:
        logger.error(f"Ошибка проверки прав на сервере {guild.name}: {e}", exc_info=True)
        return False, required_permissions


async def can_manage_role(
    bot_member: discord.Member,
    role: discord.Role
) -> bool:
    """
    Проверить может ли бот управлять конкретной ролью

    Args:
        bot_member: Объект бота как участника сервера
        role: Роль для проверки

    Returns:
        True если бот может управлять этой ролью
    """
    try:
        # Проверяем есть ли право manage_roles
        if not bot_member.guild_permissions.manage_roles:
            logger.debug(f"У бота нет права manage_roles на сервере {bot_member.guild.name}")
            return False

        # Проверяем иерархию ролей
        # Бот может управлять только ролями ниже своей самой высокой роли
        bot_top_role = bot_member.top_role
        if role >= bot_top_role:
            logger.debug(
                f"Роль {role.name} ({role.position}) выше или равна "
                f"роли бота {bot_top_role.name} ({bot_top_role.position})"
            )
            return False

        # Проверяем что роль не managed (не создана ботом/интеграцией)
        if role.managed:
            logger.debug(f"Роль {role.name} является managed и не может быть изменена")
            return False

        # Проверяем что роль не @everyone
        if role.is_default():
            logger.debug("Нельзя управлять ролью @everyone")
            return False

        return True

    except Exception as e:
        logger.error(f"Ошибка проверки возможности управления ролью {role.name}: {e}", exc_info=True)
        return False


async def validate_server_permissions(
    guild: discord.Guild,
    check_manage_roles: bool = True
) -> Tuple[bool, List[str]]:
    """
    Валидировать все необходимые права бота на сервере

    Args:
        guild: Объект сервера Discord
        check_manage_roles: Проверять ли право manage_roles

    Returns:
        Кортеж (все_права_есть, список_проблем)
    """
    issues = []

    # Список необходимых прав
    required_perms = [
        'view_channel',      # Просмотр каналов
        'send_messages',     # Отправка сообщений
        'embed_links',       # Вставка ссылок
        'read_message_history',  # Чтение истории сообщений
    ]

    if check_manage_roles:
        required_perms.append('manage_roles')

    # Проверяем права
    has_all, missing = await check_bot_permissions(guild, required_perms)

    if not has_all:
        for perm in missing:
            issues.append(f"Отсутствует право: {perm}")

    # Проверяем позицию роли бота
    try:
        bot_member = guild.me
        if bot_member:
            bot_top_role = bot_member.top_role

            # Подсчитываем сколько ролей выше роли бота
            roles_above = sum(1 for role in guild.roles if role > bot_top_role and not role.is_default())

            if roles_above > 0:
                issues.append(
                    f"Роль бота находится слишком низко в иерархии. "
                    f"Ролей выше: {roles_above}"
                )
                logger.warning(
                    f"На сервере {guild.name} роль бота ({bot_top_role.name}) "
                    f"находится ниже {roles_above} других ролей"
                )

    except Exception as e:
        logger.error(f"Ошибка проверки позиции роли: {e}", exc_info=True)
        issues.append("Не удалось проверить позицию роли бота")

    return len(issues) == 0, issues


async def validate_all_servers(
    bot: discord.Client,
    servers_to_check: Optional[List[int]] = None
) -> Dict[int, List[str]]:
    """
    Валидировать права бота на всех серверах

    Args:
        bot: Объект Discord клиента/бота
        servers_to_check: Список ID серверов для проверки (None = все)

    Returns:
        Словарь {server_id: список_проблем}
    """
    results = {}

    guilds_to_check = bot.guilds
    if servers_to_check:
        guilds_to_check = [g for g in bot.guilds if g.id in servers_to_check]

    logger.info(f"Проверка прав на {len(guilds_to_check)} серверах...")

    for guild in guilds_to_check:
        is_valid, issues = await validate_server_permissions(guild)
        if not is_valid:
            results[guild.id] = issues
            logger.warning(f"Проблемы на сервере {guild.name}: {', '.join(issues)}")
        else:
            logger.info(f"Все права на сервере {guild.name} в порядке")

    return results


async def get_manageable_roles(
    guild: discord.Guild,
    role_ids: List[int]
) -> Tuple[List[discord.Role], List[int]]:
    """
    Получить список ролей, которыми бот может управлять

    Args:
        guild: Объект сервера
        role_ids: Список ID ролей для проверки

    Returns:
        Кортеж (список_управляемых_ролей, список_ID_неуправляемых_ролей)
    """
    bot_member = guild.me
    if not bot_member:
        return [], role_ids

    manageable = []
    unmanageable = []

    for role_id in role_ids:
        role = guild.get_role(role_id)

        if not role:
            logger.warning(f"Роль {role_id} не найдена на сервере {guild.name}")
            unmanageable.append(role_id)
            continue

        if await can_manage_role(bot_member, role):
            manageable.append(role)
        else:
            unmanageable.append(role_id)
            logger.debug(f"Роль {role.name} ({role_id}) не может быть управляема ботом")

    return manageable, unmanageable


async def check_channel_permissions(
    channel: discord.TextChannel,
    required_permissions: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Проверить права бота в конкретном канале

    Args:
        channel: Объект текстового канала
        required_permissions: Список требуемых прав (None = базовые права)

    Returns:
        Кортеж (все_права_есть, список_отсутствующих_прав)
    """
    if required_permissions is None:
        required_permissions = [
            'view_channel',
            'send_messages',
            'embed_links'
        ]

    try:
        bot_member = channel.guild.me
        if not bot_member:
            return False, required_permissions

        permissions = channel.permissions_for(bot_member)
        missing_permissions = []

        for perm_name in required_permissions:
            if not getattr(permissions, perm_name, False):
                missing_permissions.append(perm_name)

        has_all = len(missing_permissions) == 0

        if not has_all:
            logger.warning(
                f"В канале {channel.name} ({channel.guild.name}) "
                f"отсутствуют права: {', '.join(missing_permissions)}"
            )

        return has_all, missing_permissions

    except Exception as e:
        logger.error(
            f"Ошибка проверки прав в канале {channel.name}: {e}",
            exc_info=True
        )
        return False, required_permissions


def format_permissions_report(validation_results: Dict[int, List[str]]) -> str:
    """
    Форматировать отчет о проблемах с правами

    Args:
        validation_results: Результаты валидации от validate_all_servers

    Returns:
        Отформатированный текстовый отчет
    """
    if not validation_results:
        return "Все права в порядке на всех серверах."

    report_lines = ["Обнаружены проблемы с правами на серверах:", ""]

    for server_id, issues in validation_results.items():
        report_lines.append(f"Сервер ID {server_id}:")
        for issue in issues:
            report_lines.append(f"  - {issue}")
        report_lines.append("")

    return "\n".join(report_lines)
