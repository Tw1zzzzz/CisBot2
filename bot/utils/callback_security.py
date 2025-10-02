"""
Модуль безопасности для обработки callback_data в CIS FINDER Bot
Создано организацией Twizz_Project

Этот модуль обеспечивает:
- Безопасный парсинг callback_data
- Валидацию user_id из callback данных
- Проверки диапазонов для числовых значений
- Санитизацию текстовых входов
- Защиту от инъекций и манипуляций
"""

import re
import logging
import html
from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class SecurityLevel(Enum):
    """Уровни безопасности для валидации"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ValidationResult:
    """Результат валидации callback_data"""
    is_valid: bool
    parsed_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    sanitized_input: Optional[str] = None

@dataclass
class CallbackPattern:
    """Паттерн для валидации callback_data"""
    pattern: str
    required_fields: List[str]
    optional_fields: List[str] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    max_length: int = 64

class CallbackSecurityValidator:
    """Класс для безопасной валидации callback_data"""
    
    # Предопределенные паттерны callback_data
    CALLBACK_PATTERNS = {
        # Модерация
        'approve_user': CallbackPattern(
            pattern=r'^approve_(\d+)$',
            required_fields=['user_id'],
            security_level=SecurityLevel.CRITICAL
        ),
        'reject_user': CallbackPattern(
            pattern=r'^reject_(\d+)$',
            required_fields=['user_id'],
            security_level=SecurityLevel.CRITICAL
        ),
        'reject_reason': CallbackPattern(
            pattern=r'^reject_reason_([a-z_]+)$',
            required_fields=['reason'],
            security_level=SecurityLevel.HIGH
        ),
        
        # Лайки и профили
        'reply_like': CallbackPattern(
            pattern=r'^reply_like_(\d+)$',
            required_fields=['user_id'],
            security_level=SecurityLevel.HIGH
        ),
        'skip_like': CallbackPattern(
            pattern=r'^skip_like_(\d+)$',
            required_fields=['user_id'],
            security_level=SecurityLevel.HIGH
        ),
        'view_profile': CallbackPattern(
            pattern=r'^view_profile_(\d+)$',
            required_fields=['user_id'],
            security_level=SecurityLevel.HIGH
        ),
        
        # Пагинация
        'likes_page': CallbackPattern(
            pattern=r'^likes_page_(\d+)$',
            required_fields=['page'],
            security_level=SecurityLevel.MEDIUM
        ),
        
        # Настройки
        'set_compatibility': CallbackPattern(
            pattern=r'^set_compatibility_(\d+)$',
            required_fields=['value'],
            security_level=SecurityLevel.MEDIUM
        ),
        
        # Фильтры
        'filter_elo': CallbackPattern(
            pattern=r'^filter_elo_([a-z_]+)$',
            required_fields=['filter_id'],
            security_level=SecurityLevel.MEDIUM
        ),
        'toggle_role': CallbackPattern(
            pattern=r'^toggle_role_([a-zA-Z_]+)$',
            required_fields=['role_name'],
            security_level=SecurityLevel.MEDIUM
        ),
        'set_maps_filter': CallbackPattern(
            pattern=r'^set_maps_filter_([a-z_]+)$',
            required_fields=['filter_value'],
            security_level=SecurityLevel.MEDIUM
        ),
        'set_time_filter': CallbackPattern(
            pattern=r'^set_time_filter_([a-z_]+)$',
            required_fields=['filter_value'],
            security_level=SecurityLevel.MEDIUM
        ),
        
        # Уведомления
        'notify_toggle': CallbackPattern(
            pattern=r'^notify_toggle_([a-z_]+)$',
            required_fields=['notification_type'],
            security_level=SecurityLevel.MEDIUM
        ),
        'notify_quiet_set': CallbackPattern(
            pattern=r'^notify_quiet_set_(\d+)_(\d+)$',
            required_fields=['start_hour', 'end_hour'],
            security_level=SecurityLevel.MEDIUM
        ),
        
        # Приватность
        'visibility_change': CallbackPattern(
            pattern=r'^visibility_([a-z_]+)$',
            required_fields=['visibility_type'],
            security_level=SecurityLevel.MEDIUM
        ),
        'likes_change': CallbackPattern(
            pattern=r'^likes_([a-z_]+)$',
            required_fields=['likes_type'],
            security_level=SecurityLevel.MEDIUM
        ),
        'toggle_display': CallbackPattern(
            pattern=r'^toggle_([a-z_]+)_([a-z]+)$',
            required_fields=['setting_key', 'action'],
            security_level=SecurityLevel.MEDIUM
        ),
        'confirm_privacy': CallbackPattern(
            pattern=r'^confirm_privacy_([a-z_]+)$',
            required_fields=['action'],
            security_level=SecurityLevel.MEDIUM
        ),
        'cancel_privacy': CallbackPattern(
            pattern=r'^cancel_privacy_([a-z_]+)$',
            required_fields=['action'],
            security_level=SecurityLevel.MEDIUM
        )
    }
    
    # Диапазоны для валидации
    USER_ID_RANGE = (1, 2**63 - 1)  # Telegram user ID range
    PAGE_RANGE = (0, 1000)  # Максимум 1000 страниц
    COMPATIBILITY_RANGE = (0, 100)  # Процент совместимости
    HOUR_RANGE = (0, 23)  # Часы дня
    
    # Разрешенные значения для различных полей
    ALLOWED_REJECT_REASONS = {
        'inappropriate', 'invalid_link', 'bad_nickname', 'incomplete', 'custom'
    }
    ALLOWED_ELO_FILTERS = {
        'any', 'low', 'medium', 'high', 'very_high', 'top1000'
    }
    ALLOWED_ROLE_NAMES = {
        'IGL', 'Entry_Fragger', 'Support_Player', 'Lurker', 'AWPer'
    }
    ALLOWED_MAPS_FILTERS = {
        'any', 'soft', 'moderate', 'strict'
    }
    ALLOWED_TIME_FILTERS = {
        'any', 'soft', 'strict'
    }
    ALLOWED_NOTIFICATION_TYPES = {
        'new_match', 'new_like', 'new_candidates', 'weekly_stats',
        'profile_tips', 'return_reminders'
    }
    ALLOWED_VISIBILITY_TYPES = {
        'all', 'matches_only', 'hidden'
    }
    ALLOWED_LIKES_TYPES = {
        'all', 'compatible_elo', 'common_maps', 'active_users'
    }
    ALLOWED_DISPLAY_ACTIONS = {
        'show', 'hide'
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_callback_data(self, callback_data: str, expected_pattern: str = None) -> ValidationResult:
        """
        Безопасная валидация callback_data
        
        Args:
            callback_data: Данные callback для валидации
            expected_pattern: Ожидаемый паттерн (если известен)
            
        Returns:
            ValidationResult с результатом валидации
        """
        if not callback_data:
            return ValidationResult(
                is_valid=False,
                error_message="Callback data не может быть пустым"
            )
        
        if not isinstance(callback_data, str):
            return ValidationResult(
                is_valid=False,
                error_message="Callback data должен быть строкой"
            )
        
        # Проверка длины
        if len(callback_data) > 64:
            return ValidationResult(
                is_valid=False,
                error_message="Callback data слишком длинный (максимум 64 символа)"
            )
        
        # Санитизация входных данных
        sanitized_data = self._sanitize_callback_data(callback_data)
        
        # Если указан ожидаемый паттерн, проверяем его
        if expected_pattern:
            return self._validate_against_pattern(sanitized_data, expected_pattern)
        
        # Иначе пытаемся определить паттерн автоматически
        return self._auto_validate_callback_data(sanitized_data)
    
    def safe_parse_user_id(self, callback_data: str, pattern_prefix: str) -> ValidationResult:
        """
        Безопасный парсинг user_id из callback_data
        
        Args:
            callback_data: Данные callback
            pattern_prefix: Префикс паттерна (например, "approve_", "reject_")
            
        Returns:
            ValidationResult с user_id в parsed_data
        """
        if not callback_data or not pattern_prefix:
            return ValidationResult(
                is_valid=False,
                error_message="Неверные параметры для парсинга user_id"
            )
        
        # Проверяем, что callback_data начинается с ожидаемого префикса
        if not callback_data.startswith(pattern_prefix):
            return ValidationResult(
                is_valid=False,
                error_message=f"Callback data не соответствует ожидаемому формату: {pattern_prefix}"
            )
        
        # Извлекаем user_id
        user_id_str = callback_data[len(pattern_prefix):]
        
        # Валидируем user_id
        return self._validate_user_id(user_id_str)
    
    def safe_parse_numeric_value(self, callback_data: str, pattern_prefix: str, 
                                value_range: Tuple[int, int] = None) -> ValidationResult:
        """
        Безопасный парсинг числового значения из callback_data
        
        Args:
            callback_data: Данные callback
            pattern_prefix: Префикс паттерна
            value_range: Диапазон допустимых значений (min, max)
            
        Returns:
            ValidationResult с числовым значением в parsed_data
        """
        if not callback_data or not pattern_prefix:
            return ValidationResult(
                is_valid=False,
                error_message="Неверные параметры для парсинга числового значения"
            )
        
        # Проверяем префикс
        if not callback_data.startswith(pattern_prefix):
            return ValidationResult(
                is_valid=False,
                error_message=f"Callback data не соответствует ожидаемому формату: {pattern_prefix}"
            )
        
        # Извлекаем значение
        value_str = callback_data[len(pattern_prefix):]
        
        # Валидируем числовое значение
        return self._validate_numeric_value(value_str, value_range)
    
    def safe_parse_string_value(self, callback_data: str, pattern_prefix: str,
                               allowed_values: set = None) -> ValidationResult:
        """
        Безопасный парсинг строкового значения из callback_data
        
        Args:
            callback_data: Данные callback
            pattern_prefix: Префикс паттерна
            allowed_values: Множество разрешенных значений
            
        Returns:
            ValidationResult со строковым значением в parsed_data
        """
        if not callback_data or not pattern_prefix:
            return ValidationResult(
                is_valid=False,
                error_message="Неверные параметры для парсинга строкового значения"
            )
        
        # Проверяем префикс
        if not callback_data.startswith(pattern_prefix):
            return ValidationResult(
                is_valid=False,
                error_message=f"Callback data не соответствует ожидаемому формату: {pattern_prefix}"
            )
        
        # Извлекаем значение
        value_str = callback_data[len(pattern_prefix):]
        
        # Валидируем строковое значение
        return self._validate_string_value(value_str, allowed_values)
    
    def sanitize_text_input(self, text: str, max_length: int = 1000) -> str:
        """
        Санитизация текстового ввода пользователя
        
        Args:
            text: Текст для санитизации
            max_length: Максимальная длина текста
            
        Returns:
            Санитизированный текст
        """
        if not text:
            return ""
        
        if not isinstance(text, str):
            text = str(text)
        
        # HTML экранирование
        sanitized = html.escape(text)
        
        # Удаление потенциально опасных символов
        sanitized = re.sub(r'[<>"\']', '', sanitized)
        
        # Ограничение длины
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        # Удаление лишних пробелов
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        return sanitized
    
    def _sanitize_callback_data(self, callback_data: str) -> str:
        """Санитизация callback_data"""
        # Удаляем потенциально опасные символы
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', callback_data)
        
        # Ограничиваем длину
        if len(sanitized) > 64:
            sanitized = sanitized[:64]
        
        return sanitized
    
    def _validate_against_pattern(self, callback_data: str, pattern_name: str) -> ValidationResult:
        """Валидация против конкретного паттерна"""
        if pattern_name not in self.CALLBACK_PATTERNS:
            return ValidationResult(
                is_valid=False,
                error_message=f"Неизвестный паттерн: {pattern_name}"
            )
        
        pattern = self.CALLBACK_PATTERNS[pattern_name]
        
        # Проверяем соответствие регулярному выражению
        match = re.match(pattern.pattern, callback_data)
        if not match:
            return ValidationResult(
                is_valid=False,
                error_message=f"Callback data не соответствует паттерну {pattern_name}",
                security_level=pattern.security_level
            )
        
        # Извлекаем данные
        parsed_data = {}
        groups = match.groups()
        
        for i, field in enumerate(pattern.required_fields):
            if i < len(groups):
                parsed_data[field] = groups[i]
        
        # Дополнительная валидация в зависимости от типа
        validation_result = self._validate_parsed_data(parsed_data, pattern_name)
        if not validation_result.is_valid:
            return validation_result
        
        return ValidationResult(
            is_valid=True,
            parsed_data=parsed_data,
            security_level=pattern.security_level,
            sanitized_input=callback_data
        )
    
    def _auto_validate_callback_data(self, callback_data: str) -> ValidationResult:
        """Автоматическая валидация callback_data"""
        # Пытаемся найти подходящий паттерн
        for pattern_name, pattern in self.CALLBACK_PATTERNS.items():
            match = re.match(pattern.pattern, callback_data)
            if match:
                return self._validate_against_pattern(callback_data, pattern_name)
        
        # Если паттерн не найден, проверяем базовую безопасность
        if self._is_potentially_dangerous(callback_data):
            return ValidationResult(
                is_valid=False,
                error_message="Потенциально опасный callback_data",
                security_level=SecurityLevel.HIGH
            )
        
        return ValidationResult(
            is_valid=True,
            parsed_data={'raw_data': callback_data},
            security_level=SecurityLevel.LOW
        )
    
    def _validate_user_id(self, user_id_str: str) -> ValidationResult:
        """Валидация user_id"""
        try:
            user_id = int(user_id_str)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error_message="User ID должен быть числом"
            )
        
        # Проверяем диапазон
        if not (self.USER_ID_RANGE[0] <= user_id <= self.USER_ID_RANGE[1]):
            return ValidationResult(
                is_valid=False,
                error_message=f"User ID вне допустимого диапазона: {self.USER_ID_RANGE[0]}-{self.USER_ID_RANGE[1]}"
            )
        
        return ValidationResult(
            is_valid=True,
            parsed_data={'user_id': user_id},
            security_level=SecurityLevel.CRITICAL
        )
    
    def _validate_numeric_value(self, value_str: str, value_range: Tuple[int, int] = None) -> ValidationResult:
        """Валидация числового значения"""
        try:
            value = int(value_str)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error_message="Значение должно быть числом"
            )
        
        # Проверяем диапазон если указан
        if value_range and not (value_range[0] <= value <= value_range[1]):
            return ValidationResult(
                is_valid=False,
                error_message=f"Значение вне допустимого диапазона: {value_range[0]}-{value_range[1]}"
            )
        
        return ValidationResult(
            is_valid=True,
            parsed_data={'value': value},
            security_level=SecurityLevel.MEDIUM
        )
    
    def _validate_string_value(self, value_str: str, allowed_values: set = None) -> ValidationResult:
        """Валидация строкового значения"""
        # Проверяем разрешенные значения если указаны
        if allowed_values and value_str not in allowed_values:
            return ValidationResult(
                is_valid=False,
                error_message=f"Недопустимое значение: {value_str}. Разрешенные: {', '.join(allowed_values)}"
            )
        
        return ValidationResult(
            is_valid=True,
            parsed_data={'value': value_str},
            security_level=SecurityLevel.MEDIUM
        )
    
    def _validate_parsed_data(self, parsed_data: Dict[str, Any], pattern_name: str) -> ValidationResult:
        """Дополнительная валидация распарсенных данных"""
        # Валидация user_id
        if 'user_id' in parsed_data:
            user_id_result = self._validate_user_id(parsed_data['user_id'])
            if not user_id_result.is_valid:
                return user_id_result
        
        # Валидация page
        if 'page' in parsed_data:
            page_result = self._validate_numeric_value(parsed_data['page'], self.PAGE_RANGE)
            if not page_result.is_valid:
                return page_result
        
        # Валидация value (compatibility)
        if 'value' in parsed_data and pattern_name == 'set_compatibility':
            value_result = self._validate_numeric_value(parsed_data['value'], self.COMPATIBILITY_RANGE)
            if not value_result.is_valid:
                return value_result
        
        # Валидация часов
        if 'start_hour' in parsed_data or 'end_hour' in parsed_data:
            if 'start_hour' in parsed_data:
                hour_result = self._validate_numeric_value(parsed_data['start_hour'], self.HOUR_RANGE)
                if not hour_result.is_valid:
                    return hour_result
            if 'end_hour' in parsed_data:
                hour_result = self._validate_numeric_value(parsed_data['end_hour'], self.HOUR_RANGE)
                if not hour_result.is_valid:
                    return hour_result
        
        # Валидация строковых значений
        if 'reason' in parsed_data:
            reason_result = self._validate_string_value(parsed_data['reason'], self.ALLOWED_REJECT_REASONS)
            if not reason_result.is_valid:
                return reason_result
        
        if 'filter_id' in parsed_data:
            filter_result = self._validate_string_value(parsed_data['filter_id'], self.ALLOWED_ELO_FILTERS)
            if not filter_result.is_valid:
                return filter_result
        
        if 'role_name' in parsed_data:
            role_result = self._validate_string_value(parsed_data['role_name'], self.ALLOWED_ROLE_NAMES)
            if not role_result.is_valid:
                return role_result
        
        if 'filter_value' in parsed_data:
            if pattern_name == 'set_maps_filter':
                filter_result = self._validate_string_value(parsed_data['filter_value'], self.ALLOWED_MAPS_FILTERS)
            elif pattern_name == 'set_time_filter':
                filter_result = self._validate_string_value(parsed_data['filter_value'], self.ALLOWED_TIME_FILTERS)
            else:
                filter_result = ValidationResult(is_valid=True)
            
            if not filter_result.is_valid:
                return filter_result
        
        if 'notification_type' in parsed_data:
            notif_result = self._validate_string_value(parsed_data['notification_type'], self.ALLOWED_NOTIFICATION_TYPES)
            if not notif_result.is_valid:
                return notif_result
        
        if 'visibility_type' in parsed_data:
            vis_result = self._validate_string_value(parsed_data['visibility_type'], self.ALLOWED_VISIBILITY_TYPES)
            if not vis_result.is_valid:
                return vis_result
        
        if 'likes_type' in parsed_data:
            likes_result = self._validate_string_value(parsed_data['likes_type'], self.ALLOWED_LIKES_TYPES)
            if not likes_result.is_valid:
                return likes_result
        
        if 'action' in parsed_data and pattern_name == 'toggle_display':
            action_result = self._validate_string_value(parsed_data['action'], self.ALLOWED_DISPLAY_ACTIONS)
            if not action_result.is_valid:
                return action_result
        
        return ValidationResult(is_valid=True)
    
    def _is_potentially_dangerous(self, callback_data: str) -> bool:
        """Проверка на потенциально опасные паттерны"""
        dangerous_patterns = [
            r'<script',  # XSS попытки
            r'javascript:',  # JavaScript инъекции
            r'data:',  # Data URI
            r'vbscript:',  # VBScript
            r'onload=',  # Event handlers
            r'onerror=',  # Event handlers
            r'\.\./',  # Path traversal
            r'%2e%2e%2f',  # URL encoded path traversal
            r'\\x',  # Hex encoding
            r'%[0-9a-f]{2}',  # URL encoding
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, callback_data, re.IGNORECASE):
                return True
        
        return False

# Глобальный экземпляр валидатора
callback_security = CallbackSecurityValidator()

# Удобные функции для использования в обработчиках
def safe_parse_user_id(callback_data: str, pattern_prefix: str) -> ValidationResult:
    """Безопасный парсинг user_id из callback_data"""
    return callback_security.safe_parse_user_id(callback_data, pattern_prefix)

def safe_parse_numeric_value(callback_data: str, pattern_prefix: str, 
                           value_range: Tuple[int, int] = None) -> ValidationResult:
    """Безопасный парсинг числового значения из callback_data"""
    return callback_security.safe_parse_numeric_value(callback_data, pattern_prefix, value_range)

def safe_parse_string_value(callback_data: str, pattern_prefix: str,
                          allowed_values: set = None) -> ValidationResult:
    """Безопасный парсинг строкового значения из callback_data"""
    return callback_security.safe_parse_string_value(callback_data, pattern_prefix, allowed_values)

def sanitize_text_input(text: str, max_length: int = 1000) -> str:
    """Санитизация текстового ввода пользователя"""
    return callback_security.sanitize_text_input(text, max_length)

def validate_callback_data(callback_data: str, expected_pattern: str = None) -> ValidationResult:
    """Валидация callback_data"""
    return callback_security.validate_callback_data(callback_data, expected_pattern)
