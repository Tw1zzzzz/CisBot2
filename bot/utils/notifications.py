"""
Система уведомлений для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from bot.database.operations import DatabaseManager

logger = logging.getLogger(__name__)

class NotificationManager:
    """Менеджер уведомлений для отправки push-сообщений пользователям"""
    
    def __init__(self, bot: Bot, db_manager: DatabaseManager):
        self.bot = bot
        self.db = db_manager
        self.last_notification_cache = {}  # Кэш для предотвращения спама
    
    async def send_like_notification(self, liked_user_id: int, liker_user_id: int) -> bool:
        """
        Отправляет уведомление о новом лайке
        
        Args:
            liked_user_id: ID пользователя, которого лайкнули
            liker_user_id: ID пользователя, который поставил лайк
            
        Returns:
            bool: True если уведомление отправлено успешно
        """
        try:
            # Проверяем настройки уведомлений получателя
            if not await self._should_send_notification(liked_user_id, 'new_like'):
                logger.info(f"Уведомление о лайке для {liked_user_id} отключено в настройках")
                return False
            
            # Проверяем на спам (не более 1 уведомления от одного пользователя в час)
            cache_key = f"like_{liked_user_id}_{liker_user_id}"
            if await self._is_spam_protection_active(cache_key, timedelta(hours=1)):
                logger.info(f"Спам-защита: уведомление о лайке {cache_key} заблокировано")
                return False
            
            # Получаем данные отправителя для персонализации
            liker_profile = await self.db.get_profile(liker_user_id)
            if not liker_profile:
                logger.error(f"Профиль лайкера {liker_user_id} не найден")
                return False
            
            # Формируем сообщение
            message = (
                f"❤️ <b>Новый лайк!</b>\n\n"
                f"Вам поставил лайк: <b>{liker_profile.game_nickname}</b>\n"
                f"Ранг: {liker_profile.faceit_elo} ELO\n"
                f"Роль: {liker_profile.role}\n\n"
                f"💡 Ответьте на лайк или пропустите:"
            )
            
            # Создаем интерактивную клавиатуру
            keyboard = [
                [
                    InlineKeyboardButton("❤️ Лайк в ответ", callback_data=f"reply_like_{liker_user_id}"),
                    InlineKeyboardButton("❌ Пропустить", callback_data=f"skip_like_{liker_user_id}")
                ],
                [InlineKeyboardButton("👁️ Посмотреть профиль", callback_data=f"view_profile_{liker_user_id}")],
                [InlineKeyboardButton("📋 История лайков", callback_data="likes_history")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=liked_user_id,
                text=message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
            # Обновляем кэш для защиты от спама
            self.last_notification_cache[cache_key] = datetime.now()
            
            logger.info(f"Уведомление о лайке отправлено {liked_user_id} от {liker_user_id}")
            return True
            
        except TelegramError as e:
            logger.error(f"Ошибка Telegram при отправке уведомления о лайке {liked_user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о лайке {liked_user_id}: {e}")
            return False
    
    async def send_match_notification(self, user1_id: int, user2_id: int) -> tuple[bool, bool]:
        """
        Отправляет уведомления обоим пользователям о новом матче
        
        Args:
            user1_id: ID первого пользователя
            user2_id: ID второго пользователя
            
        Returns:
            tuple[bool, bool]: (успех_для_user1, успех_для_user2)
        """
        try:
            # Получаем профили обоих пользователей
            profile1 = await self.db.get_profile(user1_id)
            profile2 = await self.db.get_profile(user2_id)
            
            if not profile1 or not profile2:
                logger.error(f"Профили не найдены: {user1_id}={bool(profile1)}, {user2_id}={bool(profile2)}")
                return False, False
            
            # Отправляем уведомления параллельно
            success1 = await self._send_match_notification_to_user(
                user1_id, profile2, user2_id
            )
            success2 = await self._send_match_notification_to_user(
                user2_id, profile1, user1_id
            )
            
            logger.info(f"Уведомления о матче отправлены: {user1_id}={success1}, {user2_id}={success2}")
            return success1, success2
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о матче {user1_id}<->{user2_id}: {e}")
            return False, False
    
    async def _send_match_notification_to_user(self, recipient_id: int, partner_profile, partner_id: int) -> bool:
        """Отправляет уведомление о матче конкретному пользователю"""
        try:
            # Проверяем настройки уведомлений
            if not await self._should_send_notification(recipient_id, 'new_match'):
                logger.info(f"Уведомление о матче для {recipient_id} отключено в настройках")
                return False
            
            # Проверяем спам-защиту (не более 1 уведомления о матче в 10 минут)
            cache_key = f"match_{recipient_id}_{partner_id}"
            if await self._is_spam_protection_active(cache_key, timedelta(minutes=10)):
                logger.info(f"Спам-защита: уведомление о матче {cache_key} заблокировано")
                return False
            
            # Формируем сообщение
            message = (
                f"🎉 <b>НОВЫЙ ТИММЕЙТ!</b>\n\n"
                f"У вас взаимный лайк с игроком:\n"
                f"<b>{partner_profile.game_nickname}</b>\n\n"
                f"🎯 Ранг: {partner_profile.faceit_elo} ELO\n"
                f"🎮 Роль: {partner_profile.role}\n"
                f"🗺️ Карты: {', '.join(partner_profile.favorite_maps[:3])}\n\n"
                f"💬 Теперь вы можете связаться друг с другом!\n"
                f"👥 Проверьте раздел 'Тиммейты' для контактов."
            )
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=recipient_id,
                text=message,
                parse_mode='HTML'
            )
            
            # Обновляем кэш
            self.last_notification_cache[cache_key] = datetime.now()
            
            return True
            
        except TelegramError as e:
            logger.error(f"Ошибка Telegram при отправке уведомления о матче {recipient_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о матче {recipient_id}: {e}")
            return False
    
    async def _should_send_notification(self, user_id: int, notification_type: str) -> bool:
        """
        Проверяет, можно ли отправить уведомление пользователю
        
        Args:
            user_id: ID пользователя
            notification_type: Тип уведомления ('new_like', 'new_match', etc.)
            
        Returns:
            bool: True если можно отправлять
        """
        try:
            # Получаем настройки пользователя
            user_settings = await self.db.get_user_settings(user_id)
            if not user_settings:
                logger.info(f"Настройки пользователя {user_id} не найдены - создаем по умолчанию")
                await self.db.update_user_settings(user_id)
                user_settings = await self.db.get_user_settings(user_id)
            
            if not user_settings:
                logger.error(f"Не удалось получить настройки для {user_id}")
                return False
            
            # Проверяем общий переключатель уведомлений
            if not user_settings.notifications_enabled:
                logger.info(f"Уведомления отключены для пользователя {user_id}")
                return False
            
            # Получаем детальные настройки уведомлений
            notification_settings = user_settings.get_notification_settings()
            
            # Проверяем конкретный тип уведомлений
            if not notification_settings.get(notification_type, False):
                logger.info(f"Уведомления типа {notification_type} отключены для {user_id}")
                return False
            
            # Проверяем тихие часы
            if await self._is_quiet_hours(user_id, notification_settings):
                logger.info(f"Тихие часы активны для пользователя {user_id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки настроек уведомлений для {user_id}: {e}")
            # В случае ошибки разрешаем отправку критически важных уведомлений
            return notification_type in ['new_like', 'new_match']
    
    async def _is_quiet_hours(self, user_id: int, notification_settings: dict) -> bool:
        """Проверяет, активны ли тихие часы для пользователя"""
        try:
            if not notification_settings.get('quiet_hours_enabled', False):
                return False
            
            now = datetime.now()
            timezone_offset = notification_settings.get('timezone_offset', 3)  # UTC+3 по умолчанию
            
            # Корректируем время с учетом временной зоны пользователя
            user_time = now + timedelta(hours=timezone_offset - 3)  # Сервер в МСК (UTC+3)
            user_hour = user_time.hour
            
            quiet_start = notification_settings.get('quiet_hours_start', 23)
            quiet_end = notification_settings.get('quiet_hours_end', 8)
            
            # Проверяем тихие часы (могут переходить через полночь)
            if quiet_start <= quiet_end:
                # Обычный случай: 23:00 - 8:00
                return quiet_start <= user_hour <= quiet_end
            else:
                # Через полночь: 8:00 - 23:00 (инвертируем логику)
                return not (quiet_end < user_hour < quiet_start)
                
        except Exception as e:
            logger.error(f"Ошибка проверки тихих часов для {user_id}: {e}")
            return False
    
    async def _is_spam_protection_active(self, cache_key: str, cooldown: timedelta) -> bool:
        """Проверяет активна ли защита от спама для данного типа уведомления"""
        last_time = self.last_notification_cache.get(cache_key)
        if not last_time:
            return False
        
        return datetime.now() - last_time < cooldown
    
    def clear_spam_cache(self):
        """Очищает кэш спам-защиты (можно вызывать периодически для очистки памяти)"""
        cutoff = datetime.now() - timedelta(hours=24)
        expired_keys = [
            key for key, timestamp in self.last_notification_cache.items()
            if timestamp < cutoff
        ]
        for key in expired_keys:
            del self.last_notification_cache[key]
        
        if expired_keys:
            logger.info(f"Очищено {len(expired_keys)} устаревших записей из кэша уведомлений")
