#!/usr/bin/env python3
"""
Безопасный запуск бота с проверкой конфликтов экземпляров
"""
import os
import sys
import time
import signal
import subprocess
import psutil
from pathlib import Path

def kill_existing_python_processes():
    """Завершает все существующие процессы Python"""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python.exe' or proc.info['name'] == 'python':
                # Проверяем, что это наш бот
                cmdline = proc.info.get('cmdline', [])
                if any('bot' in str(arg).lower() for arg in cmdline):
                    print(f"Завершаем процесс Python (PID: {proc.info['pid']}): {' '.join(cmdline)}")
                    proc.kill()
                    killed_count += 1
                    time.sleep(0.5)  # Небольшая пауза между завершениями
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if killed_count > 0:
        print(f"Завершено {killed_count} процессов Python")
        time.sleep(2)  # Даем время процессам завершиться
    else:
        print("Активных процессов Python не найдено")

def check_port_usage():
    """Проверяет использование портов"""
    try:
        # Проверяем, не занят ли порт 443 (HTTPS) или другие системные порты
        import socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(1)
        result = test_socket.connect_ex(('localhost', 443))
        test_socket.close()
        if result == 0:
            print("⚠️  Порт 443 занят - возможны конфликты с Telegram API")
    except Exception as e:
        print(f"Ошибка проверки портов: {e}")

def main():
    """Основная функция запуска"""
    print("🚀 Безопасный запуск CIS FINDER Bot")
    print("=" * 50)
    
    # Проверяем наличие файла .env
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден!")
        print("Создайте файл .env с необходимыми переменными окружения")
        sys.exit(1)
    
    # Проверяем наличие основного файла бота
    if not os.path.exists('bot/main.py'):
        print("❌ Файл bot/main.py не найден!")
        print("Убедитесь, что вы находитесь в правильной директории")
        sys.exit(1)
    
    # Завершаем существующие процессы
    print("🔍 Проверка существующих процессов...")
    kill_existing_python_processes()
    
    # Проверяем порты
    print("🔍 Проверка портов...")
    check_port_usage()
    
    # Проверяем зависимости
    print("🔍 Проверка зависимостей...")
    try:
        import telegram
        import aiosqlite
        import httpx
        print("✅ Основные зависимости найдены")
    except ImportError as e:
        print(f"❌ Отсутствует зависимость: {e}")
        print("Установите зависимости: pip install -r requirements.txt")
        sys.exit(1)
    
    # Запускаем бота
    print("🚀 Запуск бота...")
    print("=" * 50)
    
    try:
        # Импортируем и запускаем бота
        from bot.main import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        print("\n⏹️  Получен сигнал остановки")
        print("Завершение работы...")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
