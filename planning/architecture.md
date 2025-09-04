# АРХИТЕКТУРА CS2 TEAMMEET BOT

## 🏗 ОБЩАЯ АРХИТЕКТУРА

### Архитектурный стиль
**Модульная архитектура** с разделением на слои:
- **Presentation Layer** - Telegram Bot Handlers  
- **Business Logic Layer** - Matching Algorithm, Profile Management
- **Data Access Layer** - Database Operations
- **Infrastructure Layer** - Configuration, Logging, Utils

```
┌─────────────────────────────────────────┐
│           TELEGRAM BOT API              │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│         HANDLERS LAYER                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ Start   │ │ Profile │ │ Search  │   │
│  │Handler  │ │Handler  │ │Handler  │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│       BUSINESS LOGIC LAYER              │
│  ┌─────────────┐ ┌───────────────────┐  │
│  │   Profile   │ │    Matching       │  │
│  │  Service    │ │   Algorithm       │  │
│  └─────────────┘ └───────────────────┘  │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│        DATA ACCESS LAYER                │
│  ┌─────────────┐ ┌───────────────────┐  │
│  │   User      │ │     Match         │  │
│  │ Repository  │ │   Repository      │  │
│  └─────────────┘ └───────────────────┘  │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│           SQLITE DATABASE               │
└─────────────────────────────────────────┘
```

## 📦 МОДУЛИ И КОМПОНЕНТЫ

### 1. Bot Core (`bot/`)
```python
# main.py - Точка входа приложения
class CSBot:
    def __init__(self):
        self.application = Application.builder().token(TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Регистрация всех обработчиков
        pass
    
    def run(self):
        self.application.run_polling()
```

### 2. Handlers (`bot/handlers/`)
```python
# Базовый класс для всех обработчиков
class BaseHandler:
    def __init__(self, db_manager):
        self.db = db_manager
    
    async def handle_error(self, update, context, error):
        # Общая обработка ошибок
        pass

# start.py
class StartHandler(BaseHandler):
    async def start_command(self, update, context):
        # Обработка /start команды
        pass
    
    async def show_main_menu(self, update, context):
        # Показ главного меню
        pass

# profile.py  
class ProfileHandler(BaseHandler):
    async def create_profile(self, update, context):
        # Создание профиля
        pass
    
    async def edit_profile(self, update, context):
        # Редактирование профиля
        pass

# search.py
class SearchHandler(BaseHandler):
    async def start_search(self, update, context):
        # Начало поиска тиммейтов
        pass
    
    async def handle_like(self, update, context):
        # Обработка лайка
        pass
```

### 3. Database Layer (`bot/database/`)
```python
# models.py
@dataclass
class User:
    user_id: int
    username: str
    first_name: str
    created_at: datetime
    is_active: bool = True

@dataclass  
class Profile:
    user_id: int
    rank: str
    role: str
    favorite_maps: List[str]
    playtime_start: int
    playtime_end: int
    description: str
    
@dataclass
class Match:
    user1_id: int
    user2_id: int
    created_at: datetime
    is_active: bool = True

# operations.py
class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    async def create_user(self, user: User) -> bool:
        # Создание пользователя
        pass
    
    async def get_profile(self, user_id: int) -> Optional[Profile]:
        # Получение профиля
        pass
    
    async def create_like(self, from_user: int, to_user: int) -> Optional[Match]:
        # Создание лайка и проверка на матч
        pass
```

### 4. Matching Algorithm (`bot/matching/`)
```python
# algorithm.py
class MatchingAlgorithm:
    def calculate_compatibility(self, profile1: Profile, profile2: Profile) -> int:
        """
        Расчет совместимости между двумя профилями
        Возвращает score от 0 до 100
        """
        score = 0
        
        # Алгоритм расчета совместимости
        score += self._rank_compatibility(profile1.rank, profile2.rank)
        score += self._time_compatibility(profile1, profile2) 
        score += self._maps_compatibility(profile1.favorite_maps, profile2.favorite_maps)
        score += self._role_compatibility(profile1.role, profile2.role)
        
        return min(score, 100)
    
    def find_best_matches(self, user_profile: Profile, candidates: List[Profile], limit: int = 10) -> List[Tuple[Profile, int]]:
        """
        Поиск лучших матчей для пользователя
        Возвращает список кортежей (профиль, совместимость)
        """
        matches = []
        for candidate in candidates:
            compatibility = self.calculate_compatibility(user_profile, candidate)
            matches.append((candidate, compatibility))
        
        # Сортировка по совместимости
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]
```

