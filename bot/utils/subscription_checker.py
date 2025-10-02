"""
Утилита для проверки подписки на обязательные телеграм каналы
Создано организацией Twizz_Project
"""
import logging
from typing import List, Dict, Optional, Tuple, Any
from telegram import Bot, ChatMember
from telegram.error import TelegramError, BadRequest, Forbidden
import asyncio
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RequiredChannel:
    """Модель обязательного канала для подписки"""
    channel_id: str
    channel_username: str
    channel_title: str
    channel_url: str

@dataclass
class SubscriptionStatus:
    """Статус подписки пользователя"""
    user_id: int
    is_subscribed: bool
    missing_channels: List[str]
    checked_at: Optional[str] = None
    error_message: Optional[str] = None

class SubscriptionChecker:
    """Класс для проверки подписки пользователей на обязательные каналы"""
    
    # Обязательные каналы для подписки
    REQUIRED_CHANNELS = [
        RequiredChannel(
            channel_id="@cisfinder",
            channel_username="cisfinder", 
            channel_title="CIS FINDER / Поиск игроков CS2",
            channel_url="https://t.me/cisfinder"
        ),
        RequiredChannel(
            channel_id="@tw1zzV",
            channel_username="tw1zzV",
            channel_title="Twizz_Project | Developer",
            channel_url="https://t.me/tw1zzV"
        )
    ]
    
    def __init__(self, bot: Bot, enable_subscription_check: bool = True):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.enable_subscription_check = enable_subscription_check
        
    async def check_user_subscription(self, user_id: int) -> SubscriptionStatus:
        """
        Проверяет подписку пользователя на все обязательные каналы
        
        Args:
            user_id: ID пользователя для проверки
            
        Returns:
            SubscriptionStatus: Статус подписки пользователя
        """
        try:
            # Если проверка подписки отключена, возвращаем успешный статус
            if not self.enable_subscription_check:
                self.logger.debug(f"Проверка подписки отключена для пользователя {user_id}")
                return SubscriptionStatus(
                    user_id=user_id,
                    is_subscribed=True,
                    missing_channels=[],
                    checked_at=self._get_current_timestamp(),
                    error_message=None
                )
            
            self.logger.info(f"Проверка подписки пользователя {user_id} на обязательные каналы")
            
            missing_channels = []
            is_subscribed = True
            errors = []
            
            for channel in self.REQUIRED_CHANNELS:
                try:
                    # Проверяем статус подписки на канал
                    member_status = await self._check_channel_membership(user_id, channel.channel_id)
                    
                    if not member_status:
                        missing_channels.append(channel.channel_username)
                        is_subscribed = False
                        self.logger.debug(f"Пользователь {user_id} не подписан на {channel.channel_username}")
                    else:
                        self.logger.debug(f"Пользователь {user_id} подписан на {channel.channel_username}")
                        
                except Exception as e:
                    error_msg = f"Ошибка проверки подписки на {channel.channel_username} для пользователя {user_id}: {e}"
                    self.logger.error(error_msg)
                    errors.append(error_msg)
                    # В случае ошибки считаем, что пользователь не подписан
                    missing_channels.append(channel.channel_username)
                    is_subscribed = False
            
            status = SubscriptionStatus(
                user_id=user_id,
                is_subscribed=is_subscribed,
                missing_channels=missing_channels,
                checked_at=self._get_current_timestamp(),
                error_message="; ".join(errors) if errors else None
            )
            
            self.logger.info(f"Результат проверки подписки для пользователя {user_id}: подписан={is_subscribed}, отсутствующие каналы={missing_channels}")
            return status
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при проверке подписки пользователя {user_id}: {e}")
            return SubscriptionStatus(
                user_id=user_id,
                is_subscribed=False,
                missing_channels=[channel.channel_username for channel in self.REQUIRED_CHANNELS],
                error_message=str(e)
            )
    
    async def _check_channel_membership_public(self, user_id: int, channel_id: str) -> bool:
        """
        Альтернативный метод проверки подписки через публичные каналы
        Не требует прав администратора, но менее надежен
        """
        try:
            # Пытаемся получить информацию о канале
            chat = await self.bot.get_chat(chat_id=channel_id)
            
            # Если канал публичный, пытаемся проверить подписку
            if hasattr(chat, 'username') and chat.username:
                # Для публичных каналов используем другой подход
                # Отправляем временное сообщение и проверяем, может ли пользователь его увидеть
                try:
                    # Пытаемся получить информацию о пользователе в канале
                    member = await self.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                    from telegram.constants import ChatMemberStatus
                    
                    valid_statuses = [
                        ChatMemberStatus.MEMBER,
                        ChatMemberStatus.ADMINISTRATOR, 
                        ChatMemberStatus.CREATOR
                    ]
                    
                    return member.status in valid_statuses
                except Exception:
                    # Если не удалось проверить, считаем что пользователь подписан
                    # Это позволяет избежать блокировки из-за проблем с правами
                    return True
            else:
                # Для приватных каналов возвращаем True, чтобы не блокировать пользователей
                return True
                
        except Exception as e:
            self.logger.warning(f"Не удалось проверить подписку через публичный метод для канала {channel_id}: {e}")
            # В случае ошибки считаем, что пользователь подписан
            return True

    async def _check_channel_membership(self, user_id: int, channel_id: str) -> bool:
        """
        Проверяет, является ли пользователь участником канала
        
        Args:
            user_id: ID пользователя
            channel_id: ID канала (может быть @username или числовой ID)
            
        Returns:
            bool: True если пользователь подписан, False если нет
        """
        try:
            # Получаем информацию о статусе пользователя в канале
            chat_member = await self.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            
            # Проверяем статус участника
            from telegram.constants import ChatMemberStatus
            
            # Валидные статусы для подписанных пользователей
            valid_statuses = [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR, 
                ChatMemberStatus.CREATOR
            ]
            
            is_member = chat_member.status in valid_statuses
            
            self.logger.debug(f"Статус пользователя {user_id} в канале {channel_id}: {chat_member.status}, является участником: {is_member}")
            
            return is_member
            
        except BadRequest as e:
            error_message = str(e).lower()
            if "chat not found" in error_message:
                self.logger.error(f"Канал {channel_id} не найден: {e}")
                return False
            elif "user not found" in error_message:
                self.logger.error(f"Пользователь {user_id} не найден: {e}")
                return False
            elif "bot is not a member" in error_message:
                self.logger.error(f"Бот не является участником канала {channel_id}: {e}")
                return False
            elif "chat_admin_required" in error_message:
                self.logger.warning(f"Бот не имеет прав администратора в канале {channel_id}. Невозможно проверить подписку: {e}")
                # В случае отсутствия прав администратора считаем, что пользователь подписан
                # Это позволяет избежать блокировки пользователей из-за проблем с правами бота
                return True
            elif "member list is inaccessible" in error_message:
                self.logger.warning(f"Список участников канала {channel_id} недоступен. Невозможно проверить подписку: {e}")
                # В случае недоступности списка участников считаем, что пользователь подписан
                return True
            else:
                self.logger.error(f"BadRequest при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
                return False
                
        except Forbidden as e:
            self.logger.error(f"Нет доступа к каналу {channel_id} для проверки подписки пользователя {user_id}: {e}")
            return False
            
        except TelegramError as e:
            self.logger.error(f"Ошибка Telegram API при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
            return False
            
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
            return False
    
    def get_required_channels(self) -> List[RequiredChannel]:
        """Возвращает список обязательных каналов"""
        return self.REQUIRED_CHANNELS.copy()
    
    def get_subscription_message(self, missing_channels: List[str] = None) -> str:
        """
        Формирует информационное сообщение о каналах
        
        Args:
            missing_channels: Список каналов (не используется, для совместимости)
            
        Returns:
            str: Текст информационного сообщения
        """
        message = "📢 <b>Привет! 👋</b>\n\n"
        message += "Было бы классно, если бы вы подписались на наши каналы:\n\n"
        
        for channel in self.REQUIRED_CHANNELS:
            message += f"📺 <a href='{channel.channel_url}'>{channel.channel_title}</a>\n"
        
        message += "\n💡 <b>Почему стоит подписаться?</b>\n"
        message += "• Получайте новости о CS2 и киберспорте\n"
        message += "• Узнавайте о новых функциях бота\n"
        message += "• Общайтесь с другими игроками\n\n"
        message += "🎮 <b>Но это не обязательно!</b> Вы можете пользоваться ботом и без подписки."
        
        return message
    
    def get_subscription_keyboard(self, missing_channels: List[str] = None) -> 'InlineKeyboardMarkup':
        """
        Создает информационную клавиатуру с кнопками каналов
        
        Args:
            missing_channels: Список каналов (не используется, для совместимости)
            
        Returns:
            InlineKeyboardMarkup: Информационная клавиатура
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        
        # Добавляем кнопки для перехода к каналам
        for channel in self.REQUIRED_CHANNELS:
            button_text = f"📺 {channel.channel_title}"
            keyboard.append([InlineKeyboardButton(button_text, url=channel.channel_url)])
        
        # Кнопка "Понятно, продолжить"
        keyboard.append([InlineKeyboardButton("✅ Понятно, продолжить", callback_data="back_to_main")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def _get_current_timestamp(self) -> str:
        """Возвращает текущую временную метку"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def batch_check_subscriptions(self, user_ids: List[int]) -> Dict[int, SubscriptionStatus]:
        """
        Проверяет подписки для нескольких пользователей
        
        Args:
            user_ids: Список ID пользователей для проверки
            
        Returns:
            Dict[int, SubscriptionStatus]: Словарь с результатами проверки
        """
        self.logger.info(f"Пакетная проверка подписок для {len(user_ids)} пользователей")
        
        results = {}
        
        # Создаем задачи для параллельной проверки
        tasks = []
        for user_id in user_ids:
            task = self.check_user_subscription(user_id)
            tasks.append((user_id, task))
        
        # Выполняем все проверки параллельно
        for user_id, task in tasks:
            try:
                status = await task
                results[user_id] = status
            except Exception as e:
                self.logger.error(f"Ошибка при пакетной проверке подписки пользователя {user_id}: {e}")
                results[user_id] = SubscriptionStatus(
                    user_id=user_id,
                    is_subscribed=False,
                    missing_channels=[channel.channel_username for channel in self.REQUIRED_CHANNELS],
                    error_message=str(e)
                )
        
        self.logger.info(f"Пакетная проверка завершена. Результаты: {len(results)} пользователей")
        return results
    
    async def test_subscription_system(self) -> Dict[str, Any]:
        """
        Тестирует систему проверки подписки
        
        Returns:
            Dict[str, Any]: Результаты тестирования
        """
        self.logger.info("Запуск тестирования системы проверки подписки")
        
        test_results = {
            "timestamp": self._get_current_timestamp(),
            "channels": [],
            "bot_info": None,
            "errors": []
        }
        
        try:
            # Получаем информацию о боте
            bot_info = await self.bot.get_me()
            test_results["bot_info"] = {
                "id": bot_info.id,
                "username": bot_info.username,
                "first_name": bot_info.first_name
            }
            
            # Тестируем каждый канал
            for channel in self.REQUIRED_CHANNELS:
                channel_test = {
                    "channel_id": channel.channel_id,
                    "channel_username": channel.channel_username,
                    "channel_title": channel.channel_title,
                    "accessible": False,
                    "bot_is_member": False,
                    "error": None
                }
                
                try:
                    # Проверяем, можем ли мы получить информацию о канале
                    chat_info = await self.bot.get_chat(channel.channel_id)
                    channel_test["accessible"] = True
                    channel_test["chat_info"] = {
                        "id": chat_info.id,
                        "title": chat_info.title,
                        "type": str(chat_info.type)
                    }
                    
                    # Проверяем, является ли бот участником канала
                    try:
                        bot_member = await self.bot.get_chat_member(channel.channel_id, bot_info.id)
                        channel_test["bot_is_member"] = bot_member.status in [
                            "member", "administrator", "creator"
                        ]
                        channel_test["bot_status"] = str(bot_member.status)
                    except Exception as e:
                        channel_test["bot_member_error"] = str(e)
                    
                except Exception as e:
                    channel_test["error"] = str(e)
                    test_results["errors"].append(f"Ошибка доступа к каналу {channel.channel_username}: {e}")
                
                test_results["channels"].append(channel_test)
            
            self.logger.info(f"Тестирование системы проверки подписки завершено. Ошибок: {len(test_results['errors'])}")
            
        except Exception as e:
            error_msg = f"Критическая ошибка при тестировании системы проверки подписки: {e}"
            self.logger.error(error_msg)
            test_results["errors"].append(error_msg)
        
        return test_results

# Глобальный экземпляр для использования в других модулях
_subscription_checker: Optional[SubscriptionChecker] = None

def get_subscription_checker() -> Optional[SubscriptionChecker]:
    """Возвращает глобальный экземпляр SubscriptionChecker"""
    return _subscription_checker

def set_subscription_checker(checker: SubscriptionChecker) -> None:
    """Устанавливает глобальный экземпляр SubscriptionChecker"""
    global _subscription_checker
    _subscription_checker = checker
