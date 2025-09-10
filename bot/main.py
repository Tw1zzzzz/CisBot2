"""
CS2 Teammeet Bot - Основная точка входа
"""
import logging
import os
import asyncio
import random
from warnings import filterwarnings
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.warnings import PTBUserWarning
from telegram.error import NetworkError, TimedOut
import httpx

from .config import Config, setup_logging
from .utils.keyboards import Keyboards
from .utils.health_monitor import HealthMonitor
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
    
    async def _post_init(self, application):
        try:
            await self.db.connect()
            await self.db.init_database()
            logger.info("База данных и пул соединений инициализированы")
        except Exception:
            logger.critical("DB init failed", exc_info=True)
            raise
    
    async def _post_shutdown(self, application):
        try:
            await self.db.disconnect()
            logger.info("Пул соединений закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии пула: {e}")

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
            pattern="^(back_to_main|help|settings_menu|settings_|filter_|filters_reset|set_|toggle_|clear_|notify_|privacy_|visibility_|likes_|unblock_|confirm_privacy_|cancel_privacy_).*$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            profile_handler_instance.handle_callback_query,
            pattern="^(profile_menu|profile_view|profile_edit|profile_stats|edit_|confirm_edit_|cancel_edit_|elo_|role_|map_|time_|edit_categor).*$"
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
        """Fallback handler для необработанных callback запросов"""
        query = update.callback_query
        if query:
            logger.warning(f"🚨 НЕОБРАБОТАННЫЙ CALLBACK: '{query.data}' от пользователя {query.from_user.id}")
            await query.answer("❌ Команда не найдена", show_alert=True)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Улучшенный обработчик ошибок с умной обработкой сетевых проблем
        """
        error = context.error
        
        # Проверяем тип ошибки
        is_network_error = isinstance(error, (NetworkError, TimedOut, httpx.ConnectError, httpx.TimeoutException))
        is_dns_error = isinstance(error, httpx.ConnectError) and "getaddrinfo failed" in str(error)
        
        if is_dns_error or is_network_error:
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
                    
                    # Проверяем состояние соединения
                    health_status = asyncio.run(self.health_monitor.check_connection())
                    if health_status:
                        logger.info("Health check пройден, проблема может быть временной")
                    
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

def main():
    """Главная функция запуска бота"""
    try:
        bot = CS2TeammeetBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Не удалось запустить бота: {e}", exc_info=True)
        exit(1)

if __name__ == '__main__':
    main() 