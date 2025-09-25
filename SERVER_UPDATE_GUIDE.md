# 🚀 Руководство по обновлению файлов на сервере

## 📋 Что было зафиксировано в Git

### ✅ Исправления:
- **Исправлена ошибка модерации:** `'name update is not defined'` в `bot/handlers/moderation.py`
- **Улучшен скрипт:** `scripts/setup_first_moderator.py` с проверкой зависимостей

### 🆕 Новые файлы:
- `scripts/setup_first_moderator_server.sh` - серверный скрипт для назначения модераторов
- `scripts/check_dependencies.py` - проверка зависимостей Python
- `scripts/install_dependencies.sh` - установка зависимостей
- `MODERATION_SETUP_GUIDE.md` - руководство по настройке модерации

## 🔄 Способы обновления на сервере

### Вариант 1: Автоматическое обновление (Рекомендуется)

```bash
# Подключиться к серверу
ssh root@your-server-ip

# Перейти в директорию бота
cd /opt/cisbot2

# Остановить бота
systemctl stop cisbot

# Обновить файлы из Git
sudo -u cisbot git pull origin main

# Перезапустить бота
systemctl start cisbot

# Проверьте статус
systemctl status cisbot
```

### Вариант 2: Ручное обновление

```bash
# Подключиться к серверу
ssh root@your-server-ip

# Перейти в директорию бота
cd /opt/cisbot2

# Остановить бота
systemctl stop cisbot

# Создать резервную копию
cp -r . ../cisbot2_backup_$(date +%Y%m%d_%H%M%S)

# Обновить файлы
sudo -u cisbot git fetch origin
sudo -u cisbot git reset --hard origin/main

# Установить права доступа
chown -R cisbot:cisbot /opt/cisbot2
chmod +x scripts/*.sh scripts/*.py

# Перезапустить бота
systemctl start cisbot
```

### Вариант 3: Использование update_bot.sh

```bash
# Подключиться к серверу
ssh root@your-server-ip

# Перейти в директорию бота
cd /opt/cisbot2

# Запустить скрипт обновления
bash update_bot.sh
```

## 🛡️ Назначение модератора после обновления

После обновления файлов назначьте модератора:

```bash
# Назначить супер-администратора
sudo bash scripts/setup_first_moderator_server.sh 405605039

# Или назначить администратора
sudo bash scripts/setup_first_moderator_server.sh 405605039 admin
```

## 🔍 Проверка обновления

### 1. Проверьте статус бота:
```bash
systemctl status cisbot
```

### 2. Проверьте логи:
```bash
journalctl -u cisbot -f
```

### 3. Проверьте новые файлы:
```bash
ls -la scripts/
# Должны появиться:
# - setup_first_moderator_server.sh
# - check_dependencies.py
# - install_dependencies.sh
```

### 4. Проверьте модерацию:
```bash
# Проверить, что модератор назначен
sudo -u cisbot bash -c "source venv/bin/activate && python3 scripts/setup_first_moderator.py --help"
```

## 🚨 Если что-то пошло не так

### Откат к предыдущей версии:
```bash
# Остановить бота
systemctl stop cisbot

# Откатить изменения
cd /opt/cisbot2
sudo -u cisbot git reset --hard HEAD~1

# Перезапустить бота
systemctl start cisbot
```

### Восстановление из резервной копии:
```bash
# Остановить бота
systemctl stop cisbot

# Восстановить из резервной копии
rm -rf /opt/cisbot2
mv /opt/cisbot2_backup_YYYYMMDD_HHMMSS /opt/cisbot2

# Перезапустить бота
systemctl start cisbot
```

## 📋 Пошаговая инструкция

### Шаг 1: Подключение к серверу
```bash
ssh root@your-server-ip
```

### Шаг 2: Остановка бота
```bash
systemctl stop cisbot
```

### Шаг 3: Обновление файлов
```bash
cd /opt/cisbot2
sudo -u cisbot git pull origin main
```

### Шаг 4: Установка прав доступа
```bash
chown -R cisbot:cisbot /opt/cisbot2
chmod +x scripts/*.sh scripts/*.py
```

### Шаг 5: Запуск бота
```bash
systemctl start cisbot
```

### Шаг 6: Назначение модератора
```bash
sudo bash scripts/setup_first_moderator_server.sh 405605039
```

### Шаг 7: Проверка работы
```bash
systemctl status cisbot
journalctl -u cisbot -f
```

## 🔧 Дополнительные команды

### Проверка зависимостей:
```bash
cd /opt/cisbot2
sudo -u cisbot bash -c "source venv/bin/activate && python3 scripts/check_dependencies.py"
```

### Установка зависимостей:
```bash
cd /opt/cisbot2
sudo -u cisbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
```

### Просмотр логов:
```bash
# Последние логи
journalctl -u cisbot -n 50

# Следить за логами в реальном времени
journalctl -u cisbot -f

# Логи за последний час
journalctl -u cisbot --since "1 hour ago"
```

## 📞 Поддержка

Если возникли проблемы:

1. **Проверьте логи:** `journalctl -u cisbot -f`
2. **Проверьте статус:** `systemctl status cisbot`
3. **Проверьте права доступа:** `ls -la /opt/cisbot2/`
4. **Проверьте зависимости:** `python3 scripts/check_dependencies.py`

---

**Обновление завершено! Система модерации готова к работе.** 🎯
