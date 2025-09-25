#!/usr/bin/env python3
"""
Тестовый скрипт для проверки аргументов
"""
import sys

print("🔍 Тест аргументов:")
print(f"Количество аргументов: {len(sys.argv)}")
print(f"sys.argv: {sys.argv}")

for i, arg in enumerate(sys.argv):
    print(f"  sys.argv[{i}] = '{arg}' (длина: {len(arg)}, байты: {arg.encode('utf-8')})")

if len(sys.argv) > 1:
    try:
        user_id = int(sys.argv[1])
        print(f"✅ User ID успешно преобразован: {user_id}")
    except ValueError as e:
        print(f"❌ Ошибка преобразования: {e}")
        print(f"   Строка: '{sys.argv[1]}'")
        print(f"   Байты: {sys.argv[1].encode('utf-8')}")
else:
    print("❌ Аргументы не переданы")
