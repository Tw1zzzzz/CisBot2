#!/usr/bin/env python3
"""
Скрипт для проверки зависимостей
"""
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Проверяет версию Python"""
    version = sys.version_info
    print(f"🐍 Python версия: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Требуется Python 3.8 или выше")
        return False
    else:
        print("✅ Версия Python подходит")
        return True

def check_module(module_name, import_name=None):
    """Проверяет установлен ли модуль"""
    if import_name is None:
        import_name = module_name
    
    try:
        __import__(import_name)
        print(f"✅ {module_name} - установлен")
        return True
    except ImportError:
        print(f"❌ {module_name} - НЕ установлен")
        return False

def install_requirements():
    """Устанавливает зависимости из requirements.txt"""
    print("\n🔧 Попытка установки зависимостей...")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], capture_output=True, text=True, check=True)
        
        print("✅ Зависимости успешно установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки: {e}")
        print(f"Вывод: {e.stdout}")
        print(f"Ошибки: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ Файл requirements.txt не найден")
        return False

def main():
    """Основная функция"""
    print("🔍 Проверка зависимостей CIS FINDER Bot")
    print("=" * 50)
    
    # Проверяем версию Python
    if not check_python_version():
        sys.exit(1)
    
    # Проверяем pip
    try:
        import pip
        print("✅ pip - установлен")
    except ImportError:
        print("❌ pip - НЕ установлен")
        print("Установите pip: https://pip.pypa.io/en/stable/installation/")
        sys.exit(1)
    
    # Список модулей для проверки
    modules = [
        ("python-telegram-bot", "telegram"),
        ("aiosqlite", "aiosqlite"),
        ("aiohttp", "aiohttp"),
        ("python-dotenv", "dotenv"),
        ("scipy", "scipy"),
        ("pandas", "pandas")
    ]
    
    print("\n📦 Проверка модулей:")
    missing_modules = []
    
    for module_name, import_name in modules:
        if not check_module(module_name, import_name):
            missing_modules.append(module_name)
    
    if missing_modules:
        print(f"\n❌ Отсутствуют модули: {', '.join(missing_modules)}")
        
        # Предлагаем установку
        response = input("\n🔧 Установить отсутствующие зависимости? (y/N): ")
        if response.lower() == 'y':
            if install_requirements():
                print("\n🔄 Повторная проверка...")
                all_ok = True
                for module_name, import_name in modules:
                    if not check_module(module_name, import_name):
                        all_ok = False
                
                if all_ok:
                    print("\n🎉 Все зависимости установлены!")
                else:
                    print("\n❌ Некоторые зависимости все еще отсутствуют")
                    sys.exit(1)
            else:
                print("\n❌ Не удалось установить зависимости")
                sys.exit(1)
        else:
            print("\n📋 Для установки зависимостей выполните:")
            print("   python3 -m pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("\n🎉 Все зависимости установлены!")
        print("\n✅ Система готова к работе!")

if __name__ == "__main__":
    main()
