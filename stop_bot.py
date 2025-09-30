#!/usr/bin/env python3
"""
Безопасная остановка бота
"""
import os
import sys
import time
import signal
import psutil
from pathlib import Path

def stop_bot_processes():
    """Останавливает все процессы бота"""
    stopped_count = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] in ['python.exe', 'python']:
                cmdline = proc.info.get('cmdline', [])
                cmdline_str = ' '.join(cmdline)
                
                # Проверяем, что это наш бот
                if any(keyword in cmdline_str.lower() for keyword in ['bot', 'main.py', 'run_bot.py']):
                    print(f"STOP: Останавливаем процесс (PID: {proc.info['pid']}): {cmdline_str}")
                    
                    # Сначала пытаемся мягко завершить
                    proc.terminate()
                    time.sleep(2)
                    
                    # Если не завершился, принудительно убиваем
                    if proc.is_running():
                        proc.kill()
                        print(f"   Принудительно завершен")
                    
                    stopped_count += 1
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return stopped_count

def main():
    """Основная функция остановки"""
    print("STOP: Остановка CIS FINDER Bot")
    print("=" * 40)
    
    # Останавливаем процессы
    stopped_count = stop_bot_processes()
    
    if stopped_count > 0:
        print(f"OK: Остановлено {stopped_count} процессов")
        time.sleep(1)
        
        # Проверяем, что все остановилось
        remaining = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] in ['python.exe', 'python']:
                    cmdline = proc.info.get('cmdline', [])
                    cmdline_str = ' '.join(cmdline)
                    if any(keyword in cmdline_str.lower() for keyword in ['bot', 'main.py', 'run_bot.py']):
                        remaining += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if remaining > 0:
            print(f"WARNING: Осталось {remaining} процессов - попробуйте запустить скрипт еще раз")
        else:
            print("OK: Все процессы бота остановлены")
    else:
        print("INFO: Активных процессов бота не найдено")

if __name__ == "__main__":
    main()
