"""
Обработчики поиска тиммейтов
"""
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.utils.notifications import NotificationManager
from bot.utils.cs2_data import format_elo_display, format_role_display, format_maps_list, calculate_profile_compatibility, extract_faceit_nickname, PLAYTIME_OPTIONS
from bot.utils.faceit_analyzer import faceit_analyzer
from bot.utils.background_processor import TaskPriority
from bot.utils.progressive_loader import get_progressive_loader
from bot.database.operations import DatabaseManager

logger = logging.getLogger(__name__)

class SearchHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._notification_manager = None  # Будет инициализирован при первом использовании

    def _get_notification_manager(self, context: ContextTypes.DEFAULT_TYPE) -> NotificationManager:
        """Получает экземпляр NotificationManager, создавая его при необходимости"""
        if self._notification_manager is None:
            self._notification_manager = NotificationManager(context.bot, self.db)
        return self._notification_manager

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /search - меню поиска"""
        user_id = update.effective_user.id
        
        # Проверяем есть ли профиль у пользователя
        has_profile = await self.db.has_profile(user_id)
        
        if not has_profile:
            await update.message.reply_text(
                "❌ <b>Доступ запрещен!</b>\n\n"
                "📝 Для поиска тиммейтов необходимо создать игровой профиль.\n"
                "Это поможет другим игрокам найти вас!\n\n"
                "👤 Нажмите кнопку ниже для создания профиля:",
                reply_markup=Keyboards.profile_menu(False),
                parse_mode='HTML'
            )
            return
        
        # Показываем меню поиска
        text = (
            "🔍 <b>Поиск тиммейтов</b>\n\n"
            "Выберите тип поиска:"
        )
        
        await update.message.reply_text(
            text,
            reply_markup=Keyboards.search_menu(),
            parse_mode='HTML'
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback запросы поиска"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        # Защита от дублирования callback-запросов
        callback_key = f"callback_{user_id}_{data}"
        current_time = asyncio.get_event_loop().time()
        
        # Проверяем, не обрабатывался ли этот callback недавно
        if hasattr(context, 'user_data') and context.user_data:
            last_callback_time = context.user_data.get(f"last_callback_{data}", 0)
            if current_time - last_callback_time < 1.0:  # 1 секунда защиты
                logger.debug(f"Пропуск дублированного callback {data} для пользователя {user_id}")
                await query.answer()  # Подтверждаем получение, но не обрабатываем
                return
            
            # Сохраняем время последнего callback
            context.user_data[f"last_callback_{data}"] = current_time

        if data == "search_start":
            await self.start_search(update, context)
        elif data == "search_random":
            await self.random_search(update, context)
        elif data == "search_menu":
            await self.show_search_menu(update, context)
        elif data == "search_elo_filter":
            await self.show_elo_filter_menu(update, context)
        elif data.startswith("elo_filter_"):
            await self.handle_elo_filter_selection(update, context)
        elif data == "apply_elo_filter":
            await self.apply_elo_filter(update, context)
        elif data == "search_categories_filter":
            await self.show_categories_filter_menu(update, context)
        elif data.startswith("categories_filter_"):
            await self.handle_categories_filter_selection(update, context)
        elif data == "apply_categories_filter":
            await self.apply_categories_filter(update, context)
        elif data == "like":
            await self.handle_like(update, context)
        elif data == "skip":
            await self.handle_skip(update, context)

    async def start_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает поиск тиммейтов"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            
            # 🔥 ЛОГИРОВАНИЕ: Начало поиска
            logger.info(f"Начинаем поиск тиммейтов для пользователя {user_id}")
            
            # Проверяем профиль
            has_profile = await self.db.has_profile(user_id)
            if not has_profile:
                logger.warning(f"Пользователь {user_id} пытается искать без профиля")
                await query.answer("❌ Сначала создайте профиль!", show_alert=True)
                return
            
            logger.debug(f"Профиль пользователя {user_id} найден, продолжаем поиск")
            await query.answer()
            
            # 🔥 ЛОГИРОВАНИЕ: Начало поиска кандидатов
            logger.info(f"Получаем кандидатов для пользователя {user_id} (лимит: 20)")
            try:
                candidates = await self.db.find_candidates(user_id, limit=20)
                logger.info(f"Найдено {len(candidates)} кандидатов для пользователя {user_id}")
                
                # Логируем первых нескольких кандидатов для отладки
                if candidates:
                    candidate_ids = [getattr(c, 'user_id', 'неизвестен') for c in candidates[:5]]
                    logger.debug(f"Первые кандидаты для {user_id}: {candidate_ids}")
                
            except Exception as candidates_error:
                logger.error(f"Ошибка поиска кандидатов для пользователя {user_id}: {candidates_error}", exc_info=True)
                candidates = []
            
            if not candidates:
                logger.info(f"Кандидаты не найдены для пользователя {user_id}")
                await query.edit_message_text(
                    "😔 <b>Пока никого не найдено</b>\n\n"
                    "• Попробуйте зайти позже\n"
                    "• Возможно, все игроки уже просмотрены\n"
                    "• Расскажите о боте друзьям!",
                    reply_markup=Keyboards.back_button("back_to_main"),
                    parse_mode='HTML'
                )
                return
            
            # Сохраняем список кандидатов и начинаем показ
            context.user_data['candidates'] = candidates
            context.user_data['current_candidate_index'] = 0
            
            logger.info(f"Запускаем показ кандидатов для пользователя {user_id}")
            await self.show_candidate(query, context)
            
        except Exception as e:
            user_id_safe = "неизвестен"
            try:
                user_id_safe = update.callback_query.from_user.id
            except:
                pass
            logger.error(f"Критическая ошибка в start_search для пользователя {user_id_safe}: {e}", exc_info=True)

    async def random_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Случайный поиск"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        # Получаем случайных кандидатов
        candidates = await self.db.find_candidates(user_id, limit=50)
        
        if not candidates:
            await query.edit_message_text(
                "😔 Нет доступных игроков для поиска",
                reply_markup=Keyboards.back_button("back_to_main")
            )
            return
        
        # Перемешиваем случайно
        import random
        random.shuffle(candidates)
        
        # Берем первых 20
        candidates = candidates[:20]
        
        context.user_data['candidates'] = candidates
        context.user_data['current_candidate_index'] = 0
        
        await self.show_candidate(query, context)

    async def show_candidate(self, query_or_update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает анкету кандидата"""
        try:
            # 🔥 ЛОГИРОВАНИЕ: Начало отображения кандидата
            candidates = context.user_data.get('candidates', [])
            current_index = context.user_data.get('current_candidate_index', 0)
            user_id = query_or_update.from_user.id if hasattr(query_or_update, 'from_user') else query_or_update.effective_user.id
            
            # Cancel pending ELO updates when navigating to next candidate
            progressive_loader = get_progressive_loader()
            if progressive_loader:
                await progressive_loader.cancel_pending_updates(user_id)
                logger.debug(f"Cancelled pending ELO updates for user {user_id} before showing candidate")
            
            logger.info(f"show_candidate: user_id={user_id}, index={current_index}, total_candidates={len(candidates)}")
            
            if current_index >= len(candidates):
                # 🔥 ЛОГИРОВАНИЕ: Кандидаты закончились
                logger.info(f"Поиск завершен для пользователя {user_id}: просмотрено {current_index} кандидатов")
                
                text = (
                    "✅ <b>Поиск завершен!</b>\n\n"
                    "Вы просмотрели всех доступных игроков.\n"
                    "Попробуйте поискать позже или расскажите о боте друзьям!"
                )
                
                # 🔥 ИСПРАВЛЕНИЕ: Улучшенная обработка завершения поиска
                try:
                    # Определяем chat_id для отправки сообщения
                    if hasattr(query_or_update, 'message') and query_or_update.message:
                        chat_id = query_or_update.message.chat_id
                    elif hasattr(query_or_update, 'effective_chat'):
                        chat_id = query_or_update.effective_chat.id
                    else:
                        chat_id = query_or_update.from_user.id
                    
                    # Пытаемся отредактировать только если есть текстовое сообщение
                    edit_attempted = False
                    if hasattr(query_or_update, 'edit_message_text') and hasattr(query_or_update, 'message'):
                        try:
                            # Проверяем, что предыдущее сообщение было текстовым
                            if query_or_update.message.text:
                                await query_or_update.edit_message_text(
                                    text,
                                    reply_markup=Keyboards.back_button("back_to_main"),
                                    parse_mode='HTML'
                                )
                                edit_attempted = True
                                logger.debug(f"Сообщение о завершении поиска отредактировано для пользователя {user_id}")
                        except Exception as edit_error:
                            logger.warning(f"Не удалось отредактировать сообщение о завершении поиска для {user_id}: {edit_error}")
                    
                    # Если редактирование не получилось, отправляем новое сообщение
                    if not edit_attempted:
                        # Получаем контекст для отправки нового сообщения
                        if hasattr(query_or_update, 'get_bot'):
                            bot = query_or_update.get_bot()
                        else:
                            # Попытка получить бот из контекста
                            bot = context.bot if context else None
                        
                        if bot:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                reply_markup=Keyboards.back_button("back_to_main"),
                                parse_mode='HTML'
                            )
                            logger.debug(f"Новое сообщение о завершении поиска отправлено пользователю {user_id}")
                        else:
                            logger.error(f"Не удалось получить bot для отправки сообщения пользователю {user_id}")
                            # Fallback - используем message.reply_text если доступно
                            if hasattr(query_or_update, 'message'):
                                await query_or_update.message.reply_text(
                                    text,
                                    reply_markup=Keyboards.back_button("back_to_main"),
                                    parse_mode='HTML'
                                )
                
                except Exception as completion_error:
                    logger.error(f"Критическая ошибка отправки сообщения о завершении поиска для {user_id}: {completion_error}", exc_info=True)
                    # В крайнем случае просто логируем, чтобы не крашить бота
                
                return
            
            candidate = candidates[current_index]
            candidate_id = getattr(candidate, 'user_id', 'неизвестен')
            
            # 🔥 ЛОГИРОВАНИЕ: Информация о текущем кандидате
            logger.info(f"Отображение кандидата {candidate_id} для пользователя {user_id} (индекс {current_index})")
            
            # Получаем профиль текущего пользователя для расчета совместимости
            try:
                user_profile = await self.db.get_profile(user_id)
                if not user_profile:
                    logger.warning(f"Профиль пользователя {user_id} не найден при отображении кандидата {candidate_id}")
                else:
                    logger.debug(f"Профиль пользователя {user_id} получен для расчета совместимости с кандидатом {candidate_id}")
            except Exception as profile_error:
                logger.error(f"Ошибка получения профиля пользователя {user_id}: {profile_error}")
                user_profile = None
            
            # Progressive loading: Format basic profile first (without ELO API calls)
            logger.debug(f"Начинаем форматирование базовой анкеты кандидата {candidate_id}")
            try:
                text = await self.format_candidate_profile_basic(candidate, user_profile, user_id)
                logger.debug(f"Базовая анкета кандидата {candidate_id} сформатирована, длина: {len(text)} символов")
            except Exception as format_error:
                logger.error(f"Ошибка форматирования анкеты кандидата {candidate_id}: {format_error}")
                text = f"❌ <b>Ошибка отображения анкеты</b>\n\nКандидат: {candidate_id}"
            
            # Сохраняем текущего кандидата
            context.user_data['current_candidate'] = candidate
            
            # Определяем chat_id для отправки
            if hasattr(query_or_update, 'message') and query_or_update.message:
                chat_id = query_or_update.message.chat_id
            elif hasattr(query_or_update, 'effective_chat'):
                chat_id = query_or_update.effective_chat.id
            else:
                chat_id = query_or_update.from_user.id
            
            # 🔥 ЛОГИРОВАНИЕ: Информация о медиа
            has_media = False
            media_type = None
            try:
                has_media = candidate.has_media()
                media_type = getattr(candidate, 'media_type', None) if has_media else None
                logger.debug(f"Кандидат {candidate_id}: has_media={has_media}, media_type={media_type}")
            except Exception as media_check_error:
                logger.warning(f"Ошибка проверки медиа у кандидата {candidate_id}: {media_check_error}")
            
            # Отправляем профиль с медиа если есть
            query_for_edit = query_or_update if hasattr(query_or_update, 'edit_message_text') else None
            
            # Progressive loading: Send basic profile immediately and schedule ELO update
            logger.info(f"Отправляем базовую анкету кандидата {candidate_id} пользователю {user_id} (chat_id={chat_id}, has_media={has_media})")
            
            try:
                # Send basic profile first
                message_info = await self.send_candidate_with_media(
                    chat_id=chat_id,
                    candidate=candidate,
                    text=text,
                    reply_markup=Keyboards.like_buttons(),
                    context=context,
                    query_for_edit=query_for_edit
                )
                logger.info(f"Базовая анкета кандидата {candidate_id} успешно отправлена пользователю {user_id}")
                
                # Progressive loading: Register message and schedule ELO update
                if message_info and len(message_info) >= 4:
                    chat_id_msg, message_id, is_media, is_photo = message_info
                    
                    # Only register progressive updates if message was sent successfully
                    if message_id > 0:
                        # Get progressive loader
                        progressive_loader = get_progressive_loader()
                        if progressive_loader:
                            # Generate context ID to prevent race conditions
                            import uuid
                            context_id = f"search_{user_id}_{candidate_id}_{uuid.uuid4().hex[:8]}"
                            
                            # Set user context
                            await progressive_loader.set_user_context(user_id, context_id)
                            
                            # Register message for ELO updates
                            message_key = progressive_loader.register_message(
                                chat_id_msg, message_id, is_media, is_photo,
                                user_id, 'search', context_id
                            )
                            
                            # Schedule ELO update in background if candidate has faceit nickname
                            game_nickname = getattr(candidate, 'game_nickname', '')
                            if game_nickname and game_nickname.strip():
                                logger.debug(f"Scheduling ELO update for candidate {candidate_id} with nickname {game_nickname}")
                                
                                # Create faceit data for the update
                                faceit_data = {
                                    'faceit_nickname': game_nickname,
                                    'faceit_elo': getattr(candidate, 'faceit_elo', 0)
                                }
                                
                                # Schedule the ELO update
                                await self._schedule_candidate_elo_update(
                                    message_key, candidate, faceit_data, user_profile, user_id
                                )
                            else:
                                logger.debug(f"No faceit nickname for candidate {candidate_id}, skipping ELO update")
                
            except Exception as send_error:
                logger.error(f"Критическая ошибка отправки анкеты кандидата {candidate_id} пользователю {user_id}: {send_error}", exc_info=True)
                # Попытка отправить простое уведомление об ошибке
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ <b>Ошибка отображения анкеты</b>\n\nПопробуйте продолжить поиск или обратитесь в поддержку.",
                        parse_mode='HTML',
                        reply_markup=Keyboards.like_buttons()
                    )
                except:
                    logger.error(f"Не удалось отправить даже уведомление об ошибке пользователю {user_id}")
        
        except Exception as e:
            user_id_safe = "неизвестен"
            try:
                user_id_safe = query_or_update.from_user.id if hasattr(query_or_update, 'from_user') else query_or_update.effective_user.id
            except:
                pass
            logger.error(f"Критическая ошибка в show_candidate для пользователя {user_id_safe}: {e}", exc_info=True)

    async def format_candidate_profile_basic(self, candidate, user_profile=None, current_user_id=None):
        """Форматирует анкету кандидата"""
        try:
            # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка взаимного лайка
            show_name = False
            if current_user_id:
                try:
                    show_name = await self.db.check_mutual_like(current_user_id, candidate.user_id)
                except Exception as like_error:
                    logger.warning(f"Ошибка проверки взаимного лайка для {current_user_id} -> {candidate.user_id}: {like_error}")
                    show_name = False  # По умолчанию не показываем имя при ошибке
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение игрового ника
            game_nickname = getattr(candidate, 'game_nickname', None)
            if not game_nickname or game_nickname.strip() == '':
                game_nickname = f"Игрок #{candidate.user_id}"  # Fallback значение
            
            text = f"👤 <b>{game_nickname}</b>\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное получение Telegram данных при взаимном лайке
            if show_name:
                try:
                    user = await self.db.get_user(candidate.user_id)
                    if user and user.first_name:
                        telegram_info = user.first_name
                        if hasattr(user, 'username') and user.username:
                            telegram_info += f" (@{user.username})"
                        text += f"🔗 <b>Telegram:</b> {telegram_info}\n"
                except Exception as user_error:
                    logger.warning(f"Ошибка получения пользователя {candidate.user_id}: {user_error}")
                    # Не добавляем Telegram информацию при ошибке
            
            text += "\n"
            
            # Progressive loading: Show ELO loading placeholder immediately
            try:
                faceit_elo = getattr(candidate, 'faceit_elo', 0)
                
                if not isinstance(faceit_elo, int) or faceit_elo < 0:
                    faceit_elo = 0  # По умолчанию
                
                if faceit_elo > 0:
                    # Show loading placeholder for immediate display
                    text += f"🎯 <b>ELO Faceit:</b> {Keyboards.elo_loading_placeholder()}\n"
                else:
                    text += f"🎯 <b>ELO Faceit:</b> Не указан\n"
            except Exception as elo_error:
                logger.warning(f"Ошибка отображения ELO для кандидата {candidate.user_id}: {elo_error}")
                text += f"🎯 <b>ELO Faceit:</b> Не указан\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное извлечение Faceit никнейма и URL
            try:
                faceit_url = getattr(candidate, 'faceit_url', '')
                if faceit_url:
                    nickname = extract_faceit_nickname(faceit_url)
                    if not nickname:  # Если извлечь не удалось
                        nickname = "профиль"
                    text += f"🔗 <b>Faceit:</b> <a href='{faceit_url}'>{nickname}</a>\n"
                else:
                    text += f"🔗 <b>Faceit:</b> Не указан\n"
            except Exception as faceit_error:
                logger.warning(f"Ошибка обработки Faceit URL для кандидата {candidate.user_id}: {faceit_error}")
                text += f"🔗 <b>Faceit:</b> Ошибка загрузки\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение роли
            try:
                role = getattr(candidate, 'role', 'Не указана')
                text += f"👥 <b>Роль:</b> {format_role_display(role)}\n"
            except Exception as role_error:
                logger.warning(f"Ошибка отображения роли для кандидата {candidate.user_id}: {role_error}")
                text += f"👥 <b>Роль:</b> Не указана\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение карт
            try:
                favorite_maps = getattr(candidate, 'favorite_maps', [])
                if not isinstance(favorite_maps, list):
                    favorite_maps = []
                text += f"🗺️ <b>Любимые карты:</b> {format_maps_list(favorite_maps)}\n"
            except Exception as maps_error:
                logger.warning(f"Ошибка отображения карт для кандидата {candidate.user_id}: {maps_error}")
                text += f"🗺️ <b>Любимые карты:</b> Ошибка загрузки\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение времени игры
            try:
                playtime_slots = getattr(candidate, 'playtime_slots', [])
                if not isinstance(playtime_slots, list):
                    playtime_slots = []
                
                time_displays = []
                for slot_id in playtime_slots:
                    try:
                        time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
                        if time_option:
                            time_displays.append(f"{time_option['emoji']} {time_option['name']}")
                    except Exception as slot_error:
                        logger.debug(f"Ошибка обработки временного слота {slot_id}: {slot_error}")
                        continue  # Пропускаем некорректный слот
                
                if time_displays:
                    text += f"⏰ <b>Время игры:</b>\n"
                    for time_display in time_displays:
                        text += f"   {time_display}\n"
                else:
                    text += f"⏰ <b>Время игры:</b> Не указано\n"
            except Exception as time_error:
                logger.warning(f"Ошибка отображения времени игры для кандидата {candidate.user_id}: {time_error}")
                text += f"⏰ <b>Время игры:</b> Ошибка загрузки\n"
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение категорий
            try:
                if hasattr(candidate, 'categories') and candidate.categories:
                    categories = candidate.categories
                    if isinstance(categories, list) and len(categories) > 0:
                        from bot.utils.cs2_data import format_categories_display
                        categories_text = format_categories_display(categories)
                        text += f"🎮 <b>Категории:</b> {categories_text}\n"
            except Exception as categories_error:
                logger.warning(f"Ошибка отображения категорий для кандидата {candidate.user_id}: {categories_error}")
                # Не добавляем категории при ошибке
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное отображение описания
            try:
                description = getattr(candidate, 'description', None)
                if description and description.strip():
                    # Ограничиваем длину описания для предотвращения слишком длинных сообщений
                    max_description_length = 200
                    if len(description) > max_description_length:
                        description = description[:max_description_length] + "..."
                    text += f"\n💬 <b>О себе:</b>\n{description}\n"
            except Exception as description_error:
                logger.warning(f"Ошибка отображения описания для кандидата {candidate.user_id}: {description_error}")
                # Не добавляем описание при ошибке
            
            # Примечание: Faceit данные обрабатываются в show_candidate перед отправкой
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка медиа
            try:
                if candidate.has_media():
                    media_icon = "📷" if candidate.is_photo() else "🎥"
                    text += f"\n{media_icon} <b>Медиа:</b> прикреплено\n"
            except Exception as media_error:
                logger.warning(f"Ошибка проверки медиа для кандидата {candidate.user_id}: {media_error}")
                # Не добавляем информацию о медиа при ошибке
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный расчет совместимости
            if user_profile:
                try:
                    compatibility = calculate_profile_compatibility(user_profile, candidate)
                    if compatibility and 'total' in compatibility:
                        total_compat = compatibility['total']
                        compat_emoji = "🔥" if total_compat >= 80 else "⭐" if total_compat >= 60 else "👌" if total_compat >= 40 else "🤔"
                        text += f"\n{compat_emoji} <b>Совместимость:</b> {total_compat}%"
                except Exception as compatibility_error:
                    logger.warning(f"Ошибка расчета совместимости для кандидата {candidate.user_id}: {compatibility_error}")
                    # Не добавляем совместимость при ошибке
            
            return text
            
        except Exception as e:
            logger.error(f"Критическая ошибка форматирования профиля кандидата {candidate.user_id}: {e}", exc_info=True)
            
            # 🔥 ИСПРАВЛЕНИЕ: Fallback профиль при критических ошибках
            try:
                fallback_nickname = getattr(candidate, 'game_nickname', f"Игрок #{candidate.user_id}")
                fallback_elo = getattr(candidate, 'faceit_elo', 0)
                
                return (
                    f"👤 <b>{fallback_nickname}</b>\n\n"
                    f"🎯 <b>ELO Faceit:</b> {fallback_elo}\n"
                    f"⚠️ <b>Информация:</b> Ошибка загрузки полного профиля\n\n"
                    f"<i>Обратитесь в поддержку если проблема повторяется.</i>"
                )
            except Exception as fallback_error:
                logger.error(f"Критическая ошибка создания fallback профиля для кандидата {candidate.user_id}: {fallback_error}")
                return f"❌ <b>Ошибка отображения анкеты</b>\n\nИдентификатор: {candidate.user_id if hasattr(candidate, 'user_id') else 'неизвестен'}"

    async def format_candidate_profile_with_elo(self, candidate, elo_data, user_profile=None, current_user_id=None):
        """Форматирует анкету кандидата с ELO данными (для прогрессивного обновления)"""
        try:
            # Get basic profile text
            text = await self.format_candidate_profile_basic(candidate, user_profile, current_user_id)
            
            # Replace ELO loading placeholder with actual data
            if elo_data:
                from bot.utils.cs2_data import format_faceit_elo_display
                
                faceit_elo = getattr(candidate, 'faceit_elo', 0)
                game_nickname = getattr(candidate, 'game_nickname', '')
                
                # Get min/max ELO from API data
                lowest_elo = elo_data.get('lowest_elo', 0)
                highest_elo = elo_data.get('highest_elo', 0)
                
                # Validate ELO data
                if isinstance(lowest_elo, (int, float)) and isinstance(highest_elo, (int, float)):
                    lowest_elo = int(lowest_elo) if lowest_elo >= 0 else 0
                    highest_elo = int(highest_elo) if highest_elo >= 0 else 0
                    
                    # Format ELO display with min/max if available
                    if lowest_elo > 0 or highest_elo > 0:
                        elo_display = format_faceit_elo_display(faceit_elo, lowest_elo, highest_elo, game_nickname)
                        logger.debug(f"ELO updated for {game_nickname}: {faceit_elo} (min: {lowest_elo}, max: {highest_elo})")
                    else:
                        elo_display = format_elo_display(faceit_elo)
                else:
                    elo_display = format_elo_display(faceit_elo)
                
                # Replace loading placeholder with actual ELO
                loading_placeholder = Keyboards.elo_loading_placeholder()
                text = text.replace(loading_placeholder, elo_display)
            
            return text
            
        except Exception as e:
            logger.error(f"Error formatting candidate profile with ELO for {candidate.user_id}: {e}", exc_info=True)
            # Return basic profile text as fallback
            return await self.format_candidate_profile_basic(candidate, user_profile, current_user_id)

    async def _schedule_candidate_elo_update(self, message_key: str, candidate, faceit_data: dict, user_profile, user_id: int) -> None:
        """Schedule ELO update for a candidate profile"""
        try:
            progressive_loader = get_progressive_loader()
            if not progressive_loader:
                logger.warning("Progressive loader not available for ELO update")
                return
                
            # Create format callback for ELO updates
            async def format_callback(updated_faceit_data, include_elo=True):
                if include_elo:
                    formatted_text = await self.format_candidate_profile_with_elo(
                        candidate, updated_faceit_data, user_profile, user_id
                    )
                else:
                    formatted_text = await self.format_candidate_profile_basic(
                        candidate, user_profile, user_id
                    )
                return formatted_text, Keyboards.like_buttons()
            
            # Schedule the ELO update with HIGH priority for search results
            success = await progressive_loader.schedule_elo_update(
                message_key, faceit_data, format_callback, TaskPriority.HIGH
            )
            
            if success:
                logger.debug(f"ELO update scheduled for candidate {candidate.user_id}")
            else:
                logger.warning(f"Failed to schedule ELO update for candidate {candidate.user_id}")
                
        except Exception as e:
            logger.error(f"Error scheduling ELO update for candidate {candidate.user_id}: {e}", exc_info=True)

    async def send_candidate_with_media(self, chat_id: int, candidate, text: str, reply_markup=None, context=None, query_for_edit=None):
        """Отправляет профиль кандидата с медиа и возвращает информацию о сообщении"""
        try:
            # 🔥 ИСПРАВЛЕНИЕ: Проверяем длину caption для медиа (лимит Telegram = 1024 символа)  
            if candidate.has_media():
                # Обрезаем caption если он слишком длинный
                caption_limit = 1020  # Небольшой запас для безопасности  
                media_caption = text if len(text) <= caption_limit else text[:caption_limit] + "..."
                
                logger.info(f"Отправка медиа для кандидата {candidate.user_id}: type={candidate.media_type}, caption_length={len(media_caption)}")
                
                # Отправляем медиа с caption
                media_sent = False
                sent_message = None
                if candidate.is_photo():
                    try:
                        sent_message = await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=candidate.media_file_id,
                            caption=media_caption,
                            parse_mode='HTML',
                            reply_markup=reply_markup
                        )
                        media_sent = True
                    except Exception as photo_error:
                        error_msg = str(photo_error).lower()
                        if "wrong file identifier" in error_msg or "file not found" in error_msg:
                            logger.warning(f"File ID недействителен для фото кандидата {candidate.user_id}: {photo_error}")
                            # Помечаем медиа как недействительное в БД
                            await self._invalidate_media(candidate.user_id, "invalid_file_id")
                        else:
                            logger.error(f"Ошибка отправки фото для кандидата {candidate.user_id}: {photo_error}")
                        
                elif candidate.is_video():
                    try:
                        sent_message = await context.bot.send_video(
                            chat_id=chat_id,
                            video=candidate.media_file_id,
                            caption=media_caption,
                            parse_mode='HTML',
                            reply_markup=reply_markup
                        )
                        media_sent = True
                    except Exception as video_error:
                        error_msg = str(video_error).lower()
                        if "wrong file identifier" in error_msg or "file not found" in error_msg:
                            logger.warning(f"File ID недействителен для видео кандидата {candidate.user_id}: {video_error}")
                            # Помечаем медиа как недействительное в БД
                            await self._invalidate_media(candidate.user_id, "invalid_file_id")
                        else:
                            logger.error(f"Ошибка отправки видео для кандидата {candidate.user_id}: {video_error}")
                
                # Если медиа не удалось отправить, отправляем как обычное текстовое сообщение
                if not media_sent:
                    logger.warning(f"Медиа не отправлено, отправляем текстом для кандидата {candidate.user_id}")
                    sent_message = await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                    
                # 🔥 ИСПРАВЛЕНИЕ: Безопасное удаление предыдущего сообщения
                if query_for_edit and hasattr(query_for_edit, 'message'):
                    try:
                        # Добавляем небольшую задержку перед удалением для стабильности
                        import asyncio
                        await asyncio.sleep(0.1)
                        await query_for_edit.message.delete()
                        logger.debug(f"Предыдущее сообщение удалено для кандидата {candidate.user_id}")
                    except Exception as delete_error:
                        # НЕ критичная ошибка - продолжаем работу
                        logger.warning(f"Не удалось удалить предыдущее сообщение для кандидата {candidate.user_id}: {delete_error}")
                        
                # Return message info for media messages
                if sent_message:
                    return (sent_message.chat_id, sent_message.message_id, True, candidate.is_photo())
                        
            else:
                # 🔥 ИСПРАВЛЕНИЕ: Улучшенная обработка кандидатов без медиа
                logger.debug(f"Отправка текстового профиля для кандидата {candidate.user_id}")
                
                # Пытаемся редактировать существующее сообщение
                if query_for_edit and hasattr(query_for_edit, 'edit_message_text'):
                    try:
                        await query_for_edit.edit_message_text(
                            text=text,
                            parse_mode='HTML',
                            reply_markup=reply_markup
                        )
                        logger.debug(f"Сообщение отредактировано для кандидата {candidate.user_id}")
                        # Return message info for edited message
                        return (query_for_edit.message.chat_id, query_for_edit.message.message_id, False, False)
                    except Exception as edit_error:
                        logger.warning(f"Не удалось редактировать сообщение для кандидата {candidate.user_id}: {edit_error}")
                        # Продолжаем к отправке нового сообщения
                
                # Отправляем новое текстовое сообщение
                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                logger.debug(f"Новое текстовое сообщение отправлено для кандидата {candidate.user_id}")
                
                # Return message info for new text message
                return (sent_message.chat_id, sent_message.message_id, False, False)
                
        except Exception as e:
            logger.error(f"Критическая ошибка отправки профиля кандидата {candidate.user_id}: {e}", exc_info=True)
            
            # 🔥 ИСПРАВЛЕНИЕ: Улучшенный fallback с дополнительными проверками
            try:
                # Убеждаемся что текст не пустой и не слишком длинный
                fallback_text = text[:4000] if text and len(text) > 4000 else (text or "❌ Ошибка загрузки профиля")
                
                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ <b>Профиль кандидата</b>\n\n{fallback_text}\n\n<i>Примечание: возникла ошибка при загрузке полной версии профиля.</i>",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                logger.info(f"Fallback сообщение отправлено для кандидата {candidate.user_id}")
                
                # Return message info for fallback message
                return (sent_message.chat_id, sent_message.message_id, False, False)
                
            except Exception as fallback_error:
                logger.error(f"Критическая ошибка fallback отправки для кандидата {candidate.user_id}: {fallback_error}", exc_info=True)
                # В крайнем случае отправляем простое сообщение об ошибке
                try:
                    sent_message = await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ <b>Ошибка отображения анкеты</b>\n\nПопробуйте обновить поиск или обратитесь в поддержку.",
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                    # Return message info even for error messages
                    if sent_message:
                        return (sent_message.chat_id, sent_message.message_id, False, False)
                except:
                    pass  # Не можем даже отправить ошибку
                    
        # Return message info if we have a sent message
        if 'sent_message' in locals() and sent_message:
            is_media = bool(candidate.has_media() and media_sent)
            is_photo = bool(candidate.is_photo() and media_sent)
            return (sent_message.chat_id, sent_message.message_id, is_media, is_photo)
        
        # Fallback return if no message was sent successfully  
        return (chat_id, 0, False, False)

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает лайк"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            
            # 🔥 ЛОГИРОВАНИЕ: Начало обработки лайка
            logger.info(f"Обработка лайка от пользователя {user_id}")
            
            current_candidate = context.user_data.get('current_candidate')
            if not current_candidate:
                await query.answer("❌ Ошибка: кандидат не найден", show_alert=True)
                logger.warning(f"Кандидат не найден в контексте для пользователя {user_id}")
                return
            
            candidate_id = getattr(current_candidate, 'user_id', 'неизвестен')
            logger.info(f"Лайк от {user_id} кандидату {candidate_id}")
            
            # Проверяем настройки приватности кандидата (who_can_like)
            try:
                can_like = await self._check_can_like(user_id, current_candidate.user_id)
                if not can_like:
                    await query.answer("❌ Этот пользователь ограничил получение лайков", show_alert=True)
                    logger.info(f"Лайк от {user_id} к {candidate_id} заблокирован настройками приватности")
                    # Переходим к следующему кандидату
                    await self.next_candidate(query, context)
                    return
            except Exception as privacy_error:
                logger.error(f"Ошибка проверки настроек приватности для лайка {user_id} -> {candidate_id}: {privacy_error}")
                # Продолжаем, разрешая лайк по умолчанию
            
            # 🔥 ИСПРАВЛЕНИЕ: Подтверждаем получение callback перед операциями с БД
            await query.answer("❤️ Лайк поставлен!")
            logger.debug(f"Callback acknowledged для лайка {user_id} -> {candidate_id}")
            
            # Добавляем лайк в БД
            try:
                await self.db.add_like(user_id, current_candidate.user_id)
                logger.info(f"Лайк {user_id} -> {candidate_id} успешно добавлен в БД")
            except Exception as db_error:
                logger.error(f"Ошибка добавления лайка в БД {user_id} -> {candidate_id}: {db_error}")
                # Уведомляем пользователя об ошибке и продолжаем
                await query.edit_message_text(
                    "❌ <b>Ошибка при добавлении лайка</b>\n\nПопробуйте еще раз или обратитесь в поддержку.",
                    reply_markup=Keyboards.like_buttons(),
                    parse_mode='HTML'
                )
                return
            
            # Отправляем уведомление получателю лайка
            try:
                notification_manager = self._get_notification_manager(context)
                await notification_manager.send_like_notification(
                    liked_user_id=current_candidate.user_id, 
                    liker_user_id=user_id
                )
                logger.debug(f"Уведомление о лайке отправлено от {user_id} к {candidate_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о лайке {user_id} -> {candidate_id}: {e}")
                # Продолжаем выполнение, не прерывая основную логику
            
            # Проверяем взаимный лайк
            try:
                is_mutual = await self.db.check_mutual_like(user_id, current_candidate.user_id)
                logger.debug(f"Проверка взаимного лайка {user_id} <-> {candidate_id}: {is_mutual}")
            except Exception as mutual_error:
                logger.error(f"Ошибка проверки взаимного лайка {user_id} <-> {candidate_id}: {mutual_error}")
                is_mutual = False  # По умолчанию считаем что взаимного лайка нет
            
            if is_mutual:
                logger.info(f"🎉 ВЗАИМНЫЙ ЛАЙК! {user_id} <-> {candidate_id}")
                
                # Создаем связь с тиммейтом
                try:
                    await self.db.create_match(user_id, current_candidate.user_id)
                    logger.info(f"Матч создан между {user_id} и {candidate_id}")
                except Exception as match_error:
                    logger.error(f"Ошибка создания матча {user_id} <-> {candidate_id}: {match_error}")
                
                # Отправляем уведомления о новом матче обоим пользователям
                try:
                    notification_manager = self._get_notification_manager(context)
                    await notification_manager.send_match_notification(
                        user1_id=user_id,
                        user2_id=current_candidate.user_id
                    )
                    logger.debug(f"Уведомления о матче отправлены {user_id} <-> {candidate_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомлений о матче {user_id} <-> {candidate_id}: {e}")
                    # Продолжаем выполнение, не прерывая основную логику
                
                match_text = (
                    "🎉 <b>ПОЗДРАВЛЯЕМ! У ВАС ТИММЕЙТ!</b>\n\n"
                    f"Вы понравились друг другу!\n"
                    "Теперь вы можете начать общение.\n\n"
                    "Найти контакты игрока можно в разделе 'Мои тиммейты'."
                )
                
                # 🔥 ИСПРАВЛЕНИЕ: Обрабатываем редактирование сообщения для взаимного лайка
                try:
                    # Определяем chat_id
                    if hasattr(query, 'message') and query.message:
                        chat_id = query.message.chat_id
                    else:
                        chat_id = query.from_user.id
                    
                    # Пытаемся отредактировать, если сообщение текстовое
                    if hasattr(query, 'message') and query.message and query.message.text:
                        await query.edit_message_text(
                            match_text,
                            reply_markup=Keyboards.back_button("back_to_main"),
                            parse_mode='HTML'
                        )
                        logger.debug(f"Сообщение о матче отредактировано для {user_id}")
                    else:
                        # Отправляем новое сообщение если предыдущее было медиа
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=match_text,
                            reply_markup=Keyboards.back_button("back_to_main"),
                            parse_mode='HTML'
                        )
                        logger.debug(f"Новое сообщение о матче отправлено для {user_id}")
                        
                except Exception as message_error:
                    logger.error(f"Ошибка отправки сообщения о матче для {user_id}: {message_error}")
                    # Fallback - просто логируем, пользователь уже получил уведомление
                
                return
            
            # Переходим к следующему кандидату
            logger.debug(f"Переход к следующему кандидату для пользователя {user_id}")
            await self.next_candidate(query, context)
            
        except Exception as e:
            user_id_safe = "неизвестен"
            try:
                user_id_safe = update.callback_query.from_user.id
            except:
                pass
            logger.error(f"Критическая ошибка в handle_like для пользователя {user_id_safe}: {e}", exc_info=True)
            
            # Пытаемся дать обратную связь пользователю
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Произошла ошибка. Попробуйте еще раз.", show_alert=True)
            except:
                pass  # Не можем даже ответить на callback

    async def handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает пропуск"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            
            # 🔥 ЛОГИРОВАНИЕ: Начало обработки пропуска
            current_candidate = context.user_data.get('current_candidate')
            candidate_id = getattr(current_candidate, 'user_id', 'неизвестен') if current_candidate else 'неизвестен'
            logger.info(f"Пропуск от пользователя {user_id}, кандидат {candidate_id}")
            
            # 🔥 ИСПРАВЛЕНИЕ: Всегда подтверждаем получение callback
            await query.answer("➡️ Пропущено")
            logger.debug(f"Callback acknowledged для пропуска {user_id}")
            
            # Переходим к следующему кандидату
            await self.next_candidate(query, context)
            
        except Exception as e:
            user_id_safe = "неизвестен"
            try:
                user_id_safe = update.callback_query.from_user.id
            except:
                pass
            logger.error(f"Критическая ошибка в handle_skip для пользователя {user_id_safe}: {e}", exc_info=True)
            
            # Пытаемся дать обратную связь пользователю
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Произошла ошибка. Попробуйте еще раз.", show_alert=True)
            except:
                pass  # Не можем даже ответить на callback

    async def next_candidate(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Переход к следующему кандидату"""
        try:
            current_index = context.user_data.get('current_candidate_index', 0)
            context.user_data['current_candidate_index'] = current_index + 1
            
            user_id = query.from_user.id if hasattr(query, 'from_user') else "неизвестен"
            
            # Cancel pending ELO updates before navigating to next candidate
            progressive_loader = get_progressive_loader()
            if progressive_loader and hasattr(query, 'from_user'):
                await progressive_loader.cancel_pending_updates(query.from_user.id)
                logger.debug(f"Cancelled pending ELO updates for user {query.from_user.id} before next candidate")
            
            logger.debug(f"Переход к кандидату #{current_index + 1} для пользователя {user_id}")
            
            await self.show_candidate(query, context)
            
        except Exception as e:
            user_id_safe = "неизвестен"
            try:
                user_id_safe = query.from_user.id if hasattr(query, 'from_user') else "неизвестен"
            except:
                pass
            logger.error(f"Критическая ошибка в next_candidate для пользователя {user_id_safe}: {e}", exc_info=True)
            
            # Пытаемся дать обратную связь пользователю
            try:
                if hasattr(query, 'answer'):
                    await query.answer("❌ Ошибка перехода к следующему кандидату. Попробуйте начать поиск заново.", show_alert=True)
            except:
                pass  # Не можем даже ответить

    async def show_search_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню поиска"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "🔍 <b>Поиск тиммейтов</b>\n\n"
            "Выберите тип поиска:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.search_menu(),
            parse_mode='HTML'
        )

    async def show_elo_filter_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню выбора ELO фильтра"""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        # Получаем текущие настройки пользователя
        user_settings = await self.db.get_user_settings(user_id)
        current_filter = 'any'
        if user_settings:
            filters = user_settings.get_search_filters()
            current_filter = filters.get('elo_filter', 'any')
        
        # Сохраняем текущий фильтр в контекст
        context.user_data['selected_elo_filter'] = current_filter
        
        text = (
            "🎯 <b>Фильтр по ELO</b>\n\n"
            "Выберите диапазон ELO для поиска:\n\n"
            "🔰 <b>До 1999 ELO</b> - Новички и растущие игроки\n"
            "⭐ <b>2000-2699 ELO</b> - Средний уровень игры\n"
            "🏆 <b>2700-3099 ELO</b> - Продвинутый уровень\n"
            "💎 <b>3100+ ELO</b> - Профессиональный уровень\n"
            "👑 <b>TOP 1000</b> - Лучшие игроки сервера"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.elo_filter_menu(current_filter),
            parse_mode='HTML'
        )

    async def handle_elo_filter_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор ELO фильтра"""
        query = update.callback_query
        data = query.data
        await query.answer()
        
        # Извлекаем выбранный фильтр
        filter_id = data.replace("elo_filter_", "")
        context.user_data['selected_elo_filter'] = filter_id
        
        # Обновляем меню с новым выделением
        await self.show_elo_filter_menu(update, context)

    async def apply_elo_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Применяет выбранный ELO фильтр и начинает поиск"""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        # Получаем выбранный фильтр
        selected_filter = context.user_data.get('selected_elo_filter', 'any')
        
        # Сохраняем фильтр в настройки пользователя
        await self._save_elo_filter(user_id, selected_filter)
        
        # Уведомляем пользователя
        from bot.utils.cs2_data import format_elo_filter_display
        filter_text = format_elo_filter_display(selected_filter)
        
        await query.edit_message_text(
            f"✅ <b>Фильтр установлен!</b>\n\n"
            f"🎯 <b>Активный фильтр:</b> {filter_text}\n\n"
            f"Начинаем поиск...",
            parse_mode='HTML'
        )
        
        # Начинаем поиск с примененным фильтром
        await self.start_search(update, context)

    async def show_categories_filter_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню выбора фильтра категорий"""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        # Получаем текущие настройки пользователя
        user_settings = await self.db.get_user_settings(user_id)
        current_filter = []
        if user_settings:
            filters = user_settings.get_search_filters()
            current_filter = filters.get('categories_filter', [])
        
        # Сохраняем текущий фильтр в контекст
        context.user_data['selected_categories_filter'] = current_filter.copy()
        
        text = (
            "🎮 <b>Фильтр по категориям</b>\n\n"
            "Выберите категории для поиска игроков.\n"
            "Будут показаны только игроки с выбранными категориями:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.categories_filter_menu(current_filter),
            parse_mode='HTML'
        )

    async def handle_categories_filter_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает выбор фильтра категорий"""
        query = update.callback_query
        data = query.data
        await query.answer()
        
        selected_categories = context.user_data.get('selected_categories_filter', [])
        
        if data == "categories_filter_any":
            # Сбрасываем фильтр
            selected_categories = []
        else:
            # Извлекаем ID категории
            category_id = data.replace("categories_filter_", "")
            
            # Переключаем выбор категории
            if category_id in selected_categories:
                selected_categories.remove(category_id)
            else:
                selected_categories.append(category_id)
        
        context.user_data['selected_categories_filter'] = selected_categories
        
        # Обновляем меню с новым выделением
        await self.show_categories_filter_menu(update, context)

    async def apply_categories_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Применяет выбранный фильтр категорий и начинает поиск"""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        # Получаем выбранный фильтр
        selected_filter = context.user_data.get('selected_categories_filter', [])
        
        # Сохраняем фильтр в настройки пользователя
        await self._save_categories_filter(user_id, selected_filter)
        
        # Уведомляем пользователя
        if selected_filter:
            from bot.utils.cs2_data import format_categories_display
            filter_text = format_categories_display(selected_filter)
            text = f"✅ <b>Фильтр установлен!</b>\n\n🎮 <b>Категории:</b> {filter_text}\n\nНачинаем поиск..."
        else:
            text = "✅ <b>Фильтр сброшен!</b>\n\n🎮 <b>Категории:</b> Любые\n\nНачинаем поиск..."
        
        await query.edit_message_text(
            text,
            parse_mode='HTML'
        )
        
        # Начинаем поиск с примененным фильтром
        await self.start_search(update, context)

    async def _save_categories_filter(self, user_id: int, categories_filter: list):
        """Сохраняет фильтр категорий в настройки пользователя"""
        try:
            # Получаем текущие настройки
            user_settings = await self.db.get_user_settings(user_id)
            if user_settings:
                # Обновляем фильтр категорий
                current_filters = user_settings.get_search_filters()
                current_filters['categories_filter'] = categories_filter
                await self.db.update_user_settings(user_id, search_filters=current_filters)
            else:
                # Создаем новые настройки
                await self.db.update_user_settings(user_id, search_filters={'categories_filter': categories_filter})
            
            logger.info(f"Фильтр категорий '{categories_filter}' сохранен для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения фильтра категорий для {user_id}: {e}")

    async def _save_elo_filter(self, user_id: int, elo_filter: str):
        """Сохраняет ELO фильтр в настройки пользователя"""
        try:
            # Получаем текущие настройки
            user_settings = await self.db.get_user_settings(user_id)
            if user_settings:
                # Обновляем фильтр ELO
                current_filters = user_settings.get_search_filters()
                current_filters['elo_filter'] = elo_filter
                await self.db.update_user_settings(user_id, search_filters=current_filters)
            else:
                # Создаем новые настройки
                await self.db.update_user_settings(user_id, search_filters={'elo_filter': elo_filter})
            
            logger.info(f"ELO фильтр '{elo_filter}' сохранен для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения ELO фильтра для {user_id}: {e}")

    async def _invalidate_media(self, user_id: int, reason: str):
        """Помечает медиа профиля как недействительное, очищая file_id"""
        try:
            # Обновляем профиль, очищая медиа данные
            success = await self.db.update_profile(
                user_id, 
                media_type=None, 
                media_file_id=None
            )
            
            if success:
                logger.info(f"Медиа профиля {user_id} помечено как недействительное: {reason}")
                
                # Уведомляем пользователя об этом (опционально)
                try:
                    user = await self.db.get_user(user_id)
                    if user:
                        # Можно отправить уведомление пользователю о том, что медиа стало недоступным
                        # Пока просто логируем
                        logger.info(f"Пользователю {user_id} требуется обновить медиа в профиле")
                except Exception as notify_error:
                    logger.warning(f"Не удалось уведомить пользователя {user_id} о недействительном медиа: {notify_error}")
            else:
                logger.error(f"Не удалось обновить профиль {user_id} для очистки недействительного медиа")
                
        except Exception as e:
            logger.error(f"Ошибка инвалидации медиа для пользователя {user_id}: {e}", exc_info=True)
    
    async def _check_can_like(self, liker_id: int, target_id: int) -> bool:
        """Проверяет может ли пользователь поставить лайк согласно настройкам приватности цели"""
        try:
            # Получаем настройки приватности цели
            target_settings = await self.db.get_user_settings(target_id)
            if not target_settings or not target_settings.privacy_settings:
                return True  # По умолчанию разрешаем
            
            who_can_like = target_settings.privacy_settings.get('who_can_like', 'all')
            
            if who_can_like == 'all':
                return True
            
            # Получаем профили для проверки критериев
            liker_profile = await self.db.get_profile(liker_id)
            target_profile = await self.db.get_profile(target_id)
            
            if not liker_profile or not target_profile:
                return True  # Если профилей нет, разрешаем
            
            if who_can_like == 'compatible_elo':
                # Проверяем совместимость ELO (±300)
                elo_diff = abs(liker_profile.faceit_elo - target_profile.faceit_elo)
                return elo_diff <= 300
            
            elif who_can_like == 'common_maps':
                # Проверяем общие карты (минимум 2)
                liker_maps = set(liker_profile.favorite_maps)
                target_maps = set(target_profile.favorite_maps)
                common_maps = len(liker_maps & target_maps)
                return common_maps >= 2
            
            elif who_can_like == 'active_users':
                # Проверяем активность (заходил за неделю)
                # Получаем данные пользователя
                liker_user = await self.db.get_user(liker_id)
                if not liker_user:
                    return False
                
                # Проверяем что профиль обновлялся в последнюю неделю
                from datetime import datetime, timedelta
                week_ago = datetime.now() - timedelta(days=7)
                return liker_profile.updated_at > week_ago
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки возможности лайка {liker_id} -> {target_id}: {e}")
            return True  # По умолчанию разрешаем