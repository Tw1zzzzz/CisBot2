"""
🛡️ Security Middleware для CIS FINDER Bot
Создано организацией Twizz_Project

Этот модуль обеспечивает:
- Интеграцию rate limiting с существующими обработчиками
- Защиту от спама в callback обработчиках
- Мониторинг подозрительной активности
- Автоматическое логирование событий безопасности
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable
from telegram import Update, CallbackQuery, Message
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from .rate_limiter import (
    rate_limiter, RateLimitType, check_user_rate_limit, 
    get_user_security_stats, get_recent_security_events
)

logger = logging.getLogger(__name__)

class SecurityMiddleware:
    """Middleware для обеспечения безопасности обработчиков"""
    
    def __init__(self):
        self.suspicious_activities: Dict[int, Dict[str, Any]] = {}
        self.blocked_patterns: Dict[str, float] = {}  # pattern -> block_until
        self.security_logger = logging.getLogger('bot.security')
        
        # Настройка специального логгера для безопасности
        self._setup_security_logging()
        
        logger.info("🛡️ Security Middleware инициализирован")
    
    def _setup_security_logging(self):
        """Настройка специального логирования для безопасности"""
        import os
        os.makedirs('logs', exist_ok=True)
        
        # Создаем специальный handler для событий безопасности
        security_handler = logging.FileHandler('logs/security.log', encoding='utf-8')
        security_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        security_handler.setFormatter(security_formatter)
        self.security_logger.addHandler(security_handler)
        self.security_logger.setLevel(logging.INFO)
    
    async def protect_command(self, handler_func: Callable) -> Callable:
        """Защита команды от спама и злоупотреблений"""
        async def protected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            command = update.message.text.split()[0] if update.message else "unknown"
            
            # Проверка rate limit для команд
            allowed, message, metadata = await check_user_rate_limit(
                user_id, RateLimitType.COMMAND
            )
            
            if not allowed:
                self.security_logger.warning(
                    f"🚫 Command rate limit exceeded: user {user_id}, command {command}, "
                    f"violations: {metadata.get('violation_count', 0)}, "
                    f"risk_level: {metadata.get('risk_level', 'unknown')}"
                )
                
                await update.message.reply_text(
                    f"🚫 {message}\n\n"
                    f"Попробуйте позже или обратитесь к администратору если это ошибка.",
                    parse_mode='HTML'
                )
                return
            
            # Дополнительная проверка на подозрительную активность
            if await self._check_suspicious_command_activity(user_id, command, update):
                return
            
            # Выполнение оригинального обработчика
            try:
                return await handler_func(update, context)
            except Exception as e:
                self.security_logger.error(
                    f"❌ Error in protected command {command} for user {user_id}: {e}"
                )
                raise
        
        return protected_handler
    
    async def protect_callback(self, handler_func: Callable) -> Callable:
        """Защита callback обработчика от спама"""
        async def protected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            user_id = query.from_user.id
            callback_data = query.data
            
            # Проверка rate limit для callback'ов
            allowed, message, metadata = await check_user_rate_limit(
                user_id, RateLimitType.CALLBACK
            )
            
            if not allowed:
                self.security_logger.warning(
                    f"🚫 Callback rate limit exceeded: user {user_id}, "
                    f"callback: {callback_data}, violations: {metadata.get('violation_count', 0)}"
                )
                
                await query.answer(
                    f"🚫 {message}",
                    show_alert=True
                )
                return
            
            # Проверка на подозрительные callback паттерны
            if await self._check_suspicious_callback_activity(user_id, callback_data, query):
                return
            
            # Проверка на дублирующиеся callback'ы
            if await self._check_duplicate_callback(user_id, callback_data, query):
                return
            
            # Выполнение оригинального обработчика
            try:
                return await handler_func(update, context)
            except Exception as e:
                self.security_logger.error(
                    f"❌ Error in protected callback {callback_data} for user {user_id}: {e}"
                )
                # Отвечаем на callback даже при ошибке
                try:
                    await query.answer("❌ Произошла ошибка при обработке запроса")
                except:
                    pass
                raise
        
        return protected_callback
    
    async def protect_message(self, handler_func: Callable) -> Callable:
        """Защита обработчика сообщений"""
        async def protected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            message_text = update.message.text if update.message else ""
            
            # Проверка rate limit для сообщений
            allowed, message, metadata = await check_user_rate_limit(
                user_id, RateLimitType.MESSAGE
            )
            
            if not allowed:
                self.security_logger.warning(
                    f"🚫 Message rate limit exceeded: user {user_id}, "
                    f"message length: {len(message_text)}"
                )
                
                await update.message.reply_text(
                    f"🚫 {message}\n\n"
                    f"Пожалуйста, не спамьте сообщениями.",
                    parse_mode='HTML'
                )
                return
            
            # Проверка на подозрительное содержимое сообщения
            if await self._check_suspicious_message_content(user_id, message_text, update.message):
                return
            
            # Выполнение оригинального обработчика
            try:
                return await handler_func(update, context)
            except Exception as e:
                self.security_logger.error(
                    f"❌ Error in protected message handler for user {user_id}: {e}"
                )
                raise
        
        return protected_message
    
    async def _check_suspicious_command_activity(self, user_id: int, command: str, 
                                               update: Update) -> bool:
        """Проверка на подозрительную активность команд"""
        current_time = time.time()
        
        # Инициализация данных пользователя
        if user_id not in self.suspicious_activities:
            self.suspicious_activities[user_id] = {
                'commands': [],
                'last_command_time': 0,
                'command_frequency': 0,
                'suspicious_score': 0
            }
        
        user_data = self.suspicious_activities[user_id]
        
        # Анализ частоты команд
        time_since_last = current_time - user_data['last_command_time']
        if time_since_last < 1:  # Менее секунды между командами
            user_data['suspicious_score'] += 10
            user_data['command_frequency'] += 1
        
        # Анализ повторяющихся команд
        recent_commands = [
            cmd for cmd, timestamp in user_data['commands']
            if current_time - timestamp <= 60  # последняя минута
        ]
        
        if len(recent_commands) >= 5:  # 5+ команд за минуту
            user_data['suspicious_score'] += 15
        
        # Проверка на автоматизированное поведение
        if user_data['suspicious_score'] >= 25:
            self.security_logger.warning(
                f"🤖 Suspicious automated behavior detected: user {user_id}, "
                f"score: {user_data['suspicious_score']}, command: {command}"
            )
            
            await update.message.reply_text(
                "🤖 Обнаружено подозрительное поведение. "
                "Пожалуйста, используйте бота вручную.",
                parse_mode='HTML'
            )
            return True
        
        # Обновление данных
        user_data['commands'].append((command, current_time))
        user_data['last_command_time'] = current_time
        user_data['commands'] = user_data['commands'][-20:]  # Храним только последние 20
        
        return False
    
    async def _check_suspicious_callback_activity(self, user_id: int, callback_data: str, 
                                                query: CallbackQuery) -> bool:
        """Проверка на подозрительную активность callback'ов"""
        current_time = time.time()
        
        # Инициализация данных пользователя
        if user_id not in self.suspicious_activities:
            self.suspicious_activities[user_id] = {
                'callbacks': [],
                'last_callback_time': 0,
                'callback_frequency': 0,
                'suspicious_score': 0
            }
        
        user_data = self.suspicious_activities[user_id]
        
        # Анализ частоты callback'ов
        time_since_last = current_time - user_data['last_callback_time']
        if time_since_last < 0.5:  # Менее 0.5 секунды между callback'ами
            user_data['suspicious_score'] += 15
            user_data['callback_frequency'] += 1
        
        # Анализ повторяющихся callback'ов
        recent_callbacks = [
            cb for cb, timestamp in user_data['callbacks']
            if current_time - timestamp <= 30  # последние 30 секунд
        ]
        
        if len(recent_callbacks) >= 10:  # 10+ callback'ов за 30 секунд
            user_data['suspicious_score'] += 20
        
        # Проверка на автоматизированное поведение
        if user_data['suspicious_score'] >= 30:
            self.security_logger.warning(
                f"🤖 Suspicious callback behavior detected: user {user_id}, "
                f"score: {user_data['suspicious_score']}, callback: {callback_data}"
            )
            
            await query.answer(
                "🤖 Обнаружено подозрительное поведение. "
                "Пожалуйста, используйте бота вручную.",
                show_alert=True
            )
            return True
        
        # Обновление данных
        user_data['callbacks'].append((callback_data, current_time))
        user_data['last_callback_time'] = current_time
        user_data['callbacks'] = user_data['callbacks'][-50:]  # Храним только последние 50
        
        return False
    
    async def _check_duplicate_callback(self, user_id: int, callback_data: str, 
                                      query: CallbackQuery) -> bool:
        """Проверка на дублирующиеся callback'ы"""
        current_time = time.time()
        
        if user_id not in self.suspicious_activities:
            self.suspicious_activities[user_id] = {
                'recent_callbacks': [],
                'duplicate_count': 0
            }
        
        user_data = self.suspicious_activities[user_id]
        
        # Проверка на дублирующиеся callback'ы в последние 5 секунд
        recent_duplicates = [
            cb for cb, timestamp in user_data.get('recent_callbacks', [])
            if cb == callback_data and current_time - timestamp <= 5
        ]
        
        if len(recent_duplicates) >= 3:  # 3+ одинаковых callback'а за 5 секунд
            user_data['duplicate_count'] += 1
            
            self.security_logger.warning(
                f"🔄 Duplicate callback detected: user {user_id}, "
                f"callback: {callback_data}, duplicates: {len(recent_duplicates)}"
            )
            
            await query.answer(
                "🔄 Дублирующийся запрос игнорирован. "
                "Пожалуйста, не нажимайте кнопки многократно.",
                show_alert=True
            )
            return True
        
        # Обновление списка недавних callback'ов
        if 'recent_callbacks' not in user_data:
            user_data['recent_callbacks'] = []
        
        user_data['recent_callbacks'].append((callback_data, current_time))
        user_data['recent_callbacks'] = [
            (cb, ts) for cb, ts in user_data['recent_callbacks']
            if current_time - ts <= 10  # Храним только последние 10 секунд
        ]
        
        return False
    
    async def _check_suspicious_message_content(self, user_id: int, message_text: str, 
                                              message: Message) -> bool:
        """Проверка на подозрительное содержимое сообщения"""
        if not message_text:
            return False
        
        # Проверка на спам-паттерны
        spam_patterns = [
            r'(.)\1{10,}',  # Повторяющиеся символы
            r'[^\w\s]{20,}',  # Много специальных символов
            r'http[s]?://[^\s]{50,}',  # Подозрительно длинные URL
        ]
        
        import re
        for pattern in spam_patterns:
            if re.search(pattern, message_text):
                self.security_logger.warning(
                    f"📧 Suspicious message content detected: user {user_id}, "
                    f"pattern: {pattern}, message length: {len(message_text)}"
                )
                
                await message.reply_text(
                    "📧 Сообщение содержит подозрительное содержимое. "
                    "Пожалуйста, отправьте корректное сообщение.",
                    parse_mode='HTML'
                )
                return True
        
        # Проверка на слишком длинные сообщения
        if len(message_text) > 2000:
            self.security_logger.warning(
                f"📏 Oversized message detected: user {user_id}, "
                f"length: {len(message_text)}"
            )
            
            await message.reply_text(
                "📏 Сообщение слишком длинное. "
                "Пожалуйста, сократите текст до 2000 символов.",
                parse_mode='HTML'
            )
            return True
        
        return False
    
    def get_user_security_report(self, user_id: int) -> Dict[str, Any]:
        """Получение отчета по безопасности пользователя"""
        # Получаем данные из rate limiter
        rate_limiter_stats = get_user_security_stats(user_id)
        
        # Получаем данные из middleware
        middleware_data = self.suspicious_activities.get(user_id, {})
        
        return {
            "user_id": user_id,
            "rate_limiter_stats": rate_limiter_stats,
            "middleware_data": middleware_data,
            "timestamp": time.time()
        }
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Получение сводки по безопасности"""
        return {
            "monitored_users": len(self.suspicious_activities),
            "blocked_patterns": len(self.blocked_patterns),
            "recent_security_events": get_recent_security_events(20),
            "timestamp": time.time()
        }
    
    def cleanup_old_data(self):
        """Очистка старых данных"""
        current_time = time.time()
        cleanup_threshold = current_time - 3600  # 1 час
        
        # Очистка старых данных пользователей
        users_to_remove = []
        for user_id, data in self.suspicious_activities.items():
            # Очистка старых команд
            if 'commands' in data:
                data['commands'] = [
                    (cmd, ts) for cmd, ts in data['commands']
                    if ts > cleanup_threshold
                ]
            
            # Очистка старых callback'ов
            if 'callbacks' in data:
                data['callbacks'] = [
                    (cb, ts) for cb, ts in data['callbacks']
                    if ts > cleanup_threshold
                ]
            
            # Очистка старых callback'ов
            if 'recent_callbacks' in data:
                data['recent_callbacks'] = [
                    (cb, ts) for cb, ts in data['recent_callbacks']
                    if ts > cleanup_threshold
                ]
            
            # Удаление неактивных пользователей
            if (not data.get('commands') and 
                not data.get('callbacks') and 
                not data.get('recent_callbacks')):
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.suspicious_activities[user_id]
        
        # Очистка истекших блокировок паттернов
        expired_patterns = [
            pattern for pattern, block_until in self.blocked_patterns.items()
            if block_until < current_time
        ]
        for pattern in expired_patterns:
            del self.blocked_patterns[pattern]
        
        if users_to_remove or expired_patterns:
            logger.info(
                f"🧹 Security middleware cleanup: removed {len(users_to_remove)} users, "
                f"expired {len(expired_patterns)} pattern blocks"
            )

# Глобальный экземпляр security middleware
security_middleware = SecurityMiddleware()

# Функции для удобного использования
def protect_command(handler_func: Callable) -> Callable:
    """Декоратор для защиты команд"""
    return security_middleware.protect_command(handler_func)

def protect_callback(handler_func: Callable) -> Callable:
    """Декоратор для защиты callback'ов"""
    return security_middleware.protect_callback(handler_func)

def protect_message(handler_func: Callable) -> Callable:
    """Декоратор для защиты сообщений"""
    return security_middleware.protect_message(handler_func)

def get_user_security_report(user_id: int) -> Dict[str, Any]:
    """Получение отчета по безопасности пользователя"""
    return security_middleware.get_user_security_report(user_id)

def get_security_summary() -> Dict[str, Any]:
    """Получение сводки по безопасности"""
    return security_middleware.get_security_summary()
