"""
Данные Counter-Strike 2: ELO Faceit, роли, карты
Создано организацией Twizz_Project для CIS FINDER Bot
"""

FACEIT_ELO_RANGES = [
    {"name": "1-500 ELO", "min_elo": 1, "max_elo": 500, "level": 1, "emoji": "🟫"},
    {"name": "501-750 ELO", "min_elo": 501, "max_elo": 750, "level": 2, "emoji": "🟫"},
    {"name": "751-900 ELO", "min_elo": 751, "max_elo": 900, "level": 3, "emoji": "🟤"},
    {"name": "901-1050 ELO", "min_elo": 901, "max_elo": 1050, "level": 4, "emoji": "🟤"},
    {"name": "1051-1200 ELO", "min_elo": 1051, "max_elo": 1200, "level": 5, "emoji": "🟡"},
    {"name": "1201-1350 ELO", "min_elo": 1201, "max_elo": 1350, "level": 6, "emoji": "🟡"},
    {"name": "1351-1500 ELO", "min_elo": 1351, "max_elo": 1500, "level": 7, "emoji": "🟠"},
    {"name": "1501-1650 ELO", "min_elo": 1501, "max_elo": 1650, "level": 8, "emoji": "🟠"},
    {"name": "1651-1800 ELO", "min_elo": 1651, "max_elo": 1800, "level": 9, "emoji": "🔴"},
    {"name": "1801+ ELO", "min_elo": 1801, "max_elo": 9999, "level": 10, "emoji": "🔴"}
]

# Новые фильтры ELO по диапазонам
ELO_FILTER_RANGES = [
    {"id": "newbie", "name": "До 1999 ELO", "emoji": "🔰", "max_elo": 1999},
    {"id": "intermediate", "name": "2000-2699 ELO", "emoji": "⭐", "min_elo": 2000, "max_elo": 2699},
    {"id": "advanced", "name": "2700-3099 ELO", "emoji": "🏆", "min_elo": 2700, "max_elo": 3099},
    {"id": "pro", "name": "3100+ ELO", "emoji": "💎", "min_elo": 3100},
    {"id": "top_1000", "name": "TOP 1000", "emoji": "👑", "description": "Лучшие игроки сервера"}
]

# Категории для анкет
PROFILE_CATEGORIES = [
    {"id": "mm_premier", "name": "ММ/ПРЕМЬЕР/НАПАРНИКИ", "emoji": "🎮", "description": "Поиск игроков для матчмейкинга, премьера и напарников"},
    {"id": "faceit", "name": "Faceit", "emoji": "🎯", "description": "Игра на платформе Faceit"},
    {"id": "tournaments", "name": "Турниры", "emoji": "🏆", "description": "Участие в турнирах и соревнованиях"},
    {"id": "looking_for_team", "name": "Ищу команду", "emoji": "👥", "description": "Поиск постоянной команды"}
]

CS2_ROLES = [
    {"name": "IGL", "description": "Лидер команды", "emoji": "👑"},
    {"name": "Entry Fragger", "description": "Первый на вход", "emoji": "⚡"},
    {"name": "Support Player", "description": "Поддержка команды", "emoji": "🛡️"},
    {"name": "Lurker", "description": "Скрытный игрок", "emoji": "🥷"},
    {"name": "AWPer", "description": "Снайпер команды", "emoji": "🎯"}
]

CS2_MAPS = [
    {"name": "Ancient", "emoji": "🗿"},
    {"name": "Dust2", "emoji": "🏜️"},
    {"name": "Inferno", "emoji": "🔥"},
    {"name": "Mirage", "emoji": "🏛️"},
    {"name": "Nuke", "emoji": "☢️"},
    {"name": "Overpass", "emoji": "🌉"},
    {"name": "Train", "emoji": "🚂"}
]

PLAYTIME_OPTIONS = [
    {"name": "Утром (6-12)", "id": "morning", "start": 6, "end": 12, "emoji": "🌅"},
    {"name": "Днем (12-18)", "id": "day", "start": 12, "end": 18, "emoji": "☀️"},
    {"name": "Вечером (18-24)", "id": "evening", "start": 18, "end": 24, "emoji": "🌆"},
    {"name": "Ночью (0-6)", "id": "night", "start": 0, "end": 6, "emoji": "🌙"}
]

