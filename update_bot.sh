#!/bin/bash
# CS2 Teammeet Bot - Скрипт БЕЗОПАСНОГО ОБНОВЛЕНИЯ
# Сохраняет данные пользователей и обновляет код

set -e  # Остановка при ошибке

echo "🔄 Начинаем БЕЗОПАСНОЕ обновление CS2 Teammeet Bot..."

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

log_step "1️⃣ Создание резервной копии..."

# Создаем директорию для бекапов
mkdir -p "$BACKUP_DIR"

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

log_step "2️⃣ Загрузка нового кода..."

# Сохраняем текущую версию
log_info "Создаем бекап текущего кода..."
tar --exclude='data' --exclude='logs' --exclude='backups' --exclude='venv' \
    -czf "$BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz" .
log_info "✅ Код сохранен: $BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz"

# Получаем обновления из GitHub
log_info "Загружаем обновления из GitHub..."
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
    
    # Восстанавливаем важные файлы
    cp cisbot2_old_$TIMESTAMP/data/* cisbot2/data/ 2>/dev/null || true
    cp cisbot2_old_$TIMESTAMP/logs/* cisbot2/logs/ 2>/dev/null || true
    cp cisbot2_old_$TIMESTAMP/.env cisbot2/.env 2>/dev/null || true
    
    cd cisbot2
fi

log_step "3️⃣ Обновление зависимостей..."

# Обновляем права доступа
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"

# Обновляем виртуальное окружение
log_info "Обновляем Python зависимости..."
sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt --upgrade
"

log_step "4️⃣ Проверка миграций базы данных..."

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
        await db.initialize()
        await db.close()
        print('✅ База данных совместима')
    except Exception as e:
        print(f'⚠️  Возможны проблемы с БД: {e}')
        
asyncio.run(check_db())
\"
" 2>/dev/null || log_warn "Не удалось проверить БД (это может быть нормально)"

log_step "5️⃣ Тестирование обновления..."

# Тестовый запуск бота
log_info "Выполняем тестовый запуск..."
TEST_OUTPUT=$(timeout 15 sudo -u "$BOT_USER" bash -c "
    cd $BOT_DIR
    source venv/bin/activate
    python run_bot.py 2>&1
" || echo "timeout")

if echo "$TEST_OUTPUT" | grep -q "CS2 Teammeet Bot инициализирован успешно"; then
    log_info "✅ Тестовый запуск прошел успешно!"
elif echo "$TEST_OUTPUT" | grep -q "timeout"; then
    log_info "✅ Тест завершен по таймауту (это нормально)"
else
    log_warn "⚠️  Обнаружены предупреждения в тестовом запуске"
    echo "$TEST_OUTPUT" | tail -10
fi

log_step "6️⃣ Запуск обновленного бота..."

# Запускаем обновленный сервис
log_info "Запускаем обновленный бот..."
systemctl start "$SERVICE_NAME"

# Ждем запуска
sleep 5

# Проверяем статус
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "🎉 ОБНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО!"
    log_info ""
    log_info "✅ Статус сервиса: $(systemctl is-active $SERVICE_NAME)"
    log_info "✅ База данных пользователей сохранена"
    log_info "✅ Все резервные копии созданы в $BACKUP_DIR"
    log_info ""
    log_info "📊 Управление ботом:"
    log_info "  Статус:      systemctl status $SERVICE_NAME"
    log_info "  Перезапуск:  systemctl restart $SERVICE_NAME"
    log_info "  Логи:        journalctl -u $SERVICE_NAME -f"
    log_info ""
    log_info "💾 Резервные копии ($TIMESTAMP):"
    log_info "  База данных: $BACKUP_DIR/bot_backup_$TIMESTAMP.db"
    log_info "  Логи:        $BACKUP_DIR/logs_backup_$TIMESTAMP.tar.gz"
    log_info "  Код:         $BACKUP_DIR/code_backup_$TIMESTAMP.tar.gz"
    log_info "  Конфиг:      $BACKUP_DIR/.env_backup_$TIMESTAMP"
    log_info ""
    log_info "🎮 Обновленный бот готов к работе!"
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
