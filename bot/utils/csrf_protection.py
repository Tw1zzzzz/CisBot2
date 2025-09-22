"""
CSRF Protection System for CIS FINDER Bot
Создано организацией Twizz_Project

Этот модуль обеспечивает:
- Генерацию криптографически стойких CSRF токенов
- Валидацию токенов с проверкой временных ограничений
- Защиту от replay атак
- Интеграцию с callback данными
- Автоматическую очистку истекших токенов
"""

import hashlib
import hmac
import time
import secrets
import logging
import asyncio
from typing import Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)

class TokenStatus(Enum):
    """Статусы CSRF токенов"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    ALREADY_USED = "already_used"
    REVOKED = "revoked"

@dataclass
class CSRFToken:
    """Структура CSRF токена"""
    token_id: str
    user_id: int
    action: str
    created_at: float
    expires_at: float
    used_at: Optional[float] = None
    is_revoked: bool = False
    metadata: Dict[str, Any] = None

@dataclass
class TokenValidationResult:
    """Результат валидации токена"""
    is_valid: bool
    status: TokenStatus
    token: Optional[CSRFToken] = None
    error_message: Optional[str] = None
    security_level: str = "medium"

class CSRFProtectionManager:
    """Менеджер CSRF защиты"""
    
    # Конфигурация токенов
    TOKEN_LIFETIME = 300  # 5 минут в секундах
    MAX_TOKENS_PER_USER = 50  # Максимум токенов на пользователя
    CLEANUP_INTERVAL = 60  # Интервал очистки в секундах
    SECRET_KEY_LENGTH = 32  # Длина секретного ключа
    
    # Уровни безопасности для разных действий
    SECURITY_LEVELS = {
        'critical': {
            'lifetime': 60,  # 1 минута
            'max_uses': 1,
            'require_fresh': True
        },
        'high': {
            'lifetime': 180,  # 3 минуты
            'max_uses': 1,
            'require_fresh': True
        },
        'medium': {
            'lifetime': 300,  # 5 минут
            'max_uses': 3,
            'require_fresh': False
        },
        'low': {
            'lifetime': 600,  # 10 минут
            'max_uses': 5,
            'require_fresh': False
        }
    }
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Инициализация менеджера CSRF защиты
        
        Args:
            secret_key: Секретный ключ для подписи токенов (если None, генерируется автоматически)
        """
        self.secret_key = secret_key or self._generate_secret_key()
        self.tokens: Dict[str, CSRFToken] = {}
        self.used_tokens: Set[str] = set()
        self.user_token_counts: Dict[int, int] = {}
        self._cleanup_task = None
        self._start_cleanup_task()
        
        logger.info("CSRF Protection Manager initialized")
    
    def _generate_secret_key(self) -> str:
        """Генерация криптографически стойкого секретного ключа"""
        return secrets.token_hex(self.SECRET_KEY_LENGTH)
    
    def _start_cleanup_task(self):
        """Запуск фоновой задачи очистки токенов"""
        try:
            if self._cleanup_task is None or self._cleanup_task.done():
                # Проверяем, есть ли запущенный event loop
                try:
                    loop = asyncio.get_running_loop()
                    self._cleanup_task = asyncio.create_task(self._cleanup_expired_tokens())
                except RuntimeError:
                    # Нет запущенного event loop, создаем новый
                    self._cleanup_task = None
                    logger.debug("No running event loop, cleanup task will be started when needed")
        except Exception as e:
            logger.warning(f"Could not start cleanup task: {e}")
            self._cleanup_task = None
    
    async def _cleanup_expired_tokens(self):
        """Фоновая очистка истекших токенов"""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                current_time = time.time()
                
                # Находим истекшие токены
                expired_tokens = []
                for token_id, token in self.tokens.items():
                    if token.expires_at < current_time:
                        expired_tokens.append(token_id)
                
                # Удаляем истекшие токены
                for token_id in expired_tokens:
                    self._remove_token(token_id)
                
                # Очищаем счетчики пользователей
                self._cleanup_user_counts()
                
                if expired_tokens:
                    logger.debug(f"Cleaned up {len(expired_tokens)} expired CSRF tokens")
                    
            except Exception as e:
                logger.error(f"Error in CSRF token cleanup: {e}")
    
    def _cleanup_user_counts(self):
        """Очистка счетчиков токенов пользователей"""
        current_time = time.time()
        active_user_tokens = {}
        
        for token in self.tokens.values():
            if token.expires_at > current_time and not token.is_revoked:
                active_user_tokens[token.user_id] = active_user_tokens.get(token.user_id, 0) + 1
        
        self.user_token_counts = active_user_tokens
    
    def _ensure_cleanup_task(self):
        """Убеждаемся, что задача очистки запущена"""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._cleanup_task = asyncio.create_task(self._cleanup_expired_tokens())
            except RuntimeError:
                # Нет запущенного event loop, пропускаем
                pass

    def generate_token(self, user_id: int, action: str, security_level: str = "medium", 
                      metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Генерация CSRF токена
        
        Args:
            user_id: ID пользователя
            action: Действие для которого создается токен
            security_level: Уровень безопасности (critical, high, medium, low)
            metadata: Дополнительные метаданные
            
        Returns:
            Сгенерированный токен
        """
        if security_level not in self.SECURITY_LEVELS:
            security_level = "medium"
        
        # Проверяем лимит токенов на пользователя
        if self.user_token_counts.get(user_id, 0) >= self.MAX_TOKENS_PER_USER:
            self._cleanup_user_old_tokens(user_id)
        
        # Убеждаемся, что задача очистки запущена
        self._ensure_cleanup_task()
        
        current_time = time.time()
        config = self.SECURITY_LEVELS[security_level]
        
        # Создаем уникальный ID токена
        token_id = self._generate_token_id(user_id, action, current_time)
        
        # Создаем токен
        token = CSRFToken(
            token_id=token_id,
            user_id=user_id,
            action=action,
            created_at=current_time,
            expires_at=current_time + config['lifetime'],
            metadata=metadata or {}
        )
        
        # Сохраняем токен
        self.tokens[token_id] = token
        self.user_token_counts[user_id] = self.user_token_counts.get(user_id, 0) + 1
        
        # Генерируем подписанный токен
        signed_token = self._sign_token(token)
        
        logger.debug(f"Generated CSRF token for user {user_id}, action {action}, level {security_level}")
        
        return signed_token
    
    def _generate_token_id(self, user_id: int, action: str, timestamp: float) -> str:
        """Генерация уникального ID токена"""
        # Используем криптографически стойкий генератор
        random_part = secrets.token_hex(16)
        data = f"{user_id}:{action}:{timestamp}:{random_part}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def _sign_token(self, token: CSRFToken) -> str:
        """Подпись токена с использованием HMAC"""
        # Создаем данные для подписи
        token_data = {
            'id': token.token_id,
            'user_id': token.user_id,
            'action': token.action,
            'created_at': token.created_at,
            'expires_at': token.expires_at,
            'metadata': token.metadata
        }
        
        # Сериализуем данные
        data_str = json.dumps(token_data, sort_keys=True)
        
        # Создаем подпись
        signature = hmac.new(
            self.secret_key.encode(),
            data_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Возвращаем токен в формате: data.signature
        return f"{data_str}.{signature}"
    
    def validate_token(self, signed_token: str, user_id: int, action: str, 
                      security_level: str = "medium") -> TokenValidationResult:
        """
        Валидация CSRF токена
        
        Args:
            signed_token: Подписанный токен
            user_id: ID пользователя
            action: Ожидаемое действие
            security_level: Уровень безопасности
            
        Returns:
            Результат валидации
        """
        try:
            # Проверяем формат токена
            if '.' not in signed_token:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.INVALID,
                    error_message="Invalid token format"
                )
            
            # Разделяем данные и подпись
            data_str, signature = signed_token.rsplit('.', 1)
            
            # Проверяем подпись
            expected_signature = hmac.new(
                self.secret_key.encode(),
                data_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.INVALID,
                    error_message="Invalid token signature"
                )
            
            # Десериализуем данные
            token_data = json.loads(data_str)
            
            # Проверяем базовые поля
            if token_data.get('user_id') != user_id:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.INVALID,
                    error_message="Token user mismatch"
                )
            
            if token_data.get('action') != action:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.INVALID,
                    error_message="Token action mismatch"
                )
            
            # Проверяем время истечения
            current_time = time.time()
            if token_data.get('expires_at', 0) < current_time:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.EXPIRED,
                    error_message="Token expired"
                )
            
            # Проверяем, не был ли токен уже использован
            token_id = token_data.get('id')
            if token_id in self.used_tokens:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.ALREADY_USED,
                    error_message="Token already used"
                )
            
            # Проверяем, не отозван ли токен
            if token_id in self.tokens and self.tokens[token_id].is_revoked:
                return TokenValidationResult(
                    is_valid=False,
                    status=TokenStatus.REVOKED,
                    error_message="Token revoked"
                )
            
            # Проверяем уровень безопасности
            config = self.SECURITY_LEVELS.get(security_level, self.SECURITY_LEVELS['medium'])
            
            # Для критических операций проверяем свежесть токена
            if config.get('require_fresh', False):
                token_age = current_time - token_data.get('created_at', 0)
                if token_age > 30:  # Токен должен быть не старше 30 секунд
                    return TokenValidationResult(
                        is_valid=False,
                        status=TokenStatus.INVALID,
                        error_message="Token too old for critical operation"
                    )
            
            # Создаем объект токена
            token = CSRFToken(
                token_id=token_id,
                user_id=user_id,
                action=action,
                created_at=token_data.get('created_at', 0),
                expires_at=token_data.get('expires_at', 0),
                metadata=token_data.get('metadata', {})
            )
            
            return TokenValidationResult(
                is_valid=True,
                status=TokenStatus.VALID,
                token=token,
                security_level=security_level
            )
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"CSRF token validation error: {e}")
            return TokenValidationResult(
                is_valid=False,
                status=TokenStatus.INVALID,
                error_message="Token parsing error"
            )
        except Exception as e:
            logger.error(f"Unexpected error in CSRF token validation: {e}")
            return TokenValidationResult(
                is_valid=False,
                status=TokenStatus.INVALID,
                error_message="Internal validation error"
            )
    
    def mark_token_used(self, token_id: str) -> bool:
        """
        Отметить токен как использованный
        
        Args:
            token_id: ID токена
            
        Returns:
            True если токен был успешно отмечен как использованный
        """
        if token_id in self.used_tokens:
            return False
        
        self.used_tokens.add(token_id)
        
        # Для токенов с ограниченным количеством использований
        if token_id in self.tokens:
            token = self.tokens[token_id]
            token.used_at = time.time()
            
            # Проверяем лимит использований
            config = self.SECURITY_LEVELS.get('medium')  # По умолчанию
            max_uses = config.get('max_uses', 1)
            
            # Подсчитываем количество использований (упрощенная логика)
            if max_uses == 1:
                # Для одноразовых токенов удаляем их
                self._remove_token(token_id)
        
        return True
    
    def revoke_token(self, token_id: str) -> bool:
        """
        Отозвать токен
        
        Args:
            token_id: ID токена
            
        Returns:
            True если токен был успешно отозван
        """
        if token_id in self.tokens:
            self.tokens[token_id].is_revoked = True
            return True
        return False
    
    def revoke_user_tokens(self, user_id: int, action: Optional[str] = None) -> int:
        """
        Отозвать все токены пользователя
        
        Args:
            user_id: ID пользователя
            action: Конкретное действие (если None, отзываются все токены)
            
        Returns:
            Количество отозванных токенов
        """
        revoked_count = 0
        current_time = time.time()
        
        for token in self.tokens.values():
            if (token.user_id == user_id and 
                not token.is_revoked and 
                token.expires_at > current_time and
                (action is None or token.action == action)):
                
                token.is_revoked = True
                revoked_count += 1
        
        logger.info(f"Revoked {revoked_count} tokens for user {user_id}" + 
                   (f" for action {action}" if action else ""))
        
        return revoked_count
    
    def _remove_token(self, token_id: str):
        """Удаление токена из всех структур"""
        if token_id in self.tokens:
            token = self.tokens[token_id]
            # Уменьшаем счетчик пользователя
            if token.user_id in self.user_token_counts:
                self.user_token_counts[token.user_id] = max(0, 
                    self.user_token_counts[token.user_id] - 1)
            
            # Удаляем токен
            del self.tokens[token_id]
    
    def _cleanup_user_old_tokens(self, user_id: int):
        """Очистка старых токенов пользователя"""
        current_time = time.time()
        user_tokens = []
        
        # Собираем токены пользователя
        for token_id, token in self.tokens.items():
            if token.user_id == user_id:
                user_tokens.append((token_id, token))
        
        # Сортируем по времени создания (старые первыми)
        user_tokens.sort(key=lambda x: x[1].created_at)
        
        # Удаляем старые токены, оставляя только самые новые
        tokens_to_remove = user_tokens[:-10]  # Оставляем 10 самых новых
        
        for token_id, _ in tokens_to_remove:
            self._remove_token(token_id)
        
        logger.debug(f"Cleaned up {len(tokens_to_remove)} old tokens for user {user_id}")
    
    def get_token_stats(self) -> Dict[str, Any]:
        """Получение статистики токенов"""
        current_time = time.time()
        
        stats = {
            'total_tokens': len(self.tokens),
            'active_tokens': 0,
            'expired_tokens': 0,
            'used_tokens': len(self.used_tokens),
            'revoked_tokens': 0,
            'users_with_tokens': len(self.user_token_counts),
            'tokens_by_action': {},
            'tokens_by_user': {}
        }
        
        for token in self.tokens.values():
            if token.expires_at > current_time and not token.is_revoked:
                stats['active_tokens'] += 1
            else:
                stats['expired_tokens'] += 1
            
            if token.is_revoked:
                stats['revoked_tokens'] += 1
            
            # Статистика по действиям
            action = token.action
            stats['tokens_by_action'][action] = stats['tokens_by_action'].get(action, 0) + 1
            
            # Статистика по пользователям
            user_id = token.user_id
            stats['tokens_by_user'][user_id] = stats['tokens_by_user'].get(user_id, 0) + 1
        
        return stats
    
    def shutdown(self):
        """Корректное завершение работы"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        logger.info("CSRF Protection Manager shutdown")

# Глобальный экземпляр менеджера CSRF защиты
csrf_manager = CSRFProtectionManager()

# Удобные функции для использования в обработчиках
def generate_csrf_token(user_id: int, action: str, security_level: str = "medium", 
                       metadata: Optional[Dict[str, Any]] = None) -> str:
    """Генерация CSRF токена"""
    return csrf_manager.generate_token(user_id, action, security_level, metadata)

def validate_csrf_token(signed_token: str, user_id: int, action: str, 
                       security_level: str = "medium") -> TokenValidationResult:
    """Валидация CSRF токена"""
    return csrf_manager.validate_token(signed_token, user_id, action, security_level)

def mark_csrf_token_used(token_id: str) -> bool:
    """Отметить CSRF токен как использованный"""
    return csrf_manager.mark_token_used(token_id)

def revoke_csrf_token(token_id: str) -> bool:
    """Отозвать CSRF токен"""
    return csrf_manager.revoke_token(token_id)

def revoke_user_csrf_tokens(user_id: int, action: Optional[str] = None) -> int:
    """Отозвать все CSRF токены пользователя"""
    return csrf_manager.revoke_user_tokens(user_id, action)

def get_csrf_token_stats() -> Dict[str, Any]:
    """Получение статистики CSRF токенов"""
    return csrf_manager.get_token_stats()
