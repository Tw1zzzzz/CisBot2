"""
CS2 Teammeet Bot - Основная точка входа
"""
import logging
import os
import asyncio
import random
from warnings import filterwarnings
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.warnings import PTBUserWarning
from telegram.error import NetworkError, TimedOut
import httpx

from .config import Config, setup_logging
from .utils.keyboards import Keyboards
from .utils.health_monitor import HealthMonitor
from .utils.background_processor import get_background_processor
from .utils.progressive_loader import initialize_progressive_loader, get_progressive_loader
from .utils.faceit_cache import FaceitCacheManager
from .utils.performance_monitor import PerformanceMonitor
from .database.operations import DatabaseManager
from .handlers.start import StartHandler
from .handlers.profile import ProfileHandler, ENTERING_NICKNAME, SELECTING_ELO, ENTERING_FACEIT_URL, SELECTING_ROLE, SELECTING_MAPS, SELECTING_PLAYTIME, SELECTING_CATEGORIES, ENTERING_DESCRIPTION, SELECTING_MEDIA, EDITING_MEDIA_TYPE
from .handlers.search import SearchHandler
from .handlers.teammates import TeammatesHandler
from .handlers.moderation import ModerationHandler

# Подавляем PTBUserWarning для ConversationHandler с CallbackQueryHandler
# Это безопасно для нашего случая со смешанными handler'ами
filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

logger = setup_logging()
network_logger = logging.getLogger('bot.network')

