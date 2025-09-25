#!/usr/bin/env python3
"""
Скрипт для назначения первого модератора
Использование: python scripts/setup_first_moderator.py <user_id> [role]
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Проверяем зависимости
try:
    import aiosqlite
    from bot.database.operations import DatabaseManager
    from bot.config import Config
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("")
    print("🔧 Решение:")
    print("1. Установите зависимости:")
    print("   python3 -m pip install -r requirements.txt")
    print("")
    print("2. Или запустите скрипт установки:")
    print("   bash scripts/install_dependencies.sh")
    print("")
    print("3. Проверьте, что вы находитесь в корневой директории проекта")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def setup_first_moderator(user_id: int, role: str = 'super_admin'):
    """Назначает первого модератора"""
    
    # Инициализируем базу данных
    db_manager = DatabaseManager()
    await db_manager.init_database()
    
    try:
        # Проверяем, есть ли уже модераторы
        existing_moderators = await db_manager.get_all_moderators()
        
        if existing_moderators:
            logger.warning(f"В системе уже есть {len(existing_moderators)} модераторов:")
            for mod in existing_moderators:
                logger.info(f"  - User ID: {mod.user_id}, Role: {mod.role}, Active: {mod.is_active}")
            
            response = input("Продолжить добавление нового модератора? (y/N): ")
            if response.lower() != 'y':
                logger.info("Операция отменена")
                return False
        
        # Проверяем, существует ли пользователь
        user = await db_manager.get_user(user_id)
        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден в системе")
            logger.info("Пользователь должен сначала запустить бота командой /start")
            return False
        
        # Проверяем, не является ли уже модератором
        existing_moderator = await db_manager.get_moderator(user_id)
        if existing_moderator:
            logger.warning(f"Пользователь {user_id} уже является модератором (роль: {existing_moderator.role})")
            response = input("Обновить роль? (y/N): ")
            if response.lower() != 'y':
                logger.info("Операция отменена")
                return False
        
        # Добавляем модератора
        success = await db_manager.add_moderator(user_id, role, appointed_by=None)
        
        if success:
            logger.info(f"✅ Модератор успешно назначен!")
            logger.info(f"   User ID: {user_id}")
            logger.info(f"   Роль: {role}")
            logger.info(f"   Имя: {user.first_name}")
            if user.username:
                logger.info(f"   Username: @{user.username}")
            
            # Показываем права
            from bot.database.models import Moderator
            temp_moderator = Moderator(user_id=user_id, role=role)
            permissions = temp_moderator.get_default_permissions()
            
            logger.info("   Права:")
            for perm, value in permissions.items():
                status = "✅" if value else "❌"
                perm_name = {
                    'moderate_profiles': 'Модерация профилей',
                    'manage_moderators': 'Управление модераторами',
                    'view_stats': 'Просмотр статистики',
                    'manage_users': 'Управление пользователями',
                    'access_logs': 'Доступ к логам'
                }.get(perm, perm)
                logger.info(f"     {status} {perm_name}")
            
            return True
        else:
            logger.error("❌ Ошибка при назначении модератора")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False
    finally:
        await db_manager.close()

def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python scripts/setup_first_moderator.py <user_id> [role]")
        print("")
        print("Роли:")
        print("  super_admin - Полные права (по умолчанию)")
        print("  admin       - Расширенные права")
        print("  moderator   - Базовые права модерации")
        print("")
        print("Примеры:")
        print("  python scripts/setup_first_moderator.py 123456789")
        print("  python scripts/setup_first_moderator.py 123456789 admin")
        sys.exit(1)
    
    try:
        user_id = int(sys.argv[1])
        role = sys.argv[2] if len(sys.argv) > 2 else 'super_admin'
        
        if role not in ['moderator', 'admin', 'super_admin']:
            print(f"❌ Неверная роль: {role}")
            print("Доступные роли: moderator, admin, super_admin")
            sys.exit(1)
        
        print(f"🎯 Назначение модератора...")
        print(f"   User ID: {user_id}")
        print(f"   Роль: {role}")
        print("")
        
        # Запускаем асинхронную функцию
        success = asyncio.run(setup_first_moderator(user_id, role))
        
        if success:
            print("")
            print("🎉 Модератор успешно назначен!")
            print("")
            print("📋 Следующие шаги:")
            print("1. Пользователь должен запустить бота командой /start")
            print("2. В главном меню появится кнопка '👨‍💼 Модерация'")
            print("3. Модератор может использовать команды:")
            print("   - /add_moderator <user_id> <role> - добавить модератора")
            print("   - /remove_moderator <user_id> - удалить модератора")
            print("   - /list_moderators - список модераторов")
            print("   - /security_stats - статистика безопасности")
        else:
            print("")
            print("❌ Не удалось назначить модератора")
            sys.exit(1)
            
    except ValueError:
        print(f"❌ Неверный User ID: {sys.argv[1]}")
        print("User ID должен быть числом")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Операция отменена пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
