"""
Обработчики модерации для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import logging
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.operations import DatabaseManager
from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname, PLAYTIME_OPTIONS
from bot.utils.background_processor import TaskPriority
from bot.utils.callback_security import safe_parse_user_id, safe_parse_string_value, sanitize_text_input
from bot.utils.enhanced_callback_security import validate_secure_callback, CallbackValidationResult
from bot.utils.rate_limiter import get_user_security_stats, get_system_security_stats, get_recent_security_events
from bot.utils.security_middleware import get_user_security_report, get_security_summary

logger = logging.getLogger(__name__)

class ModerationHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def show_moderation_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает главное меню модерации"""
        query = update.callback_query
        if query:
            await query.answer()
            user_id = query.from_user.id
        else:
            user_id = update.effective_user.id

        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            text = "❌ У вас нет прав модератора"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Получаем статистику
        stats = await self.db.get_moderation_stats()
        pending_count = stats.get('profiles_pending', 0)
        approved_count = stats.get('profiles_approved', 0)
        rejected_count = stats.get('profiles_rejected', 0)

        text = f"👨‍💼 <b>Панель модератора</b>\n\n"
        text += f"📊 <b>Статистика:</b>\n"
        text += f"⏳ На модерации: {pending_count}\n"
        text += f"✅ Одобрено: {approved_count}\n"
        text += f"❌ Отклонено: {rejected_count}\n\n"
        text += "Выберите действие:"

        keyboard = [
            [InlineKeyboardButton(f"⏳ Модерировать анкеты ({pending_count})", callback_data="mod_queue")],
            [InlineKeyboardButton("✅ Одобренные анкеты", callback_data="mod_approved")],
            [InlineKeyboardButton("❌ Отклоненные анкеты", callback_data="mod_rejected")],
            [InlineKeyboardButton("📊 Статистика", callback_data="mod_stats")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    async def show_moderation_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает очередь анкет на модерацию"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем профили на модерации
        profiles = await self.db.get_profiles_for_moderation('pending', limit=1)
        
        if not profiles:
            text = "✅ Все анкеты проверены!\n\nНет анкет, ожидающих модерации."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Показываем первую анкету
        profile_data = profiles[0]
        context.user_data['moderating_profile'] = profile_data
        
        await self.show_profile_for_moderation(query, profile_data)

    async def show_profile_for_moderation(self, query, profile_data):
        """Показывает профиль для модерации"""
        text = "👨‍💼 <b>Модерация анкеты</b>\n\n"
        text += await self.format_profile_for_moderation(profile_data)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{profile_data['user_id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{profile_data['user_id']}")
            ],
            [InlineKeyboardButton("⏭️ Следующая анкета", callback_data="next_profile")],
            [InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]
        ]
        
        # 🔥 ИСПРАВЛЕНИЕ: добавляем защиту от ошибки "Message is not modified"
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except Exception as e:
            if "message is not modified" in str(e).lower():
                # Если сообщение не изменилось, просто отвечаем на callback
                await query.answer("📋 Анкета уже отображается")
            else:
                # Для других ошибок - пробрасываем дальше
                raise e

    async def format_profile_for_moderation(self, profile_data) -> str:
        """Форматирует профиль для модерации"""
        text = f"👤 <b>Пользователь:</b> {profile_data['first_name']}"
        if profile_data['username']:
            text += f" (@{profile_data['username']})"
        text += f"\n🆔 <b>ID:</b> {profile_data['user_id']}\n\n"
        
        text += f"🎮 <b>Игровой ник:</b> {profile_data['game_nickname']}\n"
        
        # Получаем ELO статистику через Background Processor (HIGH priority для moderation)
        elo_stats = None
        try:
            if profile_data['game_nickname'] and profile_data['game_nickname'].strip():
                from bot.utils.faceit_analyzer import faceit_analyzer
                # Use HIGH priority for moderation requests since moderators are actively reviewing
                elo_future = await faceit_analyzer.get_elo_stats_by_nickname_priority(profile_data['game_nickname'], TaskPriority.HIGH)
                
                try:
                    # Wait for result with timeout (don't make moderators wait too long)
                    elo_stats = await asyncio.wait_for(elo_future, timeout=7.0)
                    logger.debug(f"✅ Получена ELO статистика для модерации {profile_data['game_nickname']}")
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Таймаут получения ELO для модерации {profile_data['game_nickname']}")
                    elo_stats = None
        except Exception as e:
            logger.debug(f"❌ Ошибка фонового процессора для модерации {profile_data['game_nickname']}: {e}")
            # Fallback to direct call if background processor fails
            try:
                elo_stats = await faceit_analyzer.get_elo_stats_by_nickname(profile_data['game_nickname'])
            except Exception:
                elo_stats = None
        
        # Отображаем ELO с мин/макс значениями если есть данные (ИСПРАВЛЕННАЯ ЛОГИКА МОДЕРАЦИЯ)
        if elo_stats:
            from bot.utils.cs2_data import format_faceit_elo_display
            
            # Валидация корректности значений lowest_elo и highest_elo
            lowest_elo = elo_stats.get('lowest_elo', 0)
            highest_elo = elo_stats.get('highest_elo', 0)
            
            # Дополнительная валидация ELO данных в модерации с диагностикой для модераторов
            try:
                if isinstance(lowest_elo, (int, float)) and isinstance(highest_elo, (int, float)):
                    # Проверяем корректность значений
                    lowest_elo = int(lowest_elo) if lowest_elo >= 0 else 0
                    highest_elo = int(highest_elo) if highest_elo >= 0 else 0
                    current_elo = profile_data['faceit_elo']
                    
                    # Показываем мин/макс даже если API вернул ошибку, но есть валидные данные
                    if lowest_elo > 0 or highest_elo > 0:
                        # Специальное логирование для модерации - показываем качество ELO данных
                        data_quality = "✅ Валидная" if lowest_elo <= current_elo <= highest_elo or (lowest_elo == 0 and highest_elo == 0) else "⚠️ Подозрительная"
                        logger.info(f"🔥 MODERATION: {data_quality} ELO статистика для {profile_data['game_nickname']}: текущий={current_elo}, мин={lowest_elo}, макс={highest_elo}")
                        
                        # Валидируем логическую последовательность ELO значений
                        if lowest_elo <= current_elo <= highest_elo or (lowest_elo == 0 and highest_elo == 0):
                            text += f"🎯 <b>ELO Faceit:</b> {format_faceit_elo_display(current_elo, lowest_elo, highest_elo, profile_data['game_nickname'])}\n"
                        else:
                            logger.warning(f"⚠️ MODERATION: Логическая некорректность ELO для {profile_data['game_nickname']}: current={current_elo}, min={lowest_elo}, max={highest_elo}")
                            # Fallback при некорректных данных от API
                            text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(current_elo)} ⚠️\n"
                            # Добавляем предупреждение для модератора
                            text += f"<i>   ⚠️ Предупреждение: Некорректные мин/макс ELO в API</i>\n"
                    else:
                        # Если мин/макс равны 0, показываем только текущий ELO
                        text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(current_elo)}\n"
                else:
                    logger.warning(f"⚠️ MODERATION: ELO значения некорректного типа для {profile_data['game_nickname']}: lowest={type(lowest_elo)}, highest={type(highest_elo)}")
                    # Fallback при некорректных типах данных
                    text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile_data['faceit_elo'])} ⚠️\n"
                    text += f"<i>   ⚠️ Предупреждение: Проблемы с типами данных ELO</i>\n"
            except Exception as elo_validation_error:
                logger.error(f"Ошибка валидации ELO в модерации для {profile_data['game_nickname']}: {elo_validation_error}")
                # Fallback при ошибке валидации
                text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile_data['faceit_elo'])} ❌\n"
                text += f"<i>   ❌ Ошибка: Не удалось валидировать ELO данные</i>\n"
        else:
            # Fallback на базовое отображение ELO
            text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile_data['faceit_elo'])}\n"
        
        # Faceit профиль
        nickname = extract_faceit_nickname(profile_data['faceit_url'])
        text += f"🔗 <b>Faceit:</b> <a href='{profile_data['faceit_url']}'>{nickname}</a>\n"
        
        text += f"👥 <b>Роль:</b> {format_role_display(profile_data['role'])}\n"
        
        # Карты
        try:
            from ..utils.security_validator import security_validator
            secure_logger = security_validator.get_secure_logger(__name__)
            
            # Схема валидации для списка карт
            maps_schema = {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 50
            }
            
            parsed_data, validation_result = security_validator.safe_json_loads(
                profile_data['favorite_maps'], 
                schema=maps_schema, 
                default=[]
            )
            
            if validation_result.is_valid:
                maps = parsed_data
                text += f"🗺️ <b>Карты:</b> {', '.join(maps[:3])}{'...' if len(maps) > 3 else ''}\n"
            else:
                secure_logger.warning(f"Ошибка валидации карт в профиле {profile_data.get('user_id', 'unknown')}: {validation_result.error_message}")
                text += f"🗺️ <b>Карты:</b> Ошибка данных\n"
        except Exception as e:
            secure_logger.error(f"Ошибка обработки карт в профиле: {e}")
            text += f"🗺️ <b>Карты:</b> Ошибка данных\n"
        
        # Время игры
        try:
            from ..utils.security_validator import security_validator
            secure_logger = security_validator.get_secure_logger(__name__)
            
            # Схема валидации для временных слотов
            slots_schema = {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20
            }
            
            parsed_data, validation_result = security_validator.safe_json_loads(
                profile_data['playtime_slots'], 
                schema=slots_schema, 
                default=[]
            )
            
            if validation_result.is_valid:
                slots = parsed_data
                time_names = []
                for slot_id in slots:
                    time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
                    if time_option:
                        time_names.append(time_option['emoji'])
                text += f"⏰ <b>Время:</b> {' '.join(time_names)}\n"
            else:
                secure_logger.warning(f"Ошибка валидации временных слотов в профиле {profile_data.get('user_id', 'unknown')}: {validation_result.error_message}")
                text += f"⏰ <b>Время:</b> Ошибка данных\n"
        except Exception as e:
            secure_logger.error(f"Ошибка обработки временных слотов в профиле: {e}")
            text += f"⏰ <b>Время:</b> Ошибка данных\n"
        
        if profile_data['description']:
            text += f"\n💬 <b>Описание:</b>\n{profile_data['description']}\n"
        
        # Дата создания
        from datetime import datetime
        try:
            created = datetime.fromisoformat(profile_data['created_at'])
            text += f"\n📅 <b>Создано:</b> {created.strftime('%d.%m.%Y %H:%M')}"
        except:
            text += f"\n📅 <b>Создано:</b> {profile_data['created_at']}"
        
        return text

    async def approve_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Одобряет профиль"""
        query = update.callback_query
        await query.answer("✅ Профиль одобрен!")
        
        # Безопасный парсинг user_id
        user_id_result = safe_parse_user_id(query.data, "approve_")
        if not user_id_result.is_valid:
            logger.error(f"Небезопасный callback_data в approve_profile: {query.data} - {user_id_result.error_message}")
            await query.answer("❌ Ошибка валидации данных")
            return
        
        user_id = user_id_result.parsed_data['user_id']
        moderator_id = query.from_user.id
        
        # 🔒 ENHANCED SECURITY: Проверка прав модератора
        if not await self.db.is_moderator(moderator_id):
            await self._log_security_event(moderator_id, "approve_profile_attempt", "unauthorized", target_user_id=user_id)
            await query.edit_message_text("❌ У вас нет прав модератора")
            return
        
        success = await self.db.moderate_profile(user_id, 'approved', moderator_id)
        
        if success:
            # 🔒 ENHANCED SECURITY: Логируем успешное одобрение
            await self._log_security_event(moderator_id, "approve_profile", "success", target_user_id=user_id)
            
            # Отправляем уведомление пользователю
            await self.send_moderation_notification(user_id, 'approved', context)
            
            # Показываем следующую анкету
            await self.show_next_profile(query, context)
        else:
            await self._log_security_event(moderator_id, "approve_profile", "database_error", target_user_id=user_id)
            await query.edit_message_text("❌ Ошибка при одобрении профиля")

    async def reject_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отклоняет профиль"""
        query = update.callback_query
        await query.answer()
        
        # Безопасный парсинг user_id
        user_id_result = safe_parse_user_id(query.data, "reject_")
        if not user_id_result.is_valid:
            logger.error(f"Небезопасный callback_data в reject_profile: {query.data} - {user_id_result.error_message}")
            await query.answer("❌ Ошибка валидации данных")
            return
        
        user_id = user_id_result.parsed_data['user_id']
        context.user_data['rejecting_user_id'] = user_id
        
        text = "❌ <b>Отклонение анкеты</b>\n\n"
        text += "Укажите причину отклонения или выберите готовый вариант:"
        
        keyboard = [
            [InlineKeyboardButton("🔞 Неподходящий контент", callback_data="reject_reason_inappropriate")],
            [InlineKeyboardButton("📸 Неверная ссылка Faceit", callback_data="reject_reason_invalid_link")],
            [InlineKeyboardButton("🎮 Неподходящий ник", callback_data="reject_reason_bad_nickname")],
            [InlineKeyboardButton("📝 Неполная информация", callback_data="reject_reason_incomplete")],
            [InlineKeyboardButton("✏️ Своя причина", callback_data="reject_reason_custom")],
            [InlineKeyboardButton("🔙 Отмена", callback_data="mod_queue")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    async def reject_with_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отклоняет профиль с указанной причиной"""
        query = update.callback_query
        await query.answer()
        
        user_id = context.user_data.get('rejecting_user_id')
        moderator_id = query.from_user.id
        
        reason_map = {
            'inappropriate': 'Неподходящий контент (оскорбления, спам и т.д.)',
            'invalid_link': 'Неверная или недоступная ссылка на Faceit профиль',
            'bad_nickname': 'Неподходящий игровой ник',
            'incomplete': 'Неполная или недостоверная информация'
        }
        
        # Безопасный парсинг reason_key
        reason_result = safe_parse_string_value(query.data, "reject_reason_")
        if not reason_result.is_valid:
            logger.error(f"Небезопасный callback_data в reject_with_reason: {query.data} - {reason_result.error_message}")
            await query.answer("❌ Ошибка валидации данных")
            return
        
        reason_key = reason_result.parsed_data['value']
        
        if reason_key == 'custom':
            # Запрашиваем кастомную причину
            text = (
                "✏️ <b>Кастомная причина отклонения</b>\n\n"
                "Напишите причину отклонения профиля.\n"
                "Пользователь увидит вашу причину."
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="mod_queue")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
            context.user_data['awaiting_rejection_reason'] = True
            return
        
        reason = reason_map.get(reason_key, 'Нарушение правил сообщества')
        
        # 🔒 ENHANCED SECURITY: Проверка прав модератора
        if not await self.db.is_moderator(moderator_id):
            await self._log_security_event(moderator_id, "reject_profile_attempt", "unauthorized", target_user_id=user_id)
            await query.edit_message_text("❌ У вас нет прав модератора")
            return
        
        success = await self.db.moderate_profile(user_id, 'rejected', moderator_id, reason)
        
        if success:
            # 🔒 ENHANCED SECURITY: Логируем успешное отклонение
            await self._log_security_event(moderator_id, "reject_profile", "success", target_user_id=user_id, 
                                         details=f"Reason: {reason}")
            
            await query.answer(f"❌ Профиль отклонен: {reason}")
            
            # Отправляем уведомление пользователю
            await self.send_moderation_notification(user_id, 'rejected', context, reason)
            
            # Показываем следующую анкету
            await self.show_next_profile(query, context)
        else:
            await self._log_security_event(moderator_id, "reject_profile", "database_error", target_user_id=user_id)
            await query.edit_message_text("❌ Ошибка при отклонении профиля")

    async def show_next_profile(self, query_or_update, context):
        """Показывает следующую анкету"""
        # Определяем, это query или update
        if hasattr(query_or_update, 'callback_query'):
            query = query_or_update.callback_query
        else:
            query = query_or_update
        
        # 🔥 ИСПРАВЛЕНИЕ: исключаем текущую модерируемую анкету если она есть
        current_profile = context.user_data.get('moderating_profile')
        exclude_user_id = current_profile.get('user_id') if current_profile else None
        
        profiles = await self.db.get_profiles_for_moderation('pending', limit=1, exclude_user_id=exclude_user_id)
        
        if not profiles:
            text = "✅ Все анкеты проверены!\n\nНет анкет, ожидающих модерации."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]]
            
            # 🔥 ИСПРАВЛЕНИЕ: защита от ошибки "Message is not modified"
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    await query.answer("✅ Все анкеты уже проверены")
                else:
                    raise e
            return
        
        profile_data = profiles[0]
        context.user_data['moderating_profile'] = profile_data
        await self.show_profile_for_moderation(query, profile_data)

    async def send_moderation_notification(self, user_id: int, status: str, context: ContextTypes.DEFAULT_TYPE, reason: str = None):
        """Отправляет уведомление пользователю о результате модерации"""
        try:
            if status == 'approved':
                text = (
                    "🎉 <b>Ваша анкета одобрена!</b>\n\n"
                    "Теперь другие игроки смогут найти вас через поиск тиммейтов.\n"
                    "Удачи в поиске команды!"
                )
            else:  # rejected
                text = (
                    "❌ <b>Ваша анкета отклонена</b>\n\n"
                    f"<b>Причина:</b> {reason}\n\n"
                    "Вы можете отредактировать профиль и отправить на повторную модерацию."
                )
            
            keyboard = [[InlineKeyboardButton("👤 Мой профиль", callback_data="profile_menu")]]
            
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

    async def _log_security_event(self, admin_user_id: int, action_type: str, event_type: str, 
                                 target_user_id: Optional[int] = None, details: Optional[str] = None):
        """
        Логирует событие безопасности
        
        Args:
            admin_user_id: ID администратора
            action_type: Тип действия
            event_type: Тип события (success, failure, attempt, etc.)
            target_user_id: ID целевого пользователя
            details: Дополнительные детали
        """
        try:
            # Формируем детали события
            event_details = f"Event: {event_type}"
            if details:
                event_details += f", Details: {details}"
            
            # Логируем в аудит
            await self.db.log_admin_action(
                admin_user_id=admin_user_id,
                action_type=f"{action_type}_{event_type}",
                target_user_id=target_user_id,
                details=event_details
            )
            
            # Дополнительное логирование в основной лог
            logger.warning(f"SECURITY EVENT: {action_type}_{event_type} by admin {admin_user_id} on target {target_user_id} - {event_details}")
            
        except Exception as e:
            logger.error(f"Ошибка логирования события безопасности: {e}")



    async def add_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления модератора (только для super_admin)"""
        user_id = update.effective_user.id
        
        # 🔒 ENHANCED SECURITY: Многоуровневая проверка прав
        moderator = await self.db.get_moderator(user_id)
        if not moderator:
            await self._log_security_event(user_id, "add_moderator_attempt", "no_moderator_rights")
            await update.message.reply_text("❌ У вас нет прав модератора.")
            return
            
        if not moderator.can_manage_moderators():
            await self._log_security_event(user_id, "add_moderator_attempt", "insufficient_permissions", 
                                         details=f"Role: {moderator.role}")
            await update.message.reply_text(
                "❌ У вас нет прав для управления модераторами.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]])
            )
            return
        
        # 🔒 ENHANCED SECURITY: Проверка на попытку эскалации привилегий
        if moderator.role != 'super_admin':
            await self._log_security_event(user_id, "add_moderator_attempt", "privilege_escalation_attempt", 
                                         details=f"Non-super_admin trying to add moderator: {moderator.role}")
            await update.message.reply_text("❌ Только супер-администраторы могут добавлять модераторов.")
            return
        
        # Проверяем аргументы команды
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "📋 <b>Как добавить модератора:</b>\n\n"
                "<code>/add_moderator USER_ID ROLE</code>\n\n"
                "<b>Роли:</b>\n"
                "• <code>moderator</code> - Базовая модерация\n"
                "• <code>admin</code> - Расширенные права\n"
                "• <code>super_admin</code> - Полные права\n\n"
                "<b>Пример:</b>\n"
                "<code>/add_moderator 123456789 moderator</code>",
                parse_mode='HTML'
            )
            return
        
        try:
            # Безопасный парсинг user_id из аргументов команды
            target_user_id_str = context.args[0].strip()
            if not target_user_id_str.isdigit():
                await self._log_security_event(user_id, "add_moderator_attempt", "invalid_user_id_format", 
                                             details=f"Input: {target_user_id_str}")
                await update.message.reply_text("❌ User ID должен быть числом")
                return
            
            target_user_id = int(target_user_id_str)
            if not (1 <= target_user_id <= 2**63 - 1):
                await self._log_security_event(user_id, "add_moderator_attempt", "user_id_out_of_range", 
                                             details=f"User ID: {target_user_id}")
                await update.message.reply_text("❌ User ID вне допустимого диапазона")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка на самоповышение
            if target_user_id == user_id:
                await self._log_security_event(user_id, "add_moderator_attempt", "self_promotion_attempt")
                await update.message.reply_text("❌ Нельзя назначать себя модератором")
                return
            
            # Санитизация роли
            role = sanitize_text_input(context.args[1].lower(), max_length=20)
            
            if role not in ['moderator', 'admin', 'super_admin']:
                await self._log_security_event(user_id, "add_moderator_attempt", "invalid_role", 
                                             details=f"Role: {role}")
                await update.message.reply_text("❌ Неверная роль. Используйте: moderator, admin или super_admin")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка на попытку назначить супер-админа
            if role == 'super_admin':
                await self._log_security_event(user_id, "add_moderator_attempt", "super_admin_creation_attempt", 
                                             details=f"Target: {target_user_id}")
                await update.message.reply_text("❌ Назначение супер-администраторов запрещено через команды")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка существования целевого пользователя
            target_user = await self.db.get_user(target_user_id)
            if not target_user:
                await self._log_security_event(user_id, "add_moderator_attempt", "target_user_not_found", 
                                             details=f"Target: {target_user_id}")
                await update.message.reply_text("❌ Пользователь не найден в системе")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка на уже существующего модератора
            existing_moderator = await self.db.get_moderator(target_user_id)
            if existing_moderator and existing_moderator.is_active:
                await self._log_security_event(user_id, "add_moderator_attempt", "duplicate_moderator_attempt", 
                                             details=f"Target: {target_user_id}, existing role: {existing_moderator.role}")
                await update.message.reply_text(f"❌ Пользователь уже является активным модератором (роль: {existing_moderator.role})")
                return
            
            # 🔒 ENHANCED SECURITY: Создание токена подтверждения для критической операции
            confirmation_token = await self.db.create_confirmation_token(
                user_id, "add_moderator", target_user_id, expires_minutes=10
            )
            
            if not confirmation_token:
                await self._log_security_event(user_id, "add_moderator_attempt", "confirmation_token_failed")
                await update.message.reply_text("❌ Ошибка создания подтверждения. Попробуйте позже.")
                return
            
            # Отправляем подтверждение
            await update.message.reply_text(
                f"🔒 <b>Подтверждение назначения модератора</b>\n\n"
                f"<b>Целевой пользователь:</b> {target_user_id} ({target_user.first_name})\n"
                f"<b>Роль:</b> {role}\n\n"
                f"⚠️ <b>Это критическая операция!</b>\n"
                f"Для подтверждения выполните команду:\n"
                f"<code>/confirm_add_moderator {confirmation_token}</code>\n\n"
                f"⏰ Токен действителен 10 минут",
                parse_mode='HTML'
            )
            
            # Логируем создание токена подтверждения
            await self._log_security_event(user_id, "add_moderator_confirmation_created", 
                                         target_user_id=target_user_id, details=f"Role: {role}")
            
        except ValueError:
            await self._log_security_event(user_id, "add_moderator_attempt", "value_error")
            await update.message.reply_text("❌ Неверный ID пользователя")
        except Exception as e:
            await self._log_security_event(user_id, "add_moderator_attempt", "exception", details=str(e))
            logger.error(f"Ошибка добавления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при добавлении модератора")

    async def confirm_add_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда подтверждения добавления модератора"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator or not moderator.can_manage_moderators() or moderator.role != 'super_admin':
            await self._log_security_event(user_id, "confirm_add_moderator_attempt", "unauthorized")
            await update.message.reply_text("❌ У вас нет прав для подтверждения этой операции.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Укажите токен подтверждения.")
            return
        
        token = context.args[0].strip()
        
        # Проверяем токен подтверждения
        if not await self.db.verify_confirmation_token(token, user_id, "add_moderator"):
            await self._log_security_event(user_id, "confirm_add_moderator_attempt", "invalid_token", 
                                         details=f"Token: {token[:10]}...")
            await update.message.reply_text("❌ Неверный или истекший токен подтверждения.")
            return
        
        # Получаем детали из токена (нужно будет расширить метод для возврата target_user_id)
        # Пока используем упрощенную логику - получаем последний токен для этого админа
        try:
            # Получаем детали операции из лога аудита
            audit_logs = await self.db.get_admin_audit_log(admin_user_id=user_id, action_type="add_moderator_confirmation_created", limit=1)
            if not audit_logs:
                await self._log_security_event(user_id, "confirm_add_moderator_attempt", "no_audit_record")
                await update.message.reply_text("❌ Не найдена запись о создании токена.")
                return
            
            # Парсим детали из лога
            details = audit_logs[0].get('details', '')
            if 'Role:' not in details:
                await self._log_security_event(user_id, "confirm_add_moderator_attempt", "invalid_audit_details")
                await update.message.reply_text("❌ Некорректные данные в логе аудита.")
                return
            
            target_user_id = audit_logs[0].get('target_user_id')
            role = details.split('Role: ')[1] if 'Role: ' in details else 'moderator'
            
            if not target_user_id:
                await self._log_security_event(user_id, "confirm_add_moderator_attempt", "no_target_user_id")
                await update.message.reply_text("❌ Не найден ID целевого пользователя.")
                return
            
            # Выполняем добавление модератора
            success = await self.db.add_moderator(target_user_id, role, user_id)
            
            if success:
                # Логируем успешное добавление
                await self._log_security_event(user_id, "add_moderator_success", target_user_id=target_user_id, 
                                             details=f"Role: {role}")
                
                await update.message.reply_text(
                    f"✅ Пользователь {target_user_id} успешно назначен как {role}"
                )
                
                # Уведомляем нового модератора
                try:
                    role_names = {
                        'moderator': 'Модератор',
                        'admin': 'Администратор',
                        'super_admin': 'Супер-администратор'
                    }
                    
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=(
                            f"🎉 <b>Вы назначены модератором!</b>\n\n"
                            f"<b>Роль:</b> {role_names[role]}\n\n"
                            "Теперь у вас есть доступ к панели модерации.\n"
                            "Используйте кнопку 'Модерация' в главном меню."
                        ),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💼 Панель модерации", callback_data="moderation_menu")]]),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить модератора {target_user_id}: {e}")
            else:
                await self._log_security_event(user_id, "confirm_add_moderator_attempt", "database_error")
                await update.message.reply_text("❌ Ошибка при добавлении модератора в базу данных.")
                
        except Exception as e:
            await self._log_security_event(user_id, "confirm_add_moderator_attempt", "exception", details=str(e))
            logger.error(f"Ошибка подтверждения добавления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при подтверждении операции.")

    async def remove_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для удаления модератора"""
        user_id = update.effective_user.id
        
        # 🔒 ENHANCED SECURITY: Многоуровневая проверка прав
        moderator = await self.db.get_moderator(user_id)
        if not moderator:
            await self._log_security_event(user_id, "remove_moderator_attempt", "no_moderator_rights")
            await update.message.reply_text("❌ У вас нет прав модератора.")
            return
            
        if not moderator.can_manage_moderators():
            await self._log_security_event(user_id, "remove_moderator_attempt", "insufficient_permissions", 
                                         details=f"Role: {moderator.role}")
            await update.message.reply_text("❌ У вас нет прав для управления модераторами.")
            return
        
        # 🔒 ENHANCED SECURITY: Проверка на попытку эскалации привилегий
        if moderator.role != 'super_admin':
            await self._log_security_event(user_id, "remove_moderator_attempt", "privilege_escalation_attempt", 
                                         details=f"Non-super_admin trying to remove moderator: {moderator.role}")
            await update.message.reply_text("❌ Только супер-администраторы могут удалять модераторов.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "📋 <b>Как удалить модератора:</b>\n\n"
                "<code>/remove_moderator USER_ID</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/remove_moderator 123456789</code>",
                parse_mode='HTML'
            )
            return
        
        try:
            # Безопасный парсинг user_id из аргументов команды
            target_user_id_str = context.args[0].strip()
            if not target_user_id_str.isdigit():
                await self._log_security_event(user_id, "remove_moderator_attempt", "invalid_user_id_format", 
                                             details=f"Input: {target_user_id_str}")
                await update.message.reply_text("❌ User ID должен быть числом")
                return
            
            target_user_id = int(target_user_id_str)
            if not (1 <= target_user_id <= 2**63 - 1):
                await self._log_security_event(user_id, "remove_moderator_attempt", "user_id_out_of_range", 
                                             details=f"User ID: {target_user_id}")
                await update.message.reply_text("❌ User ID вне допустимого диапазона")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка на самоудаление
            if target_user_id == user_id:
                await self._log_security_event(user_id, "remove_moderator_attempt", "self_removal_attempt")
                await update.message.reply_text("❌ Нельзя удалить самого себя")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка существования целевого модератора
            target_moderator = await self.db.get_moderator(target_user_id)
            if not target_moderator:
                await self._log_security_event(user_id, "remove_moderator_attempt", "target_not_moderator", 
                                             details=f"Target: {target_user_id}")
                await update.message.reply_text("❌ Пользователь не является модератором")
                return
            
            if not target_moderator.is_active:
                await self._log_security_event(user_id, "remove_moderator_attempt", "target_already_inactive", 
                                             details=f"Target: {target_user_id}")
                await update.message.reply_text("❌ Модератор уже деактивирован")
                return
            
            # 🔒 ENHANCED SECURITY: Проверка на удаление супер-админа
            if target_moderator.role == 'super_admin':
                await self._log_security_event(user_id, "remove_moderator_attempt", "super_admin_removal_attempt", 
                                             details=f"Target: {target_user_id}")
                await update.message.reply_text("❌ Удаление супер-администраторов запрещено")
                return
            
            # 🔒 ENHANCED SECURITY: Создание токена подтверждения для критической операции
            confirmation_token = await self.db.create_confirmation_token(
                user_id, "remove_moderator", target_user_id, expires_minutes=10
            )
            
            if not confirmation_token:
                await self._log_security_event(user_id, "remove_moderator_attempt", "confirmation_token_failed")
                await update.message.reply_text("❌ Ошибка создания подтверждения. Попробуйте позже.")
                return
            
            # Отправляем подтверждение
            await update.message.reply_text(
                f"🔒 <b>Подтверждение удаления модератора</b>\n\n"
                f"<b>Целевой модератор:</b> {target_user_id}\n"
                f"<b>Роль:</b> {target_moderator.role}\n\n"
                f"⚠️ <b>Это критическая операция!</b>\n"
                f"Для подтверждения выполните команду:\n"
                f"<code>/confirm_remove_moderator {confirmation_token}</code>\n\n"
                f"⏰ Токен действителен 10 минут",
                parse_mode='HTML'
            )
            
            # Логируем создание токена подтверждения
            await self._log_security_event(user_id, "remove_moderator_confirmation_created", 
                                         target_user_id=target_user_id, details=f"Role: {target_moderator.role}")
            
        except ValueError:
            await self._log_security_event(user_id, "remove_moderator_attempt", "value_error")
            await update.message.reply_text("❌ Неверный ID пользователя")
        except Exception as e:
            await self._log_security_event(user_id, "remove_moderator_attempt", "exception", details=str(e))
            logger.error(f"Ошибка удаления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при удалении модератора")

    async def confirm_remove_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда подтверждения удаления модератора"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator or not moderator.can_manage_moderators() or moderator.role != 'super_admin':
            await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "unauthorized")
            await update.message.reply_text("❌ У вас нет прав для подтверждения этой операции.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Укажите токен подтверждения.")
            return
        
        token = context.args[0].strip()
        
        # Проверяем токен подтверждения
        if not await self.db.verify_confirmation_token(token, user_id, "remove_moderator"):
            await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "invalid_token", 
                                         details=f"Token: {token[:10]}...")
            await update.message.reply_text("❌ Неверный или истекший токен подтверждения.")
            return
        
        try:
            # Получаем детали операции из лога аудита
            audit_logs = await self.db.get_admin_audit_log(admin_user_id=user_id, action_type="remove_moderator_confirmation_created", limit=1)
            if not audit_logs:
                await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "no_audit_record")
                await update.message.reply_text("❌ Не найдена запись о создании токена.")
                return
            
            target_user_id = audit_logs[0].get('target_user_id')
            if not target_user_id:
                await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "no_target_user_id")
                await update.message.reply_text("❌ Не найден ID целевого пользователя.")
                return
            
            # Выполняем удаление модератора (деактивацию)
            success = await self.db.update_moderator_status(target_user_id, False)
            
            if success:
                # Логируем успешное удаление
                await self._log_security_event(user_id, "remove_moderator_success", target_user_id=target_user_id)
                
                await update.message.reply_text(f"✅ Модератор {target_user_id} деактивирован")
                
                # Уведомляем бывшего модератора
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="📋 Ваши права модератора были отозваны.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить бывшего модератора {target_user_id}: {e}")
            else:
                await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "database_error")
                await update.message.reply_text("❌ Ошибка при удалении модератора из базы данных.")
                
        except Exception as e:
            await self._log_security_event(user_id, "confirm_remove_moderator_attempt", "exception", details=str(e))
            logger.error(f"Ошибка подтверждения удаления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при подтверждении операции.")

    async def list_moderators_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для просмотра списка модераторов"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator:
            await update.message.reply_text("❌ У вас нет прав модератора.")
            return
        
        # Получаем список модераторов
        moderators = await self.db.get_all_moderators()
        
        if not moderators:
            await update.message.reply_text("👥 Модераторы не найдены.")
            return
        
        text = "👥 <b>Список модераторов:</b>\n\n"
        
        for mod in moderators:
            status = "✅" if mod.is_active else "❌"
            text += f"{status} <code>{mod.user_id}</code> - {mod.role}\n"
        
        await update.message.reply_text(text, parse_mode='HTML')

    async def audit_log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для просмотра лога аудита (только для super_admin)"""
        user_id = update.effective_user.id
        
        # 🔒 ENHANCED SECURITY: Проверка прав
        moderator = await self.db.get_moderator(user_id)
        if not moderator or moderator.role != 'super_admin':
            await self._log_security_event(user_id, "audit_log_attempt", "unauthorized")
            await update.message.reply_text("❌ У вас нет прав для просмотра лога аудита.")
            return
        
        # Получаем параметры команды
        limit = 20
        if context.args and len(context.args) > 0:
            try:
                limit = min(int(context.args[0]), 100)  # Максимум 100 записей
            except ValueError:
                await update.message.reply_text("❌ Неверный формат лимита. Используйте число.")
                return
        
        # Получаем лог аудита
        audit_logs = await self.db.get_admin_audit_log(limit=limit)
        
        if not audit_logs:
            await update.message.reply_text("📋 Лог аудита пуст.")
            return
        
        # Формируем сообщение
        text = f"🔍 <b>Лог аудита (последние {len(audit_logs)} записей)</b>\n\n"
        
        for i, log_entry in enumerate(audit_logs, 1):
            admin_id = log_entry['admin_user_id']
            action = log_entry['action_type']
            target_id = log_entry.get('target_user_id', 'N/A')
            details = log_entry.get('details', '')
            created_at = log_entry['created_at']
            
            # Форматируем время
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                time_str = dt.strftime('%d.%m.%Y %H:%M')
            except:
                time_str = created_at
            
            text += f"{i}. <b>{action}</b>\n"
            text += f"   👤 Админ: {admin_id}\n"
            if target_id != 'N/A':
                text += f"   🎯 Цель: {target_id}\n"
            if details:
                text += f"   📝 Детали: {details[:50]}{'...' if len(details) > 50 else ''}\n"
            text += f"   ⏰ Время: {time_str}\n\n"
            
            # Ограничиваем длину сообщения
            if len(text) > 3500:
                text += f"... и еще {len(audit_logs) - i} записей"
                break
        
        await update.message.reply_text(text, parse_mode='HTML')
        
        # Логируем просмотр аудита
        await self._log_security_event(user_id, "audit_log_view", "success", details=f"Limit: {limit}")

    async def security_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для просмотра статистики безопасности (только для super_admin)"""
        user_id = update.effective_user.id
        
        # 🔒 ENHANCED SECURITY: Проверка прав
        moderator = await self.db.get_moderator(user_id)
        if not moderator or moderator.role != 'super_admin':
            await self._log_security_event(user_id, "security_stats_attempt", "unauthorized")
            await update.message.reply_text("❌ У вас нет прав для просмотра статистики безопасности.")
            return
        
        # Получаем статистику
        stats = await self.db.get_admin_action_stats(days=30)
        
        text = "📊 <b>Статистика безопасности (30 дней)</b>\n\n"
        
        if stats:
            text += f"🔢 <b>Всего действий:</b> {stats.get('total_actions', 0)}\n\n"
            
            # Группируем по типам действий
            action_groups = {}
            for action, count in stats.items():
                if action == 'total_actions':
                    continue
                
                base_action = action.split('_')[0] if '_' in action else action
                if base_action not in action_groups:
                    action_groups[base_action] = 0
                action_groups[base_action] += count
            
            text += "<b>По типам действий:</b>\n"
            for action, count in sorted(action_groups.items()):
                text += f"• {action}: {count}\n"
        else:
            text += "📋 Нет данных за последние 30 дней"
        
        await update.message.reply_text(text, parse_mode='HTML')
        
        # Логируем просмотр статистики
        await self._log_security_event(user_id, "security_stats_view", "success")

    async def security_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /security_stats - статистика безопасности системы"""
        user_id = update.effective_user.id
        
        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            await update.message.reply_text("❌ У вас нет прав модератора")
            return
        
        try:
            # Получаем системную статистику безопасности
            system_stats = get_system_security_stats()
            security_summary = get_security_summary()
            
            text = "🛡️ <b>Статистика безопасности системы</b>\n\n"
            
            # Статистика пользователей
            user_stats = system_stats.get('user_stats', {})
            text += f"👥 <b>Пользователи:</b>\n"
            text += f"• Всего отслеживается: {user_stats.get('total_users', 0)}\n"
            text += f"• Заблокировано: {user_stats.get('blocked_users', 0)}\n"
            
            # Уровни риска
            risk_levels = user_stats.get('risk_levels', {})
            if risk_levels:
                text += f"• Уровни риска:\n"
                for level, count in risk_levels.items():
                    emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(level, "⚪")
                    text += f"  {emoji} {level.title()}: {count}\n"
            
            # Статистика запросов
            request_stats = system_stats.get('request_stats', {})
            if request_stats:
                text += f"\n📊 <b>Активность (последние 5 мин):</b>\n"
                for req_type, count in request_stats.items():
                    text += f"• {req_type}: {count}\n"
            
            # События безопасности
            security_stats = system_stats.get('security_stats', {})
            text += f"\n🚨 <b>События безопасности:</b>\n"
            text += f"• Всего событий: {security_stats.get('total_events', 0)}\n"
            text += f"• За последний час: {security_stats.get('recent_events', 0)}\n"
            
            # События по серьезности
            events_by_severity = security_stats.get('events_by_severity', {})
            if events_by_severity:
                text += f"• По серьезности:\n"
                for severity, count in events_by_severity.items():
                    emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🚨", "critical": "💥"}.get(severity, "❓")
                    text += f"  {emoji} {severity.title()}: {count}\n"
            
            # Время работы системы
            uptime = system_stats.get('system_uptime', 0)
            if uptime > 0:
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)
                text += f"\n⏱️ <b>Время работы:</b> {hours}ч {minutes}м\n"
            
            # Мониторинг пользователей
            monitored_users = security_summary.get('monitored_users', 0)
            blocked_patterns = security_summary.get('blocked_patterns', 0)
            text += f"\n🔍 <b>Мониторинг:</b>\n"
            text += f"• Отслеживается пользователей: {monitored_users}\n"
            text += f"• Заблокировано паттернов: {blocked_patterns}\n"
            
            await update.message.reply_text(text, parse_mode='HTML')
            
            # Логируем просмотр статистики безопасности
            await self._log_security_event(user_id, "security_stats_view", "success")
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики безопасности: {e}")
            await update.message.reply_text("❌ Ошибка получения статистики безопасности")

    async def user_security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /user_security - информация о безопасности пользователя"""
        user_id = update.effective_user.id
        
        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            await update.message.reply_text("❌ У вас нет прав модератора")
            return
        
        # Получаем ID пользователя из аргументов команды
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID пользователя\n"
                "Использование: /user_security <user_id>"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя")
            return
        
        try:
            # Получаем отчет по безопасности пользователя
            security_report = get_user_security_report(target_user_id)
            
            text = f"🛡️ <b>Отчет по безопасности пользователя {target_user_id}</b>\n\n"
            
            # Статистика rate limiter
            rate_limiter_stats = security_report.get('rate_limiter_stats', {})
            if rate_limiter_stats and 'error' not in rate_limiter_stats:
                text += f"📊 <b>Rate Limiter:</b>\n"
                text += f"• Всего запросов: {rate_limiter_stats.get('total_requests', 0)}\n"
                text += f"• Нарушений: {rate_limiter_stats.get('violation_count', 0)}\n"
                text += f"• Уровень риска: {rate_limiter_stats.get('risk_level', 'unknown').title()}\n"
                text += f"• Заблокирован: {'Да' if rate_limiter_stats.get('is_blocked') else 'Нет'}\n"
                
                if rate_limiter_stats.get('is_blocked'):
                    blocked_until = rate_limiter_stats.get('blocked_until')
                    if blocked_until:
                        import time
                        remaining = int(blocked_until - time.time())
                        text += f"• Блокировка до: {remaining}с\n"
                
                # Подозрительные паттерны
                suspicious_patterns = rate_limiter_stats.get('suspicious_patterns', [])
                if suspicious_patterns:
                    text += f"• Подозрительные паттерны: {', '.join(suspicious_patterns)}\n"
                
                # Недавние запросы
                recent_requests = rate_limiter_stats.get('recent_requests_count', 0)
                text += f"• Запросов за 5 мин: {recent_requests}\n"
            else:
                text += f"📊 <b>Rate Limiter:</b> Данные недоступны\n"
            
            # Данные middleware
            middleware_data = security_report.get('middleware_data', {})
            if middleware_data:
                text += f"\n🔍 <b>Middleware:</b>\n"
                
                # Подозрительный счет
                suspicious_score = middleware_data.get('suspicious_score', 0)
                text += f"• Подозрительный счет: {suspicious_score}\n"
                
                # Частота команд
                command_frequency = middleware_data.get('command_frequency', 0)
                text += f"• Частота команд: {command_frequency}\n"
                
                # Частота callback'ов
                callback_frequency = middleware_data.get('callback_frequency', 0)
                text += f"• Частота callback'ов: {callback_frequency}\n"
                
                # Дублирующиеся callback'ы
                duplicate_count = middleware_data.get('duplicate_count', 0)
                if duplicate_count > 0:
                    text += f"• Дублирующиеся callback'ы: {duplicate_count}\n"
            
            # Время первого появления
            first_seen = security_report.get('timestamp', 0)
            if first_seen:
                import time
                from datetime import datetime
                first_seen_dt = datetime.fromtimestamp(first_seen)
                text += f"\n⏰ <b>Время отчета:</b> {first_seen_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            await update.message.reply_text(text, parse_mode='HTML')
            
            # Логируем просмотр отчета пользователя
            await self._log_security_event(user_id, "user_security_view", "success", 
                                         details=f"Target user: {target_user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка получения отчета пользователя {target_user_id}: {e}")
            await update.message.reply_text("❌ Ошибка получения отчета пользователя")

    async def security_events_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /security_events - последние события безопасности"""
        user_id = update.effective_user.id
        
        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            await update.message.reply_text("❌ У вас нет прав модератора")
            return
        
        # Получаем количество событий (по умолчанию 10)
        limit = 10
        if context.args:
            try:
                limit = min(int(context.args[0]), 50)  # Максимум 50 событий
            except ValueError:
                pass
        
        try:
            # Получаем последние события безопасности
            events = get_recent_security_events(limit)
            
            if not events:
                await update.message.reply_text("📋 Нет событий безопасности")
                return
            
            text = f"🚨 <b>Последние {len(events)} событий безопасности</b>\n\n"
            
            for i, event in enumerate(events, 1):
                # Время события
                event_time = event.get('datetime', 'Unknown')
                if event_time != 'Unknown':
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                        event_time = dt.strftime('%H:%M:%S')
                    except:
                        pass
                
                # Эмодзи по серьезности
                severity_emoji = {
                    "low": "ℹ️",
                    "medium": "⚠️", 
                    "high": "🚨",
                    "critical": "💥"
                }.get(event.get('severity', 'unknown'), "❓")
                
                # Тип события
                event_type = event.get('event_type', 'unknown')
                event_type_display = {
                    "rate_limit_exceeded": "Превышен лимит",
                    "burst_limit_exceeded": "Превышен burst лимит",
                    "suspicious_activity": "Подозрительная активность",
                    "security_stats_view": "Просмотр статистики",
                    "user_security_view": "Просмотр отчета пользователя"
                }.get(event_type, event_type)
                
                text += f"{i}. {severity_emoji} <b>{event_time}</b>\n"
                text += f"   👤 User: {event.get('user_id', 'Unknown')}\n"
                text += f"   📝 Event: {event_type_display}\n"
                text += f"   🔍 Severity: {event.get('severity', 'unknown').title()}\n"
                
                # Детали события
                details = event.get('details', {})
                if details:
                    if 'limit_type' in details:
                        text += f"   🎯 Type: {details['limit_type']}\n"
                    if 'violation_count' in details:
                        text += f"   ⚠️ Violations: {details['violation_count']}\n"
                    if 'risk_level' in details:
                        text += f"   🚨 Risk: {details['risk_level'].title()}\n"
                
                text += "\n"
            
            # Если событий много, обрезаем текст
            if len(text) > 4000:
                text = text[:3900] + "\n\n... (события обрезаны)"
            
            await update.message.reply_text(text, parse_mode='HTML')
            
            # Логируем просмотр событий
            await self._log_security_event(user_id, "security_events_view", "success", 
                                         details=f"Limit: {limit}")
            
        except Exception as e:
            logger.error(f"Ошибка получения событий безопасности: {e}")
            await update.message.reply_text("❌ Ошибка получения событий безопасности")

    async def unblock_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unblock_user - разблокировка пользователя"""
        user_id = update.effective_user.id
        
        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            await update.message.reply_text("❌ У вас нет прав модератора")
            return
        
        # Получаем ID пользователя из аргументов команды
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID пользователя\n"
                "Использование: /unblock_user <user_id>"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя")
            return
        
        try:
            # Импортируем rate_limiter для разблокировки
            from bot.utils.rate_limiter import rate_limiter
            
            # Разблокируем пользователя
            unblocked = rate_limiter.unblock_user(target_user_id)
            
            if unblocked:
                # Сбрасываем нарушения пользователя
                rate_limiter.reset_user_violations(target_user_id)
                
                await update.message.reply_text(
                    f"✅ Пользователь {target_user_id} успешно разблокирован\n"
                    f"🔄 Нарушения сброшены"
                )
                
                # Логируем разблокировку
                await self._log_security_event(user_id, "user_unblocked", "high", 
                                             details=f"Target user: {target_user_id}")
            else:
                await update.message.reply_text(f"ℹ️ Пользователь {target_user_id} не был заблокирован")
            
        except Exception as e:
            logger.error(f"Ошибка разблокировки пользователя {target_user_id}: {e}")
            await update.message.reply_text("❌ Ошибка разблокировки пользователя")

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик callback запросов модерации"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # Пытаемся валидировать как безопасный callback
        secure_validation = validate_secure_callback(data, user_id)
        if secure_validation.is_valid:
            await self._handle_secure_moderation_callback(query, secure_validation, context)
            return
        
        # Если не безопасный callback, используем старую логику для совместимости
        await self._handle_legacy_moderation_callback(query, data, context)
    
    async def _handle_secure_moderation_callback(self, query, validation: CallbackValidationResult, context):
        """Обработка безопасных callback'ов модерации"""
        action = validation.action
        user_id = validation.user_id
        parsed_data = validation.parsed_data or {}
        
        logger.info(f"Processing secure moderation callback: {action} for user {user_id}")
        
        try:
            if action == "moderation_menu":
                await self.show_moderation_menu(update, context)
            elif action == "mod_queue":
                await self.show_moderation_queue(update, context)
            elif action == "mod_approved":
                await self.show_approved_profiles(update, context)
            elif action == "mod_rejected":
                await self.show_rejected_profiles(update, context)
            elif action == "mod_stats":
                await self.show_moderation_stats(update, context)
            elif action == "approve_user":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    # Создаем временный callback для совместимости
                    query.data = f"approve_{target_user_id}"
                    await self.approve_profile(update, context)
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            elif action == "reject_user":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    # Создаем временный callback для совместимости
                    query.data = f"reject_{target_user_id}"
                    await self.reject_profile(update, context)
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            elif action == "next_profile":
                await self.show_next_profile(query, context)
            else:
                logger.warning(f"Unknown secure moderation callback action: {action}")
                await query.answer("❌ Неизвестная команда")
                
        except Exception as e:
            logger.error(f"Error handling secure moderation callback {action}: {e}")
            await query.answer("❌ Произошла ошибка при обработке команды")
    
    async def _handle_legacy_moderation_callback(self, query, data, context):
        """Обработка legacy callback'ов модерации для совместимости"""
        try:
            if data == "moderation_menu":
                await self.show_moderation_menu(update, context)
            elif data == "mod_queue":
                await self.show_moderation_queue(update, context)
            elif data == "mod_approved":
                await self.show_approved_profiles(update, context)
            elif data == "mod_rejected":
                await self.show_rejected_profiles(update, context)
            elif data == "mod_stats":
                await self.show_moderation_stats(update, context)
            elif data.startswith("approve_"):
                await self.approve_profile(update, context)
            elif data.startswith("reject_reason_"):  # 🔥 ИСПРАВЛЕНИЕ: проверяем reject_reason_ ПЕРЕД reject_
                await self.reject_with_reason(update, context)
            elif data.startswith("reject_"):
                await self.reject_profile(update, context)
            elif data == "next_profile":
                await self.show_next_profile(query, context)
            else:
                await query.answer("❌ Неизвестная команда")
        except Exception as e:
            logger.error(f"Ошибка обработки callback в модерации: {e}")
            await query.answer("❌ Произошла ошибка")

    async def show_approved_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список одобренных профилей"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем одобренные профили
        profiles = await self.db.get_profiles_for_moderation('approved', limit=10)
        
        if not profiles:
            text = "✅ <b>Одобренные анкеты</b>\n\nОдобренных анкет пока нет."
        else:
            text = f"✅ <b>Одобренные анкеты ({len(profiles)})</b>\n\n"
            
            for i, profile_data in enumerate(profiles, 1):
                nickname = profile_data['game_nickname']
                user_name = profile_data['first_name']
                moderated_at = profile_data.get('moderated_at', 'Неизвестно')
                
                text += f"{i}. <b>{nickname}</b> ({user_name})\n"
                text += f"   📅 Одобрено: {moderated_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def show_rejected_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список отклоненных профилей"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем отклоненные профили
        profiles = await self.db.get_profiles_for_moderation('rejected', limit=10)
        
        if not profiles:
            text = "❌ <b>Отклоненные анкеты</b>\n\nОтклоненных анкет пока нет."
        else:
            text = f"❌ <b>Отклоненные анкеты ({len(profiles)})</b>\n\n"
            
            for i, profile_data in enumerate(profiles, 1):
                nickname = profile_data['game_nickname']
                user_name = profile_data['first_name']
                reason = profile_data.get('moderation_reason', 'Причина не указана')
                moderated_at = profile_data.get('moderated_at', 'Неизвестно')
                
                text += f"{i}. <b>{nickname}</b> ({user_name})\n"
                text += f"   🚫 Причина: {reason}\n"
                text += f"   📅 Отклонено: {moderated_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def show_moderation_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает статистику модерации"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем статистику
        stats = await self.db.get_moderation_stats()
        
        text = "📊 <b>Статистика модерации</b>\n\n"
        text += f"⏳ <b>На модерации:</b> {stats.get('profiles_pending', 0)}\n"
        text += f"✅ <b>Одобрено:</b> {stats.get('profiles_approved', 0)}\n"
        text += f"❌ <b>Отклонено:</b> {stats.get('profiles_rejected', 0)}\n"
        text += f"👥 <b>Активных модераторов:</b> {stats.get('active_moderators', 0)}\n\n"
        
        total = stats.get('profiles_approved', 0) + stats.get('profiles_rejected', 0)
        if total > 0:
            approval_rate = round((stats.get('profiles_approved', 0) / total) * 100, 1)
            text += f"📈 <b>Процент одобрения:</b> {approval_rate}%"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые сообщения (для кастомных причин отклонения)"""
        if context.user_data.get('awaiting_rejection_reason'):
            user_id = context.user_data.get('rejecting_user_id')
            moderator_id = update.effective_user.id
            # Санитизация пользовательского ввода
            custom_reason = sanitize_text_input(update.message.text.strip(), max_length=200)
            
            if len(custom_reason) > 200:
                await update.message.reply_text(
                    "❌ Причина слишком длинная. Максимум 200 символов.\n"
                    "Попробуйте сократить:"
                )
                return
            
            # Очищаем флаг ожидания
            context.user_data['awaiting_rejection_reason'] = False
            
            # Отклоняем профиль с кастомной причиной
            success = await self.db.moderate_profile(user_id, 'rejected', moderator_id, custom_reason)
            
            if success:
                await update.message.reply_text(f"❌ Профиль отклонен с причиной: {custom_reason}")
                
                # Отправляем уведомление пользователю
                await self.send_moderation_notification(user_id, 'rejected', context, custom_reason)
                
                # Показываем следующую анкету или меню модерации
                profiles = await self.db.get_profiles_for_moderation('pending', limit=1)
                
                if profiles:
                    profile_data = profiles[0]
                    context.user_data['moderating_profile'] = profile_data
                    
                    text = "👨‍💼 <b>Модерация анкеты</b>\n\n"
                    text += await self.format_profile_for_moderation(profile_data)
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{profile_data['user_id']}"),
                            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{profile_data['user_id']}")
                        ],
                        [InlineKeyboardButton("⏭️ Следующая анкета", callback_data="next_profile")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]
                    ]
                    
                    await update.message.reply_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        "✅ Все анкеты проверены!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]])
                    )
            else:
                await update.message.reply_text("❌ Ошибка при отклонении профиля")