"""
Обработчик для работы с матчами (взаимными лайками)
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.database.operations import DatabaseManager
from bot.utils.subscription_middleware import subscription_required

logger = logging.getLogger(__name__)

class MatchesHandler:
    """
    Обработчик для работы с матчами (взаимными лайками).
    Предоставляет базовый функционал для совместимости с существующими импортами.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Инициализирует обработчик матчей.
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db = db_manager
        logger.info("MatchesHandler инициализирован")

    async def matches_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Команда для работы с матчами.
        Заглушка для будущего функционала.
        """
        user_id = update.effective_user.id
        logger.info(f"Команда matches от пользователя {user_id}")
        
        # Проверяем есть ли профиль
        has_profile = await self.db.has_profile(user_id)
        if not has_profile:
            await update.message.reply_text(
                "❌ <b>Для просмотра матчей нужен профиль!</b>\n\n"
                "Сначала создайте свой профиль.",
                reply_markup=Keyboards.profile_menu(False),
                parse_mode='HTML'
            )
            return
        
        # Базовый ответ
        await update.message.reply_text(
            "🔄 <b>Функционал матчей</b>\n\n"
            "Этот раздел находится в разработке.\n"
            "Пока вы можете использовать раздел 'Тиммейты' для просмотра ваших совпадений.",
            reply_markup=Keyboards.back_button("back_to_main"),
            parse_mode='HTML'
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обрабатывает callback запросы связанные с матчами.
        Заглушка для будущего функционала.
        """
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        logger.info(f"MatchesHandler получил callback: {data} от пользователя {user_id}")
        
        await query.answer()
        
        # Базовая обработка
        if data == "matches_back" or data == "back_to_main":
            from bot.handlers.start import StartHandler
            start_handler = StartHandler(self.db)
            await start_handler.show_main_menu(query)
        else:
            # Неизвестный callback
            await query.edit_message_text(
                "🔄 <b>Функционал в разработке</b>\n\n"
                "Этот раздел будет доступен в следующих обновлениях.",
                reply_markup=Keyboards.back_button("back_to_main"),
                parse_mode='HTML'
            )

    async def get_user_matches(self, user_id: int):
        """
        Получает матчи пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            List[Match]: Список матчей пользователя
        """
        logger.info(f"Запрос матчей для пользователя {user_id}")
        return await self.db.get_user_matches(user_id)

    async def create_match(self, user1_id: int, user2_id: int):
        """
        Создает новый матч между пользователями.
        
        Args:
            user1_id: ID первого пользователя
            user2_id: ID второго пользователя
            
        Returns:
            bool: True если матч создан успешно, False в противном случае
        """
        logger.info(f"Создание матча между пользователями {user1_id} и {user2_id}")
        return await self.db.create_match(user1_id, user2_id)

    async def check_match_exists(self, user1_id: int, user2_id: int):
        """
        Проверяет существование взаимного лайка (матча) между пользователями.
        
        Args:
            user1_id: ID первого пользователя
            user2_id: ID второго пользователя
            
        Returns:
            bool: True если между пользователями есть взаимный лайк, False в противном случае
        """
        logger.info(f"Проверка матча между пользователями {user1_id} и {user2_id}")
        return await self.db.check_mutual_like(user1_id, user2_id)
