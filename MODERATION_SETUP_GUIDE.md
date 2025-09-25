# 🛡️ Быстрое решение проблемы с модерацией

## ❌ Проблема: "ModuleNotFoundError: No module named 'aiosqlite'"

Эта ошибка возникает, когда на сервере не установлены зависимости Python.

## ✅ Решение

### Вариант 1: Использование серверного скрипта (Рекомендуется)

```bash
# Назначить супер-администратора
sudo bash scripts/setup_first_moderator_server.sh 405605039

# Назначить администратора
sudo bash scripts/setup_first_moderator_server.sh 405605039 admin

# Назначить модератора
sudo bash scripts/setup_first_moderator_server.sh 405605039 moderator
```

### Вариант 2: Ручная установка зависимостей

```bash
# Перейти в директорию бота
cd /opt/cisbot2

# Активировать виртуальное окружение
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Назначить модератора
python3 scripts/setup_first_moderator.py 405605039
```

### Вариант 3: Проверка и установка зависимостей

```bash
# Проверить зависимости
python3 scripts/check_dependencies.py

# Или установить автоматически
bash scripts/install_dependencies.sh
```

## 🔧 Что исправлено

1. **✅ Ошибка модерации:** Исправлена ошибка "name 'update' is not defined"
2. **✅ Скрипты установки:** Созданы скрипты для работы с виртуальным окружением
3. **✅ Проверка зависимостей:** Добавлена проверка и автоматическая установка

## 🚀 Быстрый старт

```bash
# 1. Назначить модератора
sudo bash scripts/setup_first_moderator_server.sh 405605039

# 2. Перезапустить бота
systemctl restart cisbot

# 3. Проверить статус
systemctl status cisbot

# 4. Проверить логи
journalctl -u cisbot -f
```

## 📋 Проверка работы

1. Пользователь с ID `405605039` запускает бота: `/start`
2. В главном меню появляется кнопка "👨‍💼 Модерация"
3. Модератор может модерировать профили

## 🆘 Если проблемы остаются

1. **Проверьте логи бота:**
   ```bash
   journalctl -u cisbot -f
   ```

2. **Проверьте права доступа:**
   ```bash
   ls -la /opt/cisbot2/
   ```

3. **Переустановите зависимости:**
   ```bash
   cd /opt/cisbot2
   source venv/bin/activate
   pip install --upgrade -r requirements.txt
   ```

4. **Проверьте базу данных:**
   ```bash
   ls -la /opt/cisbot2/data/
   ```

## 📞 Поддержка

Если проблемы не решаются, проверьте:
- Версию Python (должна быть 3.8+)
- Права доступа к файлам
- Статус сервиса systemd
- Логи системы

---

**Система модерации готова к работе!** 🎯
