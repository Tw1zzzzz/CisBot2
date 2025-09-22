# 🛡️ Руководство по безопасности CIS FINDER Bot

**Статус:** ✅ Активно поддерживается  
**Версия:** 1.0  
**Последнее обновление:** 2024

---

## 🚨 Критические принципы безопасности

### ⚠️ **НИКОГДА НЕ ДЕЛАЙТЕ:**
- ❌ Не коммитьте файл `.env` в git
- ❌ Не публикуйте токены в открытом доступе
- ❌ Не используйте тестовые токены в продакшене
- ❌ Не храните токены в коде
- ❌ Не передавайте токены через незащищенные каналы

### ✅ **ВСЕГДА ДЕЛАЙТЕ:**
- ✅ Используйте переменные окружения для секретов
- ✅ Регулярно обновляйте токены
- ✅ Проверяйте код перед коммитом
- ✅ Используйте сильные, уникальные токены
- ✅ Отзывайте скомпрометированные токены немедленно

---

## 🔐 Управление токенами и секретами

### 📋 **Список критических секретов:**

| Секрет | Источник | Описание |
|--------|----------|----------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | Токен Telegram бота |
| `FACEIT_ANALYSER_API_KEY` | [faceitanalyser.com](https://faceitanalyser.com/api/) | API ключ для анализа FACEIT |

### 🔑 **Получение токенов:**

#### Telegram Bot Token:
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен
5. **НЕМЕДЛЕННО** сохраните токен в `.env` файл

#### FACEIT Analyser API Key:
1. Перейдите на [faceitanalyser.com/api/](https://faceitanalyser.com/api/)
2. Зарегистрируйтесь или войдите в аккаунт
3. Создайте новый API ключ
4. Скопируйте полученный ключ
5. **НЕМЕДЛЕННО** сохраните ключ в `.env` файл

### 📁 **Настройка .env файла:**

```bash
# 1. Создайте .env из шаблона
cp .env.example .env

# 2. Отредактируйте .env файл
nano .env

# 3. Замените все значения "your_*_here" на реальные токены
BOT_TOKEN=ваш_реальный_токен_от_BotFather
FACEIT_ANALYSER_API_KEY=ваш_реальный_api_ключ

# 4. Установите правильные права доступа (Linux/Mac)
chmod 600 .env
```

---

## 🔍 Автоматическая проверка безопасности

### 🛠️ **Скрипт проверки секретов:**

```bash
# Базовая проверка
python scripts/check_secrets.py

# Подробная проверка с контекстом
python scripts/check_secrets.py --verbose

# Сохранение отчета в файл
python scripts/check_secrets.py --output security_report.json

# Проверка конкретной папки
python scripts/check_secrets.py --path /path/to/project
```

### 📊 **Интерпретация результатов:**

| Уровень | Описание | Действие |
|---------|----------|----------|
| 🚨 **CRITICAL** | Найден реальный секрет | Немедленно исправить! |
| ⚠️ **HIGH** | Высокий риск утечки | Исправить перед коммитом |
| ⚡ **MEDIUM** | Средний риск | Проверить и исправить |
| ℹ️ **LOW** | Низкий риск | Проверить при возможности |

### 🔄 **Интеграция с CI/CD:**

```yaml
# Пример для GitHub Actions
name: Security Check
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Check for secrets
        run: python scripts/check_secrets.py
```

---

## 🚨 Процедуры при компрометации

### 🔥 **Если токен был скомпрометирован:**

#### 1. **Немедленные действия (0-5 минут):**
```bash
# Остановите бота
systemctl stop cisbot

# Отзовите токен в Telegram
# Перейдите к @BotFather и используйте команду /revoke
```

#### 2. **Создание нового токена (5-15 минут):**
```bash
# Создайте новый бот через @BotFather
# Получите новый токен
# Обновите .env файл
nano .env
# BOT_TOKEN=новый_токен

# Установите правильные права
chmod 600 .env
```

#### 3. **Проверка безопасности (15-30 минут):**
```bash
# Запустите проверку секретов
python scripts/check_secrets.py --verbose

# Проверьте логи на подозрительную активность
journalctl -u cisbot --since "1 hour ago"

# Перезапустите бота
systemctl start cisbot
```

#### 4. **Мониторинг (следующие 24 часа):**
```bash
# Следите за логами
journalctl -u cisbot -f

# Проверяйте активность бота
# Убедитесь, что нет неавторизованного доступа
```

---

## 🔒 Лучшие практики разработки

### 📝 **При написании кода:**

```python
# ❌ НЕПРАВИЛЬНО - жестко закодированный токен
BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"

# ✅ ПРАВИЛЬНО - использование переменных окружения
import os
BOT_TOKEN = os.getenv('BOT_TOKEN')
```

### 🧪 **При тестировании:**

```python
# ❌ НЕПРАВИЛЬНО - использование реальных токенов в тестах
def test_bot():
    bot = Bot("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")

# ✅ ПРАВИЛЬНО - использование моков
@patch.dict(os.environ, {'BOT_TOKEN': 'test_token'})
def test_bot():
    bot = Bot(os.getenv('BOT_TOKEN'))
```

### 📋 **Контрольный список перед коммитом:**

- [ ] Запущена проверка секретов: `python scripts/check_secrets.py`
- [ ] Нет критических или высокорисковых находок
- [ ] Файл `.env` не добавлен в коммит
- [ ] Все токены заменены на переменные окружения
- [ ] Тесты проходят без ошибок
- [ ] Код проверен на наличие хардкода секретов

---

## 🛡️ Настройка безопасности сервера

### 🔐 **Права доступа к файлам:**

```bash
# Установите правильные права для .env
chmod 600 .env
chown cisbot:cisbot .env

# Права для папки проекта
chmod 755 /opt/cisbot2
chown -R cisbot:cisbot /opt/cisbot2

# Права для логов
chmod 644 /opt/cisbot2/logs/*.log
chown cisbot:cisbot /opt/cisbot2/logs/*.log
```

### 🔥 **Настройка firewall:**

```bash
# Разрешить только необходимые порты
ufw allow ssh
ufw allow 80
ufw allow 443
ufw deny 22  # Отключить SSH на стандартном порту (если используете другой)
ufw --force enable
```

### 📊 **Мониторинг безопасности:**

```bash
# Создайте скрипт мониторинга
cat > /opt/cisbot2/security_monitor.sh << 'EOF'
#!/bin/bash
# Проверка целостности .env файла
if [ ! -f /opt/cisbot2/.env ]; then
    echo "CRITICAL: .env file missing!" | logger -t cisbot-security
fi

# Проверка прав доступа
if [ "$(stat -c %a /opt/cisbot2/.env)" != "600" ]; then
    echo "WARNING: .env file has incorrect permissions!" | logger -t cisbot-security
fi

# Проверка активности бота
if ! systemctl is-active --quiet cisbot; then
    echo "WARNING: Bot service is not running!" | logger -t cisbot-security
fi
EOF

chmod +x /opt/cisbot2/security_monitor.sh

# Добавьте в crontab для регулярной проверки
echo "*/5 * * * * /opt/cisbot2/security_monitor.sh" | crontab -
```

---

## 📞 Контакты для сообщений о безопасности

### 🚨 **Если вы обнаружили уязвимость:**

1. **НЕ** создавайте публичный issue
2. Отправьте приватное сообщение разработчику
3. Опишите уязвимость подробно
4. Укажите шаги для воспроизведения
5. Дождитесь ответа и исправления

### 📧 **Контакты:**
- **Telegram:** [@cs2teammeet_bot](https://t.me/cs2teammeet_bot)
- **GitHub:** [Tw1zzzzz](https://github.com/Tw1zzzzz)

---

## 📚 Дополнительные ресурсы

### 🔗 **Полезные ссылки:**
- [Telegram Bot API Security](https://core.telegram.org/bots/api#security)
- [OWASP Secrets Management](https://owasp.org/www-project-secrets-management/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

### 📖 **Документация проекта:**
- [README.md](README.md) - Основная документация
- [planning/DEPLOYMENT_GUIDE.md](planning/DEPLOYMENT_GUIDE.md) - Руководство по деплою
- [bot/utils/security_validator.py](bot/utils/security_validator.py) - Модуль валидации

---

## 🔄 Обновления безопасности

### 📅 **Планируемые обновления:**
- [ ] Интеграция с внешними системами мониторинга
- [ ] Автоматическое обновление токенов
- [ ] Расширенная система аудита
- [ ] Интеграция с HSM для хранения секретов

### 📝 **Журнал изменений:**
- **2024-09-22** - Создание документа по безопасности
- **2024-09-22** - Добавление автоматической проверки секретов
- **2024-09-22** - Интеграция валидации токенов в конфигурацию

---

**⚠️ Помните: Безопасность - это не разовое мероприятие, а постоянный процесс!**

Регулярно обновляйте этот документ и следите за новыми угрозами безопасности.
