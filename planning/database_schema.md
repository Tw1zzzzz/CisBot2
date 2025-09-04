# СХЕМА БАЗЫ ДАННЫХ CS2 TEAMMEET BOT

## 📊 СТРУКТУРА ТАБЛИЦ

### 1. Таблица пользователей (users)
```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,           -- Telegram user ID
    username TEXT,                         -- @username
    first_name TEXT NOT NULL,              -- Имя пользователя
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE         -- Активен ли аккаунт
);
```

**Пример данных:**
```sql
INSERT INTO users VALUES 
(123456789, 'john_cs2', 'John', '2025-01-15 10:00:00', TRUE),
(987654321, 'maria_gamer', 'Maria', '2025-01-15 11:30:00', TRUE),
(555444333, NULL, 'Alex', '2025-01-15 12:15:00', TRUE);
```

### 2. Таблица профилей (profiles)
```sql
CREATE TABLE profiles (
    user_id INTEGER PRIMARY KEY,
    rank TEXT NOT NULL,                    -- Ранг в CS2
    role TEXT NOT NULL,                    -- Роль игрока
    favorite_maps TEXT,                    -- JSON массив любимых карт
    playtime_start INTEGER,                -- Час начала игры (0-23)
    playtime_end INTEGER,                  -- Час окончания игры (0-23)
    description TEXT,                      -- Описание от игрока
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);
```

**Пример данных:**
```sql
INSERT INTO profiles VALUES 
(123456789, 'Legendary Eagle', 'AWPer', '["Dust2", "Mirage", "Inferno"]', 18, 23, 'Играю агрессивно, люблю дальние дуэли', '2025-01-15 10:05:00', '2025-01-15 10:05:00'),
(987654321, 'Master Guardian II', 'Support', '["Mirage", "Cache", "Overpass"]', 14, 18, 'Командный игрок, хорошо играю в поддержке', '2025-01-15 11:35:00', '2025-01-15 11:35:00'),
(555444333, 'Gold Nova III', 'Entry Fragger', '["Dust2", "Inferno", "Train"]', 20, 24, 'Первым иду на сайт, быстрые решения', '2025-01-15 12:20:00', '2025-01-15 12:20:00');
```

### 3. Таблица лайков (likes)
```sql
CREATE TABLE likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,         -- Кто поставил лайк
    to_user_id INTEGER NOT NULL,           -- Кому поставили лайк
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
    FOREIGN KEY (to_user_id) REFERENCES users (user_id),
    UNIQUE(from_user_id, to_user_id)       -- Один лайк между пользователями
);
```

**Пример данных:**
```sql
INSERT INTO likes VALUES 
(1, 123456789, 987654321, '2025-01-15 15:00:00'),
(2, 987654321, 123456789, '2025-01-15 15:30:00'),  -- Взаимный лайк!
(3, 555444333, 123456789, '2025-01-15 16:00:00');
```

### 4. Таблица матчей (matches)
```sql
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,             -- Первый пользователь
    user2_id INTEGER NOT NULL,             -- Второй пользователь
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,        -- Активен ли матч
    FOREIGN KEY (user1_id) REFERENCES users (user_id),
    FOREIGN KEY (user2_id) REFERENCES users (user_id)
);
```

**Пример данных:**
```sql
INSERT INTO matches VALUES 
(1, 123456789, 987654321, '2025-01-15 15:30:01', TRUE);  -- Создался после взаимного лайка
```

### 5. Таблица настроек пользователей (user_settings)
```sql
CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY,
    search_radius INTEGER DEFAULT 3,       -- ±N рангов для поиска
    notifications_enabled BOOLEAN DEFAULT TRUE,
    preferred_maps TEXT,                   -- JSON массив предпочитаемых карт для фильтра
    max_matches_per_day INTEGER DEFAULT 20, -- Лимит показов анкет в день
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);
```

