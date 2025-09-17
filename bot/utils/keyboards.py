"""
Inline клавиатуры для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .cs2_data import CS2_ROLES, CS2_MAPS, PLAYTIME_OPTIONS, ELO_FILTER_RANGES, PROFILE_CATEGORIES, format_elo_filter_display

logger = logging.getLogger(__name__)

class Keyboards:
    @staticmethod
    def _log_button_creation(button_type: str, callback_data: str, context: str = ""):
        """Helper method to log button creation with callback data"""
        logger.debug(f"🔘 BUTTON CREATED: type='{button_type}', callback_data='{callback_data}', context='{context}'")
    
    @staticmethod
    def _log_keyboard_generation(keyboard_name: str, has_back_button: bool = False, 
                                back_callback: str = "", context: str = ""):
        """Enhanced logging for keyboard generation"""
        log_message = f"⌨️ KEYBOARD GENERATED: name='{keyboard_name}', has_back={has_back_button}"
        if has_back_button and back_callback:
            log_message += f", back_callback='{back_callback}'"
        if context:
            log_message += f", context='{context}'"
        logger.debug(log_message)

    @staticmethod
    def main_menu():
        keyboard = [
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile_menu")],
            [InlineKeyboardButton("🔍 Поиск тиммейтов", callback_data="search_start")],
            [InlineKeyboardButton("💝 Мои тиммейты", callback_data="teammates_list")],
            [InlineKeyboardButton("💌 История лайков", callback_data="likes_history")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_profile_mandatory():
        """Принудительное создание профиля для новых пользователей"""
        keyboard = [
            [InlineKeyboardButton("📝 Создать профиль", callback_data="create_profile")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_menu(has_profile: bool = False, is_rejected: bool = False):
        """DEPRECATED: Используется только для совместимости"""
        keyboard = []
        
        if has_profile:
            keyboard.append([InlineKeyboardButton("👁️ Посмотреть профиль", callback_data="profile_view")])
            
            if is_rejected:
                # Для отклоненных профилей показываем кнопку создания нового профиля
                keyboard.append([InlineKeyboardButton("🆕 Создать новый профиль", callback_data="profile_create")])
            else:
                # Для обычных профилей показываем редактирование и статистику
                keyboard.extend([
                    [InlineKeyboardButton("✏️ Редактировать", callback_data="profile_edit")],
                    [InlineKeyboardButton("📊 Статистика", callback_data="profile_stats")]
                ])
        else:
            keyboard.append([InlineKeyboardButton("✨ Создать профиль", callback_data="profile_create")])
        
        keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_main_menu():
        """Главное меню профиля для одобренных профилей"""
        keyboard = [
            [InlineKeyboardButton("✏️ Редактировать", callback_data="profile_edit")],
            [InlineKeyboardButton("📊 Статистика", callback_data="profile_stats")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_rejected_menu():
        """Меню профиля для отклоненных профилей"""
        keyboard = [
            [InlineKeyboardButton("🆕 Создать новый профиль", callback_data="profile_create")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_no_profile_menu():
        """Меню когда у пользователя нет профиля"""
        keyboard = [
            [InlineKeyboardButton("✨ Создать профиль", callback_data="profile_create")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def elo_input_menu():
        """Меню для ввода точного ELO (без диапазонов)."""
        keyboard = [
            [InlineKeyboardButton("📝 Ввести точное ELO", callback_data="elo_custom")],
            [InlineKeyboardButton("🔙 Отмена", callback_data="back")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def role_selection():
        keyboard = []
        
        for role in CS2_ROLES:
            button_text = f"{role['emoji']} {role['name']}"
            callback_data = f"role_{role['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Log back button creation
        Keyboards._log_button_creation("back", "back", "role_selection keyboard")
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
        
        Keyboards._log_keyboard_generation("role_selection", True, "back", "Role selection with back button")
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def maps_selection(selected_maps: list = None):
        if selected_maps is None:
            selected_maps = []
            
        keyboard = []
        
        # Группируем карты по 2 в ряд
        for i in range(0, len(CS2_MAPS), 2):
            row = []
            for j in range(2):
                if i + j < len(CS2_MAPS):
                    map_data = CS2_MAPS[i + j]
                    map_name = map_data['name']
                    is_selected = map_name in selected_maps
                    
                    # Добавляем галочку если карта выбрана
                    button_text = f"{'✅' if is_selected else map_data['emoji']} {map_name}"
                    callback_data = f"map_{map_name}"
                    row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.append(row)
        
        # Кнопки управления
        control_row = []
        if selected_maps:
            control_row.append(InlineKeyboardButton(f"✅ Готово ({len(selected_maps)})", callback_data="maps_done"))
        
        # Log back button creation
        Keyboards._log_button_creation("back", "back", "maps_selection keyboard")
        control_row.append(InlineKeyboardButton("🔙 Назад", callback_data="back"))
        keyboard.append(control_row)
        
        Keyboards._log_keyboard_generation("maps_selection", True, "back", f"Maps selection with {len(selected_maps)} selected")
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def playtime_selection(selected_slots: list = None):
        if selected_slots is None:
            selected_slots = []
            
        keyboard = []
        
        for time_option in PLAYTIME_OPTIONS:
            is_selected = time_option['id'] in selected_slots
            button_text = f"{'✅' if is_selected else time_option['emoji']} {time_option['name']}"
            callback_data = f"time_{time_option['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Кнопки управления
        control_row = []
        if selected_slots:
            control_row.append(InlineKeyboardButton(f"✅ Готово ({len(selected_slots)})", callback_data="time_done"))
        
        control_row.append(InlineKeyboardButton("🔙 Назад", callback_data="back"))
        keyboard.append(control_row)
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def categories_selection(selected_categories: list = None, edit_mode: bool = False):
        """Клавиатура для выбора категорий"""
        if selected_categories is None:
            selected_categories = []
            
        keyboard = []
        
        # Добавляем все категории
        for category in PROFILE_CATEGORIES:
            is_selected = category['id'] in selected_categories
            button_text = f"{'✅' if is_selected else category['emoji']} {category['name']}"
            # Используем разные callback_data для создания и редактирования
            callback_data = f"{'edit_category_' if edit_mode else 'category_'}{category['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Кнопки управления
        control_row = []
        if selected_categories:
            done_callback = "edit_categories_done" if edit_mode else "categories_done"
            control_row.append(InlineKeyboardButton(f"✅ Готово ({len(selected_categories)})", callback_data=done_callback))
        
        control_row.append(InlineKeyboardButton("🔙 Назад", callback_data="back"))
        keyboard.append(control_row)
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def skip_description():
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_description")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def media_selection():
        """Клавиатура для выбора типа медиа"""
        keyboard = [
            [InlineKeyboardButton("📷 Добавить фото", callback_data="media_photo")],
            [InlineKeyboardButton("🎥 Добавить видео", callback_data="media_video")],
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="media_skip")],
        ]
        
        # Log back button creation - now consistent with ConversationHandler pattern
        Keyboards._log_button_creation("back", "media_back", "media_selection keyboard - CONSISTENT CALLBACK")
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="media_back")])
        
        Keyboards._log_keyboard_generation("media_selection", True, "media_back", "Media selection with consistent media_back callback")
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirm_profile_creation():
        """Клавиатура для подтверждения создания профиля"""
        keyboard = [
            [InlineKeyboardButton("✅ Сохранить профиль", callback_data="confirm_save_profile")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_created():
        keyboard = [
            [InlineKeyboardButton("👁️ Посмотреть профиль", callback_data="profile_view")],
            [InlineKeyboardButton("🔍 Искать тиммейтов", callback_data="search_start")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_view_menu():
        keyboard = [
            [InlineKeyboardButton("✏️ Редактировать", callback_data="profile_edit")],
            [InlineKeyboardButton("📊 Статистика", callback_data="profile_stats")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def like_buttons():
        keyboard = [
            [
                InlineKeyboardButton("❤️ Лайк", callback_data="like"),
                InlineKeyboardButton("❌ Пропустить", callback_data="skip")
            ],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def profile_edit_menu():
        keyboard = [
            [InlineKeyboardButton("🎯 Изменить ELO Faceit", callback_data="edit_elo")],
            [InlineKeyboardButton("🎮 Изменить ник", callback_data="edit_nickname")],
            [InlineKeyboardButton("🔗 Изменить ссылку Faceit", callback_data="edit_faceit_url")],
            [InlineKeyboardButton("👤 Изменить роль", callback_data="edit_role")],
            [InlineKeyboardButton("🗺️ Изменить карты", callback_data="edit_maps")],
            [InlineKeyboardButton("⏰ Изменить время", callback_data="edit_time")],
            [InlineKeyboardButton("🎮 Изменить категории", callback_data="edit_categories")],
            [InlineKeyboardButton("💬 Изменить описание", callback_data="edit_description")],
            [InlineKeyboardButton("📷 Изменить медиа", callback_data="edit_media")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile_view")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def media_edit_menu(has_media: bool = False):
        """Клавиатура для редактирования медиа"""
        keyboard = []
        
        if has_media:
            keyboard.extend([
                [InlineKeyboardButton("🔄 Заменить медиа", callback_data="edit_media_replace")],
                [InlineKeyboardButton("🗑️ Удалить медиа", callback_data="edit_media_remove")]
            ])
        else:
            keyboard.append([InlineKeyboardButton("➕ Добавить медиа", callback_data="edit_media_add")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="profile_edit")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirmation(action: str):
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"confirm_{action}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"cancel_{action}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def back_button(callback_data: str):
        # Log back button creation
        Keyboards._log_button_creation("back", callback_data, "single back button")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=callback_data)]]
        Keyboards._log_keyboard_generation("back_button", True, callback_data, f"Single back button with callback: {callback_data}")
        return InlineKeyboardMarkup(keyboard)

    # Дополнительные клавиатуры для поиска
    @staticmethod
    def search_menu():
        keyboard = [
            [InlineKeyboardButton("🎯 Фильтр по ELO", callback_data="search_elo_filter")],
            [InlineKeyboardButton("🎮 Фильтр по категориям", callback_data="search_categories_filter")],
            [InlineKeyboardButton("👤 Поиск по роли", callback_data="search_by_role")],
            [InlineKeyboardButton("🗺️ Поиск по картам", callback_data="search_by_maps")],
            [InlineKeyboardButton("🎲 Случайный поиск", callback_data="search_random")],
            [InlineKeyboardButton("🔍 Обычный поиск", callback_data="search_start")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def elo_filter_menu(current_filter='any'):
        """Меню выбора ELO фильтра"""
        keyboard = []
        
        # Добавляем "Любой ELO" как первый вариант
        any_text = "✅ 🎯 Любой ELO" if current_filter == 'any' else "🎯 Любой ELO"
        keyboard.append([InlineKeyboardButton(any_text, callback_data="elo_filter_any")])
        
        # Добавляем новые ELO диапазоны
        for elo_range in ELO_FILTER_RANGES:
            is_selected = current_filter == elo_range['id']
            button_text = f"✅ {elo_range['emoji']} {elo_range['name']}" if is_selected else f"{elo_range['emoji']} {elo_range['name']}"
            callback_data = f"elo_filter_{elo_range['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Кнопки управления
        keyboard.extend([
            [InlineKeyboardButton("🔍 Применить фильтр", callback_data="apply_elo_filter")],
            [InlineKeyboardButton("🔙 К поиску", callback_data="search_menu")]
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def teammates_menu():
        keyboard = [
            [InlineKeyboardButton("💌 Новые тиммейты", callback_data="teammates_new")],
            [InlineKeyboardButton("📋 Все тиммейты", callback_data="teammates_all")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def settings_menu():
        keyboard = [
            [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
            [InlineKeyboardButton("🎯 Фильтры поиска", callback_data="settings_filters")],
            [InlineKeyboardButton("🔒 Приватность", callback_data="settings_privacy")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def filters_settings_menu(current_filters):
        """Меню настроек фильтров поиска"""
        elo_filter = current_filters.get('elo_filter', 'any')
        elo_text = format_elo_filter_display(elo_filter)
        
        keyboard = [
            [InlineKeyboardButton(f"🎯 ELO: {elo_text}", callback_data="filter_elo")],
            [InlineKeyboardButton("👤 Предпочитаемые роли", callback_data="filter_roles")],
            [InlineKeyboardButton("🗺️ Совместимость карт", callback_data="filter_maps")],
            [InlineKeyboardButton("⏰ Совместимость времени", callback_data="filter_time")],
            [InlineKeyboardButton("📊 Мин. совместимость", callback_data="filter_compatibility")],
            [InlineKeyboardButton("🔄 Сбросить фильтры", callback_data="filters_reset")],
            [InlineKeyboardButton("🔙 В настройки", callback_data="settings_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def filter_elo_settings_menu(current_filter='any'):
        """Меню настройки ELO фильтра в настройках"""
        keyboard = []
        
        # Добавляем "Любой ELO" как первый вариант
        any_text = "✅ 🎯 Любой ELO" if current_filter == 'any' else "🎯 Любой ELO"
        keyboard.append([InlineKeyboardButton(any_text, callback_data="filter_elo_any")])
        
        # Добавляем новые ELO диапазоны
        for elo_range in ELO_FILTER_RANGES:
            is_selected = current_filter == elo_range['id']
            button_text = f"✅ {elo_range['emoji']} {elo_range['name']}" if is_selected else f"{elo_range['emoji']} {elo_range['name']}"
            callback_data = f"filter_elo_{elo_range['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton("🔙 К фильтрам", callback_data="settings_filters")])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def privacy_main_menu(privacy_settings):
        """Главное меню настроек приватности"""
        # Получаем текущие настройки с значениями по умолчанию
        visibility = privacy_settings.get('profile_visibility', 'all')
        who_can_like = privacy_settings.get('who_can_like', 'all')
        blocked_count = len(privacy_settings.get('blocked_users', []))
        
        # Подсчитываем показываемые данные
        display_settings = [
            privacy_settings.get('show_elo', True),
            privacy_settings.get('show_stats', True),
            privacy_settings.get('show_matches_count', True),
            privacy_settings.get('show_activity', True),
            privacy_settings.get('show_faceit_url', True)
        ]
        shown_count = sum(display_settings)
        
        # Форматируем текст статуса
        visibility_text = {
            'all': 'Всем пользователям',
            'matches_only': 'Только тиммейтам',
            'hidden': 'Скрыт'
        }.get(visibility, 'Всем пользователям')
        
        likes_text = {
            'all': 'Все пользователи',
            'compatible_elo': 'Совместимые по ELO',
            'common_maps': 'С общими картами',
            'active_users': 'Только активные'
        }.get(who_can_like, 'Все пользователи')
        
        keyboard = [
            [InlineKeyboardButton(f"👁️ Видимость: {visibility_text}", callback_data="privacy_visibility")],
            [InlineKeyboardButton(f"💌 Лайки: {likes_text}", callback_data="privacy_likes")],
            [InlineKeyboardButton(f"📊 Данные: {shown_count}/5 показано", callback_data="privacy_display")],
            [InlineKeyboardButton(f"🚫 Блокировка: {blocked_count} пользователей", callback_data="privacy_blocking")],
            [InlineKeyboardButton("🔙 В настройки", callback_data="settings_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def privacy_visibility_menu(current_setting='all'):
        """Меню настройки видимости профиля"""
        options = [
            ('all', '🌍 Всем пользователям'),
            ('matches_only', '👥 Только взаимным лайкам'),
            ('hidden', '🔒 Скрыть профиль')
        ]
        
        keyboard = []
        for value, text in options:
            if value == current_setting:
                text = f"✅ {text}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"visibility_{value}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="privacy_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def privacy_likes_menu(current_setting='all'):
        """Меню настройки лайков"""
        options = [
            ('all', '🌍 Все пользователи'),
            ('compatible_elo', '🎯 Совместимые по ELO (±2 уровня)'),
            ('common_maps', '🗺️ С общими картами (мин. 2)'),
            ('active_users', '👥 Только активные (за неделю)')
        ]
        
        keyboard = []
        for value, text in options:
            if value == current_setting:
                text = f"✅ {text}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"likes_{value}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="privacy_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod  
    def privacy_display_menu(privacy_settings):
        """Меню настройки отображения данных"""
        display_options = [
            ('show_elo', '🎯 ELO Faceit'),
            ('show_stats', '📊 Статистика лайков'),
            ('show_matches_count', '💝 Количество тиммейтов'),
            ('show_activity', '⏰ Последняя активность'),
            ('show_faceit_url', '🔗 Ссылка Faceit')
        ]
        
        keyboard = []
        for setting_key, label in display_options:
            is_shown = privacy_settings.get(setting_key, True)
            status = "✅" if is_shown else "❌"
            action = "hide" if is_shown else "show"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {label}", 
                    callback_data=f"toggle_{setting_key}_{action}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="privacy_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def privacy_blocking_menu(blocked_users_info):
        """Меню управления блокировкой"""
        keyboard = []
        
        if blocked_users_info:
            # Показываем до 5 заблокированных пользователей
            for i, (user_id, username, reason) in enumerate(blocked_users_info[:5]):
                display_name = username or f"ID: {user_id}"
                reason_text = f" ({reason})" if reason else ""
                keyboard.append([
                    InlineKeyboardButton(
                        f"🚫 {display_name}{reason_text}",
                        callback_data=f"unblock_{user_id}"
                    )
                ])
            
            if len(blocked_users_info) > 5:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📋 Показать все ({len(blocked_users_info)})",
                        callback_data="blocking_show_all"
                    )
                ])
        else:
            keyboard.append([
                InlineKeyboardButton("ℹ️ Нет заблокированных пользователей", callback_data="blocking_info")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="privacy_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def privacy_confirmation_menu(setting_type, old_value, new_value):
        """Меню подтверждения изменения настроек приватности"""
        keyboard = [
            [InlineKeyboardButton("✅ Сохранить", callback_data=f"confirm_privacy_{setting_type}_{new_value}")],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_privacy_{setting_type}")],
        ]
        return InlineKeyboardMarkup(keyboard)

    # === МОДЕРАЦИЯ ===

    @staticmethod
    def main_menu_with_moderation():
        """Главное меню с кнопкой модерации для модераторов"""
        keyboard = [
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile_menu")],
            [InlineKeyboardButton("🔍 Поиск тиммейтов", callback_data="search_start")],
            [InlineKeyboardButton("💝 Мои тиммейты", callback_data="teammates_list")],
            [InlineKeyboardButton("👨‍💼 Модерация", callback_data="moderation_menu")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def moderation_main_menu(pending_count=0):
        """Главное меню модерации"""
        keyboard = [
            [InlineKeyboardButton(f"⏳ Очередь модерации ({pending_count})", callback_data="mod_queue")],
            [InlineKeyboardButton("✅ Одобренные профили", callback_data="mod_approved")],
            [InlineKeyboardButton("❌ Отклоненные профили", callback_data="mod_rejected")],
            [InlineKeyboardButton("📊 Статистика модерации", callback_data="mod_stats")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def moderation_profile_actions(user_id):
        """Кнопки действий с профилем при модерации"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
            ],
            [InlineKeyboardButton("⏭️ Следующая анкета", callback_data="next_profile")],
            [InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def moderation_rejection_reasons():
        """Меню выбора причины отклонения"""
        keyboard = [
            [InlineKeyboardButton("🔞 Неподходящий контент", callback_data="reject_reason_inappropriate")],
            [InlineKeyboardButton("🔗 Неверная ссылка Faceit", callback_data="reject_reason_invalid_link")],
            [InlineKeyboardButton("🎮 Неподходящий ник", callback_data="reject_reason_bad_nickname")],
            [InlineKeyboardButton("📝 Неполная информация", callback_data="reject_reason_incomplete")],
            [InlineKeyboardButton("✏️ Своя причина", callback_data="reject_reason_custom")],
            [InlineKeyboardButton("🔙 Отмена", callback_data="mod_queue")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def moderation_navigation():
        """Навигация в панели модерации"""
        keyboard = [
            [InlineKeyboardButton("⏭️ Следующая", callback_data="next_profile")],
            [InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def moderation_stats_menu():
        """Меню статистики модерации"""
        keyboard = [
            [InlineKeyboardButton("📊 Общая статистика", callback_data="mod_stats_general")],
            [InlineKeyboardButton("👨‍💼 Статистика модераторов", callback_data="mod_stats_moderators")],
            [InlineKeyboardButton("📈 За неделю", callback_data="mod_stats_week")],
            [InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def categories_filter_menu(selected_categories: list = None):
        """Меню фильтрации по категориям в поиске"""
        if selected_categories is None:
            selected_categories = []
            
        keyboard = []
        
        # Добавляем "Любые категории" как первый вариант
        any_text = "✅ 🎯 Любые категории" if not selected_categories else "🎯 Любые категории"
        keyboard.append([InlineKeyboardButton(any_text, callback_data="categories_filter_any")])
        
        # Добавляем все категории
        for category in PROFILE_CATEGORIES:
            is_selected = category['id'] in selected_categories
            button_text = f"✅ {category['emoji']} {category['name']}" if is_selected else f"{category['emoji']} {category['name']}"
            callback_data = f"categories_filter_{category['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Кнопки управления
        keyboard.extend([
            [InlineKeyboardButton("🔍 Применить фильтр", callback_data="apply_categories_filter")],
            [InlineKeyboardButton("🔙 К поиску", callback_data="search_menu")]
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    # === ЛАЙКИ И ИСТОРИЯ ===
    
    @staticmethod
    def likes_history_menu():
        """Меню истории лайков"""
        keyboard = [
            [InlineKeyboardButton("💌 Новые лайки", callback_data="likes_new")],
            [InlineKeyboardButton("📋 Все лайки", callback_data="likes_all")],
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def like_response_buttons(liker_id: int):
        """Клавиатура для ответа на конкретный лайк"""
        keyboard = [
            [
                InlineKeyboardButton("❤️ Лайк в ответ", callback_data=f"reply_like_{liker_id}"),
                InlineKeyboardButton("❌ Пропустить", callback_data=f"skip_like_{liker_id}")
            ],
            [InlineKeyboardButton("👁️ Посмотреть профиль", callback_data=f"view_profile_{liker_id}")],
            [InlineKeyboardButton("🔙 К истории лайков", callback_data="likes_history")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def like_history_navigation(has_prev: bool = False, has_next: bool = False, page: int = 0):
        """Навигация для истории лайков"""
        keyboard = []
        nav_row = []
        if has_prev:
            nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"likes_page_{page-1}"))
        if has_next:
            nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"likes_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
        keyboard.append([InlineKeyboardButton("🔙 К истории лайков", callback_data="likes_history")])
        return InlineKeyboardMarkup(keyboard) 