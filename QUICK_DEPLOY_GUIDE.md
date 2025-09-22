# 🚀 Быстрое руководство по деплою CS2 Teammeet Bot

## 🔒 Новые возможности безопасности

Ваш бот теперь включает **комплексную систему безопасности**:
- ✅ **JSON Schema Validator** - защита от JSON injection
- ✅ **SecureLogger** - безопасное логирование
- ✅ **CallbackSecurityValidator** - защита от callback атак
- ✅ **Audit Trail** - полное логирование действий
- ✅ **Confirmation Tokens** - подтверждение критических операций

---

## 🚀 Первый деплой (Новая установка)

### 1. Подготовка
```bash
# Скачиваем проект
git clone https://github.com/Tw1zzzzz/CisBot2.git
cd CisBot2

# Создаем .env файл
cp .env.example .env
nano .env  # Добавляем ваши токены
```

### 2. Настройка токенов
```bash
# В .env файле укажите:
BOT_TOKEN=ваш_токен_от_BotFather
FACEIT_ANALYSER_API_KEY=ваш_api_ключ_от_faceitanalyser
```

### 3. Деплой
```bash
# Запускаем безопасный деплой
sudo ./deploy.sh
```

**Готово!** Бот запущен с полной защитой.

---

## 🔄 Обновление существующего бота

### Автоматическое обновление
```bash
# Запускаем безопасное обновление
sudo ./update_bot.sh
```

**Что происходит:**
1. 🔒 Проверка текущей безопасности
2. 💾 Создание резервных копий
3. 🔄 Загрузка новой версии
4. 🧪 Тестирование безопасности
5. 🚀 Запуск с автоматическим откатом при ошибках

---

## 🔍 Проверка безопасности

### Перед деплоем
```bash
# Комплексная проверка безопасности
python scripts/pre_deploy_security_check.py
```

### Регулярные проверки
```bash
# Проверка секретов
python scripts/check_secrets.py

# Подробная проверка
python scripts/check_secrets.py --verbose
```

---

## 📊 Управление ботом

### Основные команды
```bash
# Статус
systemctl status cisbot

# Перезапуск
systemctl restart cisbot

# Остановка
systemctl stop cisbot

# Логи
journalctl -u cisbot -f
```

### Мониторинг безопасности
```bash
# Логи безопасности
tail -f logs/bot.log | grep -i security

# Статистика аудита
python -c "
from bot.database.operations import DatabaseManager
import asyncio

async def stats():
    db = DatabaseManager('data/bot.db')
    await db.initialize()
    stats = await db.get_security_statistics()
    for stat in stats:
        print(f'{stat[\"action_type\"]}: {stat[\"count\"]}')
    await db.close()

asyncio.run(stats())
"
```

---

## 🚨 При проблемах

### Если деплой не прошел
```bash
# 1. Проверяем отчет безопасности
cat logs/security_check_report.txt

# 2. Исправляем проблемы в .env
nano .env

# 3. Повторяем проверку
python scripts/pre_deploy_security_check.py

# 4. Запускаем деплой
sudo ./deploy.sh
```

### Если обновление не удалось
```bash
# Скрипт автоматически откатывается к предыдущей версии
# Проверяем логи для диагностики
journalctl -u cisbot -n 50
```

### Если обнаружены проблемы безопасности
```bash
# 1. Останавливаем бота
sudo systemctl stop cisbot

# 2. Проверяем логи
journalctl -u cisbot --since "1 hour ago"

# 3. При необходимости отзываем токены
# Переходим к @BotFather → /revoke

# 4. Создаем новые токены и обновляем .env

# 5. Перезапускаем
sudo systemctl start cisbot
```

---

## 📋 Контрольный список

### Перед деплоем:
- [ ] Токены получены и добавлены в .env
- [ ] Права доступа к .env установлены (600)
- [ ] Проверка безопасности пройдена
- [ ] Все зависимости установлены

### После деплоя:
- [ ] Бот запущен и отвечает
- [ ] Компоненты безопасности активны
- [ ] Логи не содержат ошибок
- [ ] Мониторинг настроен

---

## 🔗 Дополнительная документация

- **[SECURE_DEPLOYMENT_GUIDE.md](SECURE_DEPLOYMENT_GUIDE.md)** - Подробное руководство по безопасному деплою
- **[SECURITY.md](SECURITY.md)** - Руководство по безопасности
- **[SECURITY_ENHANCEMENTS_IMPLEMENTED.md](SECURITY_ENHANCEMENTS_IMPLEMENTED.md)** - Реализованные улучшения

---

## ✅ Готово!

Ваш CS2 Teammeet Bot теперь защищен от:
- 🛡️ JSON injection атак
- 🛡️ XSS атак через callback_data  
- 🛡️ Утечки персональных данных
- 🛡️ Privilege escalation
- 🛡️ Неавторизованных действий

**Бот готов к безопасной работе!** 🎮