**Пример данных:**
```sql
INSERT INTO user_settings VALUES 
(123456789, 2, TRUE, '["Dust2", "Mirage"]', 15),
(987654321, 3, TRUE, NULL, 20),
(555444333, 4, FALSE, '["Dust2", "Inferno", "Train", "Cache"]', 25);
```

## 🗂 ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ

```sql
-- Индексы для быстрого поиска лайков
CREATE INDEX idx_likes_from_user ON likes (from_user_id);
CREATE INDEX idx_likes_to_user ON likes (to_user_id);
CREATE INDEX idx_likes_created_at ON likes (created_at);

-- Индексы для поиска матчей
CREATE INDEX idx_matches_user1 ON matches (user1_id);
CREATE INDEX idx_matches_user2 ON matches (user2_id);
CREATE INDEX idx_matches_active ON matches (is_active);

-- Индексы для поиска профилей
CREATE INDEX idx_profiles_rank ON profiles (rank);
CREATE INDEX idx_profiles_role ON profiles (role);
CREATE INDEX idx_profiles_updated ON profiles (updated_at);

-- Составной индекс для поиска по времени игры
CREATE INDEX idx_profiles_playtime ON profiles (playtime_start, playtime_end);
```

## 📋 ПРЕДСТАВЛЕНИЯ (VIEWS)

### 1. Полная информация о профилях
```sql
CREATE VIEW profile_full AS
SELECT 
    u.user_id,
    u.username,
    u.first_name,
    p.rank,
    p.role,
    p.favorite_maps,
    p.playtime_start,
    p.playtime_end,
    p.description,
    p.updated_at,
    us.search_radius,
    us.notifications_enabled
FROM users u
JOIN profiles p ON u.user_id = p.user_id
LEFT JOIN user_settings us ON u.user_id = us.user_id
WHERE u.is_active = TRUE;
```

### 2. Статистика матчей пользователя
```sql
CREATE VIEW user_match_stats AS
SELECT 
    u.user_id,
    u.username,
    u.first_name,
    COUNT(CASE WHEN l.from_user_id = u.user_id THEN 1 END) as likes_given,
    COUNT(CASE WHEN l.to_user_id = u.user_id THEN 1 END) as likes_received,
    COUNT(CASE WHEN m.user1_id = u.user_id OR m.user2_id = u.user_id THEN 1 END) as total_matches
FROM users u
LEFT JOIN likes l ON (l.from_user_id = u.user_id OR l.to_user_id = u.user_id)
LEFT JOIN matches m ON (m.user1_id = u.user_id OR m.user2_id = u.user_id)
WHERE u.is_active = TRUE
GROUP BY u.user_id, u.username, u.first_name;
```

## 🔍 ПОЛЕЗНЫЕ ЗАПРОСЫ

### 1. Поиск кандидатов для матчинга
```sql
-- Найти всех пользователей, которым текущий пользователь еще не ставил лайк
SELECT p.*, u.username, u.first_name
FROM profile_full p
JOIN users u ON p.user_id = u.user_id
WHERE p.user_id != ?  -- Не самого себя
  AND p.user_id NOT IN (
      SELECT to_user_id 
      FROM likes 
      WHERE from_user_id = ?
  )
  AND u.is_active = TRUE
ORDER BY p.updated_at DESC
LIMIT 20;
```

### 2. Проверка взаимного лайка
```sql
-- Проверить, есть ли взаимный лайк между двумя пользователями
SELECT 
    l1.from_user_id as user1,
    l1.to_user_id as user2,
    l2.from_user_id as user2_back,
    l2.to_user_id as user1_back
FROM likes l1
JOIN likes l2 ON l1.from_user_id = l2.to_user_id 
              AND l1.to_user_id = l2.from_user_id
WHERE l1.from_user_id = ? AND l1.to_user_id = ?;
```

