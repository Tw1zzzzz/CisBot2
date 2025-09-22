"""
Обработчики команд /start и /help
"""
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.database.operations import DatabaseManager
from bot.utils.callback_security import (
    safe_parse_user_id, safe_parse_numeric_value, safe_parse_string_value, 
    sanitize_text_input, validate_callback_data
)
from bot.utils.enhanced_callback_security import validate_secure_callback, CallbackValidationResult

logger = logging.getLogger(__name__)

class StartHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - приветствие и главное меню"""
        user = update.effective_user
        
        # Создаем пользователя если не существует
        await self.db.create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        # Проверяем статус профиля пользователя
        has_any_profile = await self.db.has_profile(user.id)
        has_approved_profile = await self.db.has_approved_profile(user.id)
        
        if not has_any_profile:
            # У пользователя нет профиля - принудительно предлагаем создать
            welcome_text = (
                f"🎮 <b>Добро пожаловать в CIS FINDER, {user.first_name}!</b>\n\n"
                "🇷🇺 Найдите идеальных тиммейтов для Counter-Strike 2 в СНГ регионе!\n"
                "Создано проектом <b>Twizz_Project</b>\n\n"
                "📝 <b>Для использования бота необходимо создать игровой профиль.</b>\n"
                "Это поможет другим игрокам найти вас и наоборот!\n\n"
                "🌐 <b>Подписывайтесь на нас:</b>\n"
                "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                "Нажмите кнопку ниже, чтобы создать профиль:"
            )
            
            keyboard = Keyboards.create_profile_mandatory()
            await update.message.reply_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        elif has_any_profile and not has_approved_profile:
            # Есть профиль, но он не одобрен - показываем статус модерации
            profile = await self.db.get_profile(user.id)
            
            if profile and profile.moderation_status == 'pending':
                welcome_text = (
                    f"🎮 <b>Добро пожаловать обратно, {user.first_name}!</b>\n\n"
                    "⏳ <b>Ваш профиль на модерации</b>\n"
                    "Модераторы проверят вашу анкету в течение 24 часов.\n"
                    "После одобрения вы сможете пользоваться всеми функциями!\n\n"
                    "🇷🇺 Найдите идеальных тиммейтов для Counter-Strike 2 в СНГ регионе!\n"
                    "Создано проектом <b>Twizz_Project</b>\n\n"
                    "🌐 <b>Подписывайтесь на нас:</b>\n"
                    "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                    "Доступные действия:"
                )
            elif profile and profile.moderation_status == 'rejected':
                welcome_text = (
                    f"🎮 <b>Добро пожаловать обратно, {user.first_name}!</b>\n\n"
                    "❌ <b>Ваш профиль отклонен</b>\n"
                    "Вы можете отредактировать профиль и отправить на повторную модерацию.\n\n"
                    "🇷🇺 Найдите идеальных тиммейтов для Counter-Strike 2 в СНГ регионе!\n"
                    "Создано проектом <b>Twizz_Project</b>\n\n"
                    "🌐 <b>Подписывайтесь на нас:</b>\n"
                    "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                    "Выберите действие:"
                )
            else:
                # Неожиданный статус или ошибка загрузки
                welcome_text = (
                    f"🎮 <b>Добро пожаловать обратно, {user.first_name}!</b>\n\n"
                    "🇷🇺 Найдите идеальных тиммейтов для Counter-Strike 2 в СНГ регионе!\n"
                    "Создано проектом <b>Twizz_Project</b>\n\n"
                    "🌐 <b>Подписывайтесь на нас:</b>\n"
                    "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                    "Выберите действие:"
                )
            
            # Проверяем права модератора
            is_moderator = await self.db.is_moderator(user.id)
            keyboard = Keyboards.main_menu_with_moderation() if is_moderator else Keyboards.main_menu()
            
            await update.message.reply_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            # Показываем обычное главное меню
            welcome_text = (
                f"🎮 <b>Добро пожаловать в CIS FINDER, {user.first_name}!</b>\n\n"
                "🇷🇺 Найдите идеальных тиммейтов для Counter-Strike 2 в СНГ регионе!\n"
                "Создано проектом <b>Twizz_Project</b>\n\n"
                "<b>Что умеет бот:</b>\n"
                "• 👤 Профиль с ELO Faceit и ссылкой\n"
                "• 🔍 Умный поиск по ELO, роли и картам\n"
                "• ❤️ Система лайков и тиммейтов\n"
                "• 🤝 Поиск команды для турниров\n"
                "• ⏰ Гибкий выбор времени игры\n\n"
                "🌐 <b>Подписывайтесь на нас:</b>\n"
                "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                "Выберите действие из меню ниже:"
            )
            
            # Проверяем права модератора
            is_moderator = await self.db.is_moderator(user.id)
            keyboard = Keyboards.main_menu_with_moderation() if is_moderator else Keyboards.main_menu()
            
            await update.message.reply_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        
        logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка"""
        help_text = (
            "🆘 <b>Справка по CIS FINDER Bot</b>\n"
            "Создано проектом <b>Twizz_Project</b>\n\n"
            "🌐 <b>Подписывайтесь на нас:</b>\n"
            "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
            
            "<b>📋 Основные команды:</b>\n"
            "/start - Главное меню\n"
            "/profile - Управление профилем\n"
            "/search - Поиск тиммейтов\n"
            "/teammates - Просмотр тиммейтов\n"
            "/help - Эта справка\n\n"
            
            "<b>🎯 Как использовать:</b>\n"
            "1️⃣ Создайте профиль с ELO Faceit и ссылкой\n"
            "2️⃣ Выберите роль и любимые карты\n"
            "3️⃣ Укажите удобное время игры\n"
            "4️⃣ Ищите тиммейтов по совместимости\n"
            "5️⃣ Ставьте лайки и находите тиммейтов!\n\n"
            
            "<b>🎮 Система ELO Faceit:</b>\n"
            "От 1 ELO до 3000+ ELO\n"
            "Интеграция с профилем Faceit\n\n"
            
            "<b>👥 Роли в команде:</b>\n"
            "👑 IGL - Лидер команды\n"
            "⚡ Entry Fragger - Первый на вход\n"
            "🛡️ Support Player - Поддержка команды\n"
            "🥷 Lurker - Скрытный игрок\n"
            "🎯 AWPer - Снайпер команды\n\n"
            
            "<b>⏰ Время игры:</b>\n"
            "Можно выбрать несколько промежутков:\n"
            "🌅 Утром (6-12) / ☀️ Днем (12-18)\n"
            "🌆 Вечером (18-24) / 🌙 Ночью (0-6)\n\n"
            
            "<b>❓ Нужна помощь?</b>\n"
            "Обратитесь к администратору: @twizz_project"
        )
        
        await update.message.reply_text(
            help_text,
            reply_markup=Keyboards.back_button("back_to_main"),
            parse_mode='HTML'
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback запросы для навигации"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # DEBUG: логируем все входящие callbacks для диагностики
        logger.info(f"StartHandler received callback: {data} from user {user_id}")
        
        # Пытаемся валидировать как безопасный callback
        secure_validation = validate_secure_callback(data, user_id)
        if secure_validation.is_valid:
            await self._handle_secure_callback(query, secure_validation, context)
            return
        
        # Если не безопасный callback, используем старую логику для совместимости
        await self._handle_legacy_callback(query, data, user_id, context)
    
    async def _handle_secure_callback(self, query, validation: CallbackValidationResult, context):
        """Обработка безопасных callback'ов с CSRF токенами"""
        action = validation.action
        user_id = validation.user_id
        parsed_data = validation.parsed_data or {}
        
        logger.info(f"Processing secure callback: {action} for user {user_id}")
        
        try:
            if action == "back_to_main":
                await self.show_main_menu(query)
            elif action == "help":
                await self.show_help(query)
            elif action == "settings_menu":
                await self.show_settings_menu(query)
            elif action == "likes_history":
                await self.show_likes_history(query)
            elif action == "reply_like":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    await self.handle_like_response(query, target_user_id, "reply")
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            elif action == "skip_like":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    await self.handle_like_response(query, target_user_id, "skip")
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            elif action == "view_profile":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    await self.show_user_profile(query, target_user_id)
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            elif action == "unblock_user":
                target_user_id = parsed_data.get("target_user_id")
                if target_user_id:
                    # Получаем настройки приватности пользователя
                    user_settings = await self.db.get_user_settings(user_id)
                    privacy_settings = user_settings.privacy_settings if user_settings and user_settings.privacy_settings else {}
                    await self.handle_unblock_user(query, f"unblock_{target_user_id}", privacy_settings)
                else:
                    await query.answer("❌ Ошибка: не указан ID пользователя")
            else:
                logger.warning(f"Unknown secure callback action: {action}")
                await query.answer("❌ Неизвестная команда")
                
        except Exception as e:
            logger.error(f"Error handling secure callback {action}: {e}")
            await query.answer("❌ Произошла ошибка при обработке команды")
    
    async def _handle_legacy_callback(self, query, data, user_id, context):
        """Обработка legacy callback'ов для совместимости"""
        if data == "back_to_main":
            await self.show_main_menu(query)
        elif data == "help":
            await self.show_help(query)
        elif data == "settings_menu":
            await self.show_settings_menu(query)
        elif data.startswith("settings_"):
            await self.handle_settings_option(query, data)
        elif data == "settings_filters":
            await self.show_search_filters_menu(query)
        elif data == "settings_notifications":
            await self.show_notifications_menu(query)
        elif data.startswith("filter_elo_"):
            await self.handle_elo_filter_update(query, data)
        elif data == "filters_reset":  # ИСПРАВЛЕНИЕ: отдельная проверка для filters_reset
            logger.info(f"Processing filters_reset for user {user_id}")
            await self.reset_search_filters(query)
        elif data.startswith("filter_"):
            await self.handle_filter_option(query, data)
        elif data.startswith("set_") or data.startswith("toggle_") or data.startswith("clear_"):
            await self.handle_filter_update(query, data)
        elif data.startswith("notify_"):
            await self.handle_notification_update(query, data)
        elif data.startswith("privacy_") or data.startswith("visibility_") or data.startswith("unblock_") or data.startswith("confirm_privacy_") or data.startswith("cancel_privacy_"):
            await self.handle_privacy_option(query, data)
        elif data == "likes_history":
            await self.show_likes_history(query)
        elif data == "likes_new":
            await self.show_likes_list(query, new_only=True)
        elif data == "likes_all":
            await self.show_likes_list(query, new_only=False)
        elif data.startswith("likes_page_"):
            # Безопасный парсинг номера страницы
            page_result = safe_parse_numeric_value(data, "likes_page_", (0, 1000))
            if not page_result.is_valid:
                logger.error(f"Небезопасный callback_data в likes_page: {data} - {page_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            page = page_result.parsed_data['value']
            await self.show_likes_list(query, page=page)
        elif data.startswith("reply_like_"):
            # Безопасный парсинг user_id для лайка
            liker_id_result = safe_parse_user_id(data, "reply_like_")
            if not liker_id_result.is_valid:
                logger.error(f"Небезопасный callback_data в reply_like: {data} - {liker_id_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            liker_id = liker_id_result.parsed_data['user_id']
            await self.handle_like_response(query, liker_id, "reply")
        elif data.startswith("skip_like_"):
            # Безопасный парсинг user_id для пропуска лайка
            liker_id_result = safe_parse_user_id(data, "skip_like_")
            if not liker_id_result.is_valid:
                logger.error(f"Небезопасный callback_data в skip_like: {data} - {liker_id_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            liker_id = liker_id_result.parsed_data['user_id']
            await self.handle_like_response(query, liker_id, "skip")
        elif data.startswith("view_profile_"):
            # Безопасный парсинг user_id для просмотра профиля
            profile_user_id_result = safe_parse_user_id(data, "view_profile_")
            if not profile_user_id_result.is_valid:
                logger.error(f"Небезопасный callback_data в view_profile: {data} - {profile_user_id_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            profile_user_id = profile_user_id_result.parsed_data['user_id']
            logger.info(f"StartHandler: Processing view_profile_ callback for user {profile_user_id} from user {query.from_user.id}")
            await self.show_user_profile(query, profile_user_id)
    
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

    async def show_main_menu(self, query):
        """Показывает главное меню"""
        await query.answer()
        
        user_id = query.from_user.id
        
        # Прогреваем сеть пользователя для быстрой загрузки ELO данных
        await self._warm_user_network(user_id)
        
        # Проверяем статус профиля пользователя
        has_any_profile = await self.db.has_profile(user_id)
        has_approved_profile = await self.db.has_approved_profile(user_id)
        
        # Если есть профиль, но он не одобрен - показываем статус модерации
        if has_any_profile and not has_approved_profile:
            profile = await self.db.get_profile(user_id)
            if profile:
                if profile.moderation_status == 'pending':
                    menu_text = (
                        "🎮 <b>CIS FINDER - Главное меню</b>\n"
                        "Создано проектом <b>Twizz_Project</b>\n\n"
                        "⏳ <b>Ваш профиль на модерации</b>\n"
                        "Модераторы проверят вашу анкету в течение 24 часов.\n"
                        "После одобрения вы сможете пользоваться всеми функциями!\n\n"
                        "🌐 <b>Подписывайтесь на нас:</b>\n"
                        "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                        "Доступные действия:"
                    )
                elif profile.moderation_status == 'rejected':
                    menu_text = (
                        "🎮 <b>CIS FINDER - Главное меню</b>\n"
                        "Создано проектом <b>Twizz_Project</b>\n\n"
                        "❌ <b>Ваш профиль отклонен</b>\n"
                        "Вы можете отредактировать профиль и отправить на повторную модерацию.\n\n"
                        "🌐 <b>Подписывайтесь на нас:</b>\n"
                        "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                        "Выберите действие:"
                    )
                else:
                    # Неожиданный статус
                    menu_text = (
                        "🎮 <b>CIS FINDER - Главное меню</b>\n"
                        "Создано проектом <b>Twizz_Project</b>\n\n"
                        "🌐 <b>Подписывайтесь на нас:</b>\n"
                        "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                        "Выберите действие:"
                    )
            else:
                # Профиль есть в проверке has_profile, но не загружается - ошибка БД
                menu_text = (
                    "🎮 <b>CIS FINDER - Главное меню</b>\n"
                    "Создано проектом <b>Twizz_Project</b>\n\n"
                    "❌ <b>Ошибка загрузки профиля</b>\n"
                    "Обратитесь в поддержку: @twizz_project\n\n"
                    "🌐 <b>Подписывайтесь на нас:</b>\n"
                    "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                    "Выберите действие:"
                )
        else:
            # Обычное меню для пользователей с одобренным профилем или без профиля
            menu_text = (
                "🎮 <b>CIS FINDER - Главное меню</b>\n"
                "Создано проектом <b>Twizz_Project</b>\n\n"
                "🌐 <b>Подписывайтесь на нас:</b>\n"
                "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
                "Выберите действие:"
            )
        
        # Проверяем права модератора
        is_moderator = await self.db.is_moderator(user_id)
        
        keyboard = Keyboards.main_menu_with_moderation() if is_moderator else Keyboards.main_menu()
        
        # Безопасно редактируем сообщение (может быть медиа)
        await self.safe_edit_or_send_message(
            query,
            menu_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    async def show_help(self, query):
        """Показывает справку из callback"""
        await query.answer()
        
        help_text = (
            "🆘 <b>Справка по боту</b>\n\n"
            "🌐 <b>Подписывайтесь на нас:</b>\n"
            "• <a href='https://vk.com/cisfinder'>VK CIS FINDER</a> | <a href='https://t.me/cisfinder'>TG CIS FINDER</a> | <a href='https://t.me/tw1zzV'>Twizz_Project</a>\n\n"
            "<b>Как пользоваться:</b>\n"
            "1. Создайте профиль с вашими данными\n"
            "2. Укажите ранг, роль и любимые карты\n"
            "3. Начните поиск тиммейтов\n"
            "4. Ставьте лайки игрокам\n"
            "5. При взаимном лайке - у вас тиммейт!\n\n"
            "<b>Удачных игр!</b> 🚀"
        )
        
        # Безопасно редактируем сообщение (может быть медиа)
        await self.safe_edit_or_send_message(
            query,
            help_text,
            reply_markup=Keyboards.back_button("back_to_main"),
            parse_mode='HTML'
        )

    async def show_settings_menu(self, query):
        """Показывает меню настроек"""
        await query.answer()
        
        settings_text = (
            "⚙️ <b>Настройки бота</b>\n\n"
            "Выберите, что хотите настроить:"
        )
        
        await query.edit_message_text(
            settings_text,
            reply_markup=Keyboards.settings_menu(),
            parse_mode='HTML'
        )

    async def handle_settings_option(self, query, data):
        """Обработка опций настроек"""
        await query.answer()
        
        option_name = data.replace("settings_", "")
        
        # Заглушки для настроек (пока в разработке)
        if option_name == "filters":
            await self.show_search_filters_menu(query)
            return
            
        # Специальная обработка для уведомлений
        if option_name == "notifications":
            await self.show_notifications_menu(query)
            return
            
        # Специальная обработка для приватности
        if option_name == "privacy":
            await self.show_privacy_menu(query)
            return
            
        # Заглушки для остальных настроек
        settings_info = {}
        
        if option_name in settings_info:
            info = settings_info[option_name]
            text = (
                f"{info['title']}\n\n"
                f"{info['text']}\n\n"
                "<i>🚧 Функция в разработке...</i>"
            )
        else:
            text = "❓ Неизвестная настройка"
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.back_button("settings_menu"),
            parse_mode='HTML'
        )
    
    # === ФИЛЬТРЫ ПОИСКА ===
    
    async def show_search_filters_menu(self, query):
        """Показывает меню настройки фильтров поиска"""
        user_id = query.from_user.id
        
        # Получаем текущие настройки
        settings = await self.db.get_user_settings(user_id)
        if not settings:
            # Создаем настройки по умолчанию
            await self.db.update_user_settings(user_id)
            settings = await self.db.get_user_settings(user_id)
        
        filters = settings.get_search_filters()
        
        # Формируем текст с текущими настройками
        text = (
            "🎯 <b>Фильтры поиска</b>\n\n"
            "Настройте параметры поиска для лучших результатов:\n\n"
        )
        
        # Добавляем текущие настройки
        from bot.utils.cs2_data import format_elo_filter_display
        elo_text = format_elo_filter_display(filters['elo_filter'])
        text += f"🎯 <b>ELO диапазон:</b> {elo_text}\n"
        
        roles_count = len(filters.get('preferred_roles', []))
        if roles_count == 0:
            text += "👥 <b>Предпочтения по ролям:</b> Любые роли\n"
        else:
            text += f"👥 <b>Предпочтения по ролям:</b> {roles_count} выбрано\n"
        
        maps_labels = {
            'any': '🌍 Любые карты',
            'soft': '🎯 Мин. 1 общая',
            'moderate': '🎯 Мин. 2 общие',
            'strict': '🗺️ Только общие'
        }
        unknown_text = "Неизвестно"
        text += f"🗺️ <b>Совместимость карт:</b> {maps_labels.get(filters['maps_compatibility'], unknown_text)}\n"
        
        time_labels = {
            'any': '🌍 Любое время',
            'soft': '🕐 Мин. 1 общий слот',
            'strict': '⏰ Только общее время'
        }
        text += f"⏰ <b>Совместимость времени:</b> {time_labels.get(filters['time_compatibility'], unknown_text)}\n"
        
        text += f"📊 <b>Мин. совместимость:</b> {filters['min_compatibility']}%\n"
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.filters_settings_menu(filters),
            parse_mode='HTML'
        )
    
    async def handle_filter_option(self, query, data):
        """Обработка опций настройки фильтров"""
        await query.answer()
        
        if data == "filter_elo":
            await self.show_elo_filter_options(query)
        elif data == "filter_roles":
            await self.show_roles_filter_options(query)
        elif data == "filter_maps":
            await self.show_maps_filter_options(query)
        elif data == "filter_time":
            await self.show_time_filter_options(query)
        elif data == "filter_compatibility":
            await self.show_compatibility_filter_options(query)
        elif data == "filters_reset":
            await self.reset_search_filters(query)
        else:
            await self.show_search_filters_menu(query)
            
    async def show_elo_filter_options(self, query):
        """Показывает опции фильтра ELO с новыми диапазонами"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        current_filter = settings.get_search_filters()['elo_filter'] if settings else 'any'
        
        text = (
            "🎯 <b>Настройка ELO диапазона</b>\n\n"
            "Выберите диапазон ELO для поиска:\n\n"
            "🔰 <b>До 1999 ELO</b>\n"
            "⭐ <b>2000-2699 ELO</b>\n"
            "🏆 <b>2700-3099 ELO</b>\n"
            "💎 <b>3100+ ELO</b>\n"
            "👑 <b>TOP 1000</b>"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.filter_elo_settings_menu(current_filter),
            parse_mode='HTML'
        )
    
    async def show_roles_filter_options(self, query):
        """Показывает опции фильтра ролей"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        preferred_roles = settings.get_search_filters()['preferred_roles'] if settings else []
        
        text = (
            "👥 <b>Настройка предпочтений по ролям</b>\n\n"
            f"Выбрано: {len(preferred_roles)} ролей\n\n"
            "Нажмите на роли, которые вы предпочитаете в команде:"
        )
        
        from bot.utils.cs2_data import CS2_ROLES
        
        keyboard = []
        for role in CS2_ROLES:
            is_selected = role['name'] in preferred_roles
            prefix = '✅ ' if is_selected else ''
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{role['emoji']} {role['name']}",
                callback_data=f"toggle_role_{role['name']}"
            )])
        
        # Кнопки управления
        control_buttons = []
        if preferred_roles:
            control_buttons.append(InlineKeyboardButton("🗑️ Очистить", callback_data="clear_roles"))
        
        control_buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="settings_filters"))
        keyboard.append(control_buttons)
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def show_maps_filter_options(self, query):
        """Показывает опции фильтра карт"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        current_filter = settings.get_search_filters()['maps_compatibility'] if settings else 'any'
        
        text = (
            "🗺️ <b>Настройка совместимости карт</b>\n\n"
            "Как строго учитывать любимые карты:"
        )
        
        options = [
            ('any', '🌍 Любые карты', 'Не учитывать карты'),
            ('soft', '🎯 Мин. 1 общая', 'Минимум 1 общая карта'),
            ('moderate', '🎯 Мин. 2 общие', 'Минимум 2 общие карты'),
            ('strict', '🗺️ Только общие', 'Только с общими картами')
        ]
        
        keyboard = []
        for value, label, desc in options:
            prefix = '✅ ' if current_filter == value else ''
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{label}", 
                callback_data=f"set_maps_filter_{value}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_filters")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def show_time_filter_options(self, query):
        """Показывает опции фильтра времени"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        current_filter = settings.get_search_filters()['time_compatibility'] if settings else 'any'
        
        text = (
            "⏰ <b>Настройка совместимости времени</b>\n\n"
            "Как строго учитывать время игры:"
        )
        
        options = [
            ('any', '🌍 Любое время', 'Не учитывать время'),
            ('soft', '🕐 Мин. 1 общий слот', 'Минимум 1 общий слот'),
            ('strict', '⏰ Только общее', 'Только с общим временем')
        ]
        
        keyboard = []
        for value, label, desc in options:
            prefix = '✅ ' if current_filter == value else ''
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{label}", 
                callback_data=f"set_time_filter_{value}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_filters")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def show_compatibility_filter_options(self, query):
        """Показывает опции минимальной совместимости"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        current_threshold = settings.get_search_filters()['min_compatibility'] if settings else 30
        
        text = (
            "📊 <b>Настройка минимальной совместимости</b>\n\n"
            f"Текущий порог: {current_threshold}%\n\n"
            "Выберите минимальный процент совместимости:"
        )
        
        thresholds = [0, 30, 50, 70, 90]
        
        keyboard = []
        for threshold in thresholds:
            if threshold == 0:
                label = "🌍 Любая (0%)"
                desc = "Показывать всех игроков"
            elif threshold == 30:
                label = "📉 Низкая (30%)"
                desc = "По умолчанию"
            elif threshold == 50:
                label = "⚖️ Средняя (50%)"
                desc = "Умеренный отбор"
            elif threshold == 70:
                label = "🔥 Высокая (70%)"
                desc = "Строгий отбор"
            else:
                label = "🏆 Очень высокая (90%)"
                desc = "Только идеальные тиммейты"
            
            prefix = '✅ ' if current_threshold == threshold else ''
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{label}",
                callback_data=f"set_compatibility_{threshold}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_filters")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def reset_search_filters(self, query):
        """Сбрасывает все фильтры поиска"""
        user_id = query.from_user.id
        
        logger.info(f"🔄 Resetting filters for user {user_id}")
        
        try:
            # Сбрасываем фильтры
            default_filters = {
                'elo_filter': 'any',
                'preferred_roles': [],
                'maps_compatibility': 'any',
                'time_compatibility': 'any',
                'min_compatibility': 30,
                'max_candidates': 20
            }
            
            logger.info(f"🔄 Default filters: {default_filters}")
            
            # Обновляем настройки пользователя
            success = await self.db.update_user_settings(user_id, search_filters=default_filters)
            
            if success:
                logger.info(f"✅ Filters reset successfully for user {user_id}")
                await query.answer("✅ Фильтры сброшены!", show_alert=True)
                await self.show_search_filters_menu(query)
            else:
                logger.error(f"❌ Failed to reset filters for user {user_id}")
                await query.answer("❌ Ошибка при сбросе фильтров", show_alert=True)
                
        except Exception as e:
            logger.error(f"❌ Exception in reset_search_filters for user {user_id}: {e}", exc_info=True)
            await query.answer("❌ Произошла ошибка", show_alert=True)
    
    async def handle_elo_filter_update(self, query, data):
        """Обработка обновления ELO фильтров (новая система диапазонов)"""
        await query.answer()
        user_id = query.from_user.id
        
        # Извлекаем ID фильтра из callback data
        filter_id = data.replace("filter_elo_", "")
        
        # Получаем текущие настройки
        settings = await self.db.get_user_settings(user_id)
        if settings:
            filters = settings.get_search_filters()
            filters['elo_filter'] = filter_id
            await self.db.update_user_settings(user_id, search_filters=filters)
        else:
            # Создаем новые настройки
            await self.db.update_user_settings(user_id, search_filters={'elo_filter': filter_id})
        
        # Уведомляем пользователя
        from bot.utils.cs2_data import format_elo_filter_display
        filter_text = format_elo_filter_display(filter_id)
        await query.answer(f"✅ ELO фильтр: {filter_text}")
        
        # Возвращаемся к общему меню фильтров
        await self.show_search_filters_menu(query)

    async def handle_filter_update(self, query, data):
        """Обработка обновления фильтров"""
        await query.answer()
        user_id = query.from_user.id
        
        if data.startswith("toggle_role_"):
            # Безопасный парсинг имени роли
            role_result = safe_parse_string_value(data, "toggle_role_")
            if not role_result.is_valid:
                logger.error(f"Небезопасный callback_data в toggle_role: {data} - {role_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            role_name = role_result.parsed_data['value']
            settings = await self.db.get_user_settings(user_id)
            filters = settings.get_search_filters() if settings else {}
            preferred_roles = filters.get('preferred_roles', [])
            
            if role_name in preferred_roles:
                preferred_roles.remove(role_name)
            else:
                preferred_roles.append(role_name)
            
            filters['preferred_roles'] = preferred_roles
            await self.db.update_user_settings(user_id, search_filters=filters)
            await self.show_roles_filter_options(query)
            
        elif data == "clear_roles":
            # Очищаем роли
            settings = await self.db.get_user_settings(user_id)
            filters = settings.get_search_filters() if settings else {}
            filters['preferred_roles'] = []
            await self.db.update_user_settings(user_id, search_filters=filters)
            await self.show_roles_filter_options(query)
            
        elif data.startswith("set_maps_filter_"):
            # Безопасный парсинг значения фильтра карт
            value_result = safe_parse_string_value(data, "set_maps_filter_")
            if not value_result.is_valid:
                logger.error(f"Небезопасный callback_data в set_maps_filter: {data} - {value_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            value = value_result.parsed_data['value']
            settings = await self.db.get_user_settings(user_id)
            filters = settings.get_search_filters() if settings else {}
            filters['maps_compatibility'] = value
            await self.db.update_user_settings(user_id, search_filters=filters)
            await self.show_search_filters_menu(query)
            
        elif data.startswith("set_time_filter_"):
            # Безопасный парсинг значения фильтра времени
            value_result = safe_parse_string_value(data, "set_time_filter_")
            if not value_result.is_valid:
                logger.error(f"Небезопасный callback_data в set_time_filter: {data} - {value_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            value = value_result.parsed_data['value']
            settings = await self.db.get_user_settings(user_id)
            filters = settings.get_search_filters() if settings else {}
            filters['time_compatibility'] = value
            await self.db.update_user_settings(user_id, search_filters=filters)
            await self.show_search_filters_menu(query)
            
        elif data.startswith("set_compatibility_"):
            # Безопасный парсинг значения совместимости
            value_result = safe_parse_numeric_value(data, "set_compatibility_", (0, 100))
            if not value_result.is_valid:
                logger.error(f"Небезопасный callback_data в set_compatibility: {data} - {value_result.error_message}")
                await query.answer("❌ Ошибка валидации данных")
                return
            
            value = value_result.parsed_data['value']
            settings = await self.db.get_user_settings(user_id)
            filters = settings.get_search_filters() if settings else {}
            filters['min_compatibility'] = value
            await self.db.update_user_settings(user_id, search_filters=filters)
            await self.show_search_filters_menu(query)
        
        else:
            # Незнакомая операция
            await self.show_search_filters_menu(query)
    
    # === УВЕДОМЛЕНИЯ ===
    
    async def show_notifications_menu(self, query):
        """Показывает меню настроек уведомлений"""
        user_id = query.from_user.id
        
        # Получаем текущие настройки
        settings = await self.db.get_user_settings(user_id)
        if not settings:
            # Создаем настройки по умолчанию
            await self.db.update_user_settings(user_id)
            settings = await self.db.get_user_settings(user_id)
        
        notifications = settings.get_notification_settings()
        
        # Формируем текст с текущими настройками
        text = (
            "🔔 <b>Настройки уведомлений</b>\n\n"
            "Выберите, какие уведомления хотите получать:\n\n"
        )
        
        # Критически важные
        text += "<b>📢 Важные уведомления:</b>\n"
        match_status = "✅" if notifications['new_match'] else "❌"
        like_status = "✅" if notifications['new_like'] else "❌"
        text += f"{match_status} Новые тиммейты\n"
        text += f"{like_status} Новые лайки\n\n"
        
        # Дополнительные
        text += "<b>📊 Дополнительные:</b>\n"
        candidates_status = "✅" if notifications['new_candidates'] else "❌"
        stats_status = "✅" if notifications['weekly_stats'] else "❌"
        text += f"{candidates_status} Новые кандидаты\n"
        text += f"{stats_status} Еженедельная статистика\n\n"
        
        # Опциональные
        text += "<b>💡 Опциональные:</b>\n"
        tips_status = "✅" if notifications['profile_tips'] else "❌"
        reminders_status = "✅" if notifications['return_reminders'] else "❌"
        text += f"{tips_status} Советы по профилю\n"
        text += f"{reminders_status} Напоминания о возвращении\n\n"
        
        # Тихие часы
        quiet_status = "✅" if notifications['quiet_hours_enabled'] else "❌"
        if notifications['quiet_hours_enabled']:
            text += f"{quiet_status} Тихие часы: {notifications['quiet_hours_start']}:00 - {notifications['quiet_hours_end']}:00"
        else:
            text += f"{quiet_status} Тихие часы отключены"
        
        # Клавиатура с настройками
        keyboard = [
            [InlineKeyboardButton("🎉 Новые тиммейты", callback_data="notify_toggle_new_match")],
            [InlineKeyboardButton("❤️ Новые лайки", callback_data="notify_toggle_new_like")],
            [InlineKeyboardButton("🔍 Новые кандидаты", callback_data="notify_toggle_new_candidates")],
            [InlineKeyboardButton("📊 Еженедельная статистика", callback_data="notify_toggle_weekly_stats")],
            [InlineKeyboardButton("💡 Советы по профилю", callback_data="notify_toggle_profile_tips")],
            [InlineKeyboardButton("🎮 Напоминания о возвращении", callback_data="notify_toggle_return_reminders")],
            [InlineKeyboardButton("😴 Настроить тихие часы", callback_data="notify_quiet_hours")],
            [
                InlineKeyboardButton("🔄 Все вкл", callback_data="notify_enable_all"),
                InlineKeyboardButton("❌ Все выкл", callback_data="notify_disable_all")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="settings_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def show_quiet_hours_menu(self, query):
        """Показывает меню настройки тихих часов"""
        user_id = query.from_user.id
        settings = await self.db.get_user_settings(user_id)
        notifications = settings.get_notification_settings()
        
        enabled = notifications['quiet_hours_enabled']
        start_hour = notifications['quiet_hours_start']
        end_hour = notifications['quiet_hours_end']
        
        text = (
            "😴 <b>Тихие часы</b>\n\n"
            "В это время уведомления приходить не будут\n\n"
        )
        
        if enabled:
            text += f"<b>Статус:</b> ✅ Включены\n"
            text += f"<b>Время:</b> с {start_hour}:00 до {end_hour}:00\n\n"
            text += "Настройте время тихих часов:"
        else:
            text += "<b>Статус:</b> ❌ Отключены\n\n"
            text += "Включите тихие часы для спокойного сна:"
        
        # Кнопки времени (популярные варианты)
        keyboard = []
        
        if enabled:
            keyboard.append([InlineKeyboardButton("❌ Отключить тихие часы", callback_data="notify_quiet_disable")])
        else:
            keyboard.append([InlineKeyboardButton("✅ Включить тихие часы", callback_data="notify_quiet_enable")])
        
        # Предустановленные варианты времени
        time_options = [
            ("🌙 23:00 - 8:00 (стандарт)", "notify_quiet_set_23_8"),
            ("😴 22:00 - 9:00 (ранний сон)", "notify_quiet_set_22_9"),
            ("🦉 1:00 - 10:00 (сова)", "notify_quiet_set_1_10"),
            ("📱 Только ночью (0:00 - 6:00)", "notify_quiet_set_0_6")
        ]
        
        for label, callback in time_options:
            current = (start_hour == int(callback.split('_')[-2]) and 
                      end_hour == int(callback.split('_')[-1]))
            prefix = "✅ " if enabled and current else ""
            keyboard.append([InlineKeyboardButton(f"{prefix}{label}", callback_data=callback)])
        
        keyboard.append([InlineKeyboardButton("🔙 К уведомлениям", callback_data="settings_notifications")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def handle_notification_update(self, query, data):
        """Обработка обновления настроек уведомлений"""
        await query.answer()
        user_id = query.from_user.id
        
        if data.startswith("notify_toggle_"):
            # Переключение отдельного уведомления
            notification_type = data.replace("notify_toggle_", "")
            settings = await self.db.get_user_settings(user_id)
            if not settings:
                await self.db.update_user_settings(user_id)
                settings = await self.db.get_user_settings(user_id)
                
            notifications = settings.get_notification_settings()
            
            # Переключаем значение
            current_value = notifications.get(notification_type, False)
            new_value = not current_value
            
            # Специальная логика для критически важных уведомлений
            if notification_type in ['new_match', 'new_like'] and new_value:
                # Если включаем важные уведомления, включаем общий переключатель
                settings.notifications_enabled = True
            
            # Сохраняем изменение через правильный метод
            settings.update_notification_settings(**{notification_type: new_value})
            await self.db.update_user_settings(
                user_id, 
                notifications_enabled=settings.notifications_enabled,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            
            # Показываем обновленное меню
            await self.show_notifications_menu(query)
            
        elif data == "notify_enable_all":
            # Включить все уведомления
            settings = await self.db.get_user_settings(user_id)
            if not settings:
                await self.db.update_user_settings(user_id)
                settings = await self.db.get_user_settings(user_id)
            
            # Проверяем, нужно ли что-то менять
            current_notifications = settings.get_notification_settings()
            if settings.notifications_enabled and all([
                current_notifications.get('new_match', False),
                current_notifications.get('new_like', False),
                current_notifications.get('new_candidates', False),
                current_notifications.get('weekly_stats', False),
                current_notifications.get('profile_tips', False),
                current_notifications.get('return_reminders', False)
            ]):
                # Уже все включено
                await query.answer("✅ Все уведомления уже включены!", show_alert=True)
                return
            
            # Включаем все
            all_on = {
                'new_match': True,
                'new_like': True,
                'new_candidates': True,
                'weekly_stats': True,
                'profile_tips': True,
                'return_reminders': True
            }
            settings.update_notification_settings(**all_on)
            await self.db.update_user_settings(
                user_id,
                notifications_enabled=True,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            await query.answer("✅ Все уведомления включены!", show_alert=True)
            await self.show_notifications_menu(query)
            
        elif data == "notify_disable_all":
            # Отключить все уведомления
            settings = await self.db.get_user_settings(user_id)
            if not settings:
                await self.db.update_user_settings(user_id)
                settings = await self.db.get_user_settings(user_id)
            
            # Проверяем, нужно ли что-то менять
            current_notifications = settings.get_notification_settings()
            if not settings.notifications_enabled and not any([
                current_notifications.get('new_match', False),
                current_notifications.get('new_like', False),
                current_notifications.get('new_candidates', False),
                current_notifications.get('weekly_stats', False),
                current_notifications.get('profile_tips', False),
                current_notifications.get('return_reminders', False)
            ]):
                # Уже все выключено
                await query.answer("❌ Все уведомления уже отключены!", show_alert=True)
                return
            
            # Выключаем все
            settings.update_notification_settings(
                new_match=False,
                new_like=False,
                new_candidates=False,
                weekly_stats=False,
                profile_tips=False,
                return_reminders=False
            )
            await self.db.update_user_settings(
                user_id, 
                notifications_enabled=False,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            await query.answer("❌ Все уведомления отключены!", show_alert=True)
            await self.show_notifications_menu(query)
            
        elif data == "notify_quiet_hours":
            # Перейти к настройке тихих часов
            await self.show_quiet_hours_menu(query)
            
        elif data == "notify_quiet_enable":
            # Включить тихие часы
            # Включить тихие часы
            settings = await self.db.get_user_settings(user_id)
            settings.update_notification_settings(quiet_hours_enabled=True)
            await self.db.update_user_settings(
                user_id,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            await self.show_quiet_hours_menu(query)
            
        elif data == "notify_quiet_disable":
            # Отключить тихие часы
            # Отключить тихие часы
            settings = await self.db.get_user_settings(user_id)
            settings.update_notification_settings(quiet_hours_enabled=False)
            await self.db.update_user_settings(
                user_id,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            await self.show_quiet_hours_menu(query)
            
        elif data.startswith("notify_quiet_set_"):
            # Установить время тихих часов
            parts = data.replace("notify_quiet_set_", "").split("_")
            start_hour = int(parts[0])
            end_hour = int(parts[1])
            
            # Установить время тихих часов
            settings = await self.db.get_user_settings(user_id)
            settings.update_notification_settings(
                quiet_hours_enabled=True,
                quiet_hours_start=start_hour,
                quiet_hours_end=end_hour
            )
            await self.db.update_user_settings(
                user_id,
                privacy_settings=json.dumps(settings.privacy_settings)
            )
            await query.answer(f"⏰ Тихие часы: {start_hour}:00 - {end_hour}:00", show_alert=True)
            await self.show_quiet_hours_menu(query)
            
        else:
            # Неизвестная операция
            await self.show_notifications_menu(query)

    # === НАСТРОЙКИ ПРИВАТНОСТИ ===

    async def show_privacy_menu(self, query):
        """Показывает главное меню настроек приватности"""
        try:
            user_id = query.from_user.id
            
            # Получаем настройки пользователя
            user_settings = await self.db.get_user_settings(user_id)
            if user_settings and user_settings.privacy_settings:
                privacy_settings = user_settings.privacy_settings
            else:
                # Настройки по умолчанию
                privacy_settings = {
                    'profile_visibility': 'all',
                    'who_can_like': 'all',
                    'show_elo': True,
                    'show_stats': True,
                    'show_matches_count': True,
                    'show_activity': True,
                    'show_faceit_url': True,
                    'blocked_users': [],
                    'block_reasons': {},
                    'block_expiry': {}
                }
            
            text = (
                "🔒 <b>Настройки приватности</b>\n\n"
                "Управляйте видимостью вашего профиля и данных:"
            )
            
            await query.edit_message_text(
                text,
                reply_markup=Keyboards.privacy_main_menu(privacy_settings),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа меню приватности: {e}")
            await query.answer("❌ Ошибка загрузки настроек приватности")

    async def handle_privacy_option(self, query, data):
        """Обработка опций настроек приватности"""
        try:
            await query.answer()
            user_id = query.from_user.id
            
            # Получаем текущие настройки
            user_settings = await self.db.get_user_settings(user_id)
            if user_settings and user_settings.privacy_settings:
                privacy_settings = user_settings.privacy_settings
            else:
                privacy_settings = {
                    'profile_visibility': 'all',
                    'who_can_like': 'all',
                    'show_elo': True,
                    'show_stats': True,
                    'show_matches_count': True,
                    'show_activity': True,
                    'show_faceit_url': True,
                    'blocked_users': [],
                    'block_reasons': {},
                    'block_expiry': {}
                }
            
            if data == "privacy_visibility":
                await self.show_privacy_visibility_menu(query, privacy_settings)
            elif data == "privacy_likes":
                await self.show_privacy_likes_menu(query, privacy_settings)
            elif data == "privacy_display":
                await self.show_privacy_display_menu(query, privacy_settings)
            elif data == "privacy_blocking":
                await self.show_privacy_blocking_menu(query, privacy_settings)
            elif data == "privacy_menu":
                await self.show_privacy_menu(query)
            elif data.startswith("visibility_"):
                await self.handle_visibility_change(query, data, privacy_settings)
            elif data.startswith("likes_"):
                await self.handle_likes_change(query, data, privacy_settings)
            elif data.startswith("toggle_"):
                await self.handle_display_toggle(query, data, privacy_settings)
            elif data.startswith("unblock_"):
                await self.handle_unblock_user(query, data, privacy_settings)
            elif data.startswith("confirm_privacy_"):
                await self.handle_privacy_confirmation(query, data, privacy_settings)
            elif data.startswith("cancel_privacy_"):
                await self.handle_privacy_cancellation(query, data)
            else:
                await self.show_privacy_menu(query)
                
        except Exception as e:
            logger.error(f"Ошибка обработки опции приватности {data}: {e}")
            await query.answer("❌ Ошибка обработки настройки")

    async def show_privacy_visibility_menu(self, query, privacy_settings):
        """Показывает меню настройки видимости профиля"""
        current_visibility = privacy_settings.get('profile_visibility', 'all')
        
        descriptions = {
            'all': 'Ваш профиль будет виден всем пользователям в поиске',
            'matches_only': 'Ваш профиль увидят только те, с кем у вас взаимные лайки',
            'hidden': 'Ваш профиль будет полностью скрыт из поиска'
        }
        
        current_desc = descriptions.get(current_visibility, descriptions['all'])
        
        text = (
            "👁️ <b>Видимость профиля</b>\n\n"
            f"<i>Текущая настройка:</i> {current_desc}\n\n"
            "Выберите новую настройку:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.privacy_visibility_menu(current_visibility),
            parse_mode='HTML'
        )

    async def show_privacy_likes_menu(self, query, privacy_settings):
        """Показывает меню настройки лайков"""
        current_likes = privacy_settings.get('who_can_like', 'all')
        
        descriptions = {
            'all': 'Любой пользователь может отправить вам лайк',
            'compatible_elo': 'Только игроки с совместимым ELO (±2 уровня)',
            'common_maps': 'Только игроки с общими картами (минимум 2)',
            'active_users': 'Только активные игроки (заходили за неделю)'
        }
        
        current_desc = descriptions.get(current_likes, descriptions['all'])
        
        text = (
            "💌 <b>Кто может отправлять лайки</b>\n\n"
            f"<i>Текущая настройка:</i> {current_desc}\n\n"
            "Выберите новую настройку:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.privacy_likes_menu(current_likes),
            parse_mode='HTML'
        )

    async def show_privacy_display_menu(self, query, privacy_settings):
        """Показывает меню настройки отображения данных"""
        text = (
            "📊 <b>Отображение данных</b>\n\n"
            "Выберите, какую информацию показывать в вашем профиле:\n\n"
            "• <i>Скрытые данные не увидят другие пользователи</i>\n"
            "• <i>Это не влияет на алгоритм поиска</i>"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.privacy_display_menu(privacy_settings),
            parse_mode='HTML'
        )

    async def show_privacy_blocking_menu(self, query, privacy_settings):
        """Показывает меню управления блокировкой"""
        blocked_users = privacy_settings.get('blocked_users', [])
        
        if blocked_users:
            # Получаем информацию о заблокированных пользователях
            blocked_users_info = []
            for user_id in blocked_users[:5]:  # Показываем только первые 5
                # В реальной реализации здесь был бы запрос к БД для получения username
                reason = privacy_settings.get('block_reasons', {}).get(str(user_id), 'Не указана')
                blocked_users_info.append((user_id, f"User_{user_id}", reason))
            
            text = (
                f"🚫 <b>Заблокированные пользователи</b>\n\n"
                f"Всего заблокировано: {len(blocked_users)}\n\n"
                "Нажмите на пользователя для разблокировки:"
            )
        else:
            blocked_users_info = []
            text = (
                "🚫 <b>Заблокированные пользователи</b>\n\n"
                "У вас нет заблокированных пользователей.\n\n"
                "Вы можете заблокировать пользователя из его профиля в поиске."
            )
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.privacy_blocking_menu(blocked_users_info),
            parse_mode='HTML'
        )

    async def handle_visibility_change(self, query, data, privacy_settings):
        """Обрабатывает изменение видимости профиля"""
        new_visibility = data.replace('visibility_', '')
        old_visibility = privacy_settings.get('profile_visibility', 'all')
        
        if new_visibility == old_visibility:
            await query.answer("✅ Эта настройка уже выбрана")
            return
        
        # Применяем изменение
        privacy_settings['profile_visibility'] = new_visibility
        
        user_id = query.from_user.id
        success = await self.db.update_user_settings(
            user_id,
            privacy_settings=privacy_settings
        )
        
        if success:
            visibility_names = {
                'all': 'Всем пользователям',
                'matches_only': 'Только взаимным лайкам',
                'hidden': 'Скрыт'
            }
            await query.answer(f"✅ Видимость изменена на: {visibility_names[new_visibility]}")
        else:
            await query.answer("❌ Ошибка сохранения настроек")
        
        await self.show_privacy_menu(query)

    async def handle_likes_change(self, query, data, privacy_settings):
        """Обрабатывает изменение настроек лайков"""
        new_likes = data.replace('likes_', '')
        old_likes = privacy_settings.get('who_can_like', 'all')
        
        if new_likes == old_likes:
            await query.answer("✅ Эта настройка уже выбрана")
            return
        
        # Применяем изменение
        privacy_settings['who_can_like'] = new_likes
        
        user_id = query.from_user.id
        success = await self.db.update_user_settings(
            user_id,
            privacy_settings=privacy_settings
        )
        
        if success:
            likes_names = {
                'all': 'Все пользователи',
                'compatible_elo': 'Совместимые по ELO',
                'common_maps': 'С общими картами',
                'active_users': 'Только активные'
            }
            await query.answer(f"✅ Настройка лайков изменена на: {likes_names[new_likes]}")
        else:
            await query.answer("❌ Ошибка сохранения настроек")
        
        await self.show_privacy_menu(query)

    async def handle_display_toggle(self, query, data, privacy_settings):
        """Обрабатывает переключение отображения данных"""
        # Парсим данные: toggle_show_elo_hide или toggle_show_elo_show
        parts = data.split('_')
        if len(parts) < 4:
            await query.answer("❌ Ошибка обработки команды")
            return
        
        setting_key = '_'.join(parts[1:3])  # show_elo, show_stats, и т.д.
        action = parts[3]  # hide или show
        
        new_value = action == 'show'
        privacy_settings[setting_key] = new_value
        
        user_id = query.from_user.id
        success = await self.db.update_user_settings(
            user_id,
            privacy_settings=privacy_settings
        )
        
        if success:
            setting_names = {
                'show_elo': 'ELO Faceit',
                'show_stats': 'Статистика лайков',
                'show_matches_count': 'Количество тиммейтов',
                'show_activity': 'Последняя активность',
                'show_faceit_url': 'Ссылка Faceit'
            }
            setting_name = setting_names.get(setting_key, setting_key)
            action_text = "показывается" if new_value else "скрыто"
            await query.answer(f"✅ {setting_name}: {action_text}")
        else:
            await query.answer("❌ Ошибка сохранения настроек")
        
        await self.show_privacy_display_menu(query, privacy_settings)

    async def handle_unblock_user(self, query, data, privacy_settings):
        """Обрабатывает разблокировку пользователя"""
        # Безопасный парсинг user_id для разблокировки
        user_id_result = safe_parse_user_id(data, "unblock_")
        if not user_id_result.is_valid:
            logger.error(f"Небезопасный callback_data в unblock_user: {data} - {user_id_result.error_message}")
            await query.answer("❌ Ошибка валидации данных")
            return
        
        user_id_to_unblock = user_id_result.parsed_data['user_id']
        
        blocked_users = privacy_settings.get('blocked_users', [])
        if user_id_to_unblock in blocked_users:
            blocked_users.remove(user_id_to_unblock)
            privacy_settings['blocked_users'] = blocked_users
            
            # Удаляем связанные данные
            block_reasons = privacy_settings.get('block_reasons', {})
            block_expiry = privacy_settings.get('block_expiry', {})
            block_reasons.pop(str(user_id_to_unblock), None)
            block_expiry.pop(str(user_id_to_unblock), None)
            
            user_id = query.from_user.id
            success = await self.db.update_user_settings(
                user_id,
                privacy_settings=privacy_settings
            )
            
            if success:
                await query.answer(f"✅ Пользователь {user_id_to_unblock} разблокирован")
            else:
                await query.answer("❌ Ошибка разблокировки")
        else:
            await query.answer("❌ Пользователь не найден в списке заблокированных")
        
        await self.show_privacy_blocking_menu(query, privacy_settings)

    async def handle_privacy_confirmation(self, query, data, privacy_settings):
        """Обрабатывает подтверждение изменений приватности"""
        # Этот метод можно использовать для критичных изменений, требующих подтверждения
        await query.answer("✅ Настройки применены")
        await self.show_privacy_menu(query)

    async def handle_privacy_cancellation(self, query, data):
        """Обрабатывает отмену изменений приватности"""
        await query.answer("❌ Изменения отменены")
        await self.show_privacy_menu(query)

    # === ИСТОРИЯ ЛАЙКОВ ===

    async def show_likes_history(self, query):
        """Показывает главное меню истории лайков"""
        await query.answer()
        user_id = query.from_user.id
        
        try:
            # Получаем статистику лайков
            stats = await self.db.get_likes_statistics(user_id)
            
            menu_text = (
                "💌 <b>История лайков</b>\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"• Всего получено: {stats['total_received']}\n"
                f"• Новых лайков: {stats['new_likes']}\n"
                f"• Взаимных лайков: {stats['mutual_likes']}\n"
                f"• Отправлено лайков: {stats['sent_likes']}\n\n"
                "Выберите действие:"
            )
            
            keyboard = Keyboards.likes_history_menu()
            await self.safe_edit_or_send_message(query, menu_text, keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка отображения истории лайков для {user_id}: {e}")
            await query.answer("❌ Произошла ошибка")
            await self.show_main_menu(query)

    async def show_likes_list(self, query, new_only: bool = False, page: int = 0):
        """Показывает список полученных лайков"""
        await query.answer()
        user_id = query.from_user.id
        
        try:
            # Параметры пагинации
            limit = 5
            offset = page * limit
            
            # Получаем лайки
            likes = await self.db.get_received_likes(
                user_id=user_id,
                new_only=new_only,
                limit=limit + 1,  # +1 чтобы понять есть ли следующая страница
                offset=offset
            )
            
            has_next = len(likes) > limit
            if has_next:
                likes = likes[:limit]  # Убираем лишний элемент
            
            if not likes:
                if new_only:
                    message_text = (
                        "💌 <b>Новые лайки</b>\n\n"
                        "📭 <b>У вас пока нет новых лайков</b>\n"
                        "Новые лайки появятся здесь, когда кто-то поставит вам лайк!"
                    )
                else:
                    message_text = (
                        "💌 <b>Все лайки</b>\n\n"
                        "📭 <b>У вас пока нет лайков</b>\n"
                        "Лайки появятся здесь, когда другие игроки оценят ваш профиль!"
                    )
                
                keyboard = Keyboards.likes_history_menu()
                await self.safe_edit_or_send_message(query, message_text, keyboard)
                return
            
            # Формируем сообщение со списком лайков с краткими строками
            title = "💌 Новые лайки" if new_only else "📋 Все лайки"
            message_text = f"{title}\n\n"
            
            # Строим клавиатуру с кнопками для каждого лайка
            keyboard_rows = []
            
            for like in likes:
                # Форматируем дату
                created_at = like['created_at']
                if isinstance(created_at, str):
                    from datetime import datetime
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                
                # Определяем статус и добавляем краткую строку в сообщение
                status_emoji = "💫" if like['response_status'] == 'mutual' else "⏳"
                message_text += f"{status_emoji} {like['game_nickname']} • {like['faceit_elo']} ELO • {like['role']} • {created_at.strftime('%d.%m')}\n"
                
                # Добавляем кнопки только для неотвеченных лайков
                if like['response_status'] != 'mutual':
                    # Row 1: Основная кнопка лайка
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            f"❤️ {like['game_nickname']} • {like['faceit_elo']} • {like['role']}",
                            callback_data=f"reply_like_{like['liker_id']}"
                        )
                    ])
                    
                    # Row 2: Кнопки просмотра и пропуска
                    keyboard_rows.append([
                        InlineKeyboardButton("👁️", callback_data=f"view_profile_{like['liker_id']}"),
                        InlineKeyboardButton("❌", callback_data=f"skip_like_{like['liker_id']}")
                    ])
            
            # Добавляем навигацию внизу
            has_prev = page > 0
            navigation_keyboard = Keyboards.like_history_navigation(
                has_prev=has_prev,
                has_next=has_next,
                page=page
            )
            
            # Объединяем кнопки лайков с навигацией
            if navigation_keyboard:
                keyboard_rows.extend(navigation_keyboard.inline_keyboard)
            
            # Создаем финальную клавиатуру
            final_keyboard = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None
            
            await self.safe_edit_or_send_message(query, message_text, final_keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка отображения списка лайков для {user_id}: {e}")
            await query.answer("❌ Произошла ошибка")
            await self.show_likes_history(query)

    async def handle_like_response(self, query, liker_id: int, action: str):
        """Обрабатывает ответ на лайк"""
        await query.answer()
        user_id = query.from_user.id
        
        try:
            if action == "reply":
                # Ставим лайк в ответ
                success = await self.db.add_like(user_id, liker_id)
                
                if success:
                    # Отправляем уведомление о лайке первому игроку
                    try:
                        from bot.utils.notifications import NotificationManager
                        bot = query.bot
                        notification_manager = NotificationManager(bot, self.db)
                        await notification_manager.send_like_notification(
                            liked_user_id=liker_id,  # Тот, кто получит уведомление (первый игрок)
                            liker_user_id=user_id    # Тот, кто поставил лайк (второй игрок)
                        )
                        logger.info(f"Уведомление о лайке отправлено {liker_id} от {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления о лайке: {e}")
                
                if success:
                    # Проверяем взаимность
                    is_mutual = await self.db.check_mutual_like(user_id, liker_id)
                    
                    if is_mutual:
                        # Создаем матч
                        match_success = await self.db.create_match(user_id, liker_id)
                        
                        if match_success:
                            response_text = (
                                "🎉 <b>Поздравляем!</b>\n\n"
                                "У вас взаимный лайк! Теперь вы можете найти контакты друг друга "
                                "в разделе 'Мои тиммейты'."
                            )
                            
                            # Отправляем уведомления о новом матче (если настроено)
                            try:
                                from bot.utils.notifications import NotificationManager
                                # Получаем бота из контекста
                                bot = query.bot
                                notification_manager = NotificationManager(bot, self.db)
                                await notification_manager.send_match_notification(user_id, liker_id)
                            except Exception as e:
                                logger.error(f"Ошибка отправки уведомления о матче: {e}")
                        else:
                            response_text = "❤️ Лайк отправлен, но произошла ошибка создания матча"
                    else:
                        response_text = "❤️ Лайк отправлен! Если будет взаимность, вы узнаете об этом."
                else:
                    response_text = "❌ Не удалось отправить лайк. Попробуйте позже."
                
            elif action == "skip":
                # Отмечаем лайк как просмотренный
                success = await self.db.mark_like_as_viewed(liker_id, user_id)
                
                if success:
                    response_text = "✅ Лайк пропущен"
                else:
                    response_text = "❌ Ошибка при обработке лайка"
            
            # Обновляем сообщение
            await self.safe_edit_or_send_message(
                query, 
                response_text,
                Keyboards.likes_history_menu()
            )
            
        except Exception as e:
            logger.error(f"Ошибка обработки ответа на лайк {liker_id} от {user_id}: {e}")
            await query.answer("❌ Произошла ошибка")
            await self.show_likes_history(query)

    async def show_user_profile(self, query, profile_user_id: int):
        """Показывает профиль другого пользователя"""
        await query.answer()
        current_user_id = query.from_user.id
        
        logger.info(f"show_user_profile: current_user_id={current_user_id}, profile_user_id={profile_user_id}")
        
        try:
            # Получаем профиль
            profile = await self.db.get_profile(profile_user_id)
            logger.info(f"show_user_profile: profile found={profile is not None}, status={profile.moderation_status if profile else 'None'}")
            
            if not profile or profile.moderation_status != 'approved':
                logger.warning(f"show_user_profile: Profile not available for user {profile_user_id}")
                await query.answer("❌ Профиль недоступен")
                return
            
            # Проверяем настройки приватности
            user_settings = await self.db.get_user_settings(profile_user_id)
            privacy_settings = user_settings.privacy_settings if user_settings and user_settings.privacy_settings else {}
            logger.info(f"show_user_profile: privacy_settings={privacy_settings}")
            
            visibility = privacy_settings.get('profile_visibility', 'all')
            logger.info(f"show_user_profile: visibility={visibility}")
            
            if visibility == 'hidden':
                logger.info(f"show_user_profile: Profile {profile_user_id} is hidden")
                await query.answer("❌ Профиль скрыт")
                return
            elif visibility == 'matches_only':
                # Проверяем есть ли взаимный лайк
                is_match = await self.db.check_mutual_like(current_user_id, profile_user_id)
                logger.info(f"show_user_profile: is_match={is_match}")
                if not is_match:
                    logger.info(f"show_user_profile: Profile {profile_user_id} requires match for user {current_user_id}")
                    await query.answer("❌ Профиль доступен только тиммейтам")
                    return
            
            # Формируем сообщение профиля
            profile_text = f"👤 <b>Профиль игрока</b>\n\n"
            profile_text += f"🎮 <b>{profile.game_nickname}</b>\n"
            
            if privacy_settings.get('show_elo', True):
                profile_text += f"🎯 ELO Faceit: {profile.faceit_elo}\n"
            
            profile_text += f"👤 Роль: {profile.role}\n"
            profile_text += f"🗺️ Карты: {', '.join(profile.favorite_maps[:3])}\n"
            
            if profile.description and len(profile.description.strip()) > 0:
                profile_text += f"\n📝 <b>О себе:</b>\n{profile.description}\n"
            
            # Отправляем профиль
            keyboard = Keyboards.likes_history_menu()
            logger.info(f"show_user_profile: Sending profile for {profile_user_id}, has_media={profile.media_type is not None}")
            
            if profile.media_type and profile.media_file_id:
                if profile.media_type == 'photo':
                    await query.message.reply_photo(
                        photo=profile.media_file_id,
                        caption=profile_text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    logger.info(f"show_user_profile: Photo sent for profile {profile_user_id}")
                elif profile.media_type == 'video':
                    await query.message.reply_video(
                        video=profile.media_file_id,
                        caption=profile_text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    logger.info(f"show_user_profile: Video sent for profile {profile_user_id}")
                else:
                    await self.safe_edit_or_send_message(query, profile_text, keyboard)
                    logger.info(f"show_user_profile: Text message sent for profile {profile_user_id}")
            else:
                await self.safe_edit_or_send_message(query, profile_text, keyboard)
                logger.info(f"show_user_profile: Text message sent for profile {profile_user_id} (no media)")
                
        except Exception as e:
            logger.error(f"Ошибка отображения профиля {profile_user_id} для {current_user_id}: {e}")
            await query.answer("❌ Произошла ошибка")
            await self.show_likes_history(query)
    
    async def _warm_user_network(self, user_id: int):
        """Прогревает сеть пользователя для быстрой загрузки ELO данных"""
        try:
            from bot.utils.faceit_analyzer import faceit_analyzer
            
            # Запускаем прогревание в фоновом режиме, не блокируя UI
            asyncio.create_task(self._background_warm_user_network(user_id))
            
        except Exception as e:
            logger.debug(f"Ошибка запуска прогревания сети для пользователя {user_id}: {e}")
    
    async def _background_warm_user_network(self, user_id: int):
        """Фоновое прогревание сети пользователя"""
        try:
            from bot.utils.faceit_analyzer import faceit_analyzer
            
            warmed_count = await faceit_analyzer.warm_user_network(user_id)
            if warmed_count > 0:
                logger.debug(f"🔥 Прогрета сеть пользователя {user_id}: {warmed_count} профилей")
            
        except Exception as e:
            logger.debug(f"Ошибка фонового прогревания сети для пользователя {user_id}: {e}")