#!/usr/bin/env python3
"""
Простой тест для проверки загрузки конфигурации
"""
import os
from dotenv import load_dotenv

print("=== Тест загрузки конфигурации ===")

# Проверим текущие переменные
print("1. BOT_TOKEN до load_dotenv:", repr(os.getenv('BOT_TOKEN')))

# Загружаем .env
result = load_dotenv()
print("2. load_dotenv() результат:", result)

# Проверим после загрузки
print("3. BOT_TOKEN после load_dotenv:", repr(os.getenv('BOT_TOKEN')))

# Проверим файл .env существует ли
import os.path
print("4. Файл .env существует:", os.path.exists('.env'))

# Попробуем загрузить конфигурацию бота
try:
    from bot.config import Config
    print("5. Config.BOT_TOKEN:", repr(Config.BOT_TOKEN))
    print("6. Config загружен успешно!")
except Exception as e:
    print("5. Ошибка загрузки Config:", e)

# Попробуем создать простого бота
try:
    from bot.main import CS2TeammeetBot
    print("7. Попытка создать бота...")
    # bot = CS2TeammeetBot()
    print("7. Импорт CS2TeammeetBot успешен!")
except Exception as e:
    print("7. Ошибка создания бота:", e) 