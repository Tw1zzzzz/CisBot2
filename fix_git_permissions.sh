#!/bin/bash
# Скрипт для исправления проблем с правами доступа Git
# Используется для решения ошибки "dubious ownership in repository"

set -e

# Переменные
BOT_USER="cisbot"
BOT_DIR="/opt/cisbot2"

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

echo "🔧 Исправление проблем с правами доступа Git..."

# Проверяем, что запущен от root
if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от имени root: sudo ./fix_git_permissions.sh"
    exit 1
fi

# Проверяем существование директории
if [ ! -d "$BOT_DIR" ]; then
    log_error "Директория бота $BOT_DIR не найдена!"
    exit 1
fi

log_step "1. Настраиваем Git safe.directory..."
git config --global --add safe.directory "$BOT_DIR" 2>/dev/null || true
log_info "✅ Git safe.directory настроен"

log_step "2. Исправляем права доступа к директории..."
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
log_info "✅ Права доступа исправлены"

log_step "3. Проверяем Git статус..."
cd "$BOT_DIR"
if git status >/dev/null 2>&1; then
    log_info "✅ Git работает корректно"
else
    log_warn "⚠️ Git все еще может иметь проблемы"
fi

log_step "4. Проверяем владельца файлов..."
OWNER=$(stat -c '%U:%G' "$BOT_DIR")
if [ "$OWNER" = "$BOT_USER:$BOT_USER" ]; then
    log_info "✅ Владелец файлов: $OWNER"
else
    log_warn "⚠️ Владелец файлов: $OWNER (ожидался: $BOT_USER:$BOT_USER)"
fi

log_info "🎉 Исправление завершено!"
log_info "Теперь можно запускать update_bot.sh без ошибок Git"
