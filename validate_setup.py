"""
Скрипт для проверки корректности настройки бота перед запуском
"""

import os
import sys
import json
import yaml
from pathlib import Path
from typing import List, Tuple

# Цвета для вывода в консоль
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Печать заголовка"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")

def print_success(text: str):
    """Печать успеха"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Печать предупреждения"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")

def print_error(text: str):
    """Печать ошибки"""
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")

def check_python_version() -> bool:
    """Проверка версии Python"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print_success(f"Python версия: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python версия слишком старая: {version.major}.{version.minor}.{version.micro}")
        print_error("Требуется Python 3.9 или выше")
        return False

def check_dependencies() -> Tuple[bool, List[str]]:
    """Проверка установленных зависимостей"""
    required = [
        'discord',
        'dotenv',
        'yaml',
        'aiosqlite'
    ]

    missing = []
    for module in required:
        try:
            __import__(module)
            print_success(f"Модуль {module} установлен")
        except ImportError:
            print_error(f"Модуль {module} НЕ установлен")
            missing.append(module)

    return len(missing) == 0, missing

def check_env_file() -> bool:
    """Проверка .env файла"""
    if not os.path.exists('.env'):
        print_error(".env файл не найден")
        print_warning("Создайте .env файл на основе .env.example")
        return False

    print_success(".env файл найден")

    # Проверяем наличие токена
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'DISCORD_BOT_TOKEN=' in content and 'your_token_here' not in content:
            print_success("DISCORD_BOT_TOKEN настроен")
            return True
        else:
            print_error("DISCORD_BOT_TOKEN не настроен или использует значение по умолчанию")
            return False

def check_config_yaml() -> bool:
    """Проверка config.yaml"""
    config_path = Path('config/config.yaml')

    if not config_path.exists():
        print_error("config/config.yaml не найден")
        return False

    print_success("config.yaml найден")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Проверка обязательных полей
        errors = []

        if 'bot' not in config:
            errors.append("Отсутствует секция 'bot'")
        else:
            main_server_id = config['bot'].get('main_server_id')
            if not main_server_id or main_server_id == 123456789012345678:
                errors.append("main_server_id не настроен (использует значение по умолчанию)")
            else:
                print_success(f"main_server_id настроен: {main_server_id}")

        if 'sync' not in config:
            errors.append("Отсутствует секция 'sync'")
        else:
            print_success("Секция 'sync' настроена")

        if 'database' not in config:
            errors.append("Отсутствует секция 'database'")
        else:
            print_success("Секция 'database' настроена")

        if errors:
            for error in errors:
                print_error(error)
            return False

        return True

    except yaml.YAMLError as e:
        print_error(f"Ошибка парсинга YAML: {e}")
        return False

def check_role_mappings() -> bool:
    """Проверка role_mappings.json"""
    mappings_path = Path('config/role_mappings.json')

    if not mappings_path.exists():
        print_error("config/role_mappings.json не найден")
        return False

    print_success("role_mappings.json найден")

    try:
        with open(mappings_path, 'r', encoding='utf-8') as f:
            mappings = json.load(f)

        if 'mappings' not in mappings:
            print_error("Отсутствует ключ 'mappings'")
            return False

        mapping_list = mappings['mappings']

        if len(mapping_list) == 0:
            print_warning("Нет настроенных маппингов ролей")
            print_warning("Добавьте хотя бы один маппинг для работы бота")
            return True

        # Проверка каждого маппинга
        default_ids = [123456789012345678, 987654321098765432, 111222333444555666, 777888999000111222]
        has_defaults = False

        for i, mapping in enumerate(mapping_list):
            required_fields = ['id', 'source_server_id', 'source_role_id', 'target_server_id', 'target_role_id']
            missing_fields = [field for field in required_fields if field not in mapping]

            if missing_fields:
                print_error(f"Маппинг #{i+1}: отсутствуют поля {missing_fields}")
                return False

            # Проверка на значения по умолчанию
            if any(mapping.get(field) in default_ids for field in ['source_server_id', 'source_role_id', 'target_role_id']):
                has_defaults = True

        if has_defaults:
            print_warning(f"Найдено {len(mapping_list)} маппингов, но некоторые используют ID по умолчанию")
            print_warning("Замените ID на реальные из ваших серверов")
        else:
            print_success(f"Настроено {len(mapping_list)} маппингов ролей")

        return True

    except json.JSONDecodeError as e:
        print_error(f"Ошибка парсинга JSON: {e}")
        return False

