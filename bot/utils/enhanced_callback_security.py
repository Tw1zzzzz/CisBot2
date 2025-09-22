"""
Enhanced Callback Security System with CSRF Protection
Создано организацией Twizz_Project

Этот модуль расширяет базовую систему безопасности callback'ов:
- Интеграция с CSRF токенами
- Автоматическая генерация токенов для callback'ов
- Валидация токенов при обработке callback'ов
- Защита от replay атак
- Временные ограничения для callback'ов
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

from .callback_security import (
    CallbackSecurityValidator, ValidationResult, SecurityLevel,
    safe_parse_user_id, safe_parse_numeric_value, safe_parse_string_value
)
from .csrf_protection import (
    generate_csrf_token, validate_csrf_token, mark_csrf_token_used,
    TokenValidationResult, TokenStatus
)

logger = logging.getLogger(__name__)

class CallbackActionType(Enum):
    """Типы действий для callback'ов"""
    CRITICAL = "critical"  # Модерация, удаление, критические операции
    HIGH = "high"         # Лайки, профили, важные действия
    MEDIUM = "medium"     # Настройки, фильтры
    LOW = "low"          # Навигация, просмотр

@dataclass
class SecureCallbackData:
    """Безопасные данные callback'а с CSRF токеном"""
    action: str
    user_id: int
    csrf_token: str
    data: Dict[str, Any]
    created_at: float
    expires_at: float

@dataclass
class CallbackValidationResult:
    """Результат валидации callback'а"""
    is_valid: bool
    action: Optional[str] = None
    user_id: Optional[int] = None
    parsed_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    csrf_valid: bool = False

