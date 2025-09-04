# 🎮 CS2 Teammeet Bot

**Telegram бот для поиска тиммейтов в Counter-Strike 2**

[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://t.me/cs2teammeet_bot)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)]()

## 🚀 **Функционал**

### ✅ **Система профилей**
- **ELO Faceit** - 18 рангов от Silver I до Global Elite  
- **5 ролей:** AWPer, Entry Fragger, Support Player, IGL, Lurker
- **7 актуальных карт:** Dust2, Mirage, Inferno, Cache, Overpass, Vertigo, Ancient
- **Время игры:** Утром, Днем, Вечером, Ночью
- **Медиа:** Фото и видео в анкетах

### 🔍 **Умный поиск тиммейтов**
- **Алгоритм совместимости** по 4 критериям:
  - **Ранг (40%)** - близость по ELO  
  - **Карты (20%)** - общие любимые карты
  - **Время (25%)** - совпадение времени игры
  - **Роль (15%)** - совместимость ролей
- **ELO фильтры:** 5 диапазонов (До 1999, 2000-2699, 2700-3099, 3100+, TOP 1000)
- **Категории поиска:** ММ/Премьер, Faceit, Турниры, Поиск команды

### ❤️ **Система лайков и матчинга**
- Кнопки **"Лайк"** и **"Пропустить"**
- **Автоматические матчи** при взаимных лайках  
- **Уведомления** о новых матчах
- **Контакты игроков** для связи

### 🛡️ **Модерация и безопасность**
- **Модерация анкет** перед публикацией
- **Панель модератора** с управлением ролями
- **Настройки приватности** (скрытие ELO, возраста, геолокации)
- **Блокировка пользователей**

## 🛠 **Технологии**

- **Python 3.10+** - основной язык
- **python-telegram-bot 22.3** - Telegram API  
- **aiosqlite** - асинхронная SQLite база данных
- **Асинхронная архитектура** - высокая производительность
- **Пул соединений** - оптимальная работа с БД

## 📦 **Установка и запуск**

### 🚀 **Быстрый старт (локально)**

```bash
# 1. Клонируем репозиторий
git clone https://github.com/Tw1zzzzz/CisBot2.git
cd CisBot2

# 2. Создаем виртуальное окружение  
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Устанавливаем зависимости
pip install -r requirements.txt

# 4. Создаем .env файл
copy .env.example .env  # Windows  
# cp .env.example .env  # Linux/Mac

# 5. Вставляем токен бота в .env
# BOT_TOKEN=ваш_токен_бота

# 6. Запускаем
python run_bot.py
```

### 🌐 **Деплой на сервер (продакшен)**

Подробная инструкция в [`planning/DEPLOYMENT_GUIDE.md`](planning/DEPLOYMENT_GUIDE.md)

**Автоматический деплой на Ubuntu:**
```bash
# Загружаем код на сервер
git clone https://github.com/Tw1zzzzz/CisBot2.git
cd CisBot2

# Запускаем автоматическую установку
chmod +x deploy.sh  
sudo ./deploy.sh

# Бот автоматически запустится как systemd сервис
```

## 📁 **Структура проекта**

```
CisBot2/
├── bot/                    # Основной код бота
│   ├── main.py            # Точка входа
│   ├── config.py          # Конфигурация
│   ├── handlers/          # Обработчики команд
│   ├── database/          # База данных
│   └── utils/             # Утилиты и данные CS2
├── planning/              # Документация (39 файлов)
├── deploy.sh             # Автоскрипт деплоя
├── cisbot.service        # Systemd конфигурация  
└── requirements.txt      # Python зависимости
```

## 🎯 **Использование**

### 👤 **Для пользователей:**
1. Найти бота: `@cs2teammeet_bot`
2. Запустить: `/start`  
3. Создать профиль с ELO и предпочтениями
4. Начать поиск: `/search`
5. Лайкать анкеты, получать матчи
6. Играть с найденными тиммейтами! 

### 👨‍💼 **Для администраторов:**
```bash
# Управление ботом
systemctl status cisbot    # Статус
systemctl restart cisbot   # Перезапуск  
journalctl -u cisbot -f    # Логи

# Добавление модераторов
/add_moderator @username
/list_moderators
```

## 📊 **Статистика проекта**

- **18,239 строк кода** - полнофункциональный бот
- **78 файлов** - модульная архитектура
- **39 MD файлов** - полная документация
- **100% готовность** - протестирован и готов к продакшену
- **4+ месяца разработки** - стабильная версия

## 🤝 **Вклад в проект**

Мы приветствуем вклад в развитие проекта!

1. Fork репозиторий
2. Создайте feature ветку (`git checkout -b feature/новая-фича`) 
3. Commit изменения (`git commit -m 'Добавил новую фичу'`)
4. Push в ветку (`git push origin feature/новая-фича`)
5. Создайте Pull Request

## 📄 **Лицензия**

Этот проект использует MIT лицензию. Подробности в файле [LICENSE](LICENSE).

## 📞 **Контакты**  

- **Разработчик:** Twizz_Project
- **Telegram:** [@cs2teammeet_bot](https://t.me/cs2teammeet_bot)
- **GitHub:** [Tw1zzzzz](https://github.com/Tw1zzzzz)

---

⭐ **Поставь звезду, если проект понравился!** ⭐