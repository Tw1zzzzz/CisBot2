"""
Обработчики для работы с тиммейтами
"""
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.keyboards import Keyboards
from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname
from bot.utils.background_processor import TaskPriority
from bot.utils.progressive_loader import get_progressive_loader
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
        """Показывает страницу тиммейтов с улучшенной прогрессивной загрузкой"""
        text = f"💝 <b>{title} тиммейты</b> ({total})\n\n"
        
        # Фаза 1: Сбор всех данных партнеров и никнеймов
        teammate_data = []
        nicknames_to_fetch = []
        
        for i, match in enumerate(teammates, 1):
            # Определяем ID партнера
            partner_id = match.user2_id if match.user1_id == query.from_user.id else match.user1_id
            
            # Получаем данные партнера
            partner = await self.db.get_user(partner_id)
            partner_profile = await self.db.get_profile(partner_id)
            
            teammate_info = {
                'index': i,
                'match': match,
                'partner_id': partner_id,
                'partner': partner,
                'partner_profile': partner_profile
            }
            
            teammate_data.append(teammate_info)
            
            # Собираем никнеймы для батч-запросов
            if partner_profile and partner_profile.game_nickname and partner_profile.game_nickname.strip():
                nicknames_to_fetch.append(partner_profile.game_nickname)
            else:
                nicknames_to_fetch.append(None)  # Placeholder для сохранения индексов
        
        # Фаза 2: Создание батч-запросов для всех ELO статистик
        from bot.utils.faceit_analyzer import faceit_analyzer
        futures = []
        
        for nickname in nicknames_to_fetch:
            if nickname:
                try:
                    # Use NORMAL priority для teammates batch loading
                    elo_future = await faceit_analyzer.get_elo_stats_by_nickname_priority(nickname, TaskPriority.NORMAL)
                    futures.append(elo_future)
                except Exception as e:
                    logger.debug(f"❌ Ошибка создания future для {nickname}: {e}")
                    # Create a failed future
                    failed_future = asyncio.get_event_loop().create_future()
                    failed_future.set_result(None)
                    futures.append(failed_future)
            else:
                # Create None future for teammates without nicknames
                none_future = asyncio.get_event_loop().create_future()
                none_future.set_result(None)
                futures.append(none_future)
        
        # Фаза 3: Форматирование базового текста с плейсхолдерами для загрузки
        basic_text = text  # Save header
        
        # Show basic teammate info immediately with loading placeholders  
        for i, teammate_info in enumerate(teammate_data):
            match = teammate_info['match']
            partner = teammate_info['partner']
            partner_profile = teammate_info['partner_profile']
            partner_id = teammate_info['partner_id']
            index = teammate_info['index']
            
            if partner and partner_profile:
                # Используем игровой ник вместо telegram данных
                name = partner_profile.game_nickname
                telegram_contact = f"@{partner.username}" if partner.username else partner.first_name
                role = format_role_display(partner_profile.role)
                nickname = extract_faceit_nickname(partner_profile.faceit_url)
                
                # Статус тиммейта
                status = "🟢 Новый" if match.is_active else "⚪ Просмотрен"
                
                # Show loading placeholder for ELO while batch processing
                elo_display = Keyboards.elo_loading_placeholder()
                
                basic_text += f"{index}. <b>{name}</b> (Faceit: {nickname})\n"
                basic_text += f"   🎯 ELO: {elo_display} • {role}\n"
                basic_text += f"   {status} • {match.created_at.strftime('%d.%m.%Y')}\n"
                basic_text += f"   💬 Telegram: {telegram_contact}\n\n"
            else:
                basic_text += f"{index}. <b>Тиммейт #{partner_id}</b>\n"
                basic_text += f"   Профиль недоступен\n\n"
        
        # Ограничиваем длину сообщения
        if len(basic_text) > 3500:
            basic_text = basic_text[:3500] + "...\n\n(показаны первые тиммейты)"
            
        basic_text += "\n💡 <b>Как связаться:</b>\n"
        basic_text += "• Напишите в Telegram по указанному контакту\n"
        basic_text += "• Договоритесь об игре!"
        
        # Send basic teammate list immediately
        sent_message = await query.edit_message_text(
            basic_text,
            reply_markup=Keyboards.teammates_menu(),
            parse_mode='HTML'
        )
        
        # Фаза 4: Запуск фоновой задачи для получения ELO данных
        if futures:
            # Create background task for ELO updates
            async def update_with_elo():
                try:
                    # Batch processing with timeout per request and exception handling
                    elo_results = await asyncio.gather(
                        *[asyncio.wait_for(f, timeout=4.0) for f in futures], 
                        return_exceptions=True
                    )
                    logger.debug(f"✅ Батч-обработка завершена для {len(futures)} teammates")
                except Exception as e:
                    logger.error(f"❌ Ошибка батч-обработки ELO запросов: {e}")
                    elo_results = [None] * len(futures)
                
                # Compose final text with ELO data
                await self._update_teammates_with_elo(query, text, teammate_data, elo_results)
            
            # Start background ELO update task
            asyncio.create_task(update_with_elo())
        
    async def _update_teammates_with_elo(self, query, header_text, teammate_data, elo_results):
        """Update teammates message with ELO data"""
        try:
            final_text = header_text  # Reset to header
            
            for i, teammate_info in enumerate(teammate_data):
                match = teammate_info['match']
                partner = teammate_info['partner']
                partner_profile = teammate_info['partner_profile']
                partner_id = teammate_info['partner_id']
                index = teammate_info['index']
                
                if partner and partner_profile:
                    name = partner_profile.game_nickname
                    telegram_contact = f"@{partner.username}" if partner.username else partner.first_name
                    
                    # Получаем ELO статистику из батч-результатов
                    elo_stats = None
                    if i < len(elo_results):
                        result = elo_results[i]
                        if isinstance(result, Exception):
                            if isinstance(result, asyncio.TimeoutError):
                                logger.debug(f"⏰ Таймаут батч-запроса ELO для teammate {partner_profile.game_nickname}")
                            else:
                                logger.debug(f"❌ Ошибка батч-запроса для teammate {partner_profile.game_nickname}: {result}")
                            elo_stats = None
                            # Enhanced fallback with progressive loader integration
                            try:
                                from bot.utils.faceit_analyzer import faceit_analyzer
                                elo_stats = await faceit_analyzer.get_elo_stats_by_nickname(partner_profile.game_nickname)
                            except Exception:
                                elo_stats = None
                        else:
                            elo_stats = result
                            if elo_stats:
                                logger.debug(f"✅ Получена ELO статистика из батча для teammate {partner_profile.game_nickname}")
                    
                    # Enhanced ELO display with better error handling
                    if elo_stats:
                        from bot.utils.cs2_data import format_faceit_elo_display
                        
                        # Проверка корректности ELO значений перед отображением
                        lowest_elo = elo_stats.get('lowest_elo', 0)
                        highest_elo = elo_stats.get('highest_elo', 0)
                        
                        # Enhanced ELO validation for teammates
                        try:
                            if isinstance(lowest_elo, (int, float)) and isinstance(highest_elo, (int, float)):
                                lowest_elo = int(lowest_elo) if lowest_elo >= 0 else 0
                                highest_elo = int(highest_elo) if highest_elo >= 0 else 0
                                current_elo = partner_profile.faceit_elo
                                
                                if lowest_elo > 0 or highest_elo > 0:
                                    if lowest_elo <= current_elo <= highest_elo or (lowest_elo == 0 and highest_elo == 0):
                                        elo_display = format_faceit_elo_display(current_elo, lowest_elo, highest_elo, partner_profile.game_nickname)
                                    else:
                                        logger.warning(f"⚠️ TEAMMATES: ELO logic error for {partner_profile.game_nickname}")
                                        elo_display = format_elo_display(current_elo)
                                else:
                                    elo_display = format_elo_display(current_elo)
                            else:
                                logger.warning(f"⚠️ TEAMMATES: Invalid ELO types for {partner_profile.game_nickname}")
                                elo_display = format_elo_display(partner_profile.faceit_elo)
                        except Exception as elo_validation_error:
                            logger.error(f"ELO validation error in teammates for {partner_profile.game_nickname}: {elo_validation_error}")
                            elo_display = format_elo_display(partner_profile.faceit_elo)
                    else:
                        # Improved fallback display
                        elo_display = format_elo_display(partner_profile.faceit_elo)
                    
                    role = format_role_display(partner_profile.role)
                    nickname = extract_faceit_nickname(partner_profile.faceit_url)
                    status = "🟢 Новый" if match.is_active else "⚪ Просмотрен"
                    
                    final_text += f"{index}. <b>{name}</b> (Faceit: {nickname})\n"
                    final_text += f"   {elo_display} • {role}\n"
                    final_text += f"   {status} • {match.created_at.strftime('%d.%m.%Y')}\n"
                    final_text += f"   💬 Telegram: {telegram_contact}\n\n"
                else:
                    final_text += f"{index}. <b>Тиммейт #{partner_id}</b>\n"
                    final_text += f"   Профиль недоступен\n\n"
                    
            # Update the message with final ELO data
            if len(final_text) > 3500:
                final_text = final_text[:3500] + "...\n\n(показаны первые тиммейты)"
                
            final_text += "\n💡 <b>Как связаться:</b>\n"
            final_text += "• Напишите в Telegram по указанному контакту\n"
            final_text += "• Договоритесь об игре!"
            
            try:
                # Progressive update with ELO data (6 second timeout for teammates)
                await asyncio.wait_for(
                    query.edit_message_text(
                        final_text,
                        reply_markup=Keyboards.teammates_menu(),
                        parse_mode='HTML'
                    ),
                    timeout=6.0
                )
                logger.debug(f"✅ Teammates list updated with ELO data for {len(teammate_data)} teammates")
            except asyncio.TimeoutError:
                logger.warning("⏰ Timeout updating teammates message with ELO data - keeping basic display")
            except Exception as update_error:
                logger.error(f"❌ Error updating teammates message: {update_error}")
                # Keep basic display on error
                
        except Exception as e:
            logger.error(f"Error in _update_teammates_with_elo: {e}", exc_info=True)