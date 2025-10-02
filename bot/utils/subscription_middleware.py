"""
Middleware для автоматической проверки подписки на каналы
Создано организацией Twizz_Project
"""
import logging
import functools
from typing import Callable, Any, Optional
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .subscription_checker import get_subscription_checker, SubscriptionChecker
from .keyboards import Keyboards

logger = logging.getLogger(__name__)

class SubscriptionMiddleware:
    """Middleware для проверки подписки пользователей на обязательные каналы"""
    
    def __init__(self, subscription_checker: SubscriptionChecker):
        self.subscription_checker = subscription_checker
        self.logger = logging.getLogger(__name__)
        
        # Команды, которые не требуют проверки подписки (все команды освобождены)
        self.exempt_commands = {
            '/start',
            '/help', 
            'back_to_main',
            'check_subscription'
        }
        
        # Callback данные, которые не требуют проверки подписки (все callbacks освобождены)
        self.exempt_callbacks = {
            'check_subscription',
            'back_to_main'
        }
    
    async def check_subscription_required(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Проверяет, требуется ли проверка подписки для данного обновления
        Теперь всегда возвращает False, так как проверка подписки не обязательна
        
        Args:
            update: Обновление от Telegram
            context: Контекст обработчика
            
        Returns:
            bool: Всегда False (проверка подписки не обязательна)
        """
        # Проверка подписки больше не обязательна
        return False
    
    async def handle_subscription_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Обрабатывает проверку подписки и блокирует доступ если пользователь не подписан
        
        Args:
            update: Обновление от Telegram
            context: Контекст обработчика
            
        Returns:
            bool: True если пользователь подписан и доступ разрешен, False если заблокирован
        """
        try:
            user_id = update.effective_user.id if update.effective_user else None
            if not user_id:
                self.logger.warning("Не удалось получить user_id для проверки подписки")
                return True  # Разрешаем доступ если не можем определить пользователя
            
            self.logger.info(f"Проверка подписки для пользователя {user_id}")
            
            # Проверяем подписку пользователя
            subscription_status = await self.subscription_checker.check_user_subscription(user_id)
            
            if subscription_status.is_subscribed:
                self.logger.debug(f"Пользователь {user_id} подписан на все каналы, доступ разрешен")
                return True
            else:
                self.logger.info(f"Пользователь {user_id} не подписан на каналы: {subscription_status.missing_channels}")
                
                # Если есть ошибки API, показываем их пользователю
                if subscription_status.error_message:
                    self.logger.warning(f"Ошибки при проверке подписки для пользователя {user_id}: {subscription_status.error_message}")
                
                await self._block_access_and_show_subscription_message(update, subscription_status)
                return False
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка при проверке подписки пользователя {user_id}: {e}")
            # В случае критической ошибки разрешаем доступ, чтобы не блокировать пользователей
            return True
    
    async def _block_access_and_show_subscription_message(self, update: Update, subscription_status) -> None:
        """
        Блокирует доступ и показывает сообщение о необходимости подписки
        
        Args:
            update: Обновление от Telegram
            subscription_status: Статус подписки пользователя
        """
        try:
            # Формируем сообщение о необходимости подписки
            message_text = self.subscription_checker.get_subscription_message(
                subscription_status.missing_channels
            )
            
            # Создаем клавиатуру с кнопками подписки
            keyboard = self.subscription_checker.get_subscription_keyboard(
                subscription_status.missing_channels
            )
            
            # Отправляем сообщение в зависимости от типа обновления
            if update.message:
                await update.message.reply_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            elif update.callback_query:
                await update.callback_query.answer("❌ Необходима подписка на каналы")
                await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            
            self.logger.info(f"Пользователю {subscription_status.user_id} показано сообщение о необходимости подписки")
            
        except Exception as e:
            self.logger.error(f"Ошибка при показе сообщения о подписке: {e}")
    
    async def process_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           next_handler: Callable) -> Any:
        """
        Обрабатывает обновление с проверкой подписки
        
        Args:
            update: Обновление от Telegram
            context: Контекст обработчика
            next_handler: Следующий обработчик в цепочке
            
        Returns:
            Any: Результат выполнения следующего обработчика
        """
        try:
            # Проверяем, требуется ли проверка подписки
            if not await self.check_subscription_required(update, context):
                return await next_handler(update, context)
            
            # Проверяем подписку пользователя
            if await self.handle_subscription_check(update, context):
                # Пользователь подписан, передаем управление следующему обработчику
                return await next_handler(update, context)
            else:
                # Пользователь не подписан, доступ заблокирован
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка в middleware проверки подписки: {e}")
            # В случае ошибки передаем управление следующему обработчику
            return await next_handler(update, context)

def subscription_required(func: Callable) -> Callable:
    """
    Декоратор для обработчиков, требующих проверки подписки
    
    Args:
        func: Функция обработчика
        
    Returns:
        Callable: Обернутая функция с проверкой подписки
    """
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        try:
            subscription_checker = get_subscription_checker()
            if not subscription_checker:
                logger.warning("SubscriptionChecker не инициализирован, пропускаем проверку подписки")
                return await func(self, update, context)
            
            middleware = SubscriptionMiddleware(subscription_checker)
            return await middleware.process_update(update, context, lambda u, c: func(self, u, c))
            
        except Exception as e:
            logger.error(f"Ошибка в декораторе проверки подписки: {e}")
            return await func(self, update, context)
    
    return wrapper

# Глобальный экземпляр middleware
_subscription_middleware: Optional[SubscriptionMiddleware] = None

def get_subscription_middleware() -> Optional[SubscriptionMiddleware]:
    """Возвращает глобальный экземпляр SubscriptionMiddleware"""
    return _subscription_middleware

def set_subscription_middleware(middleware: SubscriptionMiddleware) -> None:
    """Устанавливает глобальный экземпляр SubscriptionMiddleware"""
    global _subscription_middleware
    _subscription_middleware = middleware
