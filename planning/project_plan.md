# ПЛАН РАЗРАБОТКИ CS2 TEAMMEET BOT

## 🎯 ЦЕЛЬ ПРОЕКТА
Создать Telegram бота для поиска тиммейтов в Counter-Strike 2 с системой анкет, взаимных лайков и интеллектуального матчинга.

## 📋 ЭТАПЫ РЕАЛИЗАЦИИ

### ЭТАП 1: БАЗОВАЯ НАСТРОЙКА (2-3 дня)
**Цель:** Развернуть базовую структуру проекта и запустить простейшего бота

#### Шаг 1.1: Структура проекта
```
CisBot2/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Точка входа
│   ├── config.py            # Конфигурация
│   ├── handlers/            # Обработчики команд
│   │   ├── __init__.py
│   │   ├── start.py         # /start команда
│   │   ├── profile.py       # Работа с профилем
│   │   └── search.py        # Поиск тиммейтов
│   ├── database/            # Работа с БД
│   │   ├── __init__.py
│   │   ├── models.py        # Модели данных
│   │   └── operations.py    # CRUD операции
│   ├── matching/            # Алгоритм матчинга
│   │   ├── __init__.py
│   │   └── algorithm.py
│   └── utils/               # Утилиты
│       ├── __init__.py
│       ├── cs2_data.py      # Данные CS2
│       └── keyboards.py     # Клавиатуры
├── data/
│   └── bot.db               # SQLite база
├── requirements.txt
├── .env                     # Переменные окружения
└── README.md
```

#### Шаг 1.2: Зависимости
```txt
python-telegram-bot>=20.7
python-dotenv>=1.0.0
```

#### Шаг 1.3: Базовый бот
- Настройка токена через BotFather
- Обработчик /start
- Основное меню с inline клавиатурой
- Логирование

### ЭТАП 2: СИСТЕМА ПРОФИЛЕЙ (3-4 дня)
**Цель:** Реализовать создание и редактирование анкет игроков

#### Шаг 2.1: База данных
```sql
-- Таблица пользователей
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица профилей
CREATE TABLE profiles (
    user_id INTEGER PRIMARY KEY,
    rank TEXT NOT NULL,          -- Ранг в CS2
    role TEXT NOT NULL,          -- Роль (AWPer, Entry, Support, IGL, Lurker)
    favorite_maps TEXT,          -- JSON массив карт
    playtime_start INTEGER,      -- Время начала игры (час)
    playtime_end INTEGER,        -- Время окончания игры (час)
    description TEXT,            -- Описание
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);
```

#### Шаг 2.2: Данные CS2
```python
# Ранги CS2
CS2_RANKS = [
    "Silver I", "Silver II", "Silver III", "Silver IV",
    "Silver Elite", "Silver Elite Master",
    "Gold Nova I", "Gold Nova II", "Gold Nova III", "Gold Nova Master",
    "Master Guardian I", "Master Guardian II", "Master Guardian Elite",
    "Distinguished Master Guardian",
    "Legendary Eagle", "Legendary Eagle Master", "Supreme Master First Class",
    "The Global Elite"
]

# Роли
CS2_ROLES = ["AWPer", "Entry Fragger", "Support", "IGL", "Lurker"]

# Карты
CS2_MAPS = [
    "Dust2", "Mirage", "Inferno", "Cache", "Overpass",
    "Cobblestone", "Train", "Nuke", "Vertigo", "Ancient"
]
```

#### Шаг 2.3: Функционал
- Создание анкеты (пошаговый диалог)
- Редактирование анкеты
- Просмотр своей анкеты
- Валидация данных

### ЭТАП 3: СИСТЕМА ЛАЙКОВ И МАТЧЕЙ (4-5 дней)
**Цель:** Реализовать систему взаимных лайков

#### Шаг 3.1: Расширение БД
```sql
-- Таблица лайков
CREATE TABLE likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
    FOREIGN KEY (to_user_id) REFERENCES users (user_id),
    UNIQUE(from_user_id, to_user_id)
);

-- Таблица матчей
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user1_id) REFERENCES users (user_id),
    FOREIGN KEY (user2_id) REFERENCES users (user_id)
);
```

