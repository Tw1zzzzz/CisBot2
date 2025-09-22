"""
🛡️ Rate Limiting Middleware для CIS FINDER Bot
Создано организацией Twizz_Project

Этот модуль обеспечивает:
- Ограничение частоты команд пользователей
- Защиту от спама в callback обработчиках
- Мониторинг подозрительной активности
- Адаптивные лимиты на основе поведения пользователя
- Интеграцию с системой безопасности
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RateLimitType(Enum):
    """Типы ограничений скорости"""
    COMMAND = "command"
    CALLBACK = "callback"
    MESSAGE = "message"
    API_CALL = "api_call"
    DATABASE_QUERY = "database_query"

class UserRiskLevel(Enum):
    """Уровни риска пользователей"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RateLimitConfig:
    """Конфигурация ограничений скорости"""
    max_requests: int
    time_window: int  # в секундах
    burst_limit: int = 5  # максимальное количество запросов в burst
    cooldown_time: int = 60  # время охлаждения после превышения лимита
    escalation_factor: float = 1.5  # коэффициент увеличения лимита при повторных нарушениях

@dataclass
class UserActivity:
    """Активность пользователя"""
    user_id: int
    request_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    violation_count: int = 0
    last_violation: Optional[float] = None
    risk_level: UserRiskLevel = UserRiskLevel.LOW
    blocked_until: Optional[float] = None
    suspicious_patterns: List[str] = field(default_factory=list)
    total_requests: int = 0
    first_seen: float = field(default_factory=time.time)

@dataclass
class SecurityEvent:
    """Событие безопасности"""
    timestamp: float
    user_id: int
    event_type: str
    severity: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None

