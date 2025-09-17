"""
Обработчики для работы с профилем пользователя в CIS FINDER Bot
Создано организацией Twizz_Project
"""
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.utils.keyboards import Keyboards
from bot.utils.cs2_data import (
    get_role_by_name, CS2_MAPS, PLAYTIME_OPTIONS,
    validate_faceit_url, format_elo_display, format_faceit_display
)
from bot.utils.faceit_analyzer import faceit_analyzer
from bot.database.operations import DatabaseManager

logger = logging.getLogger(__name__)

# Состояния для создания профиля
ENTERING_NICKNAME, SELECTING_ELO, ENTERING_FACEIT_URL, SELECTING_ROLE, SELECTING_MAPS, SELECTING_PLAYTIME, SELECTING_CATEGORIES, ENTERING_DESCRIPTION, SELECTING_MEDIA = range(9)

# Состояния для редактирования медиа
EDITING_MEDIA_TYPE = 100

class ProfileHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def _log_back_navigation(self, user_id: int, current_state: str, target_state: str, 
                           user_data_context: dict = None, additional_info: str = "",
                           timestamp: str = None, navigation_validation: str = None,
                           conversation_state: str = None, step_number: int = None):
        """Centralized logging method for back button navigation with enhanced tracking"""
        import datetime
        
        # Generate timestamp if not provided
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Sanitize user data for privacy
        safe_context = {}
        if user_data_context:
            for key, value in user_data_context.items():
                if key in ['creating_profile', 'editing_profile']:
                    # Sanitize profile data
                    if isinstance(value, dict):
                        safe_context[key] = {k: v for k, v in value.items() 
                                           if k not in ['faceit_url', 'game_nickname']}
                    else:
                        safe_context[key] = str(type(value))
                elif key in ['editing_field', 'editing_media', 'selecting_media_type']:
                    safe_context[key] = value
                else:
                    safe_context[key] = str(type(value)) if value else None
        
        log_message = (f"🔙 BACK NAVIGATION: user_id={user_id}, timestamp={timestamp}, "
                      f"current_state='{current_state}', target_state='{target_state}', "
                      f"context={safe_context}")
        
        if conversation_state:
            log_message += f", conversation_state='{conversation_state}'"
            
        if step_number:
            log_message += f", step_number={step_number}"
            
        if navigation_validation:
            log_message += f", validation='{navigation_validation}'"
        
        if additional_info:
            log_message += f", info='{additional_info}'"
            
        # Use warning for potentially unexpected navigation patterns
        if "unexpected" in additional_info.lower() or "incorrect" in additional_info.lower():
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def _validate_navigation_flow(self, current_state: str, target_state: str, user_id: int, 
                                context_data: dict = None) -> dict:
        """Validates navigation flow and provides recovery suggestions"""
        # Define the correct profile creation sequence
        correct_flow = {
            "ENTERING_NICKNAME": "START",
            "SELECTING_ELO": "ENTERING_NICKNAME", 
            "ENTERING_FACEIT_URL": "SELECTING_ELO",
            "SELECTING_ROLE": "ENTERING_FACEIT_URL",
            "SELECTING_MAPS": "SELECTING_ROLE",
            "SELECTING_PLAYTIME": "SELECTING_MAPS",
            "SELECTING_CATEGORIES": "SELECTING_PLAYTIME",
            "ENTERING_DESCRIPTION": "SELECTING_CATEGORIES",
            "SELECTING_MEDIA": "ENTERING_DESCRIPTION"
        }
        
        expected_previous = correct_flow.get(current_state)
        is_valid = (target_state == expected_previous or 
                   target_state in ["CANCEL_CREATION", "PROFILE_CREATION_START"])
        
        validation_result = {
            "is_valid": is_valid,
            "expected_target": expected_previous,
            "actual_target": target_state,
            "current_state": current_state,
            "user_id": user_id,
            "validation_message": "",
            "recovery_suggestion": ""
        }
        
        if is_valid:
            validation_result["validation_message"] = f"Valid navigation: {current_state} → {target_state}"
        else:
            validation_result["validation_message"] = f"INVALID navigation: {current_state} → {target_state}, expected → {expected_previous}"
            validation_result["recovery_suggestion"] = f"Should navigate to {expected_previous} instead of {target_state}"
            
        # Log validation results
        if not is_valid:
            logger.warning(f"🚨 NAVIGATION VALIDATION FAILED: {validation_result['validation_message']} for user {user_id}")
            logger.warning(f"🔧 RECOVERY SUGGESTION: {validation_result['recovery_suggestion']}")
        else:
            logger.info(f"✅ NAVIGATION VALIDATED: {validation_result['validation_message']} for user {user_id}")
            
        return validation_result
    
    def _log_state_transition(self, user_id: int, from_state: str, to_state: str,
                            trigger: str, user_data_context: dict = None,
                            validation_result: dict = None):
        """Logs state transitions with comprehensive context and validation"""
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Sanitize user context for privacy
        safe_context = {}
        if user_data_context:
            for key, value in user_data_context.items():
                if key in ['creating_profile', 'editing_profile']:
                    if isinstance(value, dict):
                        # Only include non-sensitive profile data
                        safe_context[key] = {
                            k: v for k, v in value.items() 
                            if k in ['role', 'categories', 'description_length'] and v is not None
                        }
                        # Add counts for arrays without exposing data
                        if 'maps' in value:
                            safe_context[key]['maps_count'] = len(value['maps']) if value['maps'] else 0
                        if 'playtime_slots' in value:
                            safe_context[key]['playtime_count'] = len(value['playtime_slots']) if value['playtime_slots'] else 0
                elif key in ['editing_field', 'editing_media', 'selecting_media_type']:
                    safe_context[key] = value
        
        log_message = (
            f"🔄 STATE TRANSITION: user_id={user_id}, timestamp={timestamp}, "
            f"from='{from_state}', to='{to_state}', trigger='{trigger}', context={safe_context}"
        )
        
        if validation_result:
            log_message += f", validation={validation_result['validation_message']}"
            
        if validation_result and not validation_result['is_valid']:
            logger.error(log_message)
        else:
            logger.info(log_message)

    def _get_step_number_from_state(self, state: str) -> int:
        """Maps conversation states to step numbers for better tracking"""
        state_steps = {
            "ENTERING_NICKNAME": 1,
            "SELECTING_ELO": 2,
            "ENTERING_FACEIT_URL": 3,
            "SELECTING_ROLE": 4,
            "SELECTING_MAPS": 5,
            "SELECTING_PLAYTIME": 6,
            "SELECTING_CATEGORIES": 7,
            "ENTERING_DESCRIPTION": 8,
            "SELECTING_MEDIA": 9
        }
        return state_steps.get(state, 0)
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /profile - показывает профиль пользователя с медиа"""
        user_id = update.effective_user.id
        
        # Создаем пользователя если не существует
        await self.db.create_user(
            user_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name
        )
        
        # Проверяем есть ли профиль
        has_profile = await self.db.has_profile(user_id)
        is_rejected = False
        
        # DEBUG: Добавляем логирование для отладки
        logger.info(f"ProfileHandler.profile_command: user_id={user_id}, has_profile={has_profile}")
        
        if has_profile:
            profile = await self.db.get_profile(user_id)
            if profile:
                is_rejected = profile.is_rejected()
                
                # Показываем профиль с медиа сразу
                text = "👤 <b>Ваш профиль</b>\n\n"
                text += await self._format_profile_text(profile, show_faceit_stats=True)
                
                # Определяем клавиатуру в зависимости от статуса профиля
                if is_rejected:
                    reply_markup = Keyboards.profile_rejected_menu()
                else:
                    reply_markup = Keyboards.profile_main_menu()
                
                if update.callback_query:
                    query = update.callback_query
                    await query.answer()
                    
                    # Отправляем профиль с медиа
                    await self.send_profile_with_media(
                        chat_id=query.message.chat.id,
                        profile=profile,
                        text=text,
                        reply_markup=reply_markup,
                        context=context
                    )
                else:
                    # Отправляем профиль с медиа
                    await self.send_profile_with_media(
                        chat_id=update.effective_chat.id,
                        profile=profile,
                        text=text,
                        reply_markup=reply_markup,
                        context=context
                    )
            else:
                # Если has_profile = True, но get_profile = None, то профиль поврежден
                logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: has_profile=True, но get_profile=None для user_id={user_id}")
                text = (
                    "👤 <b>Ваш профиль</b>\n\n"
                    "❌ <b>Профиль поврежден</b>\n\n"
                    "Ваш профиль найден в базе данных, но содержит ошибки.\n"
                    "🆕 Рекомендуется создать новый профиль.\n\n"
                    "Если проблема повторяется, обратитесь в поддержку: @twizz_project"
                )
                
                if update.callback_query:
                    query = update.callback_query
                    await query.answer()
                    await self.safe_edit_or_send_message(
                        query,
                        text,
                        reply_markup=Keyboards.profile_no_profile_menu(),
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        text,
                        reply_markup=Keyboards.profile_no_profile_menu(),
                        parse_mode='HTML'
                    )
        else:
            # У пользователя нет профиля
            text = (
                "👤 <b>Ваш профиль</b>\n\n"
                "📝 У вас пока нет профиля.\n"
                "Создайте анкету, чтобы другие игроки могли вас найти!"
            )
            
            if update.callback_query:
                query = update.callback_query
                await query.answer()
                await self.safe_edit_or_send_message(
                    query,
                    text,
                    reply_markup=Keyboards.profile_no_profile_menu(),
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    text,
                    reply_markup=Keyboards.profile_no_profile_menu(),
                    parse_mode='HTML'
            )

    async def _format_profile_text(self, profile, show_faceit_stats=False) -> str:
        """Форматирует текст профиля для отображения"""
        from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname, PLAYTIME_OPTIONS, format_faceit_elo_display
        from bot.utils.faceit_analyzer import faceit_analyzer
        
        # Статус модерации
        moderation_status = getattr(profile, 'moderation_status', 'pending')
        if moderation_status == 'pending':
            text = "⏳ <b>Статус:</b> На модерации\n"
        elif moderation_status == 'approved':
            text = "✅ <b>Статус:</b> Одобрен\n"
        elif moderation_status == 'rejected':
            text = "❌ <b>Статус:</b> Отклонен\n"
            if hasattr(profile, 'moderation_reason') and profile.moderation_reason:
                text += f"<i>Причина: {profile.moderation_reason}</i>\n"
            text += "\n🆕 <b>Рекомендация:</b> Создайте новый профиль с учетом замечаний модераторов.\n"
        text += "\n"
        
        text += f"🎮 <b>Игровой ник:</b> {profile.game_nickname}\n"
        
        # Получаем ELO статистику через Faceit API
        elo_stats = None
        try:
            if profile.game_nickname and profile.game_nickname.strip():
                elo_stats = await faceit_analyzer.get_elo_stats_by_nickname(profile.game_nickname)
        except Exception as e:
            logger.warning(f"Не удалось получить ELO статистику для {profile.game_nickname}: {e}")
        
        # Отображаем ELO с мин/макс значениями если есть данные (ИСПРАВЛЕННАЯ ЛОГИКА)
        if elo_stats:
            # Проверяем корректность значений перед передачей в format_faceit_elo_display()
            lowest_elo = elo_stats.get('lowest_elo', 0)
            highest_elo = elo_stats.get('highest_elo', 0)
            
            # Дополнительная валидация ELO значений
            try:
                if isinstance(lowest_elo, (int, float)) and isinstance(highest_elo, (int, float)):
                    lowest_elo = int(lowest_elo) if lowest_elo >= 0 else 0
                    highest_elo = int(highest_elo) if highest_elo >= 0 else 0
                    
                    # Показываем мин/макс даже если API вернул ошибку, но есть валидные данные
                    if lowest_elo > 0 or highest_elo > 0:
                        logger.info(f"🔥 PROFILE: Показываем ELO с мин/макс для {profile.game_nickname}: мин={lowest_elo} макс={highest_elo}")
                        text += f"🎯 <b>ELO Faceit:</b> {format_faceit_elo_display(profile.faceit_elo, lowest_elo, highest_elo, profile.game_nickname)}\n"
                    else:
                        # Если мин/макс равны 0, показываем только текущий ELO
                        text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
                else:
                    logger.warning(f"⚠️ PROFILE: ELO значения некорректного типа для {profile.game_nickname}: lowest={type(lowest_elo)}, highest={type(highest_elo)}")
                    # Fallback на базовое отображение при некорректных данных
                    text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
            except Exception as elo_validation_error:
                logger.error(f"Ошибка валидации ELO для {profile.game_nickname}: {elo_validation_error}")
                # Fallback на базовое отображение при ошибке валидации
                text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
        else:
            # Fallback на базовое отображение ELO
            text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
        
        # Faceit профиль
        nickname = extract_faceit_nickname(profile.faceit_url)
        text += f"🔗 <b>Faceit:</b> <a href='{profile.faceit_url}'>{nickname}</a>\n"
        
        # Добавляем данные Faceit Analyser если включено
        if show_faceit_stats:
            try:
                faceit_url = getattr(profile, 'faceit_url', '')
                if faceit_url:
                    logger.debug(f"Получение Faceit Analyser данных для собственного профиля {profile.user_id}")
                    faceit_data = await faceit_analyzer.get_enhanced_profile_info(faceit_url)
                    
                    # Диаграммы отключены
                        
            except Exception as faceit_error:
                logger.warning(f"Ошибка получения данных Faceit Analyser для профиля {profile.user_id}: {faceit_error}")
                # Не критично, продолжаем без данных от API
        
        text += f"👤 <b>Роль:</b> {format_role_display(profile.role)}\n"
        text += f"🗺️ <b>Любимые карты:</b> {', '.join(profile.favorite_maps[:3])}{'...' if len(profile.favorite_maps) > 3 else ''}\n"
        
        # Время игры
        time_names = []
        for slot_id in profile.playtime_slots:
            time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
            if time_option:
                time_names.append(time_option['emoji'])
        text += f"⏰ <b>Время игры:</b> {' '.join(time_names)}\n"
        
        # Категории
        if hasattr(profile, 'categories') and profile.categories:
            from bot.utils.cs2_data import format_categories_display
            categories_text = format_categories_display(profile.categories, max_count=2)
            text += f"🎮 <b>Категории:</b> {categories_text}\n"
        
        if profile.description:
            text += f"\n💬 <b>О себе:</b> {profile.description[:100]}{'...' if len(profile.description) > 100 else ''}"
        
        # Информация о медиа
        if profile.has_media():
            media_icon = "📷" if profile.is_photo() else "🎥"
            text += f"\n{media_icon} <b>Медиа:</b> прикреплено"
        
        return text

    async def send_profile_with_media(self, chat_id: int, profile, text: str, reply_markup=None, context=None):
        """Отправляет профиль с медиа если есть"""
        try:
            if profile.has_media():
                if profile.is_photo():
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=profile.media_file_id,
                        caption=text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                elif profile.is_video():
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=profile.media_file_id,
                        caption=text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            else:
                # Отправляем только текст
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки профиля с медиа: {e}")
            # Фолбэк - отправляем только текст
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )

    # === СОЗДАНИЕ ПРОФИЛЯ ===
    
    async def start_profile_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс создания профиля"""
        query = update.callback_query
        await query.answer()
        
        # Инициализируем временные данные профиля
        context.user_data['creating_profile'] = {
            'game_nickname': None,
            'faceit_elo': None,
            'faceit_url': None,
            'role': None,
            'maps': [],
            'playtime_slots': [],
            'categories': [],
            'description': None,
            'media_type': None,
            'media_file_id': None
        }
        
        await query.edit_message_text(
            "🎮 <b>Создание профиля CIS FINDER</b>\n\n"
            "Давайте создадим ваш профиль для поиска тиммейтов!\n"
            "Это займет всего несколько минут.\n\n"
            "<b>Шаг 1/7:</b> Введите ваш игровой ник\n\n"
            "🎮 Это имя будет видно другим игрокам в поиске.\n"
            "📊 <b>Важно:</b> Ваш ник используется для получения статистики ELO с Faceit.\n"
            "Используйте ваш основной игровой ник (Steam, Discord, Faceit).",
            parse_mode='HTML'
        )
        
        return ENTERING_NICKNAME

    async def handle_nickname_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод игрового ника"""
        nickname = update.message.text.strip()
        
        # Валидация ника
        if len(nickname) < 2:
            await update.message.reply_text(
                "❌ Ник слишком короткий. Минимум 2 символа.\n"
                "Попробуйте еще раз:",
                parse_mode='HTML'
            )
            return ENTERING_NICKNAME
        
        if len(nickname) > 32:
            await update.message.reply_text(
                "❌ Ник слишком длинный. Максимум 32 символа.\n"
                "Попробуйте еще раз:",
                parse_mode='HTML'
            )
            return ENTERING_NICKNAME
        
        # Сохраняем ник
        context.user_data['creating_profile']['game_nickname'] = nickname
        
        # Log state transition with validation
        validation_result = self._validate_navigation_flow(
            current_state="ENTERING_NICKNAME",
            target_state="SELECTING_ELO", 
            user_id=update.effective_user.id,
            context_data=context.user_data
        )
        self._log_state_transition(
            user_id=update.effective_user.id,
            from_state="ENTERING_NICKNAME",
            to_state="SELECTING_ELO",
            trigger="nickname_input_valid",
            user_data_context=context.user_data,
            validation_result=validation_result
        )
        
        # Переходим к выбору ELO
        text = (
            "✅ <b>Игровой ник сохранен!</b>\n\n"
            f"🎮 <b>Ваш ник:</b> {nickname}\n\n"
            "<b>Шаг 2/7:</b> Введите ваше точное ELO на Faceit:"
        )
        
        keyboard = Keyboards.elo_input_menu()
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
        
        return SELECTING_ELO

    async def handle_elo_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор ELO"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "back":
            # Enhanced back button logging with step validation
            self._log_back_navigation(
                user_id=update.effective_user.id,
                current_state="SELECTING_ELO",
                target_state="CANCEL_CREATION",
                user_data_context=context.user_data,
                additional_info="Step 2 (SELECTING_ELO) → CANCEL: Back from ELO selection cancels profile creation",
                navigation_validation="EXPECTED - ELO is step 2, back cancels creation",
                conversation_state="PROFILE_CREATION",
                step_number=2
            )
            return await self.cancel_creation(update, context)
        elif query.data == "elo_back":
            # Возврат к меню выбора ELO из экрана ввода точного ELO
            await query.edit_message_text(
                "<b>Шаг 2/7:</b> Введите ваше точное ELO на Faceit:",
                reply_markup=Keyboards.elo_input_menu(),
                parse_mode='HTML'
            )
            return SELECTING_ELO
        elif query.data == "elo_custom":
            await query.edit_message_text(
                "📝 <b>Введите ваше точное ELO на Faceit</b>\n\n"
                "Пример: 1250\n"
                "Диапазон: 1-6000",
                reply_markup=Keyboards.back_button("elo_back"),
                parse_mode='HTML'
            )
            return SELECTING_ELO

    async def handle_exact_elo_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод точного ELO при создании профиля"""
        text = update.message.text.strip()
        
        # Проверяем на точное ELO
        if text.isdigit():
            elo = int(text)
            if 1 <= elo <= 6000:
                context.user_data['creating_profile']['faceit_elo'] = elo
                
                # Log state transition with validation
                validation_result = self._validate_navigation_flow(
                    current_state="SELECTING_ELO",
                    target_state="ENTERING_FACEIT_URL", 
                    user_id=update.effective_user.id,
                    context_data=context.user_data
                )
                self._log_state_transition(
                    user_id=update.effective_user.id,
                    from_state="SELECTING_ELO",
                    to_state="ENTERING_FACEIT_URL",
                    trigger="elo_input_valid",
                    user_data_context=context.user_data,
                    validation_result=validation_result
                )
                
                await update.message.reply_text(
                    f"✅ ELO сохранено: {format_elo_display(elo)}\n\n"
                    "<b>Шаг 3/7:</b> Отправьте ссылку на ваш профиль Faceit\n\n"
                    "Пример: https://www.faceit.com/ru/players/nickname",
                    reply_markup=Keyboards.back_button("elo_back"),
                    parse_mode='HTML'
                )
                return ENTERING_FACEIT_URL
            else:
                await update.message.reply_text(
                    "❌ ELO должно быть от 1 до 6000. Попробуйте еще раз:"
                )
                return SELECTING_ELO
        else:
            await update.message.reply_text(
                "❌ Введите корректное число от 1 до 6000. Попробуйте еще раз:"
            )
            return SELECTING_ELO

    async def handle_faceit_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод ссылки на Faceit"""
        if update.message:
            text = update.message.text.strip()
            
            # Проверяем на ссылку Faceit
            if validate_faceit_url(text):
                context.user_data['creating_profile']['faceit_url'] = text
                
                # Log state transition with validation
                validation_result = self._validate_navigation_flow(
                    current_state="ENTERING_FACEIT_URL",
                    target_state="SELECTING_ROLE", 
                    user_id=update.effective_user.id,
                    context_data=context.user_data
                )
                self._log_state_transition(
                    user_id=update.effective_user.id,
                    from_state="ENTERING_FACEIT_URL",
                    to_state="SELECTING_ROLE",
                    trigger="faceit_url_valid",
                    user_data_context=context.user_data,
                    validation_result=validation_result
                )
                
                await update.message.reply_text(
                    f"✅ Faceit профиль добавлен!\n\n"
                    "<b>Шаг 4/7:</b> Выберите вашу основную роль в команде:",
                    reply_markup=Keyboards.role_selection(),
                    parse_mode='HTML'
                )
                return SELECTING_ROLE
            else:
                await update.message.reply_text(
                    "❌ Неверная ссылка на Faceit профиль!\n"
                    "Ссылка должна быть в формате:\n"
                    "https://www.faceit.com/ru/players/nickname\n\n"
                    "Попробуйте еще раз:"
                )
                return ENTERING_FACEIT_URL
        
        return ENTERING_FACEIT_URL

    async def handle_role_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор роли"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "back":
            # Enhanced back button logging with step validation
            self._log_back_navigation(
                user_id=update.effective_user.id,
                current_state="SELECTING_ROLE",
                target_state="ENTERING_FACEIT_URL",
                user_data_context=context.user_data,
                additional_info="Step 4 (SELECTING_ROLE) → Step 3 (ENTERING_FACEIT_URL): Correct navigation flow",
                navigation_validation="EXPECTED - Role selection goes back to Faceit URL",
                conversation_state="PROFILE_CREATION",
                step_number=4
            )
            # Navigate back to faceit URL input step
            text = (
                "✅ Роль будет выбрана позже.\n\n"
                "<b>Шаг 3/7:</b> Отправьте ссылку на ваш профиль Faceit\n\n"
                "Пример: https://www.faceit.com/ru/players/nickname"
            )
            await query.edit_message_text(text, reply_markup=Keyboards.back_button("elo_back"), parse_mode='HTML')
            return ENTERING_FACEIT_URL
            
        role_name = query.data.replace("role_", "")
        role_data = get_role_by_name(role_name)
        
        if not role_data:
            await query.edit_message_text(
                "❌ Неизвестная роль. Попробуйте еще раз.",
                reply_markup=Keyboards.role_selection()
            )
            return SELECTING_ROLE
        
        # Сохраняем выбранную роль
        context.user_data['creating_profile']['role'] = role_name
        
        # Log state transition with validation
        validation_result = self._validate_navigation_flow(
            current_state="SELECTING_ROLE",
            target_state="SELECTING_MAPS", 
            user_id=update.effective_user.id,
            context_data=context.user_data
        )
        self._log_state_transition(
            user_id=update.effective_user.id,
            from_state="SELECTING_ROLE",
            to_state="SELECTING_MAPS",
            trigger="role_selected",
            user_data_context=context.user_data,
            validation_result=validation_result
        )
        
        from bot.utils.cs2_data import format_role_display
        await query.edit_message_text(
            f"✅ Роль выбрана: {format_role_display(role_name)}\n\n"
            "<b>Шаг 5/7:</b> Выберите ваши любимые карты (можно выбрать несколько):",
            reply_markup=Keyboards.maps_selection([]),
            parse_mode='HTML'
        )
        
        return SELECTING_MAPS

    async def handle_maps_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор карт"""
        query = update.callback_query
        await query.answer()
        
        current_maps = context.user_data['creating_profile']['maps']
        
        if query.data == "back":
            # Enhanced back button logging - NAVIGATION BUG FIXED!
            self._log_back_navigation(
                user_id=update.effective_user.id,
                current_state="SELECTING_MAPS",
                target_state="SELECTING_ROLE",
                user_data_context=context.user_data,
                additional_info="Correct navigation: Step 5 (SELECTING_MAPS) → Step 4 (SELECTING_ROLE)",
                navigation_validation="CORRECTED - Previously went to ENTERING_FACEIT_URL incorrectly",
                step_number=5
            )
            # Return to role selection instead of faceit URL input
            text = (
                f"✅ Карты выбраны: {', '.join(current_maps) if current_maps else 'Пока не выбраны'}\n\n"
                "<b>Шаг 4/7:</b> Выберите вашу основную роль в команде:"
            )
            await query.edit_message_text(text, reply_markup=Keyboards.role_selection(), parse_mode='HTML')
            return SELECTING_ROLE
        elif query.data == "maps_done":
            if len(current_maps) == 0:
                await query.answer("❌ Выберите хотя бы одну карту!", show_alert=True)
                return SELECTING_MAPS
                
            await query.edit_message_text(
                f"✅ Карты выбраны: {', '.join(current_maps)}\n\n"
                "<b>Шаг 6/7:</b> Выберите удобное время игры (можно выбрать несколько):",
                reply_markup=Keyboards.playtime_selection([]),
                parse_mode='HTML'
            )
            return SELECTING_PLAYTIME
        elif query.data.startswith("map_"):
            map_name = query.data.replace("map_", "")
            
            # Переключаем выбор карты
            if map_name in current_maps:
                current_maps.remove(map_name)
            else:
                current_maps.append(map_name)
            
            context.user_data['creating_profile']['maps'] = current_maps
            
            # Обновляем клавиатуру
            await query.edit_message_reply_markup(
                reply_markup=Keyboards.maps_selection(current_maps)
            )
            
        return SELECTING_MAPS

    async def handle_playtime_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор времени игры"""
        query = update.callback_query
        await query.answer()
        
        current_slots = context.user_data['creating_profile']['playtime_slots']
        
        if query.data == "back":
            # Enhanced back button logging with step validation
            self._log_back_navigation(
                user_id=update.effective_user.id,
                current_state="SELECTING_PLAYTIME",
                target_state="SELECTING_MAPS",
                user_data_context=context.user_data,
                additional_info="Step 6 (SELECTING_PLAYTIME) → Step 5 (SELECTING_MAPS): Correct navigation flow",
                navigation_validation="EXPECTED - Playtime selection goes back to maps selection",
                conversation_state="PROFILE_CREATION",
                step_number=6
            )
            # Navigate back to maps selection
            current_maps = context.user_data['creating_profile']['maps']
            text = (
                f"✅ Время игры будет выбрано позже.\n\n"
                "<b>Шаг 5/7:</b> Выберите ваши любимые карты (можно выбрать несколько):"
            )
            await query.edit_message_text(text, reply_markup=Keyboards.maps_selection(current_maps), parse_mode='HTML')
            return SELECTING_MAPS
        elif query.data == "time_done":
            if len(current_slots) == 0:
                await query.answer("❌ Выберите хотя бы один временной промежуток!", show_alert=True)
                return SELECTING_PLAYTIME
                
            # Форматируем выбранные времена
            selected_names = []
            for slot_id in current_slots:
                time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
                if time_option:
                    selected_names.append(time_option['name'])
            
            await query.edit_message_text(
                f"✅ Время игры: {', '.join(selected_names)}\n\n"
                "<b>Шаг 7/9:</b> Выберите категории, которые вас интересуют.\n"
                "Можно выбрать несколько категорий:",
                reply_markup=Keyboards.categories_selection([]),
                parse_mode='HTML'
            )
            return SELECTING_CATEGORIES
        elif query.data.startswith("time_"):
            slot_id = query.data.replace("time_", "")
            
            # Переключаем выбор времени
            if slot_id in current_slots:
                current_slots.remove(slot_id)
            else:
                current_slots.append(slot_id)
            
            context.user_data['creating_profile']['playtime_slots'] = current_slots
            
            # Обновляем клавиатуру
            await query.edit_message_reply_markup(
                reply_markup=Keyboards.playtime_selection(current_slots)
            )
            
        return SELECTING_PLAYTIME

    async def handle_categories_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор категорий"""
        query = update.callback_query
        await query.answer()
        
        # Логирование для отладки ConversationHandler
        logger.info(f"ConversationHandler: handle_categories_selection получил callback: {query.data}")
        logger.warning(f"🚨 ВНИМАНИЕ: ConversationHandler перехватил callback: {query.data}")
        
        current_categories = context.user_data['creating_profile']['categories']
        
        if query.data == "back":
            # Enhanced back button logging with step validation
            self._log_back_navigation(
                user_id=update.effective_user.id,
                current_state="SELECTING_CATEGORIES",
                target_state="SELECTING_PLAYTIME",
                user_data_context=context.user_data,
                additional_info="Step 7 (SELECTING_CATEGORIES) → Step 6 (SELECTING_PLAYTIME): Correct navigation flow",
                navigation_validation="EXPECTED - Categories selection goes back to playtime selection",
                conversation_state="PROFILE_CREATION",
                step_number=7
            )
            # Navigate back to playtime selection
            current_slots = context.user_data['creating_profile']['playtime_slots']
            # Format selected times for display
            selected_names = []
            for slot_id in current_slots:
                time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
                if time_option:
                    selected_names.append(time_option['name'])
            time_display = ', '.join(selected_names) if selected_names else "Пока не выбрано"
            text = (
                f"✅ Категории будут выбраны позже.\n\n"
                "<b>Шаг 6/7:</b> Выберите удобное время игры (можно выбрать несколько):"
            )
            await query.edit_message_text(text, reply_markup=Keyboards.playtime_selection(current_slots), parse_mode='HTML')
            return SELECTING_PLAYTIME
        elif query.data == "categories_done":
            if len(current_categories) == 0:
                await query.answer("❌ Выберите хотя бы одну категорию!", show_alert=True)
                return SELECTING_CATEGORIES
                
            # Форматируем выбранные категории для отображения
            from bot.utils.cs2_data import format_categories_display
            categories_text = format_categories_display(current_categories)
            
            await query.edit_message_text(
                f"✅ Категории: {categories_text}\n\n"
                "<b>Шаг 8/9:</b> Напишите немного о себе (стиль игры, цели, характер).\n"
                "Или нажмите 'Пропустить', чтобы добавить описание позже:",
                reply_markup=Keyboards.skip_description(),
                parse_mode='HTML'
            )
            return ENTERING_DESCRIPTION
        elif query.data.startswith("category_"):
            category_id = query.data.replace("category_", "")
            
            # Переключаем выбор категории
            if category_id in current_categories:
                current_categories.remove(category_id)
            else:
                current_categories.append(category_id)
            
            context.user_data['creating_profile']['categories'] = current_categories
            
            # Обновляем клавиатуру
            await query.edit_message_reply_markup(
                reply_markup=Keyboards.categories_selection(current_categories)
            )
            
        return SELECTING_CATEGORIES

    async def handle_description_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод описания"""
        if update.callback_query:
            # Пропуск описания
            query = update.callback_query
            await query.answer()
            
            if query.data == "skip_description":
                context.user_data['creating_profile']['description'] = None
                return await self.start_media_selection(update, context)
            elif query.data == "back":
                # Enhanced back button logging - NAVIGATION BUG FIXED!
                self._log_back_navigation(
                    user_id=update.effective_user.id,
                    current_state="ENTERING_DESCRIPTION",
                    target_state="SELECTING_CATEGORIES",
                    user_data_context=context.user_data,
                    additional_info="Correct navigation: Step 8 (ENTERING_DESCRIPTION) → Step 7 (SELECTING_CATEGORIES)",
                    navigation_validation="CORRECTED - Previously went to SELECTING_MAPS incorrectly",
                    step_number=8
                )
                # Return to categories selection instead of maps selection
                current_categories = context.user_data['creating_profile']['categories']
                from bot.utils.cs2_data import format_categories_display
                categories_text = format_categories_display(current_categories) if current_categories else "Пока не выбраны"
                text = (
                    f"✅ Категории: {categories_text}\n\n"
                    "<b>Шаг 7/9:</b> Выберите категории, которые вас интересуют.\n"
                    "Можно выбрать несколько категорий:"
                )
                await query.edit_message_text(text, reply_markup=Keyboards.categories_selection(current_categories), parse_mode='HTML')
                return SELECTING_CATEGORIES
        
        elif update.message:
            # Получен текст описания
            description = update.message.text.strip()
            
            if len(description) > 500:
                await update.message.reply_text(
                    "❌ Описание слишком длинное! Максимум 500 символов.\n"
                    f"Ваше описание: {len(description)} символов.\n\n"
                    "Попробуйте сократить:"
                )
                return ENTERING_DESCRIPTION
            
            context.user_data['creating_profile']['description'] = description
            return await self.start_media_selection(update, context)
        
        return ENTERING_DESCRIPTION

    async def start_media_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает выбор медиа для профиля"""
        text = (
            "📷 <b>Шаг 9/9: Добавление медиа (необязательно)</b>\n\n"
            "Вы можете прикрепить одну фотографию или видео к вашему профилю.\n"
            "Это поможет другим игрокам лучше узнать вас!\n\n"
            "💡 <b>Рекомендации:</b>\n"
            "• Фото с игровым процессом\n"
            "• Скриншот достижений\n"
            "• Видео с лучшими моментами\n\n"
            "Что вы хотите сделать?"
        )
        
        keyboard = Keyboards.media_selection()
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                text, reply_markup=keyboard, parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                text, reply_markup=keyboard, parse_mode='HTML'
            )
        
        return SELECTING_MEDIA

    async def handle_media_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор медиа"""
        user_id = update.effective_user.id
        logger.info(f"🔥 handle_media_selection START: user_id={user_id}")
        logger.info(f"🔥 update.callback_query: {update.callback_query is not None}")
        logger.info(f"🔥 update.message: {update.message is not None}")
        logger.info(f"🔥 context.user_data keys: {list(context.user_data.keys())}")
        logger.info(f"🔥 selecting_media_type: {context.user_data.get('selecting_media_type', 'НЕТ')}")
        
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            
            if query.data == "media_photo":
                await query.edit_message_text(
                    "📷 <b>Отправьте фотографию</b>\n\n"
                    "Пришлите одну фотографию, которую хотите добавить к профилю.\n"
                    "Фото должно быть подходящим для игрового сообщества.",
                    reply_markup=Keyboards.back_button("media_back"),
                    parse_mode='HTML'
                )
                context.user_data['selecting_media_type'] = 'photo'
                logger.info(f"🔥 Установлен selecting_media_type='photo' для user_id={user_id}")
                logger.info(f"🔥 context.user_data ПОСЛЕ установки: {context.user_data}")
                
                # Возвращаем правильное состояние в зависимости от режима
                if context.user_data.get('editing_media'):
                    return EDITING_MEDIA_TYPE
                else:
                    return SELECTING_MEDIA
                
            elif query.data == "media_video":
                await query.edit_message_text(
                    "🎥 <b>Отправьте видео</b>\n\n"
                    "Пришлите одно видео, которое хотите добавить к профилю.\n"
                    "Видео должно быть подходящим для игрового сообщества.",
                    reply_markup=Keyboards.back_button("media_back"),
                    parse_mode='HTML'
                )
                context.user_data['selecting_media_type'] = 'video'
                
                # Возвращаем правильное состояние в зависимости от режима
                if context.user_data.get('editing_media'):
                    return EDITING_MEDIA_TYPE
                else:
                    return SELECTING_MEDIA
                
            elif query.data == "media_skip":
                # Пропускаем медиа и сохраняем профиль
                return await self.save_profile(update, context)
                
            elif query.data == "media_back":
                # Enhanced back button logging for media selection - LOOP BUG FIXED!
                editing_mode = context.user_data.get('editing_media', False)
                target_state = "EDIT_MEDIA_MENU" if editing_mode else "ENTERING_DESCRIPTION"
                self._log_back_navigation(
                    user_id=update.effective_user.id,
                    current_state="MEDIA_TYPE_SELECTION",
                    target_state=target_state,
                    user_data_context=context.user_data,
                    additional_info=f"Media back navigation fixed: editing_mode={editing_mode}, now goes to correct previous step",
                    navigation_validation="CORRECTED - Previously created a loop back to media selection",
                    step_number=9
                )
                
                # Проверяем, редактируем ли мы медиа или создаем профиль
                if context.user_data.get('editing_media'):
                    # Возвращаемся к меню редактирования медиа
                    await self.edit_media(update, context, context.user_data.get('editing_profile'))
                else:
                    # FIXED: Возвращаемся к предыдущему шагу (описание) вместо зацикливания
                    description = context.user_data['creating_profile'].get('description')
                    if description:
                        text = (
                            f"✅ Описание добавлено!\n\n"
                            "<b>Шаг 8/9:</b> Напишите немного о себе (стиль игры, цели, характер).\n"
                            "Или нажмите 'Пропустить', чтобы добавить описание позже:"
                        )
                    else:
                        text = (
                            "<b>Шаг 8/9:</b> Напишите немного о себе (стиль игры, цели, характер).\n"
                            "Или нажмите 'Пропустить', чтобы добавить описание позже:"
                        )
                    await query.edit_message_text(text, reply_markup=Keyboards.skip_description(), parse_mode='HTML')
                    return ENTERING_DESCRIPTION
                
        elif update.message:
            # Получили медиа файл
            logger.info(f"🔥 Получили сообщение от user_id={user_id}")
            logger.info(f"🔥 update.message.photo: {update.message.photo is not None}")
            logger.info(f"🔥 context.user_data.get('selecting_media_type'): {context.user_data.get('selecting_media_type')}")
            logger.info(f"🔥 creating_profile в context: {'creating_profile' in context.user_data}")
            
            if update.message.photo and context.user_data.get('selecting_media_type') == 'photo':
                # Получили фото
                logger.info(f"🔥 УСЛОВИЕ ВЫПОЛНЕНО: фото + selecting_media_type=photo для user_id={user_id}")
                photo = update.message.photo[-1]  # Берем самое большое разрешение
                logger.info(f"🔥 photo.file_id: {photo.file_id}")
                
                # Проверяем, редактируем ли мы профиль
                if context.user_data.get('editing_media'):
                    logger.info(f"🔥 РЕДАКТИРОВАНИЕ МЕДИА для user_id={user_id}")
                    return await self.save_media_edit(update, context, 'photo', photo.file_id)
                else:
                    # Создание нового профиля
                    logger.info(f"🔥 СОЗДАНИЕ НОВОГО ПРОФИЛЯ для user_id={user_id}")
                    logger.info(f"🔥 creating_profile ДО: {context.user_data.get('creating_profile', {})}")
                    
                    context.user_data['creating_profile']['media_type'] = 'photo'
                    context.user_data['creating_profile']['media_file_id'] = photo.file_id
                    
                    logger.info(f"🔥 creating_profile ПОСЛЕ: {context.user_data.get('creating_profile', {})}")
                    logger.info(f"🔥 Фото добавлено, автоматически сохраняем профиль для user_id={user_id}")
                    # Автоматически сохраняем профиль без дополнительного подтверждения
                    return await self.save_profile(update, context)
                
            elif update.message.video and context.user_data.get('selecting_media_type') == 'video':
                # Получили видео
                video = update.message.video
                
                # Проверяем, редактируем ли мы профиль
                if context.user_data.get('editing_media'):
                    return await self.save_media_edit(update, context, 'video', video.file_id)
                else:
                    # Создание нового профиля
                    context.user_data['creating_profile']['media_type'] = 'video'
                    context.user_data['creating_profile']['media_file_id'] = video.file_id
                    
                    logger.info(f"🔥 Видео добавлено, автоматически сохраняем профиль для user_id={update.effective_user.id}")
                    # Автоматически сохраняем профиль без дополнительного подтверждения
                    return await self.save_profile(update, context)
                
            else:
                # Неподходящий тип файла
                logger.info(f"🔥 НЕПОДХОДЯЩИЙ ТИП ФАЙЛА для user_id={user_id}")
                logger.info(f"🔥 update.message.photo: {update.message.photo is not None}")
                logger.info(f"🔥 update.message.video: {update.message.video is not None}")
                logger.info(f"🔥 selecting_media_type: {context.user_data.get('selecting_media_type')}")
                
                expected_type = context.user_data.get('selecting_media_type', 'медиа')
                await update.message.reply_text(
                    f"❌ Ожидается {expected_type}!\n"
                    f"Пожалуйста, отправьте {expected_type} или вернитесь назад.",
                    reply_markup=Keyboards.back_button("media_back")
                )
                return SELECTING_MEDIA
        
        logger.info(f"🔥 handle_media_selection END: возвращаем SELECTING_MEDIA для user_id={user_id}")
        return SELECTING_MEDIA

    async def save_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохраняет профиль в базу данных"""
        user_id = update.effective_user.id
        
        # ЭКСТРЕМАЛЬНОЕ ЛОГИРОВАНИЕ
        logger.info(f"🔥 SAVE_PROFILE START: user_id={user_id}")
        logger.info(f"🔥 update.callback_query: {update.callback_query is not None}")
        logger.info(f"🔥 callback_data: {update.callback_query.data if update.callback_query else 'None'}")
        logger.info(f"🔥 context.user_data keys: {list(context.user_data.keys())}")
        
        # Подтверждаем callback query если есть
        if update.callback_query:
            await update.callback_query.answer()
        
        if 'creating_profile' not in context.user_data:
            logger.error(f"🔥 КРИТИЧЕСКАЯ ОШИБКА: creating_profile НЕ НАЙДЕН в context.user_data!")
            logger.error(f"🔥 Доступные ключи: {list(context.user_data.keys())}")
            return ConversationHandler.END
        
        profile_data = context.user_data['creating_profile']
        logger.info(f"🔥 profile_data получен: {profile_data}")
        
        try:
            # DEBUG: Логируем попытку создания профиля
            logger.info(f"save_profile: Создание профиля для user_id={user_id}, nickname={profile_data['game_nickname']}")
            
            # Создаем профиль в БД
            logger.info(f"🔥 ВЫЗОВ create_profile для user_id={user_id}")
            logger.info(f"🔥 game_nickname: {profile_data.get('game_nickname', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 faceit_elo: {profile_data.get('faceit_elo', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 faceit_url: {profile_data.get('faceit_url', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 role: {profile_data.get('role', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 maps: {profile_data.get('maps', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 playtime_slots: {profile_data.get('playtime_slots', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 categories: {profile_data.get('categories', 'ОТСУТСТВУЕТ')}")
            logger.info(f"🔥 description: {profile_data.get('description', 'ОТСУТСТВУЕТ')}")
            
            success = await self.db.create_profile(
                user_id=user_id,
                game_nickname=profile_data['game_nickname'],
                faceit_elo=profile_data['faceit_elo'],
                faceit_url=profile_data['faceit_url'],
                role=profile_data['role'],
                favorite_maps=profile_data['maps'],
                playtime_slots=profile_data['playtime_slots'],
                categories=profile_data['categories'],
                description=profile_data['description'],
                media_type=profile_data.get('media_type'),
                media_file_id=profile_data.get('media_file_id')
            )
            
            logger.info(f"🔥 create_profile РЕЗУЛЬТАТ: {success}")
            
            # DEBUG: Проверяем результат сохранения
            logger.info(f"save_profile: Результат создания профиля: {success}")
            
            if not success:
                logger.error(f"save_profile: Ошибка создания профиля для пользователя {user_id}")
                error_text = (
                    "❌ <b>Ошибка создания профиля</b>\n\n"
                    "Не удалось сохранить профиль в базу данных.\n"
                    "Попробуйте еще раз или обратитесь в поддержку."
                )
                
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        error_text,
                        reply_markup=Keyboards.back_button("profile_menu"),
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        error_text,
                        reply_markup=Keyboards.back_button("profile_menu"),
                        parse_mode='HTML'
                    )
                return ConversationHandler.END
            
            # DEBUG: Профиль успешно создан
            logger.info(f"save_profile: Профиль успешно создан для user_id={user_id}")
            
            # Проверяем, что профиль действительно сохранился
            has_profile_check = await self.db.has_profile(user_id)
            logger.info(f"save_profile: Проверка has_profile после создания: {has_profile_check}")
            
            # Очищаем временные данные
            cleanup_keys = ['creating_profile', 'selecting_media_type']
            for key in cleanup_keys:
                if key in context.user_data:
                    del context.user_data[key]
            
            success_text = (
                "🎉 <b>Профиль создан успешно!</b>\n\n"
                "⏳ <b>Ваш профиль отправлен на модерацию</b>\n"
                "Модераторы проверят вашу анкету в течение 24 часов.\n"
                "После одобрения другие игроки смогут найти вас в поиске!\n\n"
                "📬 Мы уведомим вас о результате проверки."
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    success_text,
                    reply_markup=Keyboards.profile_created(),
                    parse_mode='HTML'
                )
            elif update.message:
                await update.message.reply_text(
                    success_text,
                    reply_markup=Keyboards.profile_created(),
                    parse_mode='HTML'
                )
            else:
                # Fallback для случаев когда нет ни callback_query ни message
                logger.warning(f"save_profile: Нет update.callback_query и update.message для user_id={user_id}")
                # Не отправляем сообщение, но логируем успех
                pass
            
            logger.info(f"Профиль создан для пользователя {user_id}")
            return ConversationHandler.END  # КРИТИЧЕСКИ ВАЖНО: завершаем conversation
            
        except Exception as e:
            logger.error(f"save_profile: Критическая ошибка создания профиля для {user_id}: {e}", exc_info=True)
            
            error_text = (
                "❌ <b>Ошибка при создании профиля</b>\n\n"
                "Произошла ошибка при сохранении данных.\n"
                "Попробуйте еще раз или обратитесь в поддержку."
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    error_text,
                    reply_markup=Keyboards.back_button("profile_menu"),
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    error_text,
                    reply_markup=Keyboards.back_button("profile_menu"),
                    parse_mode='HTML'
                )
        
        return ConversationHandler.END

    async def cancel_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменяет создание профиля"""
        query = update.callback_query
        await query.answer()
        
        # Очищаем временные данные
        if 'creating_profile' in context.user_data:
            del context.user_data['creating_profile']
        
        await query.edit_message_text(
            "❌ Создание профиля отменено.\n\n"
            "Вы можете вернуться к созданию профиля в любое время.",
            reply_markup=Keyboards.profile_menu(False),
        )
        
        return ConversationHandler.END

    # === ОБРАБОТКА CALLBACK'ОВ ===
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback запросы вне создания профиля"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
                # Временное логирование для отладки
        logger.info(f"Profile handler получил callback: {data} от пользователя {user_id}")
        logger.info(f"DEBUG: data.startswith('edit_category_') = {data.startswith('edit_category_')}")
        
        if data == "profile_menu":
            await self.profile_command(update, context)
        elif data == "profile_view":
            await self.view_full_profile(update, context)
        elif data == "profile_edit":
            await self.show_edit_menu(update, context)
        elif data == "profile_stats":
            await self.show_profile_stats(update, context)
        elif data.startswith("edit_category_"):
            logger.info(f"Обрабатываем edit_category_ callback: {data} для пользователя {user_id}")
            await self.handle_category_toggle(update, context)
        elif data == "edit_categories_done":
            logger.info(f"Обрабатываем edit_categories_done для пользователя {user_id}")
            await self.handle_categories_edit_done(update, context)
        elif data.startswith("map_"):
            # Обработка выбора карт при редактировании
            logger.info(f"Обрабатываем map_ callback: {data} для пользователя {user_id}")
            await self.handle_map_selection_edit(update, context)
        elif data == "maps_done":
            # Завершение выбора карт при редактировании
            logger.info(f"Обрабатываем maps_done для пользователя {user_id}")
            await self.handle_maps_edit_done(update, context)
        elif data == "back" and context.user_data.get('editing_field') == 'role':
            # Возврат из редактирования роли
            logger.info(f"Возврат из редактирования роли для пользователя {user_id}")
            await self.handle_role_selection_edit(update, context)
        elif data == "back" and context.user_data.get('editing_field') == 'favorite_maps':
            # Возврат из редактирования карт
            logger.info(f"Возврат из редактирования карт для пользователя {user_id}")
            await self.cancel_maps_edit(update, context)
        elif data.startswith("role_"):
            # Обработка выбора роли при редактировании
            logger.info(f"Обрабатываем role_ callback: {data} для пользователя {user_id}")
            await self.handle_role_selection_edit(update, context)
        elif data == "elo_custom":
            # Обработка выбора ELO при редактировании
            logger.info(f"Обрабатываем elo_custom callback для пользователя {user_id}")
            await self.handle_elo_selection_edit(update, context)
        elif data.startswith("time_"):
            # Обработка выбора времени при редактировании
            logger.info(f"Обрабатываем time_ callback: {data} для пользователя {user_id}")
            await self.handle_time_selection_edit(update, context)
        elif data == "time_done":
            # Завершение выбора времени при редактировании
            logger.info(f"Обрабатываем time_done для пользователя {user_id}")
            await self.handle_time_edit_done(update, context)
        elif data == "back" and context.user_data.get('editing_field') == 'playtime_slots':
            # Возврат из редактирования времени
            logger.info(f"Возврат из редактирования времени для пользователя {user_id}")
            await self.cancel_time_edit(update, context)
        elif data == "back" and context.user_data.get('editing_field'):
            # Общий возврат из редактирования
            logger.info(f"Общий возврат из редактирования для пользователя {user_id}")
            await self.cancel_edit(update, context)
        elif data == "edit_media_add" or data == "edit_media_replace":
            await self.start_media_edit(update, context)
        elif data == "edit_media_remove":
            await self.remove_media(update, context)
        elif data.startswith("edit_"):
            await self.handle_edit_request(update, context)
        elif data.startswith("confirm_edit_"):
            await self.confirm_edit(update, context)
        elif data.startswith("cancel_edit_"):
            await self.cancel_edit(update, context)
        elif data == "back_to_main":
            from bot.handlers.start import StartHandler
            start_handler = StartHandler(self.db)
            await start_handler.show_main_menu(query)

    async def view_full_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает полный профиль пользователя с медиа"""
        # Handle both callback_query and message contexts
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            is_callback = True
        elif update.message:
            user_id = update.message.from_user.id
            is_callback = False
        else:
            logger.error("view_full_profile: No callback_query or message found in update")
            return
        
        # 🔥 ОТЛАДКА: Проверяем существование профиля ДО get_profile
        has_profile_before = await self.db.has_profile(user_id)
        logger.info(f"🔥 view_full_profile START: user_id={user_id}, has_profile_before={has_profile_before}")
        
        profile = await self.db.get_profile(user_id)
        logger.info(f"🔥 view_full_profile: get_profile result={profile is not None}")
        
        # 🔥 ОТЛАДКА: Проверяем существование профиля ПОСЛЕ get_profile
        has_profile_after = await self.db.has_profile(user_id)
        logger.info(f"🔥 view_full_profile: has_profile_after={has_profile_after}")
        
        if not profile:
            logger.error(f"🔥 view_full_profile: Профиль НЕ НАЙДЕН для user_id={user_id}, has_before={has_profile_before}, has_after={has_profile_after}")
            if is_callback:
                await query.edit_message_text(
                    "❌ Профиль не найден",
                    reply_markup=Keyboards.back_button("profile_menu")
                )
            else:
                await update.message.reply_text(
                    "❌ Профиль не найден",
                    reply_markup=Keyboards.back_button("profile_menu")
                )
            return
        
        # Форматируем полный профиль
        text = "👤 <b>Ваш полный профиль:</b>\n\n"
        text += await self._format_full_profile_text(profile)
        
        # Отправляем профиль с медиа
        chat_id = query.message.chat.id if is_callback else update.message.chat.id
        await self.send_profile_with_media(
            chat_id=chat_id,
            profile=profile,
            text=text,
            reply_markup=Keyboards.profile_view_menu(),
            context=context
        )

    async def _format_full_profile_text(self, profile) -> str:
        """Форматирует полный текст профиля"""
        from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname, PLAYTIME_OPTIONS, CS2_MAPS, format_faceit_elo_display
        from bot.utils.faceit_analyzer import faceit_analyzer
        
        # Получаем ELO статистику через Faceit API
        elo_stats = None
        try:
            if profile.game_nickname and profile.game_nickname.strip():
                elo_stats = await faceit_analyzer.get_elo_stats_by_nickname(profile.game_nickname)
        except Exception as e:
            logger.warning(f"Не удалось получить ELO статистику для {profile.game_nickname}: {e}")
        
        # Отображаем ELO с мин/макс значениями если есть данные (ИСПРАВЛЕННАЯ ЛОГИКА В _format_full_profile_text)
        if elo_stats:
            # Проверяем корректность значений перед передачей в format_faceit_elo_display()
            lowest_elo = elo_stats.get('lowest_elo', 0)
            highest_elo = elo_stats.get('highest_elo', 0)
            
            # Дополнительная валидация ELO значений в полном профиле
            try:
                if isinstance(lowest_elo, (int, float)) and isinstance(highest_elo, (int, float)):
                    lowest_elo = int(lowest_elo) if lowest_elo >= 0 else 0
                    highest_elo = int(highest_elo) if highest_elo >= 0 else 0
                    
                    # Показываем мин/макс даже если API вернул ошибку, но есть валидные данные
                    if lowest_elo > 0 or highest_elo > 0:
                        logger.info(f"🔥 FULL PROFILE: Показываем ELO с мин/макс для {profile.game_nickname}: мин={lowest_elo} макс={highest_elo}")
                        text = f"🎯 <b>ELO Faceit:</b> {format_faceit_elo_display(profile.faceit_elo, lowest_elo, highest_elo, profile.game_nickname)}\n"
                    else:
                        # Если мин/макс равны 0, показываем только текущий ELO
                        text = f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
                else:
                    logger.warning(f"⚠️ FULL PROFILE: ELO значения некорректного типа для {profile.game_nickname}: lowest={type(lowest_elo)}, highest={type(highest_elo)}")
                    # Fallback на базовое отображение при некорректных данных
                    text = f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
            except Exception as elo_validation_error:
                logger.error(f"Ошибка валидации ELO в полном профиле для {profile.game_nickname}: {elo_validation_error}")
                # Fallback на базовое отображение при ошибке валидации
                text = f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
        else:
            # Fallback на базовое отображение ELO
            text = f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile.faceit_elo)}\n"
        
        text += f"👤 <b>Роль:</b> {format_role_display(profile.role)}\n\n"
        
        # Добавляем данные Faceit Analyser для полного профиля
        try:
            faceit_url = getattr(profile, 'faceit_url', '')
            if faceit_url:
                logger.debug(f"Получение Faceit Analyser данных для полного профиля {profile.user_id}")
                faceit_data = await faceit_analyzer.get_enhanced_profile_info(faceit_url)
                
                # Диаграммы отключены
                    
        except Exception as faceit_error:
            logger.warning(f"Ошибка получения данных Faceit Analyser для полного профиля {profile.user_id}: {faceit_error}")
            # Не критично, продолжаем без данных от API
        
        text += f"🗺️ <b>Любимые карты:</b>\n"
        for map_name in profile.favorite_maps:
            map_data = next((m for m in CS2_MAPS if m['name'] == map_name), None)
            emoji = map_data['emoji'] if map_data else '📍'
            text += f"   {emoji} {map_name}\n"
        
        # Форматируем время игры из слотов
        if profile.playtime_slots:
            playtime_names = []
            for slot_id in profile.playtime_slots:
                slot_data = next((slot for slot in PLAYTIME_OPTIONS if slot['id'] == slot_id), None)
                if slot_data:
                    playtime_names.append(f"{slot_data['emoji']} {slot_data['name']}")
            playtime_text = ", ".join(playtime_names) if playtime_names else "Не указано"
            text += f"\n⏰ <b>Время игры:</b> {playtime_text}\n"
        else:
            text += f"\n⏰ <b>Время игры:</b> Не указано\n"
        
        # Категории
        if hasattr(profile, 'categories') and profile.categories:
            from bot.utils.cs2_data import format_categories_display
            categories_text = format_categories_display(profile.categories)
            text += f"\n🎮 <b>Категории:</b> {categories_text}\n"
        else:
            text += f"\n🎮 <b>Категории:</b> Не указаны\n"
        
        if profile.description:
            text += f"\n💬 <b>О себе:</b>\n{profile.description}\n"
        
        # Дата создания
        created = profile.created_at.strftime("%d.%m.%Y")
        text += f"\n📅 <b>Профиль создан:</b> {created}"
        
        return text

    # === РЕДАКТИРОВАНИЕ ПРОФИЛЯ ===
    
    async def show_edit_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню редактирования профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        profile = await self.db.get_profile(user_id)
        
        if not profile:
            await self.safe_edit_or_send_message(
                query,
                "❌ Профиль не найден. Создайте профиль сначала.",
                reply_markup=Keyboards.back_button("profile_menu")
            )
            return
        
        text = (
            "✏️ <b>Редактирование профиля</b>\n\n"
            "Выберите, что хотите изменить:"
        )
        
        await self.safe_edit_or_send_message(
            query,
            text,
            reply_markup=Keyboards.profile_edit_menu(),
            parse_mode='HTML'
        )

    async def handle_edit_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает запросы на редактирование полей"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # Получаем текущий профиль
        profile = await self.db.get_profile(user_id)
        if not profile:
            await query.answer("❌ Профиль не найден!", show_alert=True)
            return
        
        # Определяем тип редактирования
        if data == "edit_elo":
            await self.edit_elo(update, context, profile)
        elif data == "edit_nickname":
            await self.edit_nickname(update, context, profile)
        elif data == "edit_faceit_url":
            await self.edit_faceit_url(update, context, profile)
        elif data == "edit_role":
            await self.edit_role(update, context, profile)
        elif data == "edit_maps":
            await self.edit_maps(update, context, profile)
        elif data == "edit_time":
            await self.edit_time(update, context, profile)
        elif data == "edit_description":
            await self.edit_description(update, context, profile)
        elif data == "edit_categories":
            await self.edit_categories(update, context, profile)
        elif data == "edit_media":
            await self.edit_media(update, context, profile)

    async def edit_elo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование ELO Faceit"""
        query = update.callback_query
        await query.answer()
        
        from bot.utils.cs2_data import format_elo_display
        current_elo_display = format_elo_display(profile.faceit_elo)
        
        text = (
            f"🎯 <b>Изменение ELO Faceit</b>\n\n"
            f"<b>Текущий ELO:</b> {current_elo_display}\n\n"
            "Введите новое точное ELO:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.elo_input_menu(),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования
        context.user_data['editing_field'] = 'faceit_elo'
        context.user_data['editing_profile'] = profile

    async def edit_nickname(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование игрового ника"""
        query = update.callback_query
        await query.answer()
        
        text = (
            f"🎮 <b>Изменение игрового ника</b>\n\n"
            f"<b>Текущий ник:</b> {profile.game_nickname}\n\n"
            "Введите новый игровой ник:\n"
            "• От 2 до 32 символов\n"
            "• Буквы, цифры, дефисы, подчеркивания\n\n"
            "📊 <b>Важно:</b> Ник используется для получения ELO статистики с Faceit.\n"
            "После изменения ника обновится отображение мин/макс ELO значений."
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="profile_edit")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст для ожидания текста
        context.user_data['editing_field'] = 'game_nickname'
        context.user_data['editing_profile'] = profile
        context.user_data['awaiting_nickname'] = True

    async def edit_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование роли"""
        query = update.callback_query
        await query.answer()
        
        from bot.utils.cs2_data import format_role_display
        current_role_display = format_role_display(profile.role)
        
        text = (
            f"👤 <b>Изменение роли</b>\n\n"
            f"<b>Текущая роль:</b> {current_role_display}\n\n"
            "Выберите новую роль:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.role_selection(),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования  
        context.user_data['editing_field'] = 'role'
        context.user_data['editing_profile'] = profile

    async def edit_maps(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование карт"""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        current_maps = ", ".join(profile.favorite_maps[:3])
        if len(profile.favorite_maps) > 3:
            current_maps += "..."
        
        text = (
            f"🗺️ <b>Изменение любимых карт</b>\n\n"
            f"<b>Текущие карты:</b> {current_maps}\n\n"
            "Выберите новые карты (от 1 до 5):"
        )
        
        logger.info(f"Начинаем редактирование карт для пользователя {user_id}, текущие карты: {profile.favorite_maps}")
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.maps_selection(profile.favorite_maps),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования
        context.user_data['editing_field'] = 'favorite_maps'
        context.user_data['editing_profile'] = profile
        context.user_data['selected_maps'] = profile.favorite_maps.copy()
        
        logger.info(f"Установили editing_field='favorite_maps' для пользователя {user_id}")
        logger.info(f"Инициализировали selected_maps: {context.user_data['selected_maps']}")

    async def edit_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование времени игры"""
        query = update.callback_query
        await query.answer()
        
        from bot.utils.cs2_data import PLAYTIME_OPTIONS
        current_times = []
        for slot_id in profile.playtime_slots:
            slot_data = next((slot for slot in PLAYTIME_OPTIONS if slot['id'] == slot_id), None)
            if slot_data:
                current_times.append(f"{slot_data['emoji']} {slot_data['name']}")
        
        current_time_display = ", ".join(current_times) if current_times else "Не указано"
        
        text = (
            f"⏰ <b>Изменение времени игры</b>\n\n"
            f"<b>Текущее время:</b> {current_time_display}\n\n"
            "Выберите новое время игры:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.playtime_selection(profile.playtime_slots),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования
        context.user_data['editing_field'] = 'playtime_slots'
        context.user_data['editing_profile'] = profile
        context.user_data['selected_playtime_slots'] = profile.playtime_slots.copy()

    async def edit_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование категорий"""
        query = update.callback_query
        await query.answer()
        
        from bot.utils.cs2_data import format_categories_display
        current_categories_display = format_categories_display(profile.categories)
        
        text = (
            f"🎮 <b>Изменение категорий</b>\n\n"
            f"<b>Текущие категории:</b> {current_categories_display}\n\n"
            "Выберите новые категории (можно выбрать несколько):"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.categories_selection(profile.categories, edit_mode=True),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования
        context.user_data['editing_field'] = 'categories'
        context.user_data['editing_profile'] = profile
        context.user_data['selected_categories'] = profile.categories.copy()

    async def handle_categories_edit_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает завершение редактирования категорий"""
        query = update.callback_query
        user_id = query.from_user.id
        
        selected_categories = context.user_data.get('selected_categories', [])
        
        if len(selected_categories) == 0:
            await query.answer("❌ Выберите хотя бы одну категорию!", show_alert=True)
            return
        
        try:
            # Обновляем профиль в БД
            success = await self.db.update_profile(user_id, categories=selected_categories)
            
            if success:
                await query.answer("✅ Категории обновлены!", show_alert=True)
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                
                # Возвращаемся к просмотру профиля
                await self.view_full_profile(update, context)
            else:
                await query.answer("❌ Ошибка при сохранении", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка при сохранении категорий: {e}")
            await query.answer("❌ Произошла ошибка", show_alert=True)

    async def handle_category_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает переключение категории при редактировании"""
        query = update.callback_query
        await query.answer()
        
        logger.info(f"handle_category_toggle: получен callback {query.data}")
        
        category_id = query.data.replace("edit_category_", "")
        selected_categories = context.user_data.get('selected_categories', [])
        
        logger.info(f"handle_category_toggle: category_id={category_id}, selected_categories={selected_categories}")
        
        # Переключаем выбор категории
        if category_id in selected_categories:
            selected_categories.remove(category_id)
        else:
            selected_categories.append(category_id)
        
        context.user_data['selected_categories'] = selected_categories
        
        # Обновляем клавиатуру с режимом редактирования
        await query.edit_message_reply_markup(
            reply_markup=Keyboards.categories_selection(selected_categories, edit_mode=True)
        )

    async def edit_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование описания"""
        query = update.callback_query
        await query.answer()
        
        current_desc = profile.description or "Не указано"
        
        text = (
            f"💬 <b>Изменение описания</b>\n\n"
            f"<b>Текущее описание:</b>\n{current_desc}\n\n"
            "Напишите новое описание профиля (до 500 символов) или нажмите кнопку ниже:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Удалить описание", callback_data="confirm_edit_description_empty")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile_edit")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст для ожидания текста
        context.user_data['editing_field'] = 'description'
        context.user_data['editing_profile'] = profile
        context.user_data['awaiting_description'] = True

    async def edit_faceit_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование Faceit URL"""
        query = update.callback_query
        await query.answer()
        
        from bot.utils.cs2_data import extract_faceit_nickname
        current_nickname = extract_faceit_nickname(profile.faceit_url)
        
        text = (
            f"🔗 <b>Изменение ссылки Faceit</b>\n\n"
            f"<b>Текущая ссылка:</b> <a href='{profile.faceit_url}'>{current_nickname}</a>\n\n"
            "Отправьте новую ссылку на ваш Faceit профиль:\n"
            "Пример: https://www.faceit.com/ru/players/nickname"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="profile_edit")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст для ожидания URL
        context.user_data['editing_field'] = 'faceit_url'
        context.user_data['editing_profile'] = profile
        context.user_data['awaiting_faceit_url'] = True

    async def edit_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE, profile):
        """Редактирование медиа"""
        query = update.callback_query
        await query.answer()
        
        current_media = "нет" if not profile.has_media() else f"прикреплено ({profile.media_type})"
        
        text = (
            f"📷 <b>Изменение медиа</b>\n\n"
            f"<b>Текущее медиа:</b> {current_media}\n\n"
            "Выберите действие:"
        )
        
        await self.safe_edit_or_send_message(
            query,
            text,
            reply_markup=Keyboards.media_edit_menu(profile.has_media()),
            parse_mode='HTML'
        )
        
        # Сохраняем контекст редактирования
        context.user_data['editing_field'] = 'media'
        context.user_data['editing_profile'] = profile

    async def start_media_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает редактирование медиа"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "📷 <b>Добавление/замена медиа</b>\n\n"
            "Выберите тип медиа для добавления:"
        )
        
        await self.safe_edit_or_send_message(
            query,
            text,
            reply_markup=Keyboards.media_selection(),
            parse_mode='HTML'
        )
        
        # Устанавливаем флаг редактирования медиа
        context.user_data['editing_media'] = True
        
        # Возвращаем состояние редактирования медиа
        return EDITING_MEDIA_TYPE

    async def remove_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет медиа из профиля"""
        query = update.callback_query
        user_id = query.from_user.id
        
        try:
            # Обновляем профиль, удаляя медиа
            success = await self.db.update_profile(
                user_id, 
                media_type=None, 
                media_file_id=None
            )
            
            if success:
                await query.answer("✅ Медиа удалено!", show_alert=True)
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                
                # Возвращаемся к просмотру профиля
                await self.view_full_profile(update, context)
            else:
                await query.answer("❌ Ошибка при удалении", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка при удалении медиа: {e}")
            await query.answer("❌ Произошла ошибка", show_alert=True)

    async def handle_media_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает медиа при редактировании профиля"""
        if update.message:
            # Получили медиа файл
            if update.message.photo and context.user_data.get('selecting_media_type') == 'photo':
                # Получили фото
                photo = update.message.photo[-1]  # Берем самое большое разрешение
                return await self.save_media_edit(update, context, 'photo', photo.file_id)
                
            elif update.message.video and context.user_data.get('selecting_media_type') == 'video':
                # Получили видео
                video = update.message.video
                return await self.save_media_edit(update, context, 'video', video.file_id)
                
            else:
                # Неподходящий тип файла
                expected_type = context.user_data.get('selecting_media_type', 'медиа')
                await update.message.reply_text(
                    f"❌ Ожидается {expected_type}!\n"
                    f"Пожалуйста, отправьте {expected_type} или вернитесь назад.",
                    reply_markup=Keyboards.back_button("media_back")
                )
                return EDITING_MEDIA_TYPE
        
        return EDITING_MEDIA_TYPE
    
    async def handle_orphan_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """FALLBACK: Обрабатывает медиа файлы вне ConversationHandler"""
        user_id = update.effective_user.id
        logger.info(f"🔥🔥🔥 ORPHAN MEDIA HANDLER ВЫЗВАН для user_id={user_id}")
        logger.info(f"🔥 update.message.photo: {update.message.photo is not None}")
        logger.info(f"🔥 update.message.video: {update.message.video is not None}")
        logger.info(f"🔥 context.user_data: {context.user_data}")
        
        # Проверяем, есть ли creating_profile в процессе
        if 'creating_profile' in context.user_data:
            logger.info(f"🔥 НАЙДЕН creating_profile! Пытаемся сохранить профиль для user_id={user_id}")
            
            # Добавляем медиа к профилю
            if update.message.photo:
                photo = update.message.photo[-1]
                context.user_data['creating_profile']['media_type'] = 'photo'
                context.user_data['creating_profile']['media_file_id'] = photo.file_id
                logger.info(f"🔥 ORPHAN: Фото добавлено, сохраняем профиль для user_id={user_id}")
            elif update.message.video:
                video = update.message.video
                context.user_data['creating_profile']['media_type'] = 'video'
                context.user_data['creating_profile']['media_file_id'] = video.file_id
                logger.info(f"🔥 ORPHAN: Видео добавлено, сохраняем профиль для user_id={user_id}")
            
            # Пытаемся сохранить профиль
            try:
                result = await self.save_profile(update, context)
                logger.info(f"🔥 ORPHAN: Результат save_profile: {result}")
                return result
            except Exception as e:
                logger.error(f"🔥 ORPHAN: Ошибка save_profile: {e}")
                await update.message.reply_text(
                    "❌ Произошла ошибка при сохранении профиля.\n"
                    "Попробуйте еще раз или обратитесь в поддержку."
                )
        else:
            logger.info(f"🔥 ORPHAN: creating_profile НЕ НАЙДЕН для user_id={user_id}")
            await update.message.reply_text(
                "🤔 Неожиданное медиа сообщение.\n"
                "Если вы создаете профиль, попробуйте начать заново командой /profile"
            )

    async def save_media_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str, file_id: str):
        """Сохраняет изменения медиа при редактировании профиля"""
        user_id = update.effective_user.id
        
        try:
            # Обновляем профиль с новым медиа
            success = await self.db.update_profile(
                user_id,
                media_type=media_type,
                media_file_id=file_id
            )
            
            if success:
                media_name = "фотография" if media_type == 'photo' else "видео"
                await update.message.reply_text(
                    f"✅ <b>{media_name.capitalize()} обновлена!</b>",
                    parse_mode='HTML'
                )
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                if 'editing_media' in context.user_data:
                    del context.user_data['editing_media']
                
                # Показываем обновленный профиль
                profile = await self.db.get_profile(user_id)
                if profile:
                    text = "👤 <b>Ваш обновленный профиль:</b>\n\n"
                    text += await self._format_full_profile_text(profile)
                    
                    await self.send_profile_with_media(
                        chat_id=update.effective_chat.id,
                        profile=profile,
                        text=text,
                        reply_markup=Keyboards.profile_view_menu(),
                        context=context
                    )
            else:
                await update.message.reply_text(
                    "❌ Ошибка при сохранении медиа"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при сохранении медиа: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении"
            )
        
        # Завершаем conversation при редактировании медиа
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    async def confirm_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение изменений"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # Парсим данные подтверждения
        parts = data.split('_', 3)  # confirm_edit_field_value
        if len(parts) < 3:
            await query.answer("❌ Ошибка данных", show_alert=True)
            return
            
        field = parts[2]
        value = parts[3] if len(parts) > 3 else ""
        
        try:
            # Формируем данные для обновления
            update_data = {}
            
            if field == 'description':
                if value == 'empty':
                    update_data['description'] = None
                else:
                    update_data['description'] = context.user_data.get('new_description', '')
            elif field == 'faceit_url':
                update_data['faceit_url'] = context.user_data.get('new_faceit_url', '')
            elif field == 'faceit_elo':
                # Парсим ELO из callback_data
                update_data['faceit_elo'] = int(value)
            elif field == 'role':
                update_data['role'] = value
            elif field == 'favorite_maps':
                update_data['favorite_maps'] = context.user_data.get('selected_maps', [])
            elif field == 'playtime_slots':
                update_data['playtime_slots'] = context.user_data.get('selected_playtime_slots', [])
            elif field == 'categories':
                update_data['categories'] = context.user_data.get('selected_categories', [])
            
            # Обновляем профиль в БД
            success = await self.db.update_profile(user_id, **update_data)
            
            if success:
                await query.answer("✅ Профиль обновлен!", show_alert=True)
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                
                # Возвращаемся к просмотру профиля
                await self.view_full_profile(update, context)
            else:
                await query.answer("❌ Ошибка при сохранении", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка при подтверждении изменений: {e}")
            await query.answer("❌ Произошла ошибка", show_alert=True)

    async def cancel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена редактирования"""
        query = update.callback_query
        await query.answer("Изменения отменены")
        
        # Очищаем временные данные
        self.clear_editing_context(context)
        
        # Возвращаемся к меню редактирования
        await self.show_edit_menu(update, context)

    async def safe_edit_or_send_message(self, query, text: str, reply_markup=None, parse_mode='HTML'):
        """Безопасно редактирует сообщение или отправляет новое, если редактирование невозможно"""
        try:
            message = query.message
            if message and (message.photo or message.video):
                # Если сообщение содержит медиа, отправляем новое сообщение
                await query.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                # Если обычное текстовое сообщение, редактируем его
                await query.edit_message_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Фоллбэк - отправляем новое сообщение
            await query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

    def clear_editing_context(self, context: ContextTypes.DEFAULT_TYPE):
        """Очищает временные данные редактирования"""
        keys_to_remove = [
            'editing_field', 'editing_profile', 'selected_maps', 
            'selected_playtime_slots', 'selected_categories', 'awaiting_description', 
            'awaiting_faceit_url', 'new_description', 'new_faceit_url',
            'editing_media', 'selecting_media_type'
        ]
        
        for key in keys_to_remove:
            if key in context.user_data:
                del context.user_data[key]

    async def show_profile_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает статистику профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Получаем статистику
        stats = await self.db.get_user_stats(user_id)
        
        text = "📊 <b>Статистика профиля:</b>\n\n"
        text += f"👁️ <b>Просмотры вашего профиля:</b> {stats.get('profile_views', 0)}\n"
        text += f"❤️ <b>Полученные лайки:</b> {stats.get('received_likes', 0)}\n"
        text += f"💌 <b>Отправленные лайки:</b> {stats.get('sent_likes', 0)}\n"
        text += f"🤝 <b>Тиммейты:</b> {stats.get('matches', 0)}\n"
        text += f"⭐ <b>Рейтинг профиля:</b> {stats.get('rating', 0)}/10\n"
        
        # Используем безопасный метод для обработки медиа-сообщений
        await self.safe_edit_or_send_message(
            query,
            text,
            reply_markup=Keyboards.back_button("profile_menu"),
            parse_mode='HTML'
        )

    async def handle_map_selection_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор карт при редактировании профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Получаем текущий профиль
        profile = await self.db.get_profile(user_id)
        if not profile:
            await query.answer("❌ Профиль не найден!", show_alert=True)
            return
        
        # Инициализируем selected_maps если его нет
        if 'selected_maps' not in context.user_data:
            context.user_data['selected_maps'] = profile.favorite_maps.copy()
            logger.info(f"Инициализировали selected_maps: {context.user_data['selected_maps']}")
        
        selected_maps = context.user_data['selected_maps']
        logger.info(f"Текущие selected_maps: {selected_maps}")
        
        if data.startswith("map_"):
            map_name = data.replace("map_", "")
            logger.info(f"Обрабатываем карту: {map_name}")
            
            # Переключаем выбор карты
            if map_name in selected_maps:
                selected_maps.remove(map_name)
                logger.info(f"Убрали карту {map_name}, осталось: {selected_maps}")
            else:
                # Проверяем лимит (максимум 5 карт)
                if len(selected_maps) >= 5:
                    await query.answer("❌ Максимум 5 карт!", show_alert=True)
                    return
                selected_maps.append(map_name)
                logger.info(f"Добавили карту {map_name}, всего: {selected_maps}")
            
            context.user_data['selected_maps'] = selected_maps
            
            # Обновляем клавиатуру
            await query.edit_message_reply_markup(
                reply_markup=Keyboards.maps_selection(selected_maps)
            )
            
            # Показываем количество выбранных карт
            count_text = f"Выбрано карт: {len(selected_maps)}/5"
            await query.answer(count_text, show_alert=False)

    async def handle_maps_edit_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершает выбор карт при редактировании"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        selected_maps = context.user_data.get('selected_maps', [])
        logger.info(f"Завершаем выбор карт для пользователя {user_id}, выбранные карты: {selected_maps}")
        
        if len(selected_maps) == 0:
            await query.answer("❌ Выберите хотя бы одну карту!", show_alert=True)
            return
        
        try:
            # Обновляем профиль в БД
            logger.info(f"Обновляем профиль пользователя {user_id} с картами: {selected_maps}")
            success = await self.db.update_profile(user_id, favorite_maps=selected_maps)
            
            if success:
                logger.info(f"Профиль пользователя {user_id} успешно обновлен")
                await query.answer("✅ Карты обновлены!", show_alert=True)
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                
                # Возвращаемся к просмотру профиля
                await self.view_full_profile(update, context)
            else:
                logger.error(f"Не удалось обновить профиль пользователя {user_id}")
                await query.answer("❌ Ошибка при сохранении", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении карт: {e}")
            await query.answer("❌ Произошла ошибка", show_alert=True)

    async def cancel_maps_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена редактирования карт"""
        query = update.callback_query
        user_id = query.from_user.id
        logger.info(f"Отменяем редактирование карт для пользователя {user_id}")
        
        await query.answer("Изменения карт отменены")
        
        # Очищаем временные данные
        self.clear_editing_context(context)
        
        # Возвращаемся к меню редактирования
        await self.show_edit_menu(update, context)

    async def cancel_time_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена редактирования времени"""
        query = update.callback_query
        await query.answer("Изменения времени отменены")
        
        # Очищаем временные данные
        self.clear_editing_context(context)
        
        # Возвращаемся к меню редактирования
        await self.show_edit_menu(update, context)

    async def handle_role_selection_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор роли при редактировании профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "back":
            # Пользователь нажал "Назад" - возвращаемся к меню редактирования профиля
            logger.info(f"User {user_id} pressed back button in role selection during edit - returning to edit menu")
            
            # Очищаем временные данные редактирования
            self.clear_editing_context(context)
            
            # Возвращаемся к меню редактирования профиля
            await self.show_edit_menu(update, context)
            return
            
        elif data.startswith("role_"):
            role_name = data.replace("role_", "")
            
            try:
                # Обновляем профиль в БД
                success = await self.db.update_profile(user_id, role=role_name)
                
                if success:
                    await query.answer("✅ Роль обновлена!", show_alert=True)
                    
                    # Очищаем временные данные
                    self.clear_editing_context(context)
                    
                    # Возвращаемся к просмотру профиля
                    await self.view_full_profile(update, context)
                else:
                    await query.answer("❌ Ошибка при сохранении", show_alert=True)
                    
            except Exception as e:
                logger.error(f"Ошибка при обновлении роли: {e}")
                await query.answer("❌ Произошла ошибка", show_alert=True)

    async def handle_elo_selection_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор ELO при редактировании профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "elo_custom":
            await query.edit_message_text(
                "📝 <b>Введите ваше точное ELO на Faceit</b>\n\n"
                "Пример: 1250\n"
                "Диапазон: 1-6000",
                reply_markup=Keyboards.back_button("profile_edit"),
                parse_mode='HTML'
            )
            
            # Сохраняем контекст для ожидания ввода ELO
            context.user_data['editing_field'] = 'faceit_elo'
            context.user_data['awaiting_elo_input'] = True

    async def handle_time_selection_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор времени при редактировании профиля"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Получаем текущий профиль
        profile = await self.db.get_profile(user_id)
        if not profile:
            await query.answer("❌ Профиль не найден!", show_alert=True)
            return
        
        # Инициализируем selected_playtime_slots если его нет
        if 'selected_playtime_slots' not in context.user_data:
            context.user_data['selected_playtime_slots'] = profile.playtime_slots.copy()
        
        selected_slots = context.user_data['selected_playtime_slots']
        
        if data.startswith("time_"):
            slot_id = data.replace("time_", "")
            
            # Переключаем выбор времени
            if slot_id in selected_slots:
                selected_slots.remove(slot_id)
            else:
                selected_slots.append(slot_id)
            
            context.user_data['selected_playtime_slots'] = selected_slots
            
            # Обновляем клавиатуру
            await query.edit_message_reply_markup(
                reply_markup=Keyboards.playtime_selection(selected_slots)
            )
            
            # Показываем количество выбранных времен
            count_text = f"Выбрано времен: {len(selected_slots)}"
            await query.answer(count_text, show_alert=False)

    async def handle_time_edit_done(self, update: Update, context:ContextTypes.DEFAULT_TYPE):
        """Завершает выбор времени при редактировании"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        selected_slots = context.user_data.get('selected_playtime_slots', [])
        
        if len(selected_slots) == 0:
            await query.answer("❌ Выберите хотя бы один временной промежуток!", show_alert=True)
            return
        
        try:
            # Обновляем профиль в БД
            success = await self.db.update_profile(user_id, playtime_slots=selected_slots)
            
            if success:
                await query.answer("✅ Время игры обновлено!", show_alert=True)
                
                # Очищаем временные данные
                self.clear_editing_context(context)
                
                # Возвращаемся к просмотру профиля
                await self.view_full_profile(update, context)
            else:
                await query.answer("❌ Ошибка при сохранении", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении времени: {e}")
            await query.answer("❌ Произошла ошибка", show_alert=True)

    async def handle_profile_edit_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Универсальный обработчик текстового ввода при редактировании профиля"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # Обработка ввода ELO
        if context.user_data.get('awaiting_elo_input') and context.user_data.get('editing_field') == 'faceit_elo':
            try:
                elo = int(text)
                if 1 <= elo <= 6000:
                    # Обновляем профиль в БД
                    success = await self.db.update_profile(user_id, faceit_elo=elo)
                    
                    if success:
                        from bot.utils.cs2_data import format_elo_display
                        await update.message.reply_text(
                            f"✅ <b>ELO обновлено!</b>\n\n"
                            f"<b>Новое ELO:</b> {format_elo_display(elo)}",
                            parse_mode='HTML'
                        )
                        
                        # Очищаем флаги редактирования
                        self.clear_editing_context(context)
                        
                        # Возвращаемся к полному профилю
                        await self.view_full_profile(update, context)
                    else:
                        await update.message.reply_text(
                            "❌ Ошибка при сохранении ELO. Попробуйте еще раз."
                        )
                else:
                    await update.message.reply_text(
                        "❌ ELO должно быть от 1 до 6000. Попробуйте еще раз:"
                    )
            except ValueError:
                await update.message.reply_text(
                    "❌ Введите корректное число от 1 до 6000. Попробуйте еще раз:"
                )
            return
        
        # Обработка ввода описания
        if context.user_data.get('awaiting_description') and context.user_data.get('editing_field') == 'description':
            if len(text) > 500:
                await update.message.reply_text(
                    "❌ Описание слишком длинное! Максимум 500 символов.\n"
                    f"Ваше описание: {len(text)} символов.\n\n"
                    "Попробуйте сократить:"
                )
                return
            
            try:
                # Обновляем профиль в БД
                success = await self.db.update_profile(user_id, description=text)
                
                if success:
                    await update.message.reply_text(
                        f"✅ <b>Описание обновлено!</b>\n\n"
                        f"<b>Новое описание:</b>\n{text[:100]}{'...' if len(text) > 100 else ''}",
                        parse_mode='HTML'
                    )
                    
                    # Очищаем флаги редактирования
                    self.clear_editing_context(context)
                    
                    # Возвращаемся к полному профилю
                    await self.view_full_profile(update, context)
                else:
                    await update.message.reply_text(
                        "❌ Ошибка при сохранении описания. Попробуйте еще раз."
                    )
            except Exception as e:
                logger.error(f"Ошибка при сохранении описания: {e}")
                await update.message.reply_text(
                    "❌ Произошла ошибка при сохранении. Попробуйте еще раз."
                )
            return
        
        # Обработка ввода Faceit URL
        if context.user_data.get('awaiting_faceit_url') and context.user_data.get('editing_field') == 'faceit_url':
            from bot.utils.cs2_data import validate_faceit_url, extract_faceit_nickname
            
            if validate_faceit_url(text):
                try:
                    # Обновляем профиль в БД
                    success = await self.db.update_profile(user_id, faceit_url=text)
                    
                    if success:
                        nickname = extract_faceit_nickname(text)
                        await update.message.reply_text(
                            f"✅ <b>Faceit профиль обновлен!</b>\n\n"
                            f"<b>Новый профиль:</b> <a href='{text}'>{nickname}</a>",
                            parse_mode='HTML'
                        )
                        
                        # Очищаем флаги редактирования
                        self.clear_editing_context(context)
                        
                        # Возвращаемся к полному профилю
                        await self.view_full_profile(update, context)
                    else:
                        await update.message.reply_text(
                            "❌ Ошибка при сохранении Faceit профиля. Попробуйте еще раз."
                        )
                except Exception as e:
                    logger.error(f"Ошибка при сохранении Faceit URL: {e}")
                    await update.message.reply_text(
                        "❌ Произошла ошибка при сохранении. Попробуйте еще раз."
                    )
            else:
                await update.message.reply_text(
                    "❌ Неверная ссылка на Faceit профиль!\n"
                    "Ссылка должна быть в формате:\n"
                    "https://www.faceit.com/ru/players/nickname\n\n"
                    "Попробуйте еще раз:"
                )
            return

        # Обработка ввода игрового ника
        if context.user_data.get('awaiting_nickname') and context.user_data.get('editing_field') == 'game_nickname':
            # Валидация ника
            if len(text) < 2 or len(text) > 32:
                await update.message.reply_text(
                    "❌ Игровой ник должен быть от 2 до 32 символов.\n"
                    "Попробуйте еще раз:"
                )
                return
            
            # Проверка на допустимые символы
            import re
            if not re.match(r'^[a-zA-Z0-9а-яА-Я_-]+$', text):
                await update.message.reply_text(
                    "❌ Ник может содержать только буквы, цифры, дефисы и подчеркивания.\n"
                    "Попробуйте еще раз:"
                )
                return
            
            # Проверка что ник не состоит только из цифр
            if text.isdigit():
                await update.message.reply_text(
                    "❌ Ник не может состоять только из цифр.\n"
                    "Попробуйте еще раз:"
                )
                return
            
            try:
                # Обновляем профиль в БД
                success = await self.db.update_profile(user_id, game_nickname=text)
                
                if success:
                    await update.message.reply_text(
                        f"✅ <b>Игровой ник обновлен!</b>\n\n"
                        f"<b>Новый ник:</b> {text}",
                        parse_mode='HTML'
                    )
                    
                    # Очищаем флаги редактирования
                    self.clear_editing_context(context)
                    
                    # Возвращаемся к полному профилю
                    await self.view_full_profile(update, context)
                else:
                    await update.message.reply_text(
                        "❌ Ошибка при сохранении ника. Попробуйте еще раз."
                    )
            except Exception as e:
                logger.error(f"Ошибка при сохранении игрового ника: {e}")
                await update.message.reply_text(
                    "❌ Произошла ошибка при сохранении. Попробуйте еще раз."
                )
            return
        
        # Если ни один из флагов редактирования не установлен, не обрабатываем сообщение
        return 