class EnhancedCallbackSecurity:
    """Расширенная система безопасности callback'ов"""
    
    # Маппинг действий на уровни безопасности
    ACTION_SECURITY_LEVELS = {
        # Критические операции
        'approve_': CallbackActionType.CRITICAL,
        'reject_': CallbackActionType.CRITICAL,
        'delete_': CallbackActionType.CRITICAL,
        'remove_moderator': CallbackActionType.CRITICAL,
        'add_moderator': CallbackActionType.CRITICAL,
        
        # Высокий приоритет
        'reply_like_': CallbackActionType.HIGH,
        'skip_like_': CallbackActionType.HIGH,
        'view_profile_': CallbackActionType.HIGH,
        'unblock_': CallbackActionType.HIGH,
        'block_': CallbackActionType.HIGH,
        
        # Средний приоритет
        'edit_': CallbackActionType.MEDIUM,
        'set_': CallbackActionType.MEDIUM,
        'toggle_': CallbackActionType.MEDIUM,
        'filter_': CallbackActionType.MEDIUM,
        'notify_': CallbackActionType.MEDIUM,
        'privacy_': CallbackActionType.MEDIUM,
        
        # Низкий приоритет
        'back_': CallbackActionType.LOW,
        'menu_': CallbackActionType.LOW,
        'page_': CallbackActionType.LOW,
        'show_': CallbackActionType.LOW,
        'help': CallbackActionType.LOW,
    }
    
    # Действия, не требующие CSRF токенов (только чтение)
    NO_CSRF_ACTIONS = {
        'back_to_main', 'help', 'show_', 'menu_', 'page_', 'view_'
    }
    
    def __init__(self):
        self.callback_validator = CallbackSecurityValidator()
        self.logger = logging.getLogger(__name__)
    
    def generate_secure_callback_data(self, action: str, user_id: int, 
                                    data: Dict[str, Any] = None) -> str:
        """
        Генерация безопасных callback данных с CSRF токеном
        
        Args:
            action: Действие callback'а
            user_id: ID пользователя
            data: Дополнительные данные
            
        Returns:
            Строка callback данных с CSRF токеном
        """
        if data is None:
            data = {}
        
        # Определяем уровень безопасности
        security_level = self._get_action_security_level(action)
        
        # Генерируем CSRF токен
        csrf_token = generate_csrf_token(
            user_id=user_id,
            action=action,
            security_level=security_level.value,
            metadata={
                'callback_action': action,
                'generated_at': time.time()
            }
        )
        
        # Создаем безопасные данные
        secure_data = SecureCallbackData(
            action=action,
            user_id=user_id,
            csrf_token=csrf_token,
            data=data,
            created_at=time.time(),
            expires_at=time.time() + 300  # 5 минут
        )
        
        # Формируем callback данные
        callback_data = self._format_callback_data(secure_data)
        
        self.logger.debug(f"Generated secure callback for user {user_id}, action {action}")
        
        return callback_data
    
    def validate_secure_callback(self, callback_data: str, user_id: int) -> CallbackValidationResult:
        """
        Валидация безопасных callback данных
        
        Args:
            callback_data: Данные callback'а
            user_id: ID пользователя
            
        Returns:
            Результат валидации
        """
        try:
            # Парсим callback данные
            parsed_callback = self._parse_callback_data(callback_data)
            if not parsed_callback:
                return CallbackValidationResult(
                    is_valid=False,
                    error_message="Invalid callback data format"
                )
            
            action = parsed_callback.action
            csrf_token = parsed_callback.csrf_token
            data = parsed_callback.data
            
            # Проверяем, требует ли действие CSRF токен
            if not self._requires_csrf_token(action):
                # Для действий без CSRF токена используем базовую валидацию
                basic_validation = self.callback_validator.validate_callback_data(callback_data)
                return CallbackValidationResult(
                    is_valid=basic_validation.is_valid,
                    action=action,
                    user_id=user_id,
                    parsed_data=data,
                    error_message=basic_validation.error_message,
                    security_level=basic_validation.security_level,
                    csrf_valid=True  # Не требуется CSRF
                )
            
            # Валидируем CSRF токен
            security_level = self._get_action_security_level(action)
            csrf_validation = validate_csrf_token(
                csrf_token, user_id, action, security_level.value
            )
            
            if not csrf_validation.is_valid:
                self.logger.warning(f"CSRF validation failed for user {user_id}, action {action}: {csrf_validation.error_message}")
                return CallbackValidationResult(
                    is_valid=False,
                    action=action,
                    user_id=user_id,
                    error_message=f"CSRF validation failed: {csrf_validation.error_message}",
                    security_level=SecurityLevel.HIGH,
                    csrf_valid=False
                )
            
            # Отмечаем токен как использованный
            if csrf_validation.token:
                mark_csrf_token_used(csrf_validation.token.token_id)
            
            # Дополнительная валидация данных
            data_validation = self._validate_callback_data(action, data)
            if not data_validation.is_valid:
                return CallbackValidationResult(
                    is_valid=False,
                    action=action,
                    user_id=user_id,
                    error_message=data_validation.error_message,
                    security_level=SecurityLevel.HIGH,
                    csrf_valid=True
                )
            
            return CallbackValidationResult(
                is_valid=True,
                action=action,
                user_id=user_id,
                parsed_data=data,
                security_level=SecurityLevel.HIGH,
                csrf_valid=True
            )
            
        except Exception as e:
            self.logger.error(f"Error validating secure callback: {e}")
            return CallbackValidationResult(
                is_valid=False,
                error_message="Internal validation error",
                security_level=SecurityLevel.HIGH
            )
    
    def _get_action_security_level(self, action: str) -> CallbackActionType:
        """Определение уровня безопасности для действия"""
        for prefix, level in self.ACTION_SECURITY_LEVELS.items():
            if action.startswith(prefix):
                return level
        
        # По умолчанию средний уровень
        return CallbackActionType.MEDIUM
    
    def _requires_csrf_token(self, action: str) -> bool:
        """Проверка, требует ли действие CSRF токен"""
        # Проверяем исключения
        for no_csrf_prefix in self.NO_CSRF_ACTIONS:
            if action.startswith(no_csrf_prefix):
                return False
        
        # Все остальные действия требуют CSRF токен
        return True
    
    def _format_callback_data(self, secure_data: SecureCallbackData) -> str:
        """Форматирование callback данных"""
        # Простой формат: action:csrf_token:data
        data_str = "|".join([f"{k}={v}" for k, v in secure_data.data.items()])
        return f"{secure_data.action}:{secure_data.csrf_token}:{data_str}"
    
    def _parse_callback_data(self, callback_data: str) -> Optional[SecureCallbackData]:
        """Парсинг callback данных"""
        try:
            parts = callback_data.split(':', 2)
            if len(parts) < 2:
                return None
            
            action = parts[0]
            csrf_token = parts[1]
            data_str = parts[2] if len(parts) > 2 else ""
            
            # Парсим дополнительные данные
            data = {}
            if data_str:
                for pair in data_str.split('|'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        data[key] = value
            
            return SecureCallbackData(
                action=action,
                user_id=0,  # Будет установлен при валидации
                csrf_token=csrf_token,
                data=data,
                created_at=time.time(),
                expires_at=time.time() + 300
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing callback data: {e}")
            return None
    
    def _validate_callback_data(self, action: str, data: Dict[str, Any]) -> ValidationResult:
        """Дополнительная валидация данных callback'а"""
        # Валидация user_id в данных
        if 'user_id' in data:
            try:
                user_id = int(data['user_id'])
                if not (1 <= user_id <= 2**63 - 1):
                    return ValidationResult(
                        is_valid=False,
                        error_message="Invalid user_id in callback data"
                    )
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False,
                    error_message="Invalid user_id format in callback data"
                )
        
        # Валидация page в данных
        if 'page' in data:
            try:
                page = int(data['page'])
                if not (0 <= page <= 1000):
                    return ValidationResult(
                        is_valid=False,
                        error_message="Invalid page number in callback data"
                    )
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False,
                    error_message="Invalid page format in callback data"
                )
        
        # Валидация value в данных
        if 'value' in data:
            try:
                value = int(data['value'])
                if not (0 <= value <= 100):
                    return ValidationResult(
                        is_valid=False,
                        error_message="Invalid value in callback data"
                    )
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False,
                    error_message="Invalid value format in callback data"
                )
        
        return ValidationResult(is_valid=True)
    
    def create_secure_callback_button(self, text: str, action: str, user_id: int, 
                                    data: Dict[str, Any] = None) -> Tuple[str, str]:
        """
        Создание безопасной кнопки callback'а
        
        Args:
            text: Текст кнопки
            action: Действие
            user_id: ID пользователя
            data: Дополнительные данные
            
        Returns:
            Кортеж (callback_data, button_text)
        """
        callback_data = self.generate_secure_callback_data(action, user_id, data)
        return callback_data, text
    
    def get_callback_security_stats(self) -> Dict[str, Any]:
        """Получение статистики безопасности callback'ов"""
        from .csrf_protection import get_csrf_token_stats
        
        csrf_stats = get_csrf_token_stats()
        
        return {
            'csrf_tokens': csrf_stats,
            'action_security_levels': {
                action: level.value for action, level in self.ACTION_SECURITY_LEVELS.items()
            },
            'no_csrf_actions': list(self.NO_CSRF_ACTIONS)
        }

# Глобальный экземпляр расширенной системы безопасности
enhanced_callback_security = EnhancedCallbackSecurity()

# Удобные функции для использования в обработчиках
def generate_secure_callback(action: str, user_id: int, data: Dict[str, Any] = None) -> str:
    """Генерация безопасного callback'а"""
    return enhanced_callback_security.generate_secure_callback_data(action, user_id, data)

def validate_secure_callback(callback_data: str, user_id: int) -> CallbackValidationResult:
    """Валидация безопасного callback'а"""
    return enhanced_callback_security.validate_secure_callback(callback_data, user_id)

def create_secure_button(text: str, action: str, user_id: int, data: Dict[str, Any] = None) -> Tuple[str, str]:
    """Создание безопасной кнопки"""
    return enhanced_callback_security.create_secure_callback_button(text, action, user_id, data)

def get_callback_security_stats() -> Dict[str, Any]:
    """Получение статистики безопасности"""
    return enhanced_callback_security.get_callback_security_stats()