#### Шаг 3.2: Функционал
- Показ анкет других игроков
- Кнопки "❤️ Лайк" и "❌ Пропустить"
- Автоматическое создание матча при взаимном лайке
- Уведомления о новых матчах
- Просмотр списка матчей

### ЭТАП 4: ИНТЕЛЛЕКТУАЛЬНЫЙ МАТЧИНГ (3-4 дня)
**Цель:** Реализовать алгоритм подбора совместимых игроков

#### Шаг 4.1: Алгоритм совместимости
```python
def calculate_compatibility(user1_profile, user2_profile):
    score = 0
    
    # Совпадение по рангу (±2 ранга = +30 очков)
    rank_diff = abs(get_rank_index(user1_profile.rank) - get_rank_index(user2_profile.rank))
    if rank_diff <= 2:
        score += 30 - (rank_diff * 5)
    
    # Совпадение по времени игры (+20 очков)
    if time_overlap(user1_profile, user2_profile):
        score += 20
    
    # Совпадение по картам (+10 очков за каждую общую карту)
    common_maps = set(user1_profile.favorite_maps) & set(user2_profile.favorite_maps)
    score += len(common_maps) * 10
    
    # Дополнительные роли (разные роли = +15 очков)
    if user1_profile.role != user2_profile.role:
        score += 15
    
    return min(score, 100)  # Максимум 100 очков
```

#### Шаг 4.2: Функционал
- Поиск по совместимости
- Фильтрация по параметрам
- Сортировка по рейтингу совместимости
- Умные рекомендации

### ЭТАП 5: РАСШИРЕННЫЙ ФУНКЦИОНАЛ (2-3 дня)
**Цель:** Добавить дополнительные возможности

#### Шаг 5.1: Дополнительные функции
- Фильтры поиска (ранг, карты, время)
- Статистика профиля
- Настройки уведомлений
- Система жалоб/блокировки
- Экспорт контактов матчей

#### Шаг 5.2: Улучшения UX
- Красивые карточки профилей
- Прогресс-бары совместимости
- Анимированные кнопки
- Подсказки и help

### ЭТАП 6: ТЕСТИРОВАНИЕ И ДЕПЛОЙ (2 дня)
**Цель:** Протестировать и развернуть бота

#### Шаг 6.1: Тестирование
- Unit тесты для алгоритма матчинга
- Интеграционные тесты БД
- Нагрузочное тестирование
- UX тестирование с реальными пользователями

#### Шаг 6.2: Деплой
- Настройка сервера
- Мониторинг и логирование
- Бэкапы базы данных
- Документация для пользователей

## 📊 ВРЕМЕННАЯ ОЦЕНКА
- **Общее время:** 16-21 день
- **Минимальная MVP версия:** 7-10 дней (Этапы 1-3)
- **Полная версия:** 16-21 день

## 🛠 ТЕХНИЧЕСКИЕ РЕШЕНИЯ

### Архитектурные принципы
1. **Модульность** - каждый компонент в отдельном модуле
2. **Асинхронность** - использование async/await для всех операций
3. **Обработка ошибок** - comprehensive error handling
4. **Логирование** - детальные логи для отладки
5. **Конфигурация** - все настройки через переменные окружения

### Паттерны проектирования
- **Handler Pattern** - для обработки команд Telegram
- **Repository Pattern** - для работы с базой данных  
- **Strategy Pattern** - для алгоритмов матчинга
- **Observer Pattern** - для уведомлений о матчах

## 🎯 КРИТЕРИИ УСПЕХА

### Функциональные требования
- [x] Создание и редактирование профилей
- [x] Система лайков и матчей
- [x] Интеллектуальный алгоритм подбора
- [x] Фильтрация по картам и другим параметрам

### Технические требования
- Время отклика < 2 сек
- Поддержка 1000+ пользователей
- 99.9% uptime
- Безопасность данных пользователей

### UX требования
- Интуитивная навигация
- Красивый интерфейс
- Быстрая работа
- Полезные уведомления

## 🚀 СЛЕДУЮЩИЕ ШАГИ
1. Настроить окружение разработки
2. Получить токен бота от @BotFather
3. Создать базовую структуру проекта
4. Реализовать минимальный рабочий бот
5. Итеративно добавлять функционал 