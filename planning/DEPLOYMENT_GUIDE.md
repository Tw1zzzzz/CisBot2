# 🚀 ПОЛНЫЙ ПЛАН ДЕПЛОЯ CS2 TEAMMEET BOT

**Статус проекта:** ✅ 100% готов к деплою  
**Для:** Junior разработчик  
**Время деплоя:** ~30-60 минут

---

## 📋 КРАТКИЙ ОБЗОР ТЕКУЩЕГО СОСТОЯНИЯ

### ✅ ЧТО У НАС ЕСТЬ:
- **Готовый бот** (100% функционал)
- **База данных** SQLite (data/bot.db)
- **Токен бота:** `7300458616:AAHaw24vJxrmjtxUn6s0Z39hROVIBW_MKWo`
- **Все зависимости** в requirements.txt
- **Рабочий код** (протестирован локально)

### ❗ ЧТО НУЖНО СДЕЛАТЬ:
1. Выбрать хостинг (VPS)
2. Настроить сервер
3. Перенести код и базу
4. Настроить автозапуск
5. Протестировать в продакшене

---

## 🎯 ШАГ 1: ВЫБОР ХОСТИНГА

### 💰 Рекомендуемые варианты (бюджетные):

#### А) **Timeweb (Россия)** - 150₽/месяц
- VPS Linux 1 ядро, 1GB RAM, 10GB SSD
- Русская поддержка 24/7
- Регистрация: timeweb.com

#### Б) **Beget (Россия)** - 200₽/месяц
- VPS 1 ядро, 1GB RAM, 5GB NVMe
- Простая панель управления
- Регистрация: beget.com

#### В) **DigitalOcean (международный)** - $6/месяц (~450₽)
- Droplet 1GB RAM, 25GB SSD
- Больше гибкости, но на английском
- Нужна карта для регистрации

### 🔧 Требования к серверу:
- **ОС:** Ubuntu 20.04/22.04 (самая простая)
- **RAM:** минимум 512MB (рекомендую 1GB)
- **Диск:** минимум 5GB
- **Python:** 3.8+ (обычно есть по умолчанию)

---

## 🔨 ШАГ 2: ПОДГОТОВКА К ДЕПЛОЮ

### 📁 Что создаем локально:

#### А) Создать .env файл:
```bash
# В корне проекта создай файл .env
BOT_TOKEN=7300458616:AAHaw24vJxrmjtxUn6s0Z39hROVIBW_MKWo
BOT_USERNAME=cs2teammeet_bot
DATABASE_PATH=/opt/cisbot2/data/bot.db
LOG_FILE=/opt/cisbot2/logs/bot.log
LOG_LEVEL=INFO
```

#### Б) Создать systemd service файл:
```bash
# Создай файл bot.service
[Unit]
Description=CS2 Teammeet Bot
After=network.target

[Service]
Type=simple
User=cisbot
WorkingDirectory=/opt/cisbot2
Environment=PATH=/opt/cisbot2/venv/bin
ExecStart=/opt/cisbot2/venv/bin/python run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 🖥️ ШАГ 3: НАСТРОЙКА СЕРВЕРА

### 📡 Подключение к серверу:
```bash
# После покупки VPS получишь:
ssh root@твой_ip_адрес
# Введи пароль, который пришлет хостинг
```

### 🛠️ Установка необходимого ПО:
```bash
# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем Python и git
apt install python3 python3-pip python3-venv git systemd -y

# Создаем пользователя для бота (безопасность)
useradd -m -s /bin/bash cisbot
```

### 📂 Создание папки для бота:
```bash
# Создаем папку
mkdir -p /opt/cisbot2
chown cisbot:cisbot /opt/cisbot2
```

---

## 📤 ШАГ 4: ЗАГРУЗКА ПРОЕКТА НА СЕРВЕР

### 🎯 Вариант A: Через GitHub (рекомендуется)

#### На твоем компе:
```bash
# 1. Инициализируем git (если еще не сделали)
cd C:\Users\АянамиРей\Documents\CisBot2
git init
git add .
git commit -m "Initial commit"

# 2. Создаем репозиторий на GitHub
# Заходи на github.com, создай новый приватный репозиторий "CisBot2"

# 3. Пушим код
git remote add origin https://github.com/твой_username/CisBot2.git
git push -u origin main
```

#### На сервере:
```bash
# Переходим к пользователю бота
su - cisbot