class CS2TeammeetBot:
    def __init__(self):
        if not Config.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не найден в переменных окружения!")
        
        logger.info("Инициализация DatabaseManager...")
        self.db = DatabaseManager(Config.DATABASE_PATH)
        
        logger.info("Инициализация Health Monitor...")
        self.health_monitor = HealthMonitor(Config.BOT_TOKEN)
        
        logger.info("Инициализация Performance Monitor...")
        self.performance_monitor = PerformanceMonitor(Config)
        
        logger.info("Инициализация Cache Manager...")
        self.cache_manager = FaceitCacheManager()
        
        logger.info("Создание Telegram Application...")
        self.application = (
            Application.builder()
            .token(Config.BOT_TOKEN)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .read_timeout(30)  # Таймаут чтения (по умолчанию 5)
            .write_timeout(30)  # Таймаут записи (по умолчанию 5) 
            .connect_timeout(30)  # Таймаут подключения (по умолчанию 5)
            .pool_timeout(30)  # Таймаут пула соединений (по умолчанию 5)
            .build()
        )
        self.setup_handlers()
        
        logger.info("Обработчики настроены успешно")
        logger.info("CS2 Teammeet Bot инициализирован успешно")
    
    def get_cache_manager(self) -> 'FaceitCacheManager':
        """Export cache manager for shared use across the application"""
        return self.cache_manager
    
    async def _post_init(self, application):
        try:
            await self.db.connect()
            await self.db.init_database()
            logger.info("База данных и пул соединений инициализированы")
            
            # Initialize cache manager
            await self.cache_manager.initialize()
            logger.info("Cache manager инициализирован успешно")
            
            # Initialize background processor
            bg_processor = get_background_processor()
            await bg_processor.start()
            logger.info("Background processor запущен успешно")
            
            # Initialize performance monitoring
            if getattr(Config, 'PERFORMANCE_MONITORING_ENABLED', True):
                # Set component references for performance monitoring
                self.performance_monitor.set_component_references(
                    health_monitor=self.health_monitor,
                    cache_manager=self.cache_manager,
                    background_processor=bg_processor
                )
                
                # Inject performance monitor into cache manager
                if hasattr(self.cache_manager, 'set_performance_monitor'):
                    self.cache_manager.set_performance_monitor(self.performance_monitor)
                
                # Start performance monitoring
                await self.performance_monitor.start_monitoring()
                logger.info("Performance monitoring запущен успешно")
            
            # Initialize progressive loader
            from bot.utils.faceit_analyzer import faceit_analyzer
            
            # Inject performance monitor into faceit analyzer
            if hasattr(faceit_analyzer, 'set_performance_monitor'):
                faceit_analyzer.set_performance_monitor(self.performance_monitor)
            
            progressive_loader = initialize_progressive_loader(
                bot=application.bot, 
                faceit_analyzer=faceit_analyzer
            )
            await progressive_loader.start()
            logger.info("Progressive loader инициализирован и запущен успешно")
            
            # Start cache maintenance tasks
            await self._start_cache_maintenance()
            logger.info("Cache maintenance tasks запущены успешно")
            
            # Preload popular profiles for faster response
            if getattr(Config, 'FACEIT_CACHE_PRELOAD_ON_STARTUP', True):
                await self._preload_popular_profiles()
                logger.info("Popular profiles preloading completed")
        except Exception:
            logger.critical("Initialization failed", exc_info=True)
            raise
    
    async def _post_shutdown(self, application):
        try:
            # Stop progressive loader first
            progressive_loader = get_progressive_loader()
            if progressive_loader:
                await progressive_loader.stop()
                logger.info("Progressive loader остановлен")
            
            # Stop performance monitoring
            if hasattr(self, 'performance_monitor') and getattr(Config, 'PERFORMANCE_MONITORING_ENABLED', True):
                await self.performance_monitor.stop_monitoring()
                logger.info("Performance monitoring остановлен")
            
            # Stop background processor
            bg_processor = get_background_processor()
            await bg_processor.stop(timeout=30)
            logger.info("Background processor остановлен")
            
            # Stop cache manager gracefully
            await self.cache_manager.shutdown()
            logger.info("Cache manager остановлен успешно")
            
            await self.db.disconnect()
            logger.info("Пул соединений закрыт")
        except Exception as e:
            logger.error(f"Ошибка при завершении работы: {e}")

    async def _start_cache_maintenance(self):
        """Запускает задачи обслуживания кеша"""
        try:
            # Cache maintenance tasks are handled internally by cache manager
            logger.info("Cache maintenance tasks started internally by cache manager")
            
            # Set up ELO preloading callback for cache warming
            from bot.utils.faceit_analyzer import faceit_analyzer
            self.cache_manager.set_preload_callback(faceit_analyzer.preload_elo_stats)
            logger.info("ELO preload callback registered with cache manager")
            
            # Explicitly bind database manager to faceit analyzer for user network warming
            faceit_analyzer.db_manager = self.db
            logger.info("Database manager explicitly bound to faceit analyzer")
            
            # Add initial cache warming based on popular profiles
            if Config.FACEIT_CACHE_WARMING_ENABLED:
                popular_profiles = await self.db.get_popular_profiles()
                if popular_profiles:
                    await faceit_analyzer.preload_elo_stats(popular_profiles)
                    logger.info(f"Initial cache warming started for {len(popular_profiles)} profiles")
                    
        except Exception as e:
            logger.error(f"Error starting cache maintenance: {e}")
    
    async def _preload_popular_profiles(self):
        """Предзагрузка популярных профилей при запуске бота"""
        try:
            from bot.utils.faceit_analyzer import faceit_analyzer
            
            logger.info("🚀 Starting popular profiles preloading...")
            preloaded_count = await faceit_analyzer.preload_popular_profiles()
            
            if preloaded_count > 0:
                logger.info(f"✅ Successfully preloaded {preloaded_count} popular profiles")
            else:
                logger.info("📊 No popular profiles found for preloading")
                
        except Exception as e:
            logger.error(f"❌ Error during popular profiles preloading: {e}")
            # Don't raise the exception to avoid blocking bot startup

    def setup_handlers(self):
        # Создаем экземпляры обработчиков
        start_handler_instance = StartHandler(self.db)
        profile_handler_instance = ProfileHandler(self.db)
        search_handler_instance = SearchHandler(self.db)
        teammates_handler_instance = TeammatesHandler(self.db)
        moderation_handler_instance = ModerationHandler(self.db)

        # === CONVERSATION HANDLER ДЛЯ СОЗДАНИЯ ПРОФИЛЕЙ ===
        profile_creation_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    profile_handler_instance.start_profile_creation, 
                    pattern="^(profile_create|create_profile)$"
                )
            ],
            states={
                ENTERING_NICKNAME: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        profile_handler_instance.handle_nickname_input
                    )
                ],
                SELECTING_ELO: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_elo_selection,
                        pattern="^(elo_custom|back|elo_back)$"
                    ),
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        profile_handler_instance.handle_exact_elo_input
                    )
                ],
                ENTERING_FACEIT_URL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        profile_handler_instance.handle_faceit_url
                    )
                ],
                SELECTING_ROLE: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_role_selection,
                        pattern="^(role_|back).*$"
                    )
                ],
                SELECTING_MAPS: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_maps_selection,
                        pattern="^(map_|maps_done|back).*$"
                    )
                ],
                SELECTING_PLAYTIME: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_playtime_selection,
                        pattern="^(time_|back).*$"
                    )
                ],
                SELECTING_CATEGORIES: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_categories_selection,
                        pattern="^(category_(mm_premier|faceit|tournaments|looking_for_team)|categories_done|back)$"
                    )
                ],
                ENTERING_DESCRIPTION: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_description_input,
                        pattern="^(skip_description|back).*$"
                    ),
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        profile_handler_instance.handle_description_input
                    )
                ],
                SELECTING_MEDIA: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_media_selection,
                        pattern="^(media_photo|media_video|media_skip|media_back)$"
                    ),
                    MessageHandler(
                        filters.PHOTO | filters.VIDEO,
                        profile_handler_instance.handle_media_selection
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    profile_handler_instance.cancel_creation,
                    pattern="^(cancel|back_to_main)$"
                ),
                CommandHandler("cancel", profile_handler_instance.cancel_creation)
            ],
            name="profile_creation",
            persistent=False
        )

        # === ОСНОВНЫЕ COMMAND HANDLERS ===
        self.application.add_handler(CommandHandler("start", start_handler_instance.start_command))
        self.application.add_handler(CommandHandler("help", start_handler_instance.help_command))
        self.application.add_handler(CommandHandler("profile", profile_handler_instance.profile_command))
        self.application.add_handler(CommandHandler("search", search_handler_instance.search_command))
        self.application.add_handler(CommandHandler("teammates", teammates_handler_instance.teammates_command))
        
        # Команды модерации
        self.application.add_handler(CommandHandler("add_moderator", moderation_handler_instance.add_moderator_command))
        self.application.add_handler(CommandHandler("remove_moderator", moderation_handler_instance.remove_moderator_command))
        self.application.add_handler(CommandHandler("list_moderators", moderation_handler_instance.list_moderators_command))

        # === CONVERSATION HANDLERS ===
        self.application.add_handler(profile_creation_handler)
        
        # ConversationHandler для редактирования медиа
        media_edit_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    profile_handler_instance.start_media_edit,
                    pattern="^(edit_media_add|edit_media_replace)$"
                )
            ],
            states={
                EDITING_MEDIA_TYPE: [
                    CallbackQueryHandler(
                        profile_handler_instance.handle_media_selection,
                        pattern="^(media_photo|media_video|media_back)$"
                    ),
                    MessageHandler(
                        filters.PHOTO | filters.VIDEO,
                        profile_handler_instance.handle_media_edit
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    profile_handler_instance.view_full_profile,
                    pattern="^(media_back|profile_view)$"
                )
            ],
            name="media_editing",
            persistent=False
        )
        
        self.application.add_handler(media_edit_handler)
        
        # === MESSAGE HANDLERS ===
        # Обработчик текстового ввода при редактировании профиля (должен быть перед модерацией)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            profile_handler_instance.handle_profile_edit_text
        ))
        
        # Обработчик текстовых сообщений для модерации (кастомные причины отклонения)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            moderation_handler_instance.handle_text_message
        ))
        
        # FALLBACK: Обработчик фото/видео вне ConversationHandler (для отладки)
        self.application.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO,
            profile_handler_instance.handle_orphan_media
        ))

        # === CALLBACK QUERY HANDLERS (порядок важен!) ===
        
        # Обработчики навигации по меню (должны быть после ConversationHandler)
        self.application.add_handler(CallbackQueryHandler(
            start_handler_instance.handle_callback_query,
            pattern="^(back_to_main|help|settings_menu|settings_|filter_|filters_reset|set_|toggle_|clear_|notify_|privacy_|visibility_|likes_|unblock_|confirm_privacy_|cancel_privacy_|reply_like_|skip_like_|view_profile_).*$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            profile_handler_instance.handle_callback_query,
            pattern="^(profile_menu|profile_view|profile_edit|profile_stats|edit_|confirm_edit_|cancel_edit_|elo_|role_|map_|time_|edit_categor|back).*$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            search_handler_instance.handle_callback_query,
            pattern="^(search_start|search_by_|search_random|search_elo_filter|search_categories_filter|apply_elo_filter|apply_categories_filter|categories_filter_|elo_filter_|like|skip).*$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            teammates_handler_instance.handle_callback_query,
            pattern="^(teammates_list|teammates_new|teammates_all)$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            moderation_handler_instance.handle_callback_query,
            pattern="^(moderation_menu|mod_queue|mod_approved|mod_rejected|mod_stats|approve_|reject_|reject_reason_|next_profile).*$"
        ))
        
        # Fallback handler для необработанных callbacks
        self.application.add_handler(CallbackQueryHandler(self._handle_unmatched_callback))

        # Обработчик ошибок
        self.application.add_error_handler(self._error_handler)
    
    async def _handle_unmatched_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced fallback handler для необработанных callback запросов"""
        query = update.callback_query
        if query:
            user_id = query.from_user.id
            username = query.from_user.username
            callback_data = query.data
            
            # Enhanced callback logging with full context
            user_info = f"user_id={user_id}"
            if username:
                user_info += f", username=@{username}"
            
            # Enhanced conversation state detection with more granular analysis
            conversation_state_info = self._detect_conversation_state(context)
            conversation_state = conversation_state_info["primary_state"]
            
            # Analyze callback pattern to understand why it failed
            callback_analysis = self._analyze_callback_pattern(callback_data, conversation_state, context)
            
            # Sanitize user data context for logging
            safe_context = {}
            if context.user_data:
                for key, value in context.user_data.items():
                    if key in ['creating_profile', 'editing_profile']:
                        if isinstance(value, dict):
                            safe_context[key] = {k: v for k, v in value.items() 
                                               if k not in ['faceit_url', 'game_nickname']}
                        else:
                            safe_context[key] = str(type(value))
                    elif key in ['editing_field', 'editing_media', 'selecting_media_type']:
                        safe_context[key] = value
                    else:
                        safe_context[key] = str(type(value)) if value else None
            
            # Enhanced logging with detailed callback analysis and conversation validation
            logger.warning(
                f"🚨 UNMATCHED CALLBACK: callback_data='{callback_data}', {user_info}, "
                f"conversation_state_info={conversation_state_info}, "
                f"callback_analysis={callback_analysis}, context={safe_context}, "
                f"timestamp={update.callback_query.message.date}"
            )
            
            # Enhanced user feedback with intelligent recovery options
            feedback_text, reply_markup = self._create_recovery_feedback(
                callback_data, conversation_state_info, context, callback_analysis
            )
            
            # Multi-level fallback strategy for error recovery
            try:
                await query.answer(feedback_text["short"], show_alert=True)
                if feedback_text["detailed"]:
                    await query.edit_message_text(
                        feedback_text["detailed"],
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Primary feedback failed: {e}. Attempting fallback recovery...")
                # Fallback recovery attempt
                try:
                    await query.answer("⚠️ Something went wrong. Please try returning to the main menu.", show_alert=True)
                    # Attempt to provide basic recovery options
                    fallback_keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")],
                        [InlineKeyboardButton("🔄 Try Again", callback_data="back_to_main")]
                    ])
                    await query.edit_message_text(
                        "⚠️ <b>Recovery Mode</b>\n\n"
                        "The system encountered an error. Please choose a recovery option:",
                        reply_markup=fallback_keyboard,
                        parse_mode='HTML'
                    )
                except Exception as final_error:
                    logger.critical(f"Complete fallback failure for user {user_id}: {final_error}")
                    # Last resort - try to clear user state
                    if context.user_data:
                        context.user_data.clear()
                    await query.answer("❌ System error. Your session has been reset.", show_alert=True)

    def _analyze_callback_pattern(self, callback_data: str, conversation_state: str, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Analyzes callback pattern to understand why it failed"""
        analysis = {
            "pattern_type": "unknown",
            "likely_cause": "undefined",
            "recovery_suggestion": "return_to_menu",
            "confidence": 0.0
        }
        
        # Check for common callback patterns
        known_patterns = [
            "profile_", "search_", "edit_", "back", "cancel", "confirm_",
            "role_", "map_", "time_", "elo_", "media_", "category_"
        ]
        
        # Pattern matching analysis
        for pattern in known_patterns:
            if callback_data.startswith(pattern):
                analysis["pattern_type"] = pattern.rstrip("_")
                analysis["confidence"] = 0.8
                break
        
        # Analyze likely causes
        if "back" in callback_data.lower():
            analysis["likely_cause"] = "navigation_mismatch"
            analysis["recovery_suggestion"] = "provide_navigation"
        elif conversation_state == "none" and any(p in callback_data for p in ["edit_", "confirm_", "save_"]):
            analysis["likely_cause"] = "outdated_message"
            analysis["recovery_suggestion"] = "refresh_context"
        elif conversation_state != "none" and callback_data in ["profile_create", "search_start"]:
            analysis["likely_cause"] = "conversation_conflict"
            analysis["recovery_suggestion"] = "resolve_conversation"
        else:
            analysis["likely_cause"] = "handler_mismatch"
            analysis["recovery_suggestion"] = "general_recovery"
        
        return analysis
    
    def _get_active_conversation_handlers(self, context: ContextTypes.DEFAULT_TYPE) -> list:
        """Gets list of currently active conversation handlers"""
        active_handlers = []
        
        # Check for conversation handler persistence data
        if hasattr(context, '_conversation_states') and context._conversation_states:
            for handler_name, state in context._conversation_states.items():
                if state is not None:
                    active_handlers.append(f"{handler_name}:{state}")
        
        # Check context user_data for conversation indicators
        if context.user_data:
            if context.user_data.get('creating_profile'):
                active_handlers.append("profile_creation")
            if context.user_data.get('editing_profile'):
                active_handlers.append("profile_editing")
            if context.user_data.get('editing_media'):
                active_handlers.append("media_editing")
        
        return active_handlers if active_handlers else ["none"]

    def _detect_conversation_state(self, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Enhanced conversation state detection with granular analysis"""
        state_info = {
            "primary_state": "none",
            "active_handlers": [],
            "conversation_data_integrity": "valid",
            "step_number": None,
            "confidence": 1.0,
            "validation_errors": [],
            "suggested_recovery": "none",
            "conversation_duration": None,
            "last_transition": None
        }
        
        if not context.user_data:
            return state_info
        
        # Check for active ConversationHandler instances
        active_handlers = self._get_active_conversation_handlers(context)
        state_info["active_handlers"] = active_handlers
        
        # Detect primary conversation state with validation
        if 'creating_profile' in context.user_data:
            state_info["primary_state"] = "creating_profile"
            profile_data = context.user_data.get('creating_profile', {})
            
            # Validate conversation data integrity
            if not isinstance(profile_data, dict):
                state_info["conversation_data_integrity"] = "corrupted"
                state_info["validation_errors"].append("profile_data_not_dict")
                state_info["suggested_recovery"] = "restart_profile_creation"
            else:
                # Check required fields and conversation completeness
                required_fields = ['game_nickname', 'current_elo']
                missing_fields = [field for field in required_fields if not profile_data.get(field)]
                if missing_fields:
                    state_info["conversation_data_integrity"] = "incomplete"
                    state_info["validation_errors"].extend(missing_fields)
                    state_info["suggested_recovery"] = "continue_from_last_step"
                    
        elif 'editing_profile' in context.user_data or context.user_data.get('editing_field'):
            state_info["primary_state"] = "editing_profile"
            editing_field = context.user_data.get('editing_field')
            if editing_field:
                state_info["step_number"] = f"editing_{editing_field}"
            
            # Validate editing context
            if context.user_data.get('editing_profile') and not isinstance(context.user_data['editing_profile'], dict):
                state_info["conversation_data_integrity"] = "corrupted"
                state_info["validation_errors"].append("editing_data_corrupted")
                state_info["suggested_recovery"] = "return_to_profile_view"
                
        elif context.user_data.get('editing_media'):
            state_info["primary_state"] = "editing_media"
            media_type = context.user_data.get('selecting_media_type')
            if media_type:
                state_info["step_number"] = f"selecting_{media_type}"
            
            # Validate media editing context
            if not context.user_data.get('user_profile_data'):
                state_info["conversation_data_integrity"] = "incomplete"
                state_info["validation_errors"].append("missing_profile_context")
                state_info["suggested_recovery"] = "return_to_profile_view"
                
        elif context.user_data.get('searching'):
            state_info["primary_state"] = "searching"
            search_data = context.user_data.get('search_filters', {})
            if search_data and not isinstance(search_data, dict):
                state_info["conversation_data_integrity"] = "corrupted"
                state_info["validation_errors"].append("search_filters_corrupted")
                state_info["suggested_recovery"] = "reset_search"
        else:
            # Check for orphaned conversation data
            conversation_keys = ['creating_profile', 'editing_profile', 'editing_field', 'editing_media', 'searching']
            orphaned_keys = [key for key in conversation_keys if key in context.user_data]
            
            if orphaned_keys:
                state_info["primary_state"] = "unknown_with_data"
                state_info["conversation_data_integrity"] = "orphaned"
                state_info["validation_errors"].extend([f"orphaned_{key}" for key in orphaned_keys])
                state_info["suggested_recovery"] = "clean_orphaned_data"
                state_info["confidence"] = 0.3
            else:
                state_info["primary_state"] = "unknown"
        
        # Track conversation history and patterns
        if context.user_data.get('conversation_start_time'):
            import time
            duration = time.time() - context.user_data['conversation_start_time']
            state_info["conversation_duration"] = duration
            
            # Detect if conversation is taking too long (potential stuck state)
            if duration > 300:  # 5 minutes
                state_info["validation_errors"].append("conversation_timeout")
                state_info["suggested_recovery"] = "reset_with_data_preservation"
        
        # Check for conversation loops (repeated failures)
        error_count = context.user_data.get('callback_error_count', 0)
        if error_count > 3:
            state_info["validation_errors"].append("repeated_callback_errors")
            state_info["suggested_recovery"] = "reset_conversation_state"
            state_info["confidence"] = 0.2
        
        return state_info
    
    def _create_recovery_feedback(self, callback_data: str, conversation_state_info: dict, context: ContextTypes.DEFAULT_TYPE, callback_analysis: dict):
        """Creates enhanced user-friendly feedback with intelligent recovery options"""
        # Extract primary state for compatibility
        conversation_state = conversation_state_info["primary_state"]
        confidence = conversation_state_info.get("confidence", 1.0)
        validation_errors = conversation_state_info.get("validation_errors", [])
        suggested_recovery = conversation_state_info.get("suggested_recovery", "none")
        
        # Initialize with user-friendly defaults
        short_feedback = "⚠️ We're having trouble with that button"
        detailed_feedback = ""
        keyboard = []
        
        # Increment error count for pattern detection
        ud = context.user_data
        ud['callback_error_count'] = ud.get('callback_error_count', 0) + 1
        
        # Analyze callback failure and create user-friendly explanation
        callback_explanation = self._get_user_friendly_explanation(callback_analysis, callback_data)
        
        # Progressive assistance based on error frequency
        assistance_level = min(context.user_data.get('callback_error_count', 1), 4)
        
        # Enhanced user-friendly messaging based on conversation state
        if conversation_state == "creating_profile":
            short_feedback = "⚠️ Let's get your profile back on track"
            
            if validation_errors:
                if "profile_data_not_dict" in validation_errors:
                    detailed_feedback = (
                        "🔧 <b>Profile Creation Issue</b>\n\n"
                        "It looks like there was a technical hiccup with your profile data. "
                        "Don't worry - this happens sometimes!\n\n"
                        f"📋 What we tried: <code>{callback_data}</code>\n"
                        f"🔍 Issue: {callback_explanation}\n\n"
                        "✨ <b>How to fix this:</b>"
                    )
                else:
                    detailed_feedback = (
                        "📝 <b>Profile Creation in Progress</b>\n\n"
                        "We noticed you're in the middle of creating your profile. "
                        "Let's continue where you left off!\n\n"
                        f"📋 Button pressed: <code>{callback_data}</code>\n"
                        f"🔍 Analysis: {callback_explanation}\n\n"
                        "✨ <b>Choose what works best for you:</b>"
                    )
            else:
                detailed_feedback = (
                    "📝 <b>Profile Creation Helper</b>\n\n"
                    "Looks like that button isn't quite working right now. "
                    "No worries - we have several ways to get you back on track!\n\n"
                    f"🔍 Analysis: {callback_explanation}\n\n"
                    "✨ <b>What would you like to do?</b>"
                )
            
            # Smart recovery options for profile creation
            keyboard.extend([
                [InlineKeyboardButton("🔄 Continue Creating Profile", callback_data="profile_create")],
                [InlineKeyboardButton("💾 Save Current Progress", callback_data="back_to_main")],
                [InlineKeyboardButton("🆘 Step-by-Step Guide", callback_data="help")]
            ])
            
        elif conversation_state == "editing_profile":
            short_feedback = "⚠️ Небольшая ошибка в редактировании профиля"
            detailed_feedback = (
                "✏️ <b>Помощник редактирования профиля</b>\n\n"
                "Произошла небольшая ошибка в навигации. Давайте быстро "
                "исправим это и продолжим редактирование!\n\n"
                f"🔍 Что произошло: {callback_explanation}\n"
                f"⚙️ Уровень уверенности: {confidence:.0%}\n\n"
                "✨ <b>Выберите подходящий вариант:</b>"
            )
            
            # Context-aware editing recovery
            if conversation_state_info.get("step_number"):
                current_step = conversation_state_info["step_number"]
                keyboard.append([InlineKeyboardButton(f"🔄 Продолжить {current_step.replace('_', ' ').title()}", callback_data="profile_edit")])
            
            keyboard.extend([
                [InlineKeyboardButton("👤 Посмотреть мой профиль", callback_data="profile_menu")],
                [InlineKeyboardButton("✏️ Начать редактирование заново", callback_data="profile_edit")],
                [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
            ])
            
        elif conversation_state == "editing_media":
            short_feedback = "⚠️ Media upload hit a snag"
            detailed_feedback = (
                "🖼️ <b>Media Upload Assistant</b>\n\n"
                "The media upload process ran into a small issue. "
                "Don't worry - we can easily get this sorted!\n\n"
                f"🔍 What happened: {callback_explanation}\n\n"
                "✨ <b>Let's fix this together:</b>"
            )
            
            keyboard.extend([
                [InlineKeyboardButton("📸 Try Upload Again", callback_data="edit_media_add")],
                [InlineKeyboardButton("🔄 Add Media", callback_data="edit_media_add"), InlineKeyboardButton("🔄 Replace Media", callback_data="edit_media_replace")],
                [InlineKeyboardButton("⏭️ Skip Media for Now", callback_data="profile_menu")]
            ])
            
        elif conversation_state == "searching":
            short_feedback = "⚠️ Search needs a quick restart"
            detailed_feedback = (
                "🔍 <b>Teammate Search Helper</b>\n\n"
                "Your search hit a small technical bump. Let's get you back "
                "to finding awesome teammates!\n\n"
                f"🔍 Issue details: {callback_explanation}\n\n"
                "✨ <b>What would you prefer?</b>"
            )
            
            keyboard.extend([
                [InlineKeyboardButton("🔍 Fresh Search", callback_data="search_start")],
                [InlineKeyboardButton("🎯 ELO Filters", callback_data="search_elo_filter"), InlineKeyboardButton("🎯 Category Filters", callback_data="search_categories_filter")],
                [InlineKeyboardButton("🎲 Random Match", callback_data="search_random")]
            ])
            
        elif conversation_state == "unknown_with_data":
            short_feedback = "⚠️ Let's clean things up"
            detailed_feedback = (
                "🧹 <b>Session Cleanup Helper</b>\n\n"
                "It looks like there's some old data that's causing confusion. "
                "We can quickly clean this up and get you back to using the bot smoothly!\n\n"
                f"🔍 Technical details: {callback_explanation}\n"
                f"🗂️ Issues found: {', '.join(validation_errors)}\n\n"
                "✨ <b>Recommended action:</b>"
            )
            
            keyboard.extend([
                [InlineKeyboardButton("🧹 Clean & Start Fresh", callback_data="back_to_main")],
                [InlineKeyboardButton("🔧 Advanced Recovery", callback_data="back_to_main")]
            ])
        else:
            detailed_feedback = (
                "🤖 <b>Smart Recovery Assistant</b>\n\n"
                "That button seems to have gotten lost in translation! "
                "But don't worry - I have several ways to get you back on track.\n\n"
                f"🔍 What I found: {callback_explanation}\n"
                f"📊 Analysis confidence: {confidence:.0%}\n\n"
                "✨ <b>Here are your best options:</b>"
            )
        
        # Progressive assistance levels
        if assistance_level >= 2:
            keyboard.append([InlineKeyboardButton("📚 Detailed Help Guide", callback_data="back_to_main")])
        
        if assistance_level >= 3:
            keyboard.append([InlineKeyboardButton("🔧 Advanced Troubleshooting", callback_data="back_to_main")])
            
        if assistance_level >= 4:
            keyboard.append([InlineKeyboardButton("🐛 Report This Issue", callback_data="back_to_main")])
        
        # Smart recovery options based on analysis
        if callback_analysis.get("recovery_suggestion") == "provide_navigation":
            keyboard.insert(0, [InlineKeyboardButton("🧭 Помощь с навигацией", callback_data="back_to_main")])
        elif callback_analysis.get("recovery_suggestion") == "refresh_context":
            keyboard.insert(0, [InlineKeyboardButton("🔄 Обновить и попробовать снова", callback_data="back_to_main")])
        
        # Always provide main menu as fallback
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")])
        
        # Add gentle cancel option for active conversations
        if conversation_state in ["creating_profile", "editing_profile", "editing_media"]:
            keyboard.append([InlineKeyboardButton("💤 Сделать перерыв", callback_data="cancel")])
        
        return {
            "short": short_feedback,
            "detailed": detailed_feedback
        }, InlineKeyboardMarkup(keyboard) if keyboard else None
    
    def _get_user_friendly_explanation(self, callback_analysis: dict, callback_data: str) -> str:
        """Converts technical callback analysis into user-friendly explanations"""
        pattern_type = callback_analysis.get("pattern_type", "unknown")
        likely_cause = callback_analysis.get("likely_cause", "undefined")
        
        explanations = {
            "navigation_mismatch": "The navigation button you pressed doesn't match your current location",
            "outdated_message": "This button is from an older message that's no longer active", 
            "conversation_conflict": "There's a conflict between different conversation flows",
            "handler_mismatch": "The button doesn't have a matching handler in the current context",
            "undefined": f"Button '{callback_data}' encountered an unexpected issue"
        }
        
        base_explanation = explanations.get(likely_cause, explanations["undefined"])
        
        if pattern_type != "unknown":
            base_explanation += f" (Related to {pattern_type} functionality)"
            
        return base_explanation

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Улучшенный обработчик ошибок с умной обработкой сетевых проблем и фонового процессора
        """
        error = context.error
        
        # Check background processor health on repeated errors
        bg_processor = get_background_processor()
        if not bg_processor.is_healthy():
            logger.warning("Background processor не в состоянии здоровья при обработке ошибки")
            processor_stats = bg_processor.get_stats()
            logger.info(f"Background processor статистика: {processor_stats}")
        
        # Record error in performance monitoring
        if hasattr(self, 'performance_monitor') and self.performance_monitor:
            try:
                # Update system health score based on error type
                health_impact = 0.1 if is_network_error else 0.05
                current_health = getattr(self.performance_monitor.current_metrics, 'system_health_score', 1.0)
                new_health = max(0.0, current_health - health_impact)
                self.performance_monitor.collect_health_metrics(
                    connectivity_status=not is_network_error,
                    health_score=new_health
                )
            except Exception as e:
                logger.debug(f"Error updating performance metrics in error handler: {e}")
        
        # Проверяем тип ошибки
        is_network_error = isinstance(error, (NetworkError, TimedOut, httpx.ConnectError, httpx.TimeoutException))
        is_dns_error = isinstance(error, httpx.ConnectError) and "getaddrinfo failed" in str(error)
        is_background_processor_error = "Background processor" in str(error) or "background" in str(error).lower()
        
        if is_background_processor_error:
            # Handle background processor specific errors
            logger.warning(f"Background processor ошибка: {error}")
            processor_stats = bg_processor.get_stats()
            logger.info(f"Processor stats при ошибке: {processor_stats}")
            # Continue processing to inform user if needed
        elif is_dns_error or is_network_error:
            # Логируем сетевые ошибки в специальный network logger
            if update is None:
                network_logger.warning(f"Сетевая ошибка при получении обновлений: {error}")
            else:
                network_logger.warning(f"Сетевая ошибка при обработке обновления {update}: {error}")
            
            # Не пытаемся отправлять сообщения пользователю при сетевых ошибках
            return
        
        # Логируем остальные ошибки как ERROR
        logger.error(f"Ошибка при обработке обновления {update}: {error}", exc_info=True)
        
        # Попытаемся отправить пользователю сообщение об ошибке (только для не-сетевых ошибок)
        try:
            if update and hasattr(update, 'effective_message') and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Произошла ошибка при обработке вашего запроса.\n"
                    "Попробуйте еще раз или обратитесь в поддержку.",
                    reply_markup=Keyboards.back_button("back_to_main")
                )
            elif update and hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer("❌ Произошла ошибка. Попробуйте еще раз.", show_alert=True)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

    async def _reconnect_db(self):
        """Переподключение к базе данных"""
        try:
            await self.db.disconnect()
        except Exception:
            pass  # игнорируем ошибки при отключении
        
        await self.db.connect()
        await self.db.init_database()

    def run(self):
        """
        Запуск бота с автоматическим переподключением при сетевых ошибках
        """
        logger.info("Запуск CS2 Teammeet Bot с пулом соединений...")
        
        max_retries = 5
        retry_delay = 5  # начальная задержка в секундах
        
        for retry_count in range(max_retries + 1):
            try:
                # Запускаем бота в режиме polling
                self.application.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                    # Параметры для повышения надежности
                    poll_interval=1.0,  # Интервал между запросами к API (сек)
                    bootstrap_retries=3,  # Количество попыток подключения при старте
                    timeout=30  # Таймаут long polling (сек)
                )
                
                # Если дошли сюда, значит бот завершился нормально
                break
                
            except KeyboardInterrupt:
                logger.info("Получен сигнал остановки. Завершение работы...")
                break
                
            except (NetworkError, TimedOut, httpx.ConnectError, httpx.TimeoutException) as e:
                if retry_count < max_retries:
                    network_logger.warning(
                        f"Сетевая ошибка при запуске бота (попытка {retry_count + 1}/{max_retries + 1}): {e}. "
                        f"Повтор через {retry_delay} секунд..."
                    )
                    
                    # Проверяем состояние соединения и кеша
                    health_status = asyncio.run(self.health_monitor.check_connection())
                    cache_health = asyncio.run(self.cache_manager.health_check())
                    
                    if health_status:
                        logger.info("Health check пройден, проблема может быть временной")
                    if cache_health.get('status') == 'healthy':
                        logger.info("Cache health check пройден")
                    else:
                        logger.warning(f"Cache health issues detected: {cache_health.get('error', 'Unknown')}")
                    
                    # Exponential backoff с jitter
                    jitter = random.uniform(0.5, 1.5)  # добавляем случайность
                    actual_delay = retry_delay * jitter
                    
                    asyncio.run(asyncio.sleep(actual_delay))
                    retry_delay *= 2  # удваиваем задержку для следующей попытки
                    
                    # Попытаемся переинициализировать соединение с БД
                    try:
                        asyncio.run(self._reconnect_db())
                        logger.info("Соединение с БД переустановлено")
                    except Exception as db_error:
                        logger.warning(f"Не удалось переустановить соединение с БД: {db_error}")
                    
                else:
                    logger.critical(f"Исчерпаны попытки переподключения. Последняя ошибка: {e}")
                    raise
                    
            except Exception as e:
                logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
                raise

