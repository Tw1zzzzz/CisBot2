#!/bin/bash
# Скрипт для назначения первого модератора на сервере
# Использование: bash scripts/setup_first_moderator_server.sh <user_id> [role]

set -e

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

# Проверяем аргументы
if [ $# -lt 1 ]; then
    echo "Использование: bash scripts/setup_first_moderator_server.sh <user_id> [role]"
    echo ""
    echo "Роли:"
    echo "  super_admin - Полные права (по умолчанию)"
    echo "  admin       - Расширенные права"
    echo "  moderator   - Базовые права модерации"
    echo ""
    echo "Примеры:"
    echo "  bash scripts/setup_first_moderator_server.sh 123456789"
    echo "  bash scripts/setup_first_moderator_server.sh 123456789 admin"
    exit 1
fi

USER_ID="$1"
ROLE="${2:-super_admin}"

# Проверяем роль
if [[ ! "$ROLE" =~ ^(moderator|admin|super_admin)$ ]]; then
    log_error "Неверная роль: $ROLE"
    echo "Доступные роли: moderator, admin, super_admin"
    exit 1
fi

# Переменные
BOT_USER="cisbot"
BOT_DIR="/opt/cisbot2"
SERVICE_NAME="cisbot"

log_step "Назначение модератора на сервере"
log_info "User ID: $USER_ID"
log_info "Роль: $ROLE"

# Проверяем, что мы root
if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от имени root: sudo bash scripts/setup_first_moderator_server.sh $USER_ID $ROLE"
    exit 1
fi

# Проверяем, что директория бота существует
if [ ! -d "$BOT_DIR" ]; then
    log_error "Директория бота не найдена: $BOT_DIR"
    log_info "Сначала запустите deploy.sh для установки бота"
    exit 1
fi

# Проверяем, что пользователь бота существует
if ! id "$BOT_USER" &>/dev/null; then
    log_error "Пользователь бота не найден: $BOT_USER"
    log_info "Сначала запустите deploy.sh для установки бота"
    exit 1
fi

# Проверяем, что виртуальное окружение существует
if [ ! -d "$BOT_DIR/venv" ]; then
    log_error "Виртуальное окружение не найдено: $BOT_DIR/venv"
    log_info "Сначала запустите deploy.sh для установки бота"
    exit 1
fi

# Проверяем, что requirements.txt существует
if [ ! -f "$BOT_DIR/requirements.txt" ]; then
    log_error "Файл requirements.txt не найден: $BOT_DIR/requirements.txt"
    exit 1
fi

log_step "Проверка зависимостей..."

# Проверяем, установлены ли зависимости
if ! sudo -u "$BOT_USER" bash -c "source $BOT_DIR/venv/bin/activate && python3 -c 'import aiosqlite'" 2>/dev/null; then
    log_warn "Зависимости не установлены, устанавливаем..."
    sudo -u "$BOT_USER" bash -c "source $BOT_DIR/venv/bin/activate && pip install -r $BOT_DIR/requirements.txt"
    
    # Проверяем еще раз
    if ! sudo -u "$BOT_USER" bash -c "source $BOT_DIR/venv/bin/activate && python3 -c 'import aiosqlite'" 2>/dev/null; then
        log_error "Не удалось установить зависимости"
        exit 1
    fi
fi

log_info "✅ Зависимости установлены"

log_step "Назначение модератора..."

# Запускаем скрипт в виртуальном окружении
sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    python3 scripts/setup_first_moderator.py $USER_ID $ROLE
"

if [ $? -eq 0 ]; then
    log_info "✅ Модератор успешно назначен!"
    log_info ""
    log_info "📋 Следующие шаги:"
    log_info "1. Перезапустите бота: systemctl restart $SERVICE_NAME"
    log_info "2. Проверьте статус: systemctl status $SERVICE_NAME"
    log_info "3. Проверьте логи: journalctl -u $SERVICE_NAME -f"
    log_info ""
    log_info "🎮 Пользователь $USER_ID теперь может:"
    log_info "- Использовать кнопку '👨‍💼 Модерация' в главном меню"
    log_info "- Модерировать профили пользователей"
    if [ "$ROLE" = "super_admin" ]; then
        log_info "- Управлять другими модераторами"
        log_info "- Просматривать логи аудита"
    fi
else
    log_error "❌ Не удалось назначить модератора"
    exit 1
fi