### 5. Utils (`bot/utils/`)
```python
# cs2_data.py
CS2_RANKS = [
    {"name": "Silver I", "index": 0},
    {"name": "Silver II", "index": 1},
    # ... остальные ранги
]

CS2_MAPS = [
    "Dust2", "Mirage", "Inferno", "Cache", 
    "Overpass", "Train", "Nuke", "Vertigo", "Ancient"
]

CS2_ROLES = [
    "AWPer", "Entry Fragger", "Support", 
    "IGL (In-Game Leader)", "Lurker"
]

# keyboards.py
class Keyboards:
    @staticmethod
    def main_menu():
        keyboard = [
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("🔍 Поиск тиммейтов", callback_data="search")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def like_buttons():
        keyboard = [
            [InlineKeyboardButton("❤️ Лайк", callback_data="like"),
             InlineKeyboardButton("❌ Пропустить", callback_data="skip")]
        ]
        return InlineKeyboardMarkup(keyboard)
```

## 🗃 СХЕМА БАЗЫ ДАННЫХ

### Основные таблицы

```sql
-- Пользователи
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Профили игроков
CREATE TABLE profiles (
    user_id INTEGER PRIMARY KEY,
    rank TEXT NOT NULL,
    role TEXT NOT NULL,
    favorite_maps TEXT, -- JSON массив
    playtime_start INTEGER, -- час начала игры
    playtime_end INTEGER,   -- час окончания игры
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Лайки
CREATE TABLE likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
    FOREIGN KEY (to_user_id) REFERENCES users (user_id),
    UNIQUE(from_user_id, to_user_id)
);

-- Матчи (взаимные лайки)
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user1_id) REFERENCES users (user_id),
    FOREIGN KEY (user2_id) REFERENCES users (user_id)
);

-- Настройки пользователей
CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY,
    search_radius INTEGER DEFAULT 3, -- ±3 ранга
    notifications_enabled BOOLEAN DEFAULT TRUE,
    preferred_maps TEXT, -- JSON массив предпочитаемых карт
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);
```

### Индексы для производительности
```sql
CREATE INDEX idx_likes_from_user ON likes (from_user_id);
CREATE INDEX idx_likes_to_user ON likes (to_user_id);
CREATE INDEX idx_matches_user1 ON matches (user1_id);
CREATE INDEX idx_matches_user2 ON matches (user2_id);
CREATE INDEX idx_profiles_rank ON profiles (rank);
```

## 🔄 ПОТОК ДАННЫХ

### 1. Создание профиля
```
User → /start → StartHandler → show_main_menu → 
User clicks "Профиль" → ProfileHandler → create_profile → 
Multi-step dialog → DatabaseManager → SQLite
```

### 2. Поиск тиммейтов
```
User clicks "Поиск" → SearchHandler → MatchingAlgorithm → 
get_candidates → calculate_compatibility → 
show_profile_card → User reaction → handle_like/skip
```

### 3. Обработка лайка
```
User clicks "❤️" → SearchHandler.handle_like → 
DatabaseManager.create_like → check_mutual_like → 
if mutual: create_match + send_notifications
```

## 🛡 БЕЗОПАСНОСТЬ И ПРОИЗВОДИТЕЛЬНОСТЬ

### Безопасность
- Валидация всех пользовательских данных
- SQL инъекции защита через параметризованные запросы
- Rate limiting для предотвращения спама
- Логирование всех действий пользователей

### Производительность  
- Индексы на часто используемые поля
- Кэширование популярных запросов
- Асинхронные операции с БД
- Batch операции для массовых действий

### Масштабируемость
- Модульная архитектура для легкого расширения
- Возможность миграции на PostgreSQL при росте
- Горизонтальное масштабирование через sharding пользователей
- Использование Redis для кэширования и сессий

## 🔧 КОНФИГУРАЦИЯ

### Environment Variables
```bash
# Bot configuration
BOT_TOKEN=your_bot_token_here
BOT_USERNAME=your_bot_username

# Database
DATABASE_PATH=data/bot.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log

# Matching algorithm
MAX_SEARCH_RESULTS=20
COMPATIBILITY_THRESHOLD=30
```

### Feature Flags
```python
class Config:
    ENABLE_NOTIFICATIONS = True
    ENABLE_ADVANCED_MATCHING = True
    ENABLE_PROFILE_PHOTOS = False  # Будущая функция
    MAX_DAILY_LIKES = 50
    COOLDOWN_BETWEEN_LIKES = 1  # секунды
``` 