def get_elo_range_by_elo(elo: int) -> dict:
    """Получает диапазон ELO по значению ELO"""
    return next((elo_range for elo_range in FACEIT_ELO_RANGES 
                if elo_range["min_elo"] <= elo <= elo_range["max_elo"]), None)



def get_elo_filter_by_id(filter_id: str) -> dict:
    """Получает ELO фильтр по ID"""
    return next((elo_filter for elo_filter in ELO_FILTER_RANGES if elo_filter["id"] == filter_id), None)

def check_elo_in_filter(elo: int, filter_id: str) -> bool:
    """Проверяет попадает ли ELO в фильтр"""
    if filter_id == "any":
        return True
    
    elo_filter = get_elo_filter_by_id(filter_id)
    if not elo_filter:
        return True
    
    # Проверяем минимальное и максимальное значение
    min_elo = elo_filter.get("min_elo", 0)
    max_elo = elo_filter.get("max_elo", 99999)
    
    return min_elo <= elo <= max_elo

def format_elo_filter_display(filter_id: str) -> str:
    """Форматирует отображение ELO фильтра"""
    if filter_id == "any":
        return "🎯 Любой ELO"
    
    elo_filter = get_elo_filter_by_id(filter_id)
    if elo_filter:
        return f"{elo_filter['emoji']} {elo_filter['name']}"
    
    return "🎯 Любой ELO"

def validate_faceit_url(url: str) -> bool:
    """Проверяет корректность ссылки на Faceit профиль"""
    import re
    pattern = r'https://www\.faceit\.com/[a-z]{2}/players/[a-zA-Z0-9_-]+'
    return bool(re.match(pattern, url))

