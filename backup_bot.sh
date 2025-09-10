#!/bin/bash
# CS2 Teammeet Bot - Скрипт создания резервной копии

set -e

echo "💾 Создание резервной копии CS2 Teammeet Bot..."

# Переменные
BOT_DIR="/opt/cisbot2"
SERVICE_NAME="cisbot"
BACKUP_DIR="/opt/cisbot2/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Создаем директорию для бекапов
mkdir -p "$BACKUP_DIR"

cd "$BOT_DIR"

log_info "Создание резервной копии..."

# Бекап базы данных (без остановки бота)
if [ -f "data/bot.db" ]; then
    sqlite3 data/bot.db ".backup $BACKUP_DIR/bot_backup_$TIMESTAMP.db"
    log_info "✅ База данных: $BACKUP_DIR/bot_backup_$TIMESTAMP.db"
else
    log_warn "⚠️  База данных не найдена"
fi

# Бекап конфигурации
if [ -f ".env" ]; then
    cp ".env" "$BACKUP_DIR/.env_backup_$TIMESTAMP"
    log_info "✅ Конфигурация: $BACKUP_DIR/.env_backup_$TIMESTAMP"
fi

# Бекап логов
if [ -d "logs" ]; then
    tar -czf "$BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz" logs/
    log_info "✅ Логи: $BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz"
fi

# Показываем информацию о бекапах
echo ""
log_info "📊 Размеры бекапов:"
ls -lah "$BACKUP_DIR"/*$TIMESTAMP* 2>/dev/null || true

# Удаляем старые бекапы (старше 30 дней)
find "$BACKUP_DIR" -name "*backup*" -type f -mtime +30 -delete 2>/dev/null || true

echo ""
log_info "✅ Резервная копия создана успешно!"
log_info "📁 Папка бекапов: $BACKUP_DIR"
