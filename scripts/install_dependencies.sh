#!/bin/bash
# Скрипт для установки зависимостей на сервере

echo "🔧 Установка зависимостей для CIS FINDER Bot..."

# Проверяем, что мы в правильной директории
if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден. Запустите скрипт из корневой директории проекта."
    exit 1
fi

# Обновляем pip
echo "📦 Обновление pip..."
python3 -m pip install --upgrade pip

# Устанавливаем зависимости
echo "📦 Установка зависимостей из requirements.txt..."
python3 -m pip install -r requirements.txt

# Проверяем установку ключевых модулей
echo "🔍 Проверка установленных модулей..."

modules=("telegram" "aiosqlite" "aiohttp" "dotenv")
for module in "${modules[@]}"; do
    if python3 -c "import $module" 2>/dev/null; then
        echo "✅ $module - установлен"
    else
        echo "❌ $module - НЕ установлен"
    fi
done

echo ""
echo "🎉 Установка зависимостей завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Перезапустите бота: systemctl restart cisbot"
echo "2. Проверьте статус: systemctl status cisbot"
echo "3. Проверьте логи: journalctl -u cisbot -f"