class RateLimiter:
    """Основной класс для ограничения скорости запросов"""
    
    # Конфигурации по умолчанию для разных типов запросов
    DEFAULT_CONFIGS = {
        RateLimitType.COMMAND: RateLimitConfig(
            max_requests=10,  # 10 команд в минуту
            time_window=60,
            burst_limit=3,
            cooldown_time=120
        ),
        RateLimitType.CALLBACK: RateLimitConfig(
            max_requests=30,  # 30 callback'ов в минуту
            time_window=60,
            burst_limit=5,
            cooldown_time=60
        ),
        RateLimitType.MESSAGE: RateLimitConfig(
            max_requests=20,  # 20 сообщений в минуту
            time_window=60,
            burst_limit=5,
            cooldown_time=90
        ),
        RateLimitType.API_CALL: RateLimitConfig(
            max_requests=100,  # 100 API вызовов в минуту
            time_window=60,
            burst_limit=10,
            cooldown_time=30
        ),
        RateLimitType.DATABASE_QUERY: RateLimitConfig(
            max_requests=200,  # 200 запросов к БД в минуту
            time_window=60,
            burst_limit=20,
            cooldown_time=15
        )
    }
    
    # Паттерны подозрительной активности
    SUSPICIOUS_PATTERNS = {
        "rapid_fire": {"threshold": 10, "window": 5},  # 10 запросов за 5 секунд
        "burst_attack": {"threshold": 20, "window": 10},  # 20 запросов за 10 секунд
        "persistent_spam": {"threshold": 50, "window": 60},  # 50 запросов за минуту
        "automated_behavior": {"threshold": 100, "window": 300},  # 100 запросов за 5 минут
        "unusual_timing": {"threshold": 5, "window": 1}  # 5 запросов за секунду
    }
    
    def __init__(self):
        self.user_activities: Dict[int, UserActivity] = {}
        self.security_events: List[SecurityEvent] = []
        self.global_limits: Dict[RateLimitType, deque] = {
            limit_type: deque(maxlen=1000) for limit_type in RateLimitType
        }
        self.blocked_users: Dict[int, float] = {}  # user_id -> block_until_timestamp
        self.configs = self.DEFAULT_CONFIGS.copy()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
        
        logger.info("🛡️ Rate Limiter инициализирован с защитой от спама")
    
    def _start_cleanup_task(self):
        """Запуск задачи очистки старых данных"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Периодическая очистка старых данных"""
        while True:
            try:
                await asyncio.sleep(300)  # каждые 5 минут
                await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в периодической очистке rate limiter: {e}")
    
    async def _cleanup_old_data(self):
        """Очистка старых данных"""
        current_time = time.time()
        cleanup_threshold = current_time - 3600  # 1 час
        
        # Очистка старых записей активности пользователей
        users_to_remove = []
        for user_id, activity in self.user_activities.items():
            # Очистка старых временных меток
            while activity.request_times and activity.request_times[0] < cleanup_threshold:
                activity.request_times.popleft()
            
            # Удаление неактивных пользователей (старше 24 часов)
            if (not activity.request_times and 
                current_time - activity.first_seen > 86400):
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.user_activities[user_id]
        
        # Очистка старых событий безопасности
        self.security_events = [
            event for event in self.security_events 
            if event.timestamp > cleanup_threshold
        ]
        
        # Очистка глобальных лимитов
        for limit_type in RateLimitType:
            while (self.global_limits[limit_type] and 
                   self.global_limits[limit_type][0] < cleanup_threshold):
                self.global_limits[limit_type].popleft()
        
        # Очистка истекших блокировок
        expired_blocks = [
            user_id for user_id, block_until in self.blocked_users.items()
            if block_until < current_time
        ]
        for user_id in expired_blocks:
            del self.blocked_users[user_id]
        
        if users_to_remove or expired_blocks:
            logger.info(f"🧹 Очистка rate limiter: удалено {len(users_to_remove)} пользователей, "
                       f"снято {len(expired_blocks)} блокировок")
    
    def _get_user_activity(self, user_id: int) -> UserActivity:
        """Получение или создание активности пользователя"""
        if user_id not in self.user_activities:
            self.user_activities[user_id] = UserActivity(user_id=user_id)
        return self.user_activities[user_id]
    
    def _detect_suspicious_patterns(self, user_id: int) -> List[str]:
        """Обнаружение подозрительных паттернов активности"""
        activity = self._get_user_activity(user_id)
        current_time = time.time()
        detected_patterns = []
        
        # Анализ паттернов
        for pattern_name, config in self.SUSPICIOUS_PATTERNS.items():
            threshold = config["threshold"]
            window = config["window"]
            
            # Подсчет запросов в окне времени
            recent_requests = [
                req_time for req_time in activity.request_times
                if current_time - req_time <= window
            ]
            
            if len(recent_requests) >= threshold:
                detected_patterns.append(pattern_name)
                if pattern_name not in activity.suspicious_patterns:
                    activity.suspicious_patterns.append(pattern_name)
        
        return detected_patterns
    
    def _update_user_risk_level(self, user_id: int):
        """Обновление уровня риска пользователя"""
        activity = self._get_user_activity(user_id)
        
        # Определение уровня риска на основе нарушений и паттернов
        if activity.violation_count >= 10 or len(activity.suspicious_patterns) >= 3:
            activity.risk_level = UserRiskLevel.CRITICAL
        elif activity.violation_count >= 5 or len(activity.suspicious_patterns) >= 2:
            activity.risk_level = UserRiskLevel.HIGH
        elif activity.violation_count >= 2 or len(activity.suspicious_patterns) >= 1:
            activity.risk_level = UserRiskLevel.MEDIUM
        else:
            activity.risk_level = UserRiskLevel.LOW
    
    def _log_security_event(self, user_id: int, event_type: str, severity: str, 
                           details: Dict[str, Any], ip_address: Optional[str] = None):
        """Логирование события безопасности"""
        event = SecurityEvent(
            timestamp=time.time(),
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            details=details,
            ip_address=ip_address
        )
        
        self.security_events.append(event)
        
        # Логирование в зависимости от серьезности
        if severity == "critical":
            logger.critical(f"🚨 CRITICAL SECURITY EVENT: {event_type} from user {user_id}: {details}")
        elif severity == "high":
            logger.warning(f"⚠️ HIGH SECURITY EVENT: {event_type} from user {user_id}: {details}")
        elif severity == "medium":
            logger.info(f"🔍 MEDIUM SECURITY EVENT: {event_type} from user {user_id}: {details}")
        else:
            logger.debug(f"ℹ️ LOW SECURITY EVENT: {event_type} from user {user_id}: {details}")
    
    async def check_rate_limit(self, user_id: int, limit_type: RateLimitType, 
                              request_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Проверка ограничения скорости для пользователя
        
        Args:
            user_id: ID пользователя
            limit_type: Тип ограничения
            request_data: Дополнительные данные запроса
            
        Returns:
            Tuple[bool, str, Dict]: (разрешено, сообщение, метаданные)
        """
        current_time = time.time()
        
        # Проверка глобальной блокировки пользователя
        if user_id in self.blocked_users:
            if current_time < self.blocked_users[user_id]:
                remaining_time = int(self.blocked_users[user_id] - current_time)
                return False, f"🚫 Вы заблокированы на {remaining_time} секунд", {
                    "blocked_until": self.blocked_users[user_id],
                    "remaining_time": remaining_time
                }
            else:
                # Блокировка истекла
                del self.blocked_users[user_id]
        
        # Получение активности пользователя
        activity = self._get_user_activity(user_id)
        activity.total_requests += 1
        
        # Получение конфигурации для типа запроса
        config = self.configs.get(limit_type, self.DEFAULT_CONFIGS[limit_type])
        
        # Очистка старых запросов
        while activity.request_times and activity.request_times[0] < current_time - config.time_window:
            activity.request_times.popleft()
        
        # Проверка лимита запросов
        if len(activity.request_times) >= config.max_requests:
            # Превышение лимита
            activity.violation_count += 1
            activity.last_violation = current_time
            
            # Обнаружение подозрительных паттернов
            suspicious_patterns = self._detect_suspicious_patterns(user_id)
            
            # Обновление уровня риска
            self._update_user_risk_level(user_id)
            
            # Определение времени блокировки на основе уровня риска
            if activity.risk_level == UserRiskLevel.CRITICAL:
                block_duration = config.cooldown_time * 4  # 4x время охлаждения
                severity = "critical"
            elif activity.risk_level == UserRiskLevel.HIGH:
                block_duration = config.cooldown_time * 2  # 2x время охлаждения
                severity = "high"
            else:
                block_duration = config.cooldown_time
                severity = "medium"
            
            # Установка блокировки
            self.blocked_users[user_id] = current_time + block_duration
            
            # Логирование события безопасности
            self._log_security_event(
                user_id=user_id,
                event_type="rate_limit_exceeded",
                severity=severity,
                details={
                    "limit_type": limit_type.value,
                    "violation_count": activity.violation_count,
                    "risk_level": activity.risk_level.value,
                    "suspicious_patterns": suspicious_patterns,
                    "block_duration": block_duration,
                    "request_count": len(activity.request_times),
                    "max_requests": config.max_requests,
                    "time_window": config.time_window
                }
            )
            
            return False, f"🚫 Превышен лимит запросов. Блокировка на {block_duration} секунд", {
                "violation_count": activity.violation_count,
                "risk_level": activity.risk_level.value,
                "block_duration": block_duration,
                "suspicious_patterns": suspicious_patterns
            }
        
        # Проверка burst лимита (быстрые последовательные запросы)
        recent_requests = [req_time for req_time in activity.request_times 
                          if current_time - req_time <= 10]  # последние 10 секунд
        
        if len(recent_requests) >= config.burst_limit:
            # Превышение burst лимита
            activity.violation_count += 1
            
            self._log_security_event(
                user_id=user_id,
                event_type="burst_limit_exceeded",
                severity="medium",
                details={
                    "limit_type": limit_type.value,
                    "burst_count": len(recent_requests),
                    "burst_limit": config.burst_limit
                }
            )
            
            return False, "⚡ Слишком много быстрых запросов. Подождите немного.", {
                "burst_count": len(recent_requests),
                "burst_limit": config.burst_limit
            }
        
        # Запрос разрешен - добавляем временную метку
        activity.request_times.append(current_time)
        
        # Добавление в глобальные лимиты
        self.global_limits[limit_type].append(current_time)
        
        return True, "✅ Запрос разрешен", {
            "requests_remaining": config.max_requests - len(activity.request_times),
            "time_window": config.time_window,
            "risk_level": activity.risk_level.value
        }
    
    async def check_global_rate_limit(self, limit_type: RateLimitType) -> Tuple[bool, str]:
        """Проверка глобального ограничения скорости"""
        current_time = time.time()
        config = self.configs.get(limit_type, self.DEFAULT_CONFIGS[limit_type])
        
        # Очистка старых запросов
        while (self.global_limits[limit_type] and 
               self.global_limits[limit_type][0] < current_time - config.time_window):
            self.global_limits[limit_type].popleft()
        
        # Проверка глобального лимита (в 10 раз больше пользовательского)
        global_limit = config.max_requests * 10
        if len(self.global_limits[limit_type]) >= global_limit:
            return False, f"🚫 Глобальный лимит {limit_type.value} превышен"
        
        return True, "✅ Глобальный лимит в норме"
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики пользователя"""
        if user_id not in self.user_activities:
            return {"error": "Пользователь не найден"}
        
        activity = self.user_activities[user_id]
        current_time = time.time()
        
        return {
            "user_id": user_id,
            "total_requests": activity.total_requests,
            "violation_count": activity.violation_count,
            "risk_level": activity.risk_level.value,
            "suspicious_patterns": activity.suspicious_patterns,
            "is_blocked": user_id in self.blocked_users,
            "blocked_until": self.blocked_users.get(user_id),
            "last_violation": activity.last_violation,
            "first_seen": activity.first_seen,
            "recent_requests_count": len([
                req_time for req_time in activity.request_times
                if current_time - req_time <= 300  # последние 5 минут
            ])
        }
    
    def get_security_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение последних событий безопасности"""
        recent_events = sorted(
            self.security_events, 
            key=lambda x: x.timestamp, 
            reverse=True
        )[:limit]
        
        return [
            {
                "timestamp": event.timestamp,
                "datetime": datetime.fromtimestamp(event.timestamp).isoformat(),
                "user_id": event.user_id,
                "event_type": event.event_type,
                "severity": event.severity,
                "details": event.details,
                "ip_address": event.ip_address
            }
            for event in recent_events
        ]
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Получение системной статистики"""
        current_time = time.time()
        
        # Статистика по пользователям
        user_stats = {
            "total_users": len(self.user_activities),
            "blocked_users": len(self.blocked_users),
            "risk_levels": defaultdict(int)
        }
        
        for activity in self.user_activities.values():
            user_stats["risk_levels"][activity.risk_level.value] += 1
        
        # Статистика по типам запросов
        request_stats = {}
        for limit_type in RateLimitType:
            recent_requests = [
                req_time for req_time in self.global_limits[limit_type]
                if current_time - req_time <= 300  # последние 5 минут
            ]
            request_stats[limit_type.value] = len(recent_requests)
        
        # Статистика событий безопасности
        security_stats = {
            "total_events": len(self.security_events),
            "events_by_severity": defaultdict(int),
            "recent_events": len([
                event for event in self.security_events
                if current_time - event.timestamp <= 3600  # последний час
            ])
        }
        
        for event in self.security_events:
            security_stats["events_by_severity"][event.severity] += 1
        
        return {
            "user_stats": dict(user_stats),
            "request_stats": request_stats,
            "security_stats": dict(security_stats),
            "system_uptime": current_time - min(
                (activity.first_seen for activity in self.user_activities.values()),
                default=current_time
            )
        }
    
    def update_config(self, limit_type: RateLimitType, config: RateLimitConfig):
        """Обновление конфигурации для типа запроса"""
        self.configs[limit_type] = config
        logger.info(f"🔄 Обновлена конфигурация rate limit для {limit_type.value}")
    
    def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя"""
        if user_id in self.blocked_users:
            del self.blocked_users[user_id]
            logger.info(f"🔓 Пользователь {user_id} разблокирован")
            return True
        return False
    
    def reset_user_violations(self, user_id: int) -> bool:
        """Сброс нарушений пользователя"""
        if user_id in self.user_activities:
            activity = self.user_activities[user_id]
            activity.violation_count = 0
            activity.suspicious_patterns.clear()
            activity.risk_level = UserRiskLevel.LOW
            logger.info(f"🔄 Сброшены нарушения для пользователя {user_id}")
            return True
        return False
    
    async def shutdown(self):
        """Корректное завершение работы"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛡️ Rate Limiter завершил работу")

