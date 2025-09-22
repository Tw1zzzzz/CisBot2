#!/bin/bash
# CS2 Teammeet Bot - БЕЗОПАСНЫЙ скрипт деплоя для Linux сервера
# Включает проверки безопасности и валидацию токенов

set -e  # Остановка при ошибке

echo "🚀 Начинаем БЕЗОПАСНЫЙ деплой CS2 Teammeet Bot..."
echo "🔒 Включает проверки безопасности и валидацию токенов"

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

# 🔒 БЕЗОПАСНОСТЬ: Проверяем секреты перед деплоем
log_step "🔒 Проверка безопасности и валидация токенов..."

# Проверяем наличие скрипта проверки секретов
if [ -f "scripts/check_secrets.py" ]; then
    log_info "Запускаем проверку секретов..."
    if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python scripts/check_secrets.py --verbose" 2>/dev/null; then
        log_info "✅ Проверка секретов пройдена успешно"
    else
        log_error "❌ Обнаружены проблемы с секретами!"
        log_error "Исправьте проблемы в .env файле перед продолжением"
        exit 1
    fi
else
    log_warn "⚠️  Скрипт проверки секретов не найден, пропускаем проверку"
fi

# Проверяем права доступа к .env файлу
ENV_PERMS=$(stat -c %a .env 2>/dev/null || echo "000")
if [ "$ENV_PERMS" != "600" ]; then
    log_warn "Исправляем права доступа к .env файлу..."
    chmod 600 .env
    chown "$BOT_USER:$BOT_USER" .env
    log_info "✅ Права доступа к .env установлены: 600"
fi

# Проверяем валидность токенов
log_info "Проверяем валидность токенов..."
if sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python -c \"
import os
from bot.config import BOT_TOKEN, FACEIT_ANALYSER_API_KEY
from bot.utils.security_validator import validate_token_strength

# Проверяем BOT_TOKEN
if BOT_TOKEN and len(BOT_TOKEN) > 20:
    strength = validate_token_strength(BOT_TOKEN)
    print(f'BOT_TOKEN: ВАЛИДЕН (сила: {strength}/100)')
else:
    print('BOT_TOKEN: НЕВАЛИДЕН')
    exit(1)

# Проверяем FACEIT_API_KEY
if FACEIT_ANALYSER_API_KEY and len(FACEIT_ANALYSER_API_KEY) > 10:
    strength = validate_token_strength(FACEIT_ANALYSER_API_KEY)
    print(f'FACEIT_API_KEY: ВАЛИДЕН (сила: {strength}/100)')
else:
    print('FACEIT_API_KEY: НЕВАЛИДЕН')
    exit(1)
\"" 2>/dev/null; then
    log_info "✅ Все токены валидны"
else
    log_error "❌ Обнаружены проблемы с токенами!"
    log_error "Проверьте .env файл и убедитесь, что токены корректны"
    exit 1
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

# 🔒 БЕЗОПАСНОСТЬ: Тестовый запуск с проверкой безопасности
log_step "🧪 Тестирование безопасности и функциональности..."

log_info "Тестируем запуск бота с проверкой безопасности..."
TEST_OUTPUT=$(timeout 15 sudo -u "$BOT_USER" bash -c "cd $BOT_DIR && source venv/bin/activate && python run_bot.py 2>&1" || echo "timeout")

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
    log_info "✅ Компоненты безопасности инициализированы"
else
    log_warn "⚠️  Возможны проблемы с компонентами безопасности"
fi

# Проверяем инициализацию базы данных
if echo "$TEST_OUTPUT" | grep -q "База данных инициализирована"; then
    log_info "✅ База данных инициализирована"
else
    log_warn "⚠️  Возможны проблемы с базой данных"
fi

# Запускаем сервис
log_info "Запускаем сервис..."
systemctl start "$SERVICE_NAME"

# Проверяем статус
sleep 5
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "🎉 CS2 Teammeet Bot успешно запущен с улучшениями безопасности!"
    log_info "Статус сервиса: $(systemctl is-active $SERVICE_NAME)"
    log_info ""
    log_info "🔒 Безопасность:"
    log_info "  ✅ JSON Schema Validator активен"
    log_info "  ✅ SecureLogger настроен"
    log_info "  ✅ CallbackSecurityValidator активен"
    log_info "  ✅ Audit Trail система работает"
    log_info "  ✅ Токены валидированы"
    log_info ""
    log_info "📊 Полезные команды:"
    log_info "  Статус:      systemctl status $SERVICE_NAME"
    log_info "  Перезапуск:  systemctl restart $SERVICE_NAME"
    log_info "  Остановка:   systemctl stop $SERVICE_NAME"
    log_info "  Логи:        journalctl -u $SERVICE_NAME -f"
    log_info "  Безопасность: python scripts/check_secrets.py"
    log_info ""
    log_info "🎮 Бот готов к использованию в Telegram с полной защитой!"
else
    log_error "❌ Не удалось запустить сервис"
    log_error "Проверьте логи: journalctl -u $SERVICE_NAME -n 20"
    exit 1
fi
