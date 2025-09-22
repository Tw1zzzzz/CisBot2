#!/usr/bin/env python3
"""
🔒 Pre-Deploy Security Check Script
Проверяет безопасность перед деплоем CS2 Teammeet Bot

Этот скрипт выполняет комплексную проверку безопасности:
- Валидация токенов и API ключей
- Проверка компонентов безопасности
- Валидация конфигурации
- Проверка прав доступа к файлам
- Тестирование компонентов безопасности
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from bot.config import BOT_TOKEN, FACEIT_ANALYSER_API_KEY
    from bot.utils.security_validator import validate_token_strength, get_secure_logger
    from bot.database.operations import DatabaseManager
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что вы запускаете скрипт из корневой директории проекта")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class SecurityCheckResult:
    """Результат проверки безопасности"""
    check_name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    details: Optional[Dict] = None

class PreDeploySecurityChecker:
    """Класс для проверки безопасности перед деплоем"""
    
    def __init__(self):
        self.results: List[SecurityCheckResult] = []
        self.project_root = Path(__file__).parent.parent
        self.secure_logger = get_secure_logger(__name__)
    
    def add_result(self, check_name: str, status: str, message: str, details: Dict = None):
        """Добавляет результат проверки"""
        self.results.append(SecurityCheckResult(check_name, status, message, details))
        
        # Логируем результат
        if status == "PASS":
            self.secure_logger.info(f"✅ {check_name}: {message}")
        elif status == "WARN":
            self.secure_logger.warning(f"⚠️  {check_name}: {message}")
        else:
            self.secure_logger.error(f"❌ {check_name}: {message}")
    
    def check_environment_variables(self) -> bool:
        """Проверяет переменные окружения"""
        self.secure_logger.info("🔍 Проверяем переменные окружения...")
        
        # Проверяем наличие .env файла
        env_file = self.project_root / ".env"
        if not env_file.exists():
            self.add_result(
                "ENV_FILE", "FAIL", 
                "Файл .env не найден"
            )
            return False
        
        # Проверяем права доступа к .env файлу
        env_perms = oct(env_file.stat().st_mode)[-3:]
        if env_perms != "600":
            self.add_result(
                "ENV_PERMISSIONS", "WARN",
                f"Файл .env имеет неправильные права доступа: {env_perms} (должно быть 600)"
            )
        else:
            self.add_result(
                "ENV_PERMISSIONS", "PASS",
                "Права доступа к .env файлу корректны"
            )
        
        return True
    
    def check_tokens(self) -> bool:
        """Проверяет токены и API ключи"""
        self.secure_logger.info("🔑 Проверяем токены и API ключи...")
        
        all_valid = True
        
        # Проверяем BOT_TOKEN
        if not BOT_TOKEN:
            self.add_result(
                "BOT_TOKEN", "FAIL",
                "BOT_TOKEN не установлен"
            )
            all_valid = False
        elif len(BOT_TOKEN) < 20:
            self.add_result(
                "BOT_TOKEN", "FAIL",
                "BOT_TOKEN слишком короткий"
            )
            all_valid = False
        else:
            try:
                strength = validate_token_strength(BOT_TOKEN)
                if strength >= 70:
                    self.add_result(
                        "BOT_TOKEN", "PASS",
                        f"BOT_TOKEN валиден (сила: {strength}/100)"
                    )
                else:
                    self.add_result(
                        "BOT_TOKEN", "WARN",
                        f"BOT_TOKEN слабый (сила: {strength}/100)"
                    )
            except Exception as e:
                self.add_result(
                    "BOT_TOKEN", "FAIL",
                    f"Ошибка валидации BOT_TOKEN: {str(e)}"
                )
                all_valid = False
        
        # Проверяем FACEIT_API_KEY
        if not FACEIT_ANALYSER_API_KEY:
            self.add_result(
                "FACEIT_API_KEY", "FAIL",
                "FACEIT_ANALYSER_API_KEY не установлен"
            )
            all_valid = False
        elif len(FACEIT_ANALYSER_API_KEY) < 10:
            self.add_result(
                "FACEIT_API_KEY", "FAIL",
                "FACEIT_ANALYSER_API_KEY слишком короткий"
            )
            all_valid = False
        else:
            try:
                strength = validate_token_strength(FACEIT_ANALYSER_API_KEY)
                if strength >= 70:
                    self.add_result(
                        "FACEIT_API_KEY", "PASS",
                        f"FACEIT_API_KEY валиден (сила: {strength}/100)"
                    )
                else:
                    self.add_result(
                        "FACEIT_API_KEY", "WARN",
                        f"FACEIT_API_KEY слабый (сила: {strength}/100)"
                    )
            except Exception as e:
                self.add_result(
                    "FACEIT_API_KEY", "FAIL",
                    f"Ошибка валидации FACEIT_API_KEY: {str(e)}"
                )
                all_valid = False
        
        return all_valid
    
    def check_security_components(self) -> bool:
        """Проверяет наличие компонентов безопасности"""
        self.secure_logger.info("🛡️ Проверяем компоненты безопасности...")
        
        all_present = True
        
        # Проверяем Security Validator
        security_validator = self.project_root / "bot" / "utils" / "security_validator.py"
        if security_validator.exists():
            self.add_result(
                "SECURITY_VALIDATOR", "PASS",
                "Security Validator найден"
            )
        else:
            self.add_result(
                "SECURITY_VALIDATOR", "FAIL",
                "Security Validator не найден"
            )
            all_present = False
        
        # Проверяем Callback Security
        callback_security = self.project_root / "bot" / "utils" / "callback_security.py"
        if callback_security.exists():
            self.add_result(
                "CALLBACK_SECURITY", "PASS",
                "Callback Security найден"
            )
        else:
            self.add_result(
                "CALLBACK_SECURITY", "FAIL",
                "Callback Security не найден"
            )
            all_present = False
        
        # Проверяем Audit Trail в базе данных
        db_file = self.project_root / "data" / "bot.db"
        if db_file.exists():
            self.add_result(
                "DATABASE", "PASS",
                "База данных найдена"
            )
        else:
            self.add_result(
                "DATABASE", "WARN",
                "База данных не найдена (будет создана при первом запуске)"
            )
        
        return all_present
    
    async def check_database_security(self) -> bool:
        """Проверяет безопасность базы данных"""
        self.secure_logger.info("🗄️ Проверяем безопасность базы данных...")
        
        db_file = self.project_root / "data" / "bot.db"
        if not db_file.exists():
            self.add_result(
                "DATABASE_SECURITY", "WARN",
                "База данных не существует (будет создана при запуске)"
            )
            return True
        
        try:
            # Проверяем права доступа к базе данных
            db_perms = oct(db_file.stat().st_mode)[-3:]
            if db_perms in ["600", "644"]:
                self.add_result(
                    "DATABASE_PERMISSIONS", "PASS",
                    f"Права доступа к базе данных корректны: {db_perms}"
                )
            else:
                self.add_result(
                    "DATABASE_PERMISSIONS", "WARN",
                    f"Права доступа к базе данных: {db_perms} (рекомендуется 600 или 644)"
                )
            
            # Проверяем подключение к базе данных
            db = DatabaseManager(str(db_file))
            await db.initialize()
            
            # Проверяем наличие таблиц аудита
            tables = await db.get_all_tables()
            audit_tables = [t for t in tables if 'audit' in t.lower()]
            
            if audit_tables:
                self.add_result(
                    "AUDIT_TABLES", "PASS",
                    f"Таблицы аудита найдены: {', '.join(audit_tables)}"
                )
            else:
                self.add_result(
                    "AUDIT_TABLES", "WARN",
                    "Таблицы аудита не найдены (будут созданы при обновлении)"
                )
            
            await db.close()
            return True
            
        except Exception as e:
            self.add_result(
                "DATABASE_SECURITY", "FAIL",
                f"Ошибка проверки базы данных: {str(e)}"
            )
            return False
    
    def check_file_permissions(self) -> bool:
        """Проверяет права доступа к файлам"""
        self.secure_logger.info("📁 Проверяем права доступа к файлам...")
        
        critical_files = [
            (".env", "600"),
            ("data/bot.db", "600"),
            ("logs/", "755"),
            ("backups/", "755")
        ]
        
        all_correct = True
        
        for file_path, expected_perms in critical_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                actual_perms = oct(full_path.stat().st_mode)[-3:]
                if actual_perms == expected_perms:
                    self.add_result(
                        f"PERMISSIONS_{file_path.replace('/', '_')}", "PASS",
                        f"Права доступа к {file_path} корректны: {actual_perms}"
                    )
                else:
                    self.add_result(
                        f"PERMISSIONS_{file_path.replace('/', '_')}", "WARN",
                        f"Права доступа к {file_path}: {actual_perms} (рекомендуется {expected_perms})"
                    )
                    all_correct = False
        
        return all_correct
    
    def check_dependencies(self) -> bool:
        """Проверяет зависимости"""
        self.secure_logger.info("📦 Проверяем зависимости...")
        
        requirements_file = self.project_root / "requirements.txt"
        if not requirements_file.exists():
            self.add_result(
                "REQUIREMENTS", "FAIL",
                "Файл requirements.txt не найден"
            )
            return False
        
        # Проверяем критические зависимости
        critical_deps = [
            "python-telegram-bot",
            "aiosqlite",
            "aiohttp",
            "python-dotenv"
        ]
        
        try:
            with open(requirements_file, 'r') as f:
                requirements = f.read().lower()
            
            missing_deps = []
            for dep in critical_deps:
                if dep not in requirements:
                    missing_deps.append(dep)
            
            if missing_deps:
                self.add_result(
                    "CRITICAL_DEPS", "FAIL",
                    f"Отсутствуют критические зависимости: {', '.join(missing_deps)}"
                )
                return False
            else:
                self.add_result(
                    "CRITICAL_DEPS", "PASS",
                    "Все критические зависимости найдены"
                )
                return True
                
        except Exception as e:
            self.add_result(
                "REQUIREMENTS", "FAIL",
                f"Ошибка чтения requirements.txt: {str(e)}"
            )
            return False
    
    async def run_all_checks(self) -> bool:
        """Запускает все проверки безопасности"""
        self.secure_logger.info("🚀 Запускаем комплексную проверку безопасности...")
        
        checks = [
            ("Environment Variables", self.check_environment_variables),
            ("Tokens and API Keys", self.check_tokens),
            ("Security Components", self.check_security_components),
            ("Database Security", self.check_database_security),
            ("File Permissions", self.check_file_permissions),
            ("Dependencies", self.check_dependencies)
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                
                if not result:
                    all_passed = False
                    
            except Exception as e:
                self.add_result(
                    check_name.upper().replace(" ", "_"), "FAIL",
                    f"Ошибка выполнения проверки: {str(e)}"
                )
                all_passed = False
        
        return all_passed
    
    def generate_report(self) -> str:
        """Генерирует отчет о проверке безопасности"""
        report = []
        report.append("🔒 ОТЧЕТ О ПРОВЕРКЕ БЕЗОПАСНОСТИ")
        report.append("=" * 50)
        report.append("")
        
        # Группируем результаты по статусу
        passed = [r for r in self.results if r.status == "PASS"]
        warnings = [r for r in self.results if r.status == "WARN"]
        failures = [r for r in self.results if r.status == "FAIL"]
        
        # Статистика
        report.append(f"📊 СТАТИСТИКА:")
        report.append(f"  ✅ Пройдено: {len(passed)}")
        report.append(f"  ⚠️  Предупреждения: {len(warnings)}")
        report.append(f"  ❌ Ошибки: {len(failures)}")
        report.append("")
        
        # Детальные результаты
        if failures:
            report.append("❌ КРИТИЧЕСКИЕ ОШИБКИ:")
            for result in failures:
                report.append(f"  • {result.check_name}: {result.message}")
            report.append("")
        
        if warnings:
            report.append("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
            for result in warnings:
                report.append(f"  • {result.check_name}: {result.message}")
            report.append("")
        
        if passed:
            report.append("✅ УСПЕШНЫЕ ПРОВЕРКИ:")
            for result in passed:
                report.append(f"  • {result.check_name}: {result.message}")
            report.append("")
        
        # Общий статус
        if failures:
            report.append("🚨 СТАТУС: НЕ ПРОЙДЕНО - Критические ошибки обнаружены")
            report.append("   Исправьте ошибки перед деплоем!")
        elif warnings:
            report.append("⚠️  СТАТУС: ПРОЙДЕНО С ПРЕДУПРЕЖДЕНИЯМИ")
            report.append("   Рекомендуется исправить предупреждения")
        else:
            report.append("✅ СТАТУС: ПРОЙДЕНО - Все проверки успешны")
            report.append("   Безопасность готова к деплою!")
        
        return "\n".join(report)

async def main():
    """Основная функция"""
    print("🔒 Pre-Deploy Security Check для CS2 Teammeet Bot")
    print("=" * 60)
    print("")
    
    checker = PreDeploySecurityChecker()
    
    try:
        # Запускаем все проверки
        all_passed = await checker.run_all_checks()
        
        # Генерируем отчет
        report = checker.generate_report()
        print(report)
        
        # Сохраняем отчет в файл
        report_file = Path(__file__).parent.parent / "logs" / "security_check_report.txt"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 Отчет сохранен в: {report_file}")
        
        # Возвращаем код выхода
        if all_passed:
            print("\n🎉 Все проверки безопасности пройдены!")
            return 0
        else:
            print("\n❌ Обнаружены проблемы безопасности!")
            return 1
            
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