# Глобальный экземпляр rate limiter
rate_limiter = RateLimiter()

# Декораторы для удобного использования
def rate_limit(limit_type: RateLimitType, custom_config: Optional[RateLimitConfig] = None):
    """Декоратор для ограничения скорости функций"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Извлечение user_id из аргументов
            user_id = None
            if args and hasattr(args[0], 'effective_user'):
                user_id = args[0].effective_user.id
            elif 'update' in kwargs and hasattr(kwargs['update'], 'effective_user'):
                user_id = kwargs['update'].effective_user.id
            
            if user_id is None:
                logger.warning("Не удалось определить user_id для rate limiting")
                return await func(*args, **kwargs)
            
            # Временное обновление конфигурации если нужно
            if custom_config:
                rate_limiter.update_config(limit_type, custom_config)
            
            # Проверка rate limit
            allowed, message, metadata = await rate_limiter.check_rate_limit(
                user_id, limit_type
            )
            
            if not allowed:
                # Отправка сообщения пользователю если возможно
                if args and hasattr(args[0], 'message'):
                    await args[0].message.reply_text(message)
                elif args and hasattr(args[0], 'callback_query'):
                    await args[0].callback_query.answer(message, show_alert=True)
                
                return None
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Функции для прямого использования
async def check_user_rate_limit(user_id: int, limit_type: RateLimitType) -> Tuple[bool, str, Dict[str, Any]]:
    """Проверка ограничения скорости для пользователя"""
    return await rate_limiter.check_rate_limit(user_id, limit_type)

async def check_global_rate_limit(limit_type: RateLimitType) -> Tuple[bool, str]:
    """Проверка глобального ограничения скорости"""
    return await rate_limiter.check_global_rate_limit(limit_type)

def get_user_security_stats(user_id: int) -> Dict[str, Any]:
    """Получение статистики безопасности пользователя"""
    return rate_limiter.get_user_stats(user_id)

def get_system_security_stats() -> Dict[str, Any]:
    """Получение системной статистики безопасности"""
    return rate_limiter.get_system_stats()

def get_recent_security_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Получение последних событий безопасности"""
    return rate_limiter.get_security_events(limit)
