"""
Обработчики для работы с тиммейтами
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname
from bot.database.operations import DatabaseManager

logger = logging.getLogger(__name__)

class TeammatesHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def teammates_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /teammates - показывает тиммейтов пользователя"""
        user_id = update.effective_user.id
        
        # Проверяем есть ли профиль
        has_profile = await self.db.has_profile(user_id)
        if not has_profile:
            await update.message.reply_text(
                "❌ <b>Для просмотра тиммейтов нужен профиль!</b>\n\n"
                "Сначала создайте свой профиль.",
                reply_markup=Keyboards.profile_menu(False),
                parse_mode='HTML'
            )
            return
        
        # Получаем тиммейтов пользователя
        teammates = await self.db.get_user_matches(user_id)
        
        if not teammates:
            await update.message.reply_text(
                "💔 <b>У вас пока нет тиммейтов</b>\n\n"
                "Начните поиск тиммейтов, чтобы найти игроков "
                "с которыми можно играть!",
                reply_markup=Keyboards.teammates_menu(),
                parse_mode='HTML'
            )
            return
        
        # Показываем статистику тиммейтов
        await self.show_teammates_overview(update, teammates)

    async def show_teammates_overview(self, update, teammates):
        """Показывает обзор тиммейтов"""
        total_teammates = len(teammates)
        new_teammates = len([m for m in teammates if m.is_active])
        
        text = (
            f"💝 <b>Ваши тиммейты ({total_teammates})</b>\n\n"
            f"🆕 <b>Новые тиммейты:</b> {new_teammates}\n"
            f"📋 <b>Всего тиммейтов:</b> {total_teammates}\n\n"
            "Выберите действие:"
        )
        
        await update.message.reply_text(
            text,
            reply_markup=Keyboards.teammates_menu(),
            parse_mode='HTML'
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback запросы тиммейтов"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        if data == "teammates_list":
            await self.show_teammates_list(update, context)
        elif data == "teammates_new":
            await self.show_new_teammates(update, context)
        elif data == "teammates_all":
            await self.show_all_teammates(update, context)

    async def show_teammates_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список тиммейтов"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        teammates = await self.db.get_user_matches(user_id)
        
        if not teammates:
            await query.edit_message_text(
                "💔 У вас пока нет тиммейтов",
                reply_markup=Keyboards.back_button("back_to_main")
            )
            return
        
        # Показываем первых 5 тиммейтов
        await self.show_teammates_page(query, teammates[:5], 0, len(teammates))

    async def show_new_teammates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает новых тиммейтов"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        teammates = await self.db.get_user_matches(user_id, active_only=True)
        
        if not teammates:
            await query.edit_message_text(
                "📭 <b>Новых тиммейтов нет</b>\n\n"
                "Продолжайте поиск тиммейтов!",
                reply_markup=Keyboards.back_button("back_to_main"),
                parse_mode='HTML'
            )
            return
        
        await self.show_teammates_page(query, teammates, 0, len(teammates), "Новые")



    async def show_all_teammates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает всех тиммейтов"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        teammates = await self.db.get_user_matches(user_id, active_only=False)
        
        if not teammates:
            await query.edit_message_text(
                "📭 У вас нет тиммейтов",
                reply_markup=Keyboards.back_button("back_to_main")
            )
            return
        
        await self.show_teammates_page(query, teammates, 0, len(teammates), "Все")

    async def show_teammates_page(self, query, teammates, page, total, title=""):
        """Показывает страницу тиммейтов"""
        text = f"💝 <b>{title} тиммейты</b> ({total})\n\n"
        
        for i, match in enumerate(teammates, 1):
            # Определяем ID партнера
            partner_id = match.user2_id if match.user1_id == query.from_user.id else match.user1_id
            
            # Получаем данные партнера
            partner = await self.db.get_user(partner_id)
            partner_profile = await self.db.get_profile(partner_id)
            
            if partner and partner_profile:
                # Используем игровой ник вместо telegram данных
                name = partner_profile.game_nickname
                telegram_contact = f"@{partner.username}" if partner.username else partner.first_name
                
                # Получаем ELO статистику через Faceit API
                elo_stats = None
                try:
                    if partner_profile.game_nickname and partner_profile.game_nickname.strip():
                        from bot.utils.faceit_analyzer import faceit_analyzer
                        elo_stats = await faceit_analyzer.get_elo_stats_by_nickname(partner_profile.game_nickname)
                except Exception as e:
                    logger.debug(f"Не удалось получить ELO статистику для {partner_profile.game_nickname}: {e}")
                
                # Отображаем ELO с мин/макс значениями если доступно (МЯГКАЯ ПРОВЕРКА TEAMMATES)
                if elo_stats and (elo_stats.get('lowest_elo', 0) > 0 or elo_stats.get('highest_elo', 0) > 0):
                    from bot.utils.cs2_data import format_faceit_elo_display
                    logger.info(f"🔥 TEAMMATES: Показываем ELO с мин/макс для {partner_profile.game_nickname}: мин={elo_stats.get('lowest_elo', 0)} макс={elo_stats.get('highest_elo', 0)}")
                    elo_display = format_faceit_elo_display(partner_profile.faceit_elo, elo_stats.get('lowest_elo'), elo_stats.get('highest_elo'))
                else:
                    if elo_stats:
                        logger.warning(f"⚠️ TEAMMATES: ELO статистика получена, но мин/макс не валидны: {elo_stats}")
                    elo_display = format_elo_display(partner_profile.faceit_elo)
                
                role = format_role_display(partner_profile.role)
                nickname = extract_faceit_nickname(partner_profile.faceit_url)
                
                # Статус тиммейта
                status = "🟢 Новый" if match.is_active else "⚪ Просмотрен"
                
                text += f"{i}. <b>{name}</b> (Faceit: {nickname})\n"
                text += f"   {elo_display} • {role}\n"
                text += f"   {status} • {match.created_at.strftime('%d.%m.%Y')}\n"
                text += f"   💬 Telegram: {telegram_contact}\n\n"
            else:
                text += f"{i}. <b>Тиммейт #{partner_id}</b>\n"
                text += f"   Профиль недоступен\n\n"
        
        # Ограничиваем длину сообщения
        if len(text) > 3500:
            text = text[:3500] + "...\n\n(показаны первые тиммейты)"
        
        text += "\n💡 <b>Как связаться:</b>\n"
        text += "• Напишите в Telegram по указанному контакту\n"
        text += "• Договоритесь об игре!"
        
        await query.edit_message_text(
            text,
            reply_markup=Keyboards.teammates_menu(),
            parse_mode='HTML'
        )