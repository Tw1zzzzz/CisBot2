"""
Модели данных для CIS FINDER Bot
Создано организацией Twizz_Project
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from ..utils.security_validator import security_validator

@dataclass
class User:
    """Модель пользователя"""
    user_id: int
    username: Optional[str]
    first_name: str
    created_at: datetime
    is_active: bool = True
    
    def __post_init__(self):
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)

@dataclass  
class Profile:
    """Модель профиля игрока"""
    user_id: int
    game_nickname: str  # Игровой ник игрока
    faceit_elo: int
    faceit_url: str
    role: str
    favorite_maps: List[str]
    playtime_slots: List[str]  # Список ID временных слотов: ["morning", "evening"]
    categories: List[str]  # Список ID категорий: ["mm_premier", "faceit"]
    description: Optional[str]
    media_type: Optional[str] = None  # photo/video/null
    media_file_id: Optional[str] = None  # file_id из Telegram
    moderation_status: str = 'pending'  # pending/approved/rejected
    moderation_reason: Optional[str] = None
    moderated_by: Optional[int] = None
    moderated_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        # Парсим даты
        for field in ['created_at', 'updated_at', 'moderated_at']:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, datetime.fromisoformat(value))
        
        # Безопасный парсинг JSON полей с валидацией схемы
        logger = logging.getLogger(__name__)
        secure_logger = security_validator.get_secure_logger(__name__)
        
        # Схемы валидации для JSON полей
        list_schema = {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 50
        }
        
        # Безопасный парсинг favorite_maps
        if isinstance(self.favorite_maps, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.favorite_maps, 
                schema=list_schema, 
                default=[]
            )
            if validation_result.is_valid:
                self.favorite_maps = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации favorite_maps для user_id={self.user_id}: {validation_result.error_message}")
                self.favorite_maps = []
        
        # Безопасный парсинг playtime_slots
        if isinstance(self.playtime_slots, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.playtime_slots, 
                schema=list_schema, 
                default=[]
            )
            if validation_result.is_valid:
                self.playtime_slots = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации playtime_slots для user_id={self.user_id}: {validation_result.error_message}")
                self.playtime_slots = []
        
        # Безопасный парсинг categories
        if isinstance(self.categories, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.categories, 
                schema=list_schema, 
                default=[]
            )
            if validation_result.is_valid:
                self.categories = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации categories для user_id={self.user_id}: {validation_result.error_message}")
                self.categories = []
    
    def is_approved(self) -> bool:
        """Проверяет, одобрен ли профиль модератором"""
        return self.moderation_status == 'approved'
    
    def is_pending(self) -> bool:
        """Проверяет, ожидает ли профиль модерации"""
        return self.moderation_status == 'pending'
    
    def is_rejected(self) -> bool:
        """Проверяет, отклонен ли профиль"""
        return self.moderation_status == 'rejected'
    
    def has_media(self) -> bool:
        """Проверяет, есть ли у профиля медиа"""
        return self.media_type is not None and self.media_file_id is not None
    
    def is_photo(self) -> bool:
        """Проверяет, является ли медиа фотографией"""
        return self.media_type == 'photo'
    
    def is_video(self) -> bool:
        """Проверяет, является ли медиа видео"""
        return self.media_type == 'video'

@dataclass
class Like:
    """Модель лайка"""
    id: Optional[int]
    from_user_id: int
    to_user_id: int
    created_at: datetime
    
    def __post_init__(self):
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)

@dataclass
class Match:
    """Модель тиммейта (взаимный лайк)"""
    id: Optional[int]
    user1_id: int
    user2_id: int
    created_at: datetime
    is_active: bool = True
    
    def __post_init__(self):
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)

@dataclass
class UserSettings:
    """Модель настроек пользователя"""
    user_id: int
    notifications_enabled: bool = True
    search_filters: Optional[dict] = None
    privacy_settings: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        # Безопасный парсинг JSON полей с валидацией
        secure_logger = security_validator.get_secure_logger(__name__)
        
        # Схемы валидации для настроек
        search_filters_schema = {
            "type": "object",
            "properties": {
                "elo_filter": {"type": "string", "enum": ["lower", "similar", "higher", "any"]},
                "preferred_roles": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                "maps_compatibility": {"type": "string", "enum": ["strict", "moderate", "soft", "any"]},
                "time_compatibility": {"type": "string", "enum": ["strict", "soft", "any"]},
                "min_compatibility": {"type": "integer", "minimum": 0, "maximum": 100},
                "max_candidates": {"type": "integer", "minimum": 1, "maximum": 100}
            }
        }
        
        privacy_settings_schema = {
            "type": "object",
            "properties": {
                "notifications": {"type": "object"},
                "profile_visibility": {"type": "string", "enum": ["public", "private", "friends"]},
                "data_sharing": {"type": "boolean"}
            }
        }
        
        # Безопасный парсинг search_filters
        if isinstance(self.search_filters, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.search_filters, 
                schema=search_filters_schema, 
                default={}
            )
            if validation_result.is_valid:
                self.search_filters = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации search_filters: {validation_result.error_message}")
                self.search_filters = {}
        elif self.search_filters is None:
            self.search_filters = {}
            
        # Безопасный парсинг privacy_settings
        if isinstance(self.privacy_settings, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.privacy_settings, 
                schema=privacy_settings_schema, 
                default={}
            )
            if validation_result.is_valid:
                self.privacy_settings = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации privacy_settings: {validation_result.error_message}")
                self.privacy_settings = {}
        elif self.privacy_settings is None:
            self.privacy_settings = {}
            
        # Парсим даты
        for field in ['created_at', 'updated_at']:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, datetime.fromisoformat(value))
    
    def get_search_filters(self) -> dict:
        """Возвращает настройки фильтров поиска с значениями по умолчанию"""
        defaults = {
            'elo_filter': 'any',  # 'lower', 'similar', 'higher', 'any'
            'preferred_roles': [],  # Список предпочитаемых ролей
            'maps_compatibility': 'any',  # 'strict', 'moderate', 'soft', 'any'
            'time_compatibility': 'any',  # 'strict', 'soft', 'any' 
            'min_compatibility': 30,  # Минимальная совместимость в %
            'max_candidates': 20  # Максимум кандидатов за раз
        }
        
        # Объединяем с сохраненными настройками
        result = defaults.copy()
        if self.search_filters:
            result.update(self.search_filters)
        return result
    
    def update_search_filters(self, **kwargs) -> dict:
        """Обновляет фильтры поиска"""
        filters = self.get_search_filters()
        filters.update(kwargs)
        self.search_filters = filters
        return filters
    
    def get_notification_settings(self) -> dict:
        """Возвращает настройки уведомлений с значениями по умолчанию"""
        # Основные настройки из базового поля
        base_enabled = self.notifications_enabled
        
        # Детальные настройки из privacy_settings
        detailed = self.privacy_settings.get('notifications', {}) if self.privacy_settings else {}
        
        defaults = {
            # Критически важные (всегда включены если notifications_enabled=True)
            'new_match': base_enabled,          # Новые тиммейты
            'new_like': base_enabled,           # Новые лайки
            
            # Важные (настраиваемые)
            'new_candidates': base_enabled,     # Новые кандидаты  
            'weekly_stats': False,              # Еженедельная статистика
            
            # Опциональные (выключены по умолчанию)
            'profile_tips': False,              # Советы по профилю
            'return_reminders': False,          # Напоминания о возвращении
            
            # Настройки времени
            'quiet_hours_enabled': False,       # Тихие часы включены
            'quiet_hours_start': 23,            # Тихие часы с 23:00
            'quiet_hours_end': 8,               # До 8:00
            'timezone_offset': 3,               # UTC+3 (МСК)
            
            # Группировка и лимиты
            'group_likes': True,                # Группировать лайки
            'max_per_day': 10                   # Максимум уведомлений в день
        }
        
        # Объединяем с сохраненными настройками
        result = defaults.copy()
        result.update(detailed)
        return result
    
    def update_notification_settings(self, **kwargs) -> dict:
        """Обновляет настройки уведомлений"""
        # Обновляем базовый переключатель если передан
        if 'notifications_enabled' in kwargs:
            self.notifications_enabled = kwargs.pop('notifications_enabled')
        
        # Обновляем детальные настройки
        if not self.privacy_settings:
            self.privacy_settings = {}
        if 'notifications' not in self.privacy_settings:
            self.privacy_settings['notifications'] = {}
            
        current_notifications = self.privacy_settings['notifications']
        current_notifications.update(kwargs)
        self.privacy_settings['notifications'] = current_notifications
        
        return self.get_notification_settings()

@dataclass
class Moderator:
    """Модель модератора"""
    user_id: int
    role: str = 'moderator'  # moderator/admin/super_admin
    permissions: Optional[dict] = None
    appointed_by: Optional[int] = None
    appointed_at: Optional[datetime] = None
    is_active: bool = True
    
    def __post_init__(self):
        # Безопасный парсинг JSON полей с валидацией
        secure_logger = security_validator.get_secure_logger(__name__)
        
        # Схема валидации для прав модератора
        permissions_schema = {
            "type": "object",
            "properties": {
                "moderate_profiles": {"type": "boolean"},
                "manage_moderators": {"type": "boolean"},
                "view_stats": {"type": "boolean"},
                "manage_users": {"type": "boolean"},
                "access_logs": {"type": "boolean"}
            }
        }
        
        # Безопасный парсинг permissions
        if isinstance(self.permissions, str):
            parsed_data, validation_result = security_validator.safe_json_loads(
                self.permissions, 
                schema=permissions_schema, 
                default={}
            )
            if validation_result.is_valid:
                self.permissions = parsed_data
            else:
                secure_logger.error(f"Ошибка валидации permissions: {validation_result.error_message}")
                self.permissions = self.get_default_permissions()
        elif self.permissions is None:
            self.permissions = self.get_default_permissions()
            
        # Парсим дату
        if isinstance(self.appointed_at, str):
            self.appointed_at = datetime.fromisoformat(self.appointed_at)
    
    def get_default_permissions(self) -> dict:
        """Возвращает права по умолчанию для роли"""
        if self.role == 'super_admin':
            return {
                'moderate_profiles': True,
                'manage_moderators': True,
                'view_stats': True,
                'manage_users': True,
                'access_logs': True
            }
        elif self.role == 'admin':
            return {
                'moderate_profiles': True,
                'manage_moderators': False,
                'view_stats': True,
                'manage_users': False,
                'access_logs': True
            }
        else:  # moderator
            return {
                'moderate_profiles': True,
                'manage_moderators': False,
                'view_stats': False,
                'manage_users': False,
                'access_logs': False
            }
    
    def can_moderate_profiles(self) -> bool:
        """Может ли модерировать профили"""
        return self.is_active and self.permissions.get('moderate_profiles', False)
    
    def can_manage_moderators(self) -> bool:
        """Может ли управлять модераторами"""
        return self.is_active and self.permissions.get('manage_moderators', False) 