# Клонируем репозиторий
cd /opt
git clone https://github.com/твой_username/CisBot2.git cisbot2
cd cisbot2
```

### 🎯 Вариант Б: Через SCP (если без GitHub)
```bash
# На твоем Windows компьютере в PowerShell:
scp -r C:\Users\АянамиРей\Documents\CisBot2\* root@твой_ip:/opt/cisbot2/
```

---

## ⚙️ ШАГ 5: НАСТРОЙКА ОКРУЖЕНИЯ НА СЕРВЕРЕ

### 📦 Установка зависимостей:
```bash
# На сервере под пользователем cisbot
cd /opt/cisbot2

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt
```

### 🔧 Настройка конфигурации:
```bash
# Создаем .env файл на сервере
nano .env
# Вставляй содержимое .env файла из Шага 2А

# Создаем папки для логов и базы
mkdir -p data logs
chown -R cisbot:cisbot /opt/cisbot2
```

### 🧪 Тестирование запуска:
```bash
# Тестируем бота
python run_bot.py

# Если работает - видишь:
# INFO - CS2 Teammeet Bot инициализирован успешно
# INFO - Запуск CS2 Teammeet Bot с пулом соединений...

# Останавливаем: Ctrl+C
```

---

## 🔄 ШАГ 6: НАСТРОЙКА АВТОЗАПУСКА

### 📋 Создание systemd service:
```bash
# Выходим из пользователя cisbot
exit

# Создаем service файл как root
nano /etc/systemd/system/cisbot.service
# Вставляй содержимое bot.service из Шага 2Б

# Активируем сервис
systemctl enable cisbot
systemctl start cisbot

# Проверяем статус
systemctl status cisbot
```

### 📊 Полезные команды управления:
```bash
# Статус бота
systemctl status cisbot

# Перезапуск
systemctl restart cisbot

# Остановка
systemctl stop cisbot

# Логи (последние 50 строк)
journalctl -u cisbot -n 50

# Живые логи
journalctl -u cisbot -f
```

---

## 🔍 ШАГ 7: ПРОВЕРКА И МОНИТОРИНГ

### ✅ Чек-лист проверки:
```bash
# 1. Сервис запущен
systemctl is-active cisbot
# Должно быть: active

# 2. Бот отвечает в Telegram
# Найди бота в Telegram: @cs2teammeet_bot
# Отправь /start

# 3. База данных работает
ls -la /opt/cisbot2/data/
# Должен быть файл bot.db

# 4. Логи пишутся
tail -f /opt/cisbot2/logs/bot.log
```

### 📈 Мониторинг:
```bash
# Использование ресурсов
htop
# Или
ps aux | grep python

# Размер базы данных
du -h /opt/cisbot2/data/bot.db

# Свободное место на диске
df -h
```

---

## 🛡️ ШАГ 8: БЕЗОПАСНОСТЬ

### 🔒 Базовая защита:
```bash
# Настройка firewall
ufw allow ssh
ufw allow 80
ufw allow 443
ufw --force enable

# Отключение root входа по SSH (опционально)
nano /etc/ssh/sshd_config
# Измени: PermitRootLogin no
systemctl restart ssh
```

---

## 🆘 РЕШЕНИЕ ПРОБЛЕМ

### ❌ Проблема: "Permission denied"
```bash
# Исправление прав
chown -R cisbot:cisbot /opt/cisbot2
chmod +x /opt/cisbot2/run_bot.py
```

### ❌ Проблема: "Module not found"
```bash
# Переустанови зависимости
cd /opt/cisbot2
source venv/bin/activate
pip install --force-reinstall -r requirements.txt
```

### ❌ Проблема: Бот не отвечает в Telegram
```bash
# Проверь токен
journalctl -u cisbot | grep -i token
# Проверь интернет на сервере
ping telegram.org
```

---

## 🎉 ГОТОВО!

### 🚀 Твой бот теперь работает 24/7!
- **URL:** https://t.me/cs2teammeet_bot
- **Логи:** `/opt/cisbot2/logs/bot.log`
- **Управление:** `systemctl restart cisbot`

### 📱 Что дальше:
1. **Протестируй все функции** в Telegram
2. **Поделись ботом** с друзьями
3. **Следи за логами** первые дни
4. **Сделай бекап базы** через неделю

---

## 💡 ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ

### 🔄 Автоматический бекап базы:
```bash
# Создай скрипт backup.sh
#!/bin/bash
cp /opt/cisbot2/data/bot.db /opt/cisbot2/backups/bot_$(date +%Y%m%d).db

# Добавь в crontab (каждый день в 3 утра)
crontab -e
0 3 * * * /opt/cisbot2/backup.sh
```

### 📊 Веб-панель мониторинга:
- Можно добавить простую веб-страницу для статистики
- Интегрировать с Grafana для красивых графиков

### 🔔 Уведомления о проблемах:
- Настроить отправку email при падении бота
- Telegram-бот для мониторинга другого бота

**Удачного деплоя! 🎮**
