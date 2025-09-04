#!/bin/bash
# CS2 Teammeet Bot - Скрипт деплоя для Linux сервера

set -e  # Остановка при ошибке

echo "🚀 Начинаем деплой CS2 Teammeet Bot..."

# Переменные
BOT_USER="cisbot"
BOT_DIR="/opt/cisbot2"
SERVICE_NAME="cisbot"

# Цвета для логов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Проверяем, что запущен от root
if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от имени root: sudo ./deploy.sh"
    exit 1
fi

log_info "Обновляем пакеты системы..."
apt update && apt upgrade -y

log_info "Устанавливаем зависимости..."
apt install -y python3 python3-pip python3-venv git systemd

# Создаем пользователя для бота
if ! id "$BOT_USER" &>/dev/null; then
    log_info "Создаем пользователя $BOT_USER..."
    useradd -m -s /bin/bash "$BOT_USER"
else
    log_info "Пользователь $BOT_USER уже существует"
fi

# Создаем директорию для бота
log_info "Создаем директорию $BOT_DIR..."
mkdir -p "$BOT_DIR"
chown "$BOT_USER:$BOT_USER" "$BOT_DIR"

# Копируем файлы проекта (если деплой из текущей папки)
if [ -f "run_bot.py" ]; then
    log_info "Копируем файлы проекта..."
    cp -r . "$BOT_DIR/"
    chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
fi

# Переходим в директорию бота
cd "$BOT_DIR"

# Создаем виртуальное окружение
log_info "Создаем виртуальное окружение..."
sudo -u "$BOT_USER" python3 -m venv venv

# Устанавливаем зависимости
log_info "Устанавливаем Python зависимости..."
sudo -u "$BOT_USER" bash -c "source venv/bin/activate && pip install -r requirements.txt"

# Создаем необходимые папки
log_info "Создаем папки для данных и логов..."
sudo -u "$BOT_USER" mkdir -p data logs backups

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    log_warn "Файл .env не найден!"
    if [ -f ".env.example" ]; then
        log_info "Копируем .env.example в .env..."
        cp .env.example .env
        chown "$BOT_USER:$BOT_USER" .env
        log_warn "Не забудьте отредактировать .env файл с вашими настройками!"
    else
        log_error "Создайте .env файл с настройками бота"
        exit 1
    fi
fi

# Устанавливаем systemd сервис
if [ -f "cisbot.service" ]; then
    log_info "Устанавливаем systemd сервис..."
    cp cisbot.service "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
else
    log_error "Файл cisbot.service не найден!"
    exit 1
fi

# Тестовый запуск
log_info "Тестируем запуск бота..."
if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && timeout 10 python run_bot.py" 2>/dev/null; then
    log_info "✅ Тестовый запуск прошел успешно!"
else
    log_warn "⚠️  Тестовый запуск завершился (это нормально для теста)"
fi

# Запускаем сервис
log_info "Запускаем сервис..."
systemctl start "$SERVICE_NAME"

# Проверяем статус
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "✅ CS2 Teammeet Bot успешно запущен!"
    log_info "Статус сервиса: $(systemctl is-active $SERVICE_NAME)"
    log_info ""
    log_info "📊 Полезные команды:"
    log_info "  Статус:      systemctl status $SERVICE_NAME"
    log_info "  Перезапуск:  systemctl restart $SERVICE_NAME"
    log_info "  Остановка:   systemctl stop $SERVICE_NAME"
    log_info "  Логи:        journalctl -u $SERVICE_NAME -f"
    log_info ""
    log_info "🎮 Бот готов к использованию в Telegram!"
else
    log_error "❌ Не удалось запустить сервис"
    log_error "Проверьте логи: journalctl -u $SERVICE_NAME -n 20"
    exit 1
fi
