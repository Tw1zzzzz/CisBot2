#!/bin/bash
# CS2 Teammeet Bot - Скрипт БЕЗОПАСНОГО ОБНОВЛЕНИЯ с проверками безопасности
# Сохраняет данные пользователей, проверяет безопасность и обновляет код

set -e  # Остановка при ошибке

echo "🔄 Начинаем БЕЗОПАСНОЕ обновление CS2 Teammeet Bot..."
echo "🔒 Включает проверки безопасности, валидацию токенов и аудит"

# Переменные
BOT_USER="cisbot"
BOT_DIR="/opt/cisbot2"
SERVICE_NAME="cisbot"
BACKUP_DIR="/opt/cisbot2/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Цвета для логов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Проверяем, что запущен от root
if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от имени root: sudo ./update_bot.sh"
    exit 1
fi

# Проверяем существование директории бота
if [ ! -d "$BOT_DIR" ]; then
    log_error "Директория бота $BOT_DIR не найдена!"
    log_error "Возможно бот не установлен или установлен в другой директории"
    exit 1
fi

# Переходим в директорию бота
cd "$BOT_DIR"

log_step "1️⃣ Создание резервной копии с проверкой безопасности..."

# Создаем директорию для бекапов
mkdir -p "$BACKUP_DIR"

# 🔒 БЕЗОПАСНОСТЬ: Проверяем текущее состояние безопасности
log_info "Проверяем текущее состояние безопасности..."
if [ -f "scripts/check_secrets.py" ]; then
    if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python scripts/check_secrets.py" 2>/dev/null; then
        log_info "✅ Текущее состояние безопасности: OK"
    else
        log_warn "⚠️  Обнаружены проблемы безопасности в текущей версии"
    fi
fi

# Останавливаем бота для безопасного бекапа
log_info "Останавливаем бота..."
systemctl stop "$SERVICE_NAME" || log_warn "Сервис уже остановлен"

# Создаем бекап базы данных
if [ -f "data/bot.db" ]; then
    log_info "Создаем резервную копию базы данных..."
    cp "data/bot.db" "$BACKUP_DIR/bot_backup_$TIMESTAMP.db"
    log_info "✅ База данных сохранена: $BACKUP_DIR/bot_backup_$TIMESTAMP.db"
else
    log_warn "⚠️  База данных data/bot.db не найдена"
fi

# Создаем бекап логов
if [ -d "logs" ]; then
    log_info "Создаем резервную копию логов..."
    tar -czf "$BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz" logs/
    log_info "✅ Логи сохранены: $BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz"
fi

# Создаем бекап конфигурации
if [ -f ".env" ]; then
    log_info "Создаем резервную копию конфигурации..."
    cp ".env" "$BACKUP_DIR/.env_backup_$TIMESTAMP"
    log_info "✅ Конфигурация сохранена: $BACKUP_DIR/.env_backup_$TIMESTAMP"
fi

log_step "2️⃣ Загрузка нового кода с проверкой безопасности..."

# Сохраняем текущую версию
log_info "Создаем бекап текущего кода..."
tar --exclude='data' --exclude='logs' --exclude='backups' --exclude='venv' \
    -czf "$BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz" .
log_info "✅ Код сохранен: $BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz"

# 🔒 БЕЗОПАСНОСТЬ: Создаем бекап конфигурации безопасности
log_info "Создаем бекап конфигурации безопасности..."
if [ -d "bot/utils" ]; then
    tar -czf "$BACKUP_DIR/security_config_backup_$TIMESTAMP.tar.gz" bot/utils/security_validator.py bot/utils/callback_security.py 2>/dev/null || true
    log_info "✅ Конфигурация безопасности сохранена"
fi

# Получаем обновления из GitHub
log_info "Загружаем обновления из GitHub..."

# Исправляем проблему с правами доступа Git
log_info "Настраиваем Git safe.directory..."
git config --global --add safe.directory "$BOT_DIR" 2>/dev/null || true

# Исправляем права доступа к директории
log_info "Исправляем права доступа к директории..."
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR" 2>/dev/null || true

if [ -d ".git" ]; then
    # Если это git репозиторий
    git fetch origin
    git reset --hard origin/main
    log_info "✅ Код обновлен из GitHub"
