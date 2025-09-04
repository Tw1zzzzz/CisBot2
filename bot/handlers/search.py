"""
Обработчики поиска тиммейтов
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.utils.cs2_data import format_elo_display, format_role_display, format_maps_list, calculate_profile_compatibility, extract_faceit_nickname, PLAYTIME_OPTIONS
from bot.database.operations import DatabaseManager

logger = logging.getLogger(__name__)

class SearchHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

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
        query = update.callback_query
        user_id = query.from_user.id
        
        # Проверяем профиль
        has_profile = await self.db.has_profile(user_id)
        if not has_profile:
            await query.answer("❌ Сначала создайте профиль!", show_alert=True)
            return
        
        await query.answer()
        
        # Получаем кандидатов
        candidates = await self.db.find_candidates(user_id, limit=20)
        
        if not candidates:
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
        
        await self.show_candidate(query, context)

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
        candidates = context.user_data.get('candidates', [])
        current_index = context.user_data.get('current_candidate_index', 0)
        
        if current_index >= len(candidates):
            # Кандидаты закончились
            text = (
                "✅ <b>Поиск завершен!</b>\n\n"
                "Вы просмотрели всех доступных игроков.\n"
                "Попробуйте поискать позже или расскажите о боте друзьям!"
            )
            
            if hasattr(query_or_update, 'edit_message_text'):
                await query_or_update.edit_message_text(
                    text,
                    reply_markup=Keyboards.back_button("back_to_main"),
                    parse_mode='HTML'
                )
            else:
                await query_or_update.message.reply_text(
                    text,
                    reply_markup=Keyboards.back_button("back_to_main"),
                    parse_mode='HTML'
                )
            return
        
        candidate = candidates[current_index]
        user_id = query_or_update.from_user.id if hasattr(query_or_update, 'from_user') else query_or_update.effective_user.id
        
        # Получаем профиль текущего пользователя для расчета совместимости
        user_profile = await self.db.get_profile(user_id)
        
        # Форматируем анкету
        text = await self.format_candidate_profile(candidate, user_profile, user_id)
        
        # Сохраняем текущего кандидата
        context.user_data['current_candidate'] = candidate
        
        # Определяем chat_id для отправки
        if hasattr(query_or_update, 'message') and query_or_update.message:
            chat_id = query_or_update.message.chat_id
        elif hasattr(query_or_update, 'effective_chat'):
            chat_id = query_or_update.effective_chat.id
        else:
            chat_id = query_or_update.from_user.id
        
        # Отправляем профиль с медиа если есть
        await self.send_candidate_with_media(
            chat_id=chat_id,
            candidate=candidate,
            text=text,
            reply_markup=Keyboards.like_buttons(),
            context=context,
            is_edit=hasattr(query_or_update, 'edit_message_text')
        )

    async def format_candidate_profile(self, candidate, user_profile=None, current_user_id=None):
        """Форматирует анкету кандидата"""
        # Проверяем есть ли взаимный лайк для отображения имени
        show_name = False
        if current_user_id:
            show_name = await self.db.check_mutual_like(current_user_id, candidate.user_id)
        
        # Всегда показываем игровой ник
        text = f"👤 <b>{candidate.game_nickname}</b>\n"
        
        if show_name:
            # Показываем Telegram данные при взаимном лайке
            user = await self.db.get_user(candidate.user_id)
            if user and user.first_name:
                telegram_info = user.first_name
                if user.username:
                    telegram_info += f" (@{user.username})"
                text += f"🔗 <b>Telegram:</b> {telegram_info}\n"
        
        text += "\n"
        text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(candidate.faceit_elo)}\n"
        
        # Faceit профиль
        nickname = extract_faceit_nickname(candidate.faceit_url)
        text += f"🔗 <b>Faceit:</b> <a href='{candidate.faceit_url}'>{nickname}</a>\n"
        
        text += f"👥 <b>Роль:</b> {format_role_display(candidate.role)}\n"
        text += f"🗺️ <b>Любимые карты:</b> {format_maps_list(candidate.favorite_maps, max_count=4)}\n"
        
        # Время игры
        time_displays = []
        for slot_id in candidate.playtime_slots:
            time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
            if time_option:
                time_displays.append(f"{time_option['emoji']} {time_option['name']}")
        
        if time_displays:
            text += f"⏰ <b>Время игры:</b>\n"
            for time_display in time_displays:
                text += f"   {time_display}\n"
        else:
            text += f"⏰ <b>Время игры:</b> Не указано\n"
        
        # Категории
        if hasattr(candidate, 'categories') and candidate.categories:
            from bot.utils.cs2_data import format_categories_display
            categories_text = format_categories_display(candidate.categories, max_count=2)
            text += f"🎮 <b>Категории:</b> {categories_text}\n"
        
        if candidate.description:
            text += f"\n💬 <b>О себе:</b>\n{candidate.description}\n"
        
        # Информация о медиа
        if candidate.has_media():
            media_icon = "📷" if candidate.is_photo() else "🎥"
            text += f"\n{media_icon} <b>Медиа:</b> прикреплено\n"
        
        # Совместимость (если есть профиль пользователя)
        if user_profile:
            compatibility = calculate_profile_compatibility(user_profile, candidate)
            compat_emoji = "🔥" if compatibility['total'] >= 80 else "⭐" if compatibility['total'] >= 60 else "👌" if compatibility['total'] >= 40 else "🤔"
            text += f"\n{compat_emoji} <b>Совместимость:</b> {compatibility['total']}%\n"
            
            details = compatibility['details']
            text += f"├ ELO: {details['elo']}%\n"
            text += f"├ Карты: {details['maps']}%\n"
            text += f"├ Время: {details['time']}%\n"
            text += f"└ Роль: {details['role']}%"
        
        return text

    async def send_candidate_with_media(self, chat_id: int, candidate, text: str, reply_markup=None, context=None, is_edit=False):
        """Отправляет профиль кандидата с медиа если есть"""
        try:
            if candidate.has_media() and not is_edit:
                # Отправляем новое сообщение с медиа
                if candidate.is_photo():
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=candidate.media_file_id,
                        caption=text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                elif candidate.is_video():
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=candidate.media_file_id,
                        caption=text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            else:
                # Отправляем только текст (или редактируем существующее сообщение)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки кандидата с медиа: {e}")
            # Фолбэк - отправляем только текст
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает лайк"""
        query = update.callback_query
        user_id = query.from_user.id
        
        current_candidate = context.user_data.get('current_candidate')
        if not current_candidate:
            await query.answer("❌ Ошибка: кандидат не найден", show_alert=True)
            return
        
        # Проверяем настройки приватности кандидата (who_can_like)
        can_like = await self._check_can_like(user_id, current_candidate.user_id)
        if not can_like:
            await query.answer("❌ Этот пользователь ограничил получение лайков", show_alert=True)
            # Переходим к следующему кандидату
            await self.next_candidate(query, context)
            return
        
        await query.answer("❤️ Лайк поставлен!")
        
        # Добавляем лайк в БД
        await self.db.add_like(user_id, current_candidate.user_id)
        
        # Проверяем взаимный лайк
        is_mutual = await self.db.check_mutual_like(user_id, current_candidate.user_id)
        
        if is_mutual:
            # Создаем связь с тиммейтом
            await self.db.create_match(user_id, current_candidate.user_id)
            
            # Уведомляем о тиммейте
            await query.answer("🎉 ЭТО ТИММЕЙТ! Взаимный лайк!", show_alert=True)
            
            match_text = (
                "🎉 <b>ПОЗДРАВЛЯЕМ! У ВАС ТИММЕЙТ!</b>\n\n"
                f"Вы понравились друг другу!\n"
                "Теперь вы можете начать общение.\n\n"
                "Найти контакты игрока можно в разделе 'Мои тиммейты'."
            )
            
            await query.edit_message_text(
                match_text,
                reply_markup=Keyboards.back_button("back_to_main"),
                parse_mode='HTML'
            )
            return
        
        # Переходим к следующему кандидату
        await self.next_candidate(query, context)

    async def handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает пропуск"""
        query = update.callback_query
        await query.answer("➡️ Пропущено")
        
        # Переходим к следующему кандидату
        await self.next_candidate(query, context)

    async def next_candidate(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Переход к следующему кандидату"""
        current_index = context.user_data.get('current_candidate_index', 0)
        context.user_data['current_candidate_index'] = current_index + 1
        
        await self.show_candidate(query, context)

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