# Global shared cache manager instance - will be set when bot initializes
_shared_cache_manager: Optional['FaceitCacheManager'] = None
# Global shared database manager instance - will be set when bot initializes
_shared_db_manager: Optional['DatabaseManager'] = None

def get_shared_cache_manager() -> Optional['FaceitCacheManager']:
    """Get the shared cache manager instance created by the main bot"""
    return _shared_cache_manager

def _set_shared_cache_manager(cache_manager: 'FaceitCacheManager') -> None:
    """Internal function to set the shared cache manager instance"""
    global _shared_cache_manager
    _shared_cache_manager = cache_manager

def get_shared_db_manager() -> Optional['DatabaseManager']:
    """Get the shared database manager instance created by the main bot"""
    return _shared_db_manager

def _set_shared_db_manager(db_manager: 'DatabaseManager') -> None:
    """Internal function to set the shared database manager instance"""
    global _shared_db_manager
    _shared_db_manager = db_manager

def main():
    """Главная функция запуска бота"""
    try:
        bot = CS2TeammeetBot()
        # Export the cache manager for global access
        _set_shared_cache_manager(bot.get_cache_manager())
        # Export the database manager for global access
        _set_shared_db_manager(bot.db)
        bot.run()
    except Exception as e:
        logger.critical(f"Не удалось запустить бота: {e}", exc_info=True)
        exit(1)

if __name__ == '__main__':
    main() 