def extract_faceit_nickname(url: str) -> str:
    """Извлекает никнейм из ссылки на Faceit"""
    import re
    match = re.search(r'/players/([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else ""

def get_role_by_name(role_name: str) -> dict:
    """Получает данные роли по имени"""
    return next((role for role in CS2_ROLES if role["name"] == role_name), None)

def get_map_by_name(map_name: str) -> dict:
    """Получает данные карты по имени"""
    return next((map_data for map_data in CS2_MAPS if map_data["name"] == map_name), None)

def get_playtime_by_range(start: int, end: int) -> dict:
    """Получает данные времени игры по диапазону"""
    return next((time for time in PLAYTIME_OPTIONS if time["start"] == start and time["end"] == end), None)

def format_elo_display(elo: int) -> str:
    """Форматирует отображение ELO с эмодзи"""
    elo_range = get_elo_range_by_elo(elo)
    if elo_range:
        return f"{elo_range['emoji']} {elo} ELO (Level {elo_range['level']})"
    return f"❓ {elo} ELO"

def format_faceit_display(elo: int, faceit_url: str) -> str:
    """Форматирует отображение Faceit профиля"""
    nickname = extract_faceit_nickname(faceit_url)
    elo_display = format_elo_display(elo)
    return f"{elo_display}\n🔗 [Faceit: {nickname}]({faceit_url})"

def format_role_display(role_name: str) -> str:
    """Форматирует отображение роли с эмодзи"""
    role = get_role_by_name(role_name)
    if role:
        return f"{role['emoji']} {role['name']}"
    return f"❓ {role_name}"

def format_map_display(map_name: str) -> str:
    """Форматирует отображение карты с эмодзи"""
    map_data = get_map_by_name(map_name)
    if map_data:
        return f"{map_data['emoji']} {map_data['name']}"
    return f"📍 {map_name}"

def format_playtime_display(start: int, end: int) -> str:
    """Форматирует отображение времени игры"""
    time_data = get_playtime_by_range(start, end)
    if time_data:
        return f"{time_data['emoji']} {time_data['name']}"
    return f"⏰ {start:02d}:00 - {end:02d}:00"

def format_maps_list(maps: list, max_count: int = 3) -> str:
    """Форматирует список карт для отображения"""
    if not maps:
        return "❌ Карты не выбраны"
    
    formatted_maps = []
    for i, map_name in enumerate(maps):
        if i >= max_count:
            break
        formatted_maps.append(format_map_display(map_name))
    
    result = ", ".join(formatted_maps)
    if len(maps) > max_count:
        result += f" и еще {len(maps) - max_count}"
    
    return result

def get_elo_compatibility(elo1: int, elo2: int) -> float:
    """Вычисляет совместимость ELO (0.0 - 1.0)"""
    # Разница в ELO
    diff = abs(elo1 - elo2)
    
    # Максимальная совместимость при разнице 0-100 ELO
    if diff <= 100:
        return 1.0
    elif diff <= 200:
        return 0.8
    elif diff <= 350:
        return 0.6
    elif diff <= 500:
        return 0.4
    else:
        return 0.2

def get_maps_compatibility(maps1: list, maps2: list) -> float:
    """Вычисляет совместимость по картам (0.0 - 1.0)"""
    if not maps1 or not maps2:
        return 0.0
    
    common_maps = set(maps1) & set(maps2)
    total_maps = set(maps1) | set(maps2)
    
    if not total_maps:
        return 0.0
    
    return len(common_maps) / len(total_maps)

def get_time_compatibility(slots1: list, slots2: list) -> float:
    """Вычисляет совместимость по временным слотам (0.0 - 1.0)"""
    if not slots1 or not slots2:
        return 0.0
    
    # Находим пересечение временных слотов
    common_slots = set(slots1) & set(slots2)
    total_slots = set(slots1) | set(slots2)
    
    if not total_slots:
        return 0.0
    
    return len(common_slots) / len(total_slots)

def calculate_profile_compatibility(profile1, profile2) -> dict:
    """Вычисляет общую совместимость профилей"""
    elo_compat = get_elo_compatibility(profile1.faceit_elo, profile2.faceit_elo)
    maps_compat = get_maps_compatibility(profile1.favorite_maps, profile2.favorite_maps)
    time_compat = get_time_compatibility(profile1.playtime_slots, profile2.playtime_slots)
    
    # Совместимость ролей (простая проверка)
    role_compat = 1.0 if profile1.role != profile2.role else 0.7
    
    # Веса для разных факторов
    weights = {
        'elo': 0.4,
        'maps': 0.2,
        'time': 0.25,
        'role': 0.15
    }
    
    total_compatibility = (
        elo_compat * weights['elo'] +
        maps_compat * weights['maps'] +
        time_compat * weights['time'] +
        role_compat * weights['role']
    )
    
    return {
        'total': round(total_compatibility * 100),
        'details': {
            'elo': round(elo_compat * 100),
            'maps': round(maps_compat * 100),
            'time': round(time_compat * 100),
            'role': round(role_compat * 100)
        }
    }

# === ФУНКЦИИ ДЛЯ РАБОТЫ С КАТЕГОРИЯМИ ===

def get_category_by_id(category_id: str) -> dict:
    """Получает данные категории по ID"""
    return next((category for category in PROFILE_CATEGORIES if category["id"] == category_id), None)

def format_categories_display(categories: list, max_count: int = 3) -> str:
    """Форматирует список категорий для отображения"""
    if not categories:
        return "❌ Категории не выбраны"
    
    formatted_categories = []
    for i, category_id in enumerate(categories):
        if i >= max_count:
            break
        category = get_category_by_id(category_id)
        if category:
            formatted_categories.append(f"{category['emoji']} {category['name']}")
        else:
            formatted_categories.append(f"❓ {category_id}")
    
    result = ", ".join(formatted_categories)
    if len(categories) > max_count:
        result += f" и еще {len(categories) - max_count}"
    
    return result

def format_category_display(category_id: str) -> str:
    """Форматирует отображение одной категории с эмодзи"""
    category = get_category_by_id(category_id)
    if category:
        return f"{category['emoji']} {category['name']}"
    return f"❓ {category_id}"

def validate_categories(categories: list) -> bool:
    """Проверяет корректность списка категорий"""
    if not categories or not isinstance(categories, list):
        return False
    
    # Проверяем что все категории существуют
    valid_category_ids = [cat["id"] for cat in PROFILE_CATEGORIES]
    return all(cat_id in valid_category_ids for cat_id in categories)

def get_categories_compatibility(categories1: list, categories2: list) -> float:
    """Вычисляет совместимость по категориям (0.0 - 1.0)"""
    if not categories1 or not categories2:
        return 0.0
    
    common_categories = set(categories1) & set(categories2)
    total_categories = set(categories1) | set(categories2)
    
    if not total_categories:
        return 0.0
    
    return len(common_categories) / len(total_categories) 