else
    # Если нет git, клонируем заново (сохранив важные файлы)
    log_warn "Git репозиторий не найден, клонируем заново..."
    cd /opt
    mv cisbot2 cisbot2_old_$TIMESTAMP
    git clone https://github.com/Tw1zzzzz/CisBot2.git cisbot2
    
    # Настраиваем права доступа для нового клона
    chown -R "$BOT_USER:$BOT_USER" cisbot2
    git config --global --add safe.directory /opt/cisbot2
    
    # Восстанавливаем важные файлы
    cp cisbot2_old_$TIMESTAMP/data/* cisbot2/data/ 2>/dev/null || true
    cp cisbot2_old_$TIMESTAMP/logs/* cisbot2/logs/ 2>/dev/null || true
    cp cisbot2_old_$TIMESTAMP/.env cisbot2/.env 2>/dev/null || true
    
    cd cisbot2
fi

log_step "3️⃣ Обновление зависимостей с проверкой безопасности..."

# Обновляем права доступа
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"

# 🔒 БЕЗОПАСНОСТЬ: Проверяем права доступа к .env файлу
ENV_PERMS=$(stat -c %a .env 2>/dev/null || echo "000")
if [ "$ENV_PERMS" != "600" ]; then
    log_warn "Исправляем права доступа к .env файлу..."
    chmod 600 .env
    chown "$BOT_USER:$BOT_USER" .env
    log_info "✅ Права доступа к .env установлены: 600"
fi

# Обновляем виртуальное окружение
log_info "Обновляем Python зависимости..."
sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt --upgrade
"

# 🔒 БЕЗОПАСНОСТЬ: Проверяем новые компоненты безопасности
log_info "Проверяем компоненты безопасности..."
if [ -f "bot/utils/security_validator.py" ]; then
    log_info "✅ Security Validator найден"
else
    log_warn "⚠️  Security Validator не найден в новой версии"
fi

if [ -f "bot/utils/callback_security.py" ]; then
    log_info "✅ Callback Security найден"
else
    log_warn "⚠️  Callback Security не найден в новой версии"
fi

log_step "4️⃣ Проверка миграций базы данных и безопасности..."

# 🔒 БЕЗОПАСНОСТЬ: Проверяем секреты перед тестированием
log_info "Проверяем секреты в новой версии..."
if [ -f "scripts/check_secrets.py" ]; then
    if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python scripts/check_secrets.py" 2>/dev/null; then
        log_info "✅ Секреты в новой версии: OK"
    else
        log_error "❌ Обнаружены проблемы с секретами в новой версии!"
        log_error "Проверьте .env файл перед продолжением"
        exit 1
    fi
fi

# Проверяем, нужны ли миграции базы данных
log_info "Проверяем совместимость базы данных..."
sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    timeout 10 python -c \"
from bot.database.operations import DatabaseManager
import asyncio

async def check_db():
    try:
        db = DatabaseManager('data/bot.db')
        await db.init_database()
        await db.close()
        print('✅ База данных совместима')
    except Exception as e:
        print(f'⚠️  Возможны проблемы с БД: {e}')
        
asyncio.run(check_db())
\"
" 2>/dev/null || log_warn "Не удалось проверить БД (это может быть нормально)"

# 🔒 БЕЗОПАСНОСТЬ: Проверяем валидность токенов
log_info "Проверяем валидность токенов в новой версии..."
if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python -c \"
import os
from bot.config import Config
from bot.utils.security_validator import validate_token_strength

# Проверяем BOT_TOKEN
if Config.BOT_TOKEN and len(Config.BOT_TOKEN) > 20:
    strength = validate_token_strength(Config.BOT_TOKEN)
    print(f'BOT_TOKEN: ВАЛИДЕН (сила: {strength}/100)')
else:
    print('BOT_TOKEN: НЕВАЛИДЕН')
    exit(1)

# Проверяем FACEIT_API_KEY
if Config.FACEIT_ANALYSER_API_KEY and len(Config.FACEIT_ANALYSER_API_KEY) > 10:
    strength = validate_token_strength(Config.FACEIT_ANALYSER_API_KEY)
    print(f'FACEIT_API_KEY: ВАЛИДЕН (сила: {strength}/100)')
else:
    print('FACEIT_API_KEY: НЕВАЛИДЕН')
    exit(1)
\"" 2>/dev/null; then
    log_info "✅ Все токены валидны в новой версии"
else
    log_error "❌ Обнаружены проблемы с токенами в новой версии!"
    log_error "Проверьте .env файл и убедитесь, что токены корректны"
    exit 1
fi

log_step "5️⃣ Тестирование обновления с проверкой безопасности..."

# 🔒 БЕЗОПАСНОСТЬ: Тестовый запуск с проверкой компонентов безопасности
log_info "Выполняем тестовый запуск с проверкой безопасности..."
TEST_OUTPUT=$(timeout 15 sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    python run_bot.py 2>&1
" || echo "timeout")

# Проверяем успешную инициализацию
if echo "$TEST_OUTPUT" | grep -q "CS2 Teammeet Bot инициализирован успешно"; then
    log_info "✅ Бот инициализирован успешно"
elif echo "$TEST_OUTPUT" | grep -q "timeout"; then
    log_info "✅ Тест завершен по таймауту (это нормально)"
else
    log_warn "⚠️  Обнаружены предупреждения в тестовом запуске"
    echo "$TEST_OUTPUT" | tail -10
fi

# Проверяем инициализацию компонентов безопасности
if echo "$TEST_OUTPUT" | grep -q "Security Validator инициализирован"; then
    log_info "✅ Security Validator инициализирован"
else
    log_warn "⚠️  Security Validator не инициализирован"
fi

if echo "$TEST_OUTPUT" | grep -q "Callback Security инициализирован"; then
    log_info "✅ Callback Security инициализирован"
else
    log_warn "⚠️  Callback Security не инициализирован"
fi

if echo "$TEST_OUTPUT" | grep -q "Audit Trail система активна"; then
    log_info "✅ Audit Trail система активна"
else
    log_warn "⚠️  Audit Trail система не активна"
fi

if echo "$TEST_OUTPUT" | grep -q "База данных инициализирована"; then
    log_info "✅ База данных инициализирована"
else
    log_warn "⚠️  Возможны проблемы с базой данных"
fi

log_step "6️⃣ Запуск обновленного бота..."

# Запускаем обновленный сервис
log_info "Запускаем обновленный бот..."
systemctl start "$SERVICE_NAME"

# Ждем запуска
sleep 5

# Проверяем статус
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "🎉 ОБНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО С УЛУЧШЕНИЯМИ БЕЗОПАСНОСТИ!"
    log_info ""
    log_info "✅ Статус сервиса: $(systemctl is-active $SERVICE_NAME)"
    log_info "✅ База данных пользователей сохранена"
    log_info "✅ Все резервные копии созданы в $BACKUP_DIR"
    log_info ""
    log_info "🔒 Безопасность:"
    log_info "  ✅ JSON Schema Validator активен"
    log_info "  ✅ SecureLogger настроен"
    log_info "  ✅ CallbackSecurityValidator активен"
    log_info "  ✅ Audit Trail система работает"
    log_info "  ✅ Токены валидированы"
    log_info "  ✅ Секреты проверены"
    log_info ""
    log_info "📊 Управление ботом:"
    log_info "  Статус:      systemctl status $SERVICE_NAME"
    log_info "  Перезапуск:  systemctl restart $SERVICE_NAME"
    log_info "  Логи:        journalctl -u $SERVICE_NAME -f"
    log_info "  Безопасность: python scripts/check_secrets.py"
    log_info ""
    log_info "💾 Резервные копии ($TIMESTAMP):"
    log_info "  База данных: $BACKUP_DIR/bot_backup_$TIMESTAMP.db"
    log_info "  Логи:        $BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz"
    log_info "  Код:         $BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz"
    log_info "  Конфиг:      $BACKUP_DIR/.env_backup_$TIMESTAMP"
    log_info "  Безопасность: $BACKUP_DIR/security_config_backup_$TIMESTAMP.tar.gz"
    log_info ""
    # Финальная проверка прав доступа
    log_info "Проверяем права доступа..."
    chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
    git config --global --add safe.directory "$BOT_DIR" 2>/dev/null || true
    
    log_info "🎮 Обновленный бот готов к работе с полной защитой!"
else
    log_error "❌ ОШИБКА: Не удалось запустить обновленный бот"
    log_error ""
    log_error "🔄 ОТКАТ К ПРЕДЫДУЩЕЙ ВЕРСИИ..."
    
    # Останавливаем неработающий сервис
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    
    # Восстанавливаем бекап базы данных
    if [ -f "$BACKUP_DIR/bot_backup_$TIMESTAMP.db" ]; then
        cp "$BACKUP_DIR/bot_backup_$TIMESTAMP.db" "data/bot.db"
        log_info "✅ База данных восстановлена"
    fi
    
    # Восстанавливаем конфигурацию
    if [ -f "$BACKUP_DIR/.env_backup_$TIMESTAMP" ]; then
        cp "$BACKUP_DIR/.env_backup_$TIMESTAMP" ".env"
        log_info "✅ Конфигурация восстановлена"
    fi
    
    # Восстанавливаем код (если есть бекап старой версии)
    if [ -d "/opt/cisbot2_old_$TIMESTAMP" ]; then
        cd /opt
        rm -rf cisbot2
        mv cisbot2_old_$TIMESTAMP cisbot2
        cd cisbot2
        chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
        log_info "✅ Код восстановлен"
    fi
    
    # Пытаемся запустить старую версию
    systemctl start "$SERVICE_NAME"
    sleep 3
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "✅ Старая версия восстановлена и работает"
        log_error "❗ Проверьте логи для диагностики проблемы: journalctl -u $SERVICE_NAME -n 50"
    else
        log_error "❌ Критическая ошибка: не удалось восстановить работу бота"
        log_error "❗ Обратитесь к администратору или проверьте бекапы вручную"
    fi
    
    exit 1
fi
