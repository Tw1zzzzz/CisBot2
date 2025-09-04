"""
Обработчики модерации для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.operations import DatabaseManager
from bot.utils.cs2_data import format_elo_display, format_role_display, extract_faceit_nickname, PLAYTIME_OPTIONS

logger = logging.getLogger(__name__)

class ModerationHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def show_moderation_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает главное меню модерации"""
        query = update.callback_query
        if query:
            await query.answer()
            user_id = query.from_user.id
        else:
            user_id = update.effective_user.id

        # Проверяем права модератора
        if not await self.db.is_moderator(user_id):
            text = "❌ У вас нет прав модератора"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Получаем статистику
        stats = await self.db.get_moderation_stats()
        pending_count = stats.get('profiles_pending', 0)
        approved_count = stats.get('profiles_approved', 0)
        rejected_count = stats.get('profiles_rejected', 0)

        text = f"👨‍💼 <b>Панель модератора</b>\n\n"
        text += f"📊 <b>Статистика:</b>\n"
        text += f"⏳ На модерации: {pending_count}\n"
        text += f"✅ Одобрено: {approved_count}\n"
        text += f"❌ Отклонено: {rejected_count}\n\n"
        text += "Выберите действие:"

        keyboard = [
            [InlineKeyboardButton(f"⏳ Модерировать анкеты ({pending_count})", callback_data="mod_queue")],
            [InlineKeyboardButton("✅ Одобренные анкеты", callback_data="mod_approved")],
            [InlineKeyboardButton("❌ Отклоненные анкеты", callback_data="mod_rejected")],
            [InlineKeyboardButton("📊 Статистика", callback_data="mod_stats")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    async def show_moderation_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает очередь анкет на модерацию"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем профили на модерации
        profiles = await self.db.get_profiles_for_moderation('pending', limit=1)
        
        if not profiles:
            text = "✅ Все анкеты проверены!\n\nНет анкет, ожидающих модерации."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Показываем первую анкету
        profile_data = profiles[0]
        context.user_data['moderating_profile'] = profile_data
        
        await self.show_profile_for_moderation(query, profile_data)

    async def show_profile_for_moderation(self, query, profile_data):
        """Показывает профиль для модерации"""
        text = "👨‍💼 <b>Модерация анкеты</b>\n\n"
        text += self.format_profile_for_moderation(profile_data)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{profile_data['user_id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{profile_data['user_id']}")
            ],
            [InlineKeyboardButton("⏭️ Следующая анкета", callback_data="next_profile")],
            [InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]
        ]
        
        # 🔥 ИСПРАВЛЕНИЕ: добавляем защиту от ошибки "Message is not modified"
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except Exception as e:
            if "message is not modified" in str(e).lower():
                # Если сообщение не изменилось, просто отвечаем на callback
                await query.answer("📋 Анкета уже отображается")
            else:
                # Для других ошибок - пробрасываем дальше
                raise e

    def format_profile_for_moderation(self, profile_data) -> str:
        """Форматирует профиль для модерации"""
        text = f"👤 <b>Пользователь:</b> {profile_data['first_name']}"
        if profile_data['username']:
            text += f" (@{profile_data['username']})"
        text += f"\n🆔 <b>ID:</b> {profile_data['user_id']}\n\n"
        
        text += f"🎮 <b>Игровой ник:</b> {profile_data['game_nickname']}\n"
        text += f"🎯 <b>ELO Faceit:</b> {format_elo_display(profile_data['faceit_elo'])}\n"
        
        # Faceit профиль
        nickname = extract_faceit_nickname(profile_data['faceit_url'])
        text += f"🔗 <b>Faceit:</b> <a href='{profile_data['faceit_url']}'>{nickname}</a>\n"
        
        text += f"👥 <b>Роль:</b> {format_role_display(profile_data['role'])}\n"
        
        # Карты
        try:
            import json
            maps = json.loads(profile_data['favorite_maps'])
            text += f"🗺️ <b>Карты:</b> {', '.join(maps[:3])}{'...' if len(maps) > 3 else ''}\n"
        except:
            text += f"🗺️ <b>Карты:</b> Ошибка данных\n"
        
        # Время игры
        try:
            import json
            slots = json.loads(profile_data['playtime_slots'])
            time_names = []
            for slot_id in slots:
                time_option = next((t for t in PLAYTIME_OPTIONS if t['id'] == slot_id), None)
                if time_option:
                    time_names.append(time_option['emoji'])
            text += f"⏰ <b>Время:</b> {' '.join(time_names)}\n"
        except:
            text += f"⏰ <b>Время:</b> Ошибка данных\n"
        
        if profile_data['description']:
            text += f"\n💬 <b>Описание:</b>\n{profile_data['description']}\n"
        
        # Дата создания
        from datetime import datetime
        try:
            created = datetime.fromisoformat(profile_data['created_at'])
            text += f"\n📅 <b>Создано:</b> {created.strftime('%d.%m.%Y %H:%M')}"
        except:
            text += f"\n📅 <b>Создано:</b> {profile_data['created_at']}"
        
        return text

    async def approve_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Одобряет профиль"""
        query = update.callback_query
        await query.answer("✅ Профиль одобрен!")
        
        user_id = int(query.data.split('_')[1])
        moderator_id = query.from_user.id
        
        success = await self.db.moderate_profile(user_id, 'approved', moderator_id)
        
        if success:
            # Отправляем уведомление пользователю
            await self.send_moderation_notification(user_id, 'approved', context)
            
            # Показываем следующую анкету
            await self.show_next_profile(query, context)
        else:
            await query.edit_message_text("❌ Ошибка при одобрении профиля")

    async def reject_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отклоняет профиль"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.split('_')[1])
        context.user_data['rejecting_user_id'] = user_id
        
        text = "❌ <b>Отклонение анкеты</b>\n\n"
        text += "Укажите причину отклонения или выберите готовый вариант:"
        
        keyboard = [
            [InlineKeyboardButton("🔞 Неподходящий контент", callback_data="reject_reason_inappropriate")],
            [InlineKeyboardButton("📸 Неверная ссылка Faceit", callback_data="reject_reason_invalid_link")],
            [InlineKeyboardButton("🎮 Неподходящий ник", callback_data="reject_reason_bad_nickname")],
            [InlineKeyboardButton("📝 Неполная информация", callback_data="reject_reason_incomplete")],
            [InlineKeyboardButton("✏️ Своя причина", callback_data="reject_reason_custom")],
            [InlineKeyboardButton("🔙 Отмена", callback_data="mod_queue")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    async def reject_with_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отклоняет профиль с указанной причиной"""
        query = update.callback_query
        await query.answer()
        
        user_id = context.user_data.get('rejecting_user_id')
        moderator_id = query.from_user.id
        
        reason_map = {
            'inappropriate': 'Неподходящий контент (оскорбления, спам и т.д.)',
            'invalid_link': 'Неверная или недоступная ссылка на Faceit профиль',
            'bad_nickname': 'Неподходящий игровой ник',
            'incomplete': 'Неполная или недостоверная информация'
        }
        
        reason_key = query.data.split('_')[-1]
        
        if reason_key == 'custom':
            # Запрашиваем кастомную причину
            text = (
                "✏️ <b>Кастомная причина отклонения</b>\n\n"
                "Напишите причину отклонения профиля.\n"
                "Пользователь увидит вашу причину."
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="mod_queue")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
            context.user_data['awaiting_rejection_reason'] = True
            return
        
        reason = reason_map.get(reason_key, 'Нарушение правил сообщества')
        
        success = await self.db.moderate_profile(user_id, 'rejected', moderator_id, reason)
        
        if success:
            await query.answer(f"❌ Профиль отклонен: {reason}")
            
            # Отправляем уведомление пользователю
            await self.send_moderation_notification(user_id, 'rejected', context, reason)
            
            # Показываем следующую анкету
            await self.show_next_profile(query, context)
        else:
            await query.edit_message_text("❌ Ошибка при отклонении профиля")

    async def show_next_profile(self, query_or_update, context):
        """Показывает следующую анкету"""
        # Определяем, это query или update
        if hasattr(query_or_update, 'callback_query'):
            query = query_or_update.callback_query
        else:
            query = query_or_update
        
        # 🔥 ИСПРАВЛЕНИЕ: исключаем текущую модерируемую анкету если она есть
        current_profile = context.user_data.get('moderating_profile')
        exclude_user_id = current_profile.get('user_id') if current_profile else None
        
        profiles = await self.db.get_profiles_for_moderation('pending', limit=1, exclude_user_id=exclude_user_id)
        
        if not profiles:
            text = "✅ Все анкеты проверены!\n\nНет анкет, ожидающих модерации."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]]
            
            # 🔥 ИСПРАВЛЕНИЕ: защита от ошибки "Message is not modified"
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    await query.answer("✅ Все анкеты уже проверены")
                else:
                    raise e
            return
        
        profile_data = profiles[0]
        context.user_data['moderating_profile'] = profile_data
        await self.show_profile_for_moderation(query, profile_data)

    async def send_moderation_notification(self, user_id: int, status: str, context: ContextTypes.DEFAULT_TYPE, reason: str = None):
        """Отправляет уведомление пользователю о результате модерации"""
        try:
            if status == 'approved':
                text = (
                    "🎉 <b>Ваша анкета одобрена!</b>\n\n"
                    "Теперь другие игроки смогут найти вас через поиск тиммейтов.\n"
                    "Удачи в поиске команды!"
                )
            else:  # rejected
                text = (
                    "❌ <b>Ваша анкета отклонена</b>\n\n"
                    f"<b>Причина:</b> {reason}\n\n"
                    "Вы можете отредактировать профиль и отправить на повторную модерацию."
                )
            
            keyboard = [[InlineKeyboardButton("👤 Мой профиль", callback_data="profile_menu")]]
            
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")



    async def add_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления модератора (только для super_admin)"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator or not moderator.can_manage_moderators():
            await update.message.reply_text(
                "❌ У вас нет прав для управления модераторами.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]])
            )
            return
        
        # Проверяем аргументы команды
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "📋 <b>Как добавить модератора:</b>\n\n"
                "<code>/add_moderator USER_ID ROLE</code>\n\n"
                "<b>Роли:</b>\n"
                "• <code>moderator</code> - Базовая модерация\n"
                "• <code>admin</code> - Расширенные права\n"
                "• <code>super_admin</code> - Полные права\n\n"
                "<b>Пример:</b>\n"
                "<code>/add_moderator 123456789 moderator</code>",
                parse_mode='HTML'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            role = context.args[1].lower()
            
            if role not in ['moderator', 'admin', 'super_admin']:
                await update.message.reply_text("❌ Неверная роль. Используйте: moderator, admin или super_admin")
                return
            
            # Добавляем модератора
            success = await self.db.add_moderator(target_user_id, role, user_id)
            
            if success:
                await update.message.reply_text(
                    f"✅ Пользователь {target_user_id} назначен как {role}"
                )
                
                # Уведомляем нового модератора
                try:
                    role_names = {
                        'moderator': 'Модератор',
                        'admin': 'Администратор',
                        'super_admin': 'Супер-администратор'
                    }
                    
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=(
                            f"🎉 <b>Вы назначены модератором!</b>\n\n"
                            f"<b>Роль:</b> {role_names[role]}\n\n"
                            "Теперь у вас есть доступ к панели модерации.\n"
                            "Используйте кнопку 'Модерация' в главном меню."
                        ),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💼 Панель модерации", callback_data="moderation_menu")]]),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить модератора {target_user_id}: {e}")
            else:
                await update.message.reply_text("❌ Ошибка при добавлении модератора")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя")
        except Exception as e:
            logger.error(f"Ошибка добавления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при добавлении модератора")

    async def remove_moderator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для удаления модератора"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator or not moderator.can_manage_moderators():
            await update.message.reply_text("❌ У вас нет прав для управления модераторами.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "📋 <b>Как удалить модератора:</b>\n\n"
                "<code>/remove_moderator USER_ID</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/remove_moderator 123456789</code>",
                parse_mode='HTML'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            # Удаляем модератора (деактивируем)
            success = await self.db.update_moderator_status(target_user_id, False)
            
            if success:
                await update.message.reply_text(f"✅ Модератор {target_user_id} деактивирован")
                
                # Уведомляем бывшего модератора
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="📋 Ваши права модератора были отозваны.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить бывшего модератора {target_user_id}: {e}")
            else:
                await update.message.reply_text("❌ Ошибка при удалении модератора")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя")
        except Exception as e:
            logger.error(f"Ошибка удаления модератора: {e}")
            await update.message.reply_text("❌ Произошла ошибка при удалении модератора")

    async def list_moderators_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для просмотра списка модераторов"""
        user_id = update.effective_user.id
        
        # Проверяем права
        moderator = await self.db.get_moderator(user_id)
        if not moderator:
            await update.message.reply_text("❌ У вас нет прав модератора.")
            return
        
        # Получаем список модераторов
        moderators = await self.db.get_all_moderators()
        
        if not moderators:
            await update.message.reply_text("👥 Модераторы не найдены.")
            return
        
        text = "👥 <b>Список модераторов:</b>\n\n"
        
        for mod in moderators:
            status = "✅" if mod.is_active else "❌"
            text += f"{status} <code>{mod.user_id}</code> - {mod.role}\n"
        
        await update.message.reply_text(text, parse_mode='HTML')

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик callback запросов модерации"""
        query = update.callback_query
        data = query.data
        
        try:
            if data == "moderation_menu":
                await self.show_moderation_menu(update, context)
            elif data == "mod_queue":
                await self.show_moderation_queue(update, context)
            elif data == "mod_approved":
                await self.show_approved_profiles(update, context)
            elif data == "mod_rejected":
                await self.show_rejected_profiles(update, context)
            elif data == "mod_stats":
                await self.show_moderation_stats(update, context)
            elif data.startswith("approve_"):
                await self.approve_profile(update, context)
            elif data.startswith("reject_reason_"):  # 🔥 ИСПРАВЛЕНИЕ: проверяем reject_reason_ ПЕРЕД reject_
                await self.reject_with_reason(update, context)
            elif data.startswith("reject_"):
                await self.reject_profile(update, context)
            elif data == "next_profile":
                await self.show_next_profile(query, context)
            else:
                await query.answer("❌ Неизвестная команда")
        except Exception as e:
            logger.error(f"Ошибка обработки callback в модерации: {e}")
            await query.answer("❌ Произошла ошибка")

    async def show_approved_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список одобренных профилей"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем одобренные профили
        profiles = await self.db.get_profiles_for_moderation('approved', limit=10)
        
        if not profiles:
            text = "✅ <b>Одобренные анкеты</b>\n\nОдобренных анкет пока нет."
        else:
            text = f"✅ <b>Одобренные анкеты ({len(profiles)})</b>\n\n"
            
            for i, profile_data in enumerate(profiles, 1):
                nickname = profile_data['game_nickname']
                user_name = profile_data['first_name']
                moderated_at = profile_data.get('moderated_at', 'Неизвестно')
                
                text += f"{i}. <b>{nickname}</b> ({user_name})\n"
                text += f"   📅 Одобрено: {moderated_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def show_rejected_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список отклоненных профилей"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем отклоненные профили
        profiles = await self.db.get_profiles_for_moderation('rejected', limit=10)
        
        if not profiles:
            text = "❌ <b>Отклоненные анкеты</b>\n\nОтклоненных анкет пока нет."
        else:
            text = f"❌ <b>Отклоненные анкеты ({len(profiles)})</b>\n\n"
            
            for i, profile_data in enumerate(profiles, 1):
                nickname = profile_data['game_nickname']
                user_name = profile_data['first_name']
                reason = profile_data.get('moderation_reason', 'Причина не указана')
                moderated_at = profile_data.get('moderated_at', 'Неизвестно')
                
                text += f"{i}. <b>{nickname}</b> ({user_name})\n"
                text += f"   🚫 Причина: {reason}\n"
                text += f"   📅 Отклонено: {moderated_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def show_moderation_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает статистику модерации"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not await self.db.is_moderator(user_id):
            await query.edit_message_text("❌ Нет прав доступа")
            return

        # Получаем статистику
        stats = await self.db.get_moderation_stats()
        
        text = "📊 <b>Статистика модерации</b>\n\n"
        text += f"⏳ <b>На модерации:</b> {stats.get('profiles_pending', 0)}\n"
        text += f"✅ <b>Одобрено:</b> {stats.get('profiles_approved', 0)}\n"
        text += f"❌ <b>Отклонено:</b> {stats.get('profiles_rejected', 0)}\n"
        text += f"👥 <b>Активных модераторов:</b> {stats.get('active_moderators', 0)}\n\n"
        
        total = stats.get('profiles_approved', 0) + stats.get('profiles_rejected', 0)
        if total > 0:
            approval_rate = round((stats.get('profiles_approved', 0) / total) * 100, 1)
            text += f"📈 <b>Процент одобрения:</b> {approval_rate}%"
        
        keyboard = [[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые сообщения (для кастомных причин отклонения)"""
        if context.user_data.get('awaiting_rejection_reason'):
            user_id = context.user_data.get('rejecting_user_id')
            moderator_id = update.effective_user.id
            custom_reason = update.message.text.strip()
            
            if len(custom_reason) > 200:
                await update.message.reply_text(
                    "❌ Причина слишком длинная. Максимум 200 символов.\n"
                    "Попробуйте сократить:"
                )
                return
            
            # Очищаем флаг ожидания
            context.user_data['awaiting_rejection_reason'] = False
            
            # Отклоняем профиль с кастомной причиной
            success = await self.db.moderate_profile(user_id, 'rejected', moderator_id, custom_reason)
            
            if success:
                await update.message.reply_text(f"❌ Профиль отклонен с причиной: {custom_reason}")
                
                # Отправляем уведомление пользователю
                await self.send_moderation_notification(user_id, 'rejected', context, custom_reason)
                
                # Показываем следующую анкету или меню модерации
                profiles = await self.db.get_profiles_for_moderation('pending', limit=1)
                
                if profiles:
                    profile_data = profiles[0]
                    context.user_data['moderating_profile'] = profile_data
                    
                    text = "👨‍💼 <b>Модерация анкеты</b>\n\n"
                    text += self.format_profile_for_moderation(profile_data)
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{profile_data['user_id']}"),
                            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{profile_data['user_id']}")
                        ],
                        [InlineKeyboardButton("⏭️ Следующая анкета", callback_data="next_profile")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="moderation_menu")]
                    ]
                    
                    await update.message.reply_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        "✅ Все анкеты проверены!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К модерации", callback_data="moderation_menu")]])
                    )
            else:
                await update.message.reply_text("❌ Ошибка при отклонении профиля")