def check_directories() -> bool:
    """Проверка необходимых директорий"""
    required_dirs = ['data', 'logs', 'config', 'bot']

    all_exist = True
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print_success(f"Директория '{dir_name}' существует")
        else:
            print_error(f"Директория '{dir_name}' НЕ существует")
            all_exist = False

    return all_exist

def check_bot_structure() -> bool:
    """Проверка структуры bot модулей"""
    required_modules = [
        'bot/main.py',
        'bot/config.py',
        'bot/cogs/sync_button.py',
        'bot/cogs/role_monitor.py',
        'bot/cogs/admin_commands.py',
        'bot/cogs/stats_commands.py',
        'bot/core/sync_engine.py',
        'bot/core/role_mapper.py',
        'bot/core/permissions.py',
        'bot/database/models.py',
        'bot/database/operations.py',
        'bot/ui/buttons.py',
        'bot/ui/embeds.py',
        'bot/utils/logger.py',
        'bot/utils/errors.py',
        'bot/utils/validators.py'
    ]

    all_exist = True
    for module_path in required_modules:
        if os.path.exists(module_path):
            print_success(f"{module_path}")
        else:
            print_error(f"{module_path} НЕ найден")
            all_exist = False

    return all_exist

def main():
    """Основная функция проверки"""
    print_header("ПРОВЕРКА КОНФИГУРАЦИИ DISCORD БОТА")

    results = {}

    # Проверка Python версии
    print(f"\n{Colors.BOLD}1. Проверка Python версии{Colors.ENDC}")
    results['python'] = check_python_version()

    # Проверка зависимостей
    print(f"\n{Colors.BOLD}2. Проверка зависимостей{Colors.ENDC}")
    deps_ok, missing = check_dependencies()
    results['dependencies'] = deps_ok
    if not deps_ok:
        print_warning(f"Установите недостающие модули: pip install -r requirements.txt")

    # Проверка директорий
    print(f"\n{Colors.BOLD}3. Проверка директорий{Colors.ENDC}")
    results['directories'] = check_directories()

    # Проверка структуры бота
    print(f"\n{Colors.BOLD}4. Проверка модулей бота{Colors.ENDC}")
    results['bot_structure'] = check_bot_structure()

    # Проверка .env
    print(f"\n{Colors.BOLD}5. Проверка .env файла{Colors.ENDC}")
    results['env'] = check_env_file()

    # Проверка config.yaml
    print(f"\n{Colors.BOLD}6. Проверка config.yaml{Colors.ENDC}")
    results['config'] = check_config_yaml()

    # Проверка role_mappings.json
    print(f"\n{Colors.BOLD}7. Проверка role_mappings.json{Colors.ENDC}")
    results['mappings'] = check_role_mappings()

    # Итоговый отчет
    print_header("РЕЗУЛЬТАТЫ ПРОВЕРКИ")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ({passed}/{total}){Colors.ENDC}\n")
        print(f"{Colors.GREEN}Бот готов к запуску! Выполните: python run.py{Colors.ENDC}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ ОБНАРУЖЕНЫ ПРОБЛЕМЫ ({passed}/{total} пройдено){Colors.ENDC}\n")
        print(f"{Colors.YELLOW}Исправьте ошибки выше перед запуском бота{Colors.ENDC}")
        print(f"{Colors.YELLOW}Смотрите SETUP.md для подробных инструкций{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Проверка прервана пользователем{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Неожиданная ошибка: {e}{Colors.ENDC}")
        sys.exit(1)