### 3. Поиск по совместимости рангов
```sql
-- Найти игроков с похожим рангом (в пределах radius)
WITH rank_mapping AS (
  SELECT 'Silver I' as rank, 0 as rank_index UNION ALL
  SELECT 'Silver II', 1 UNION ALL
  SELECT 'Silver III', 2 UNION ALL
  SELECT 'Silver IV', 3 UNION ALL
  SELECT 'Silver Elite', 4 UNION ALL
  SELECT 'Silver Elite Master', 5 UNION ALL
  SELECT 'Gold Nova I', 6 UNION ALL
  SELECT 'Gold Nova II', 7 UNION ALL
  SELECT 'Gold Nova III', 8 UNION ALL
  SELECT 'Gold Nova Master', 9 UNION ALL
  SELECT 'Master Guardian I', 10 UNION ALL
  SELECT 'Master Guardian II', 11 UNION ALL
  SELECT 'Master Guardian Elite', 12 UNION ALL
  SELECT 'Distinguished Master Guardian', 13 UNION ALL
  SELECT 'Legendary Eagle', 14 UNION ALL
  SELECT 'Legendary Eagle Master', 15 UNION ALL
  SELECT 'Supreme Master First Class', 16 UNION ALL
  SELECT 'The Global Elite', 17
)
SELECT p.*, ABS(rm1.rank_index - rm2.rank_index) as rank_difference
FROM profiles p
JOIN rank_mapping rm1 ON p.rank = rm1.rank
JOIN rank_mapping rm2 ON rm2.rank = (SELECT rank FROM profiles WHERE user_id = ?)
WHERE p.user_id != ?
  AND ABS(rm1.rank_index - rm2.rank_index) <= 3  -- В пределах 3 рангов
ORDER BY rank_difference ASC;
```

## 🔄 МИГРАЦИИ

### Версия 1.0 → 1.1: Добавление статистики
```sql
-- Добавить таблицу для отслеживания активности
CREATE TABLE user_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,  -- 'login', 'like', 'match', 'profile_update'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON с дополнительной информацией
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_activity_user ON user_activity (user_id);
CREATE INDEX idx_activity_type ON user_activity (action_type);
CREATE INDEX idx_activity_date ON user_activity (created_at);
```

### Версия 1.1 → 1.2: Система блокировок
```sql
-- Добавить таблицу для блокировок пользователей
CREATE TABLE user_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blocker_id INTEGER NOT NULL,    -- Кто заблокировал
    blocked_id INTEGER NOT NULL,    -- Кого заблокировали
    reason TEXT,                    -- Причина блокировки
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (blocker_id) REFERENCES users (user_id),
    FOREIGN KEY (blocked_id) REFERENCES users (user_id),
    UNIQUE(blocker_id, blocked_id)
);

CREATE INDEX idx_blocks_blocker ON user_blocks (blocker_id);
CREATE INDEX idx_blocks_blocked ON user_blocks (blocked_id);
```

## 📈 АНАЛИТИЧЕСКИЕ ЗАПРОСЫ

### 1. Популярность рангов
```sql
SELECT rank, COUNT(*) as count
FROM profiles
GROUP BY rank
ORDER BY count DESC;
```

### 2. Популярность карт
```sql
-- Требует обработки JSON в приложении
SELECT 
    json_extract(favorite_maps, '$[0]') as map1,
    json_extract(favorite_maps, '$[1]') as map2,
    json_extract(favorite_maps, '$[2]') as map3
FROM profiles;
```

### 3. Активность по дням
```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) as new_users
FROM users
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### 4. Коэффициент матчинга
```sql
SELECT 
    COUNT(DISTINCT l.from_user_id) as users_with_likes,
    COUNT(*) as total_likes,
    COUNT(DISTINCT m.id) as total_matches,
    ROUND(COUNT(DISTINCT m.id) * 100.0 / COUNT(*), 2) as match_rate_percent
FROM likes l
LEFT JOIN matches m ON (
    (l.from_user_id = m.user1_id AND l.to_user_id = m.user2_id) OR
    (l.from_user_id = m.user2_id AND l.to_user_id = m.user1_id)
);
``` 