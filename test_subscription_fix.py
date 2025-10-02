#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправленной системы подписки
Создано организацией Twizz_Project
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from bot.main import CS2TeammeetBot
from bot.utils.subscription_checker import get_subscription_checker

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_subscription.log')
    ]
)

logger = logging.getLogger(__name__)

async def test_subscription_system():
    """Тестирует исправленную систему проверки подписки"""
    logger.info("🚀 Запуск тестирования исправленной системы проверки подписки")
    
    try:
        # Инициализируем бота
        logger.info("📱 Инициализация бота...")
        bot = CS2TeammeetBot()
        await bot.initialize()
        
        # Получаем subscription checker
        subscription_checker = get_subscription_checker()
        if not subscription_checker:
            logger.error("❌ SubscriptionChecker не инициализирован")
            return False
        
        logger.info("✅ SubscriptionChecker успешно инициализирован")
        
        # Тестируем систему проверки подписки
        logger.info("🔍 Тестирование системы проверки подписки...")
        test_results = await subscription_checker.test_subscription_system()
        
        # Выводим результаты тестирования
        logger.info("📊 Результаты тестирования:")
        logger.info(f"   Время тестирования: {test_results['timestamp']}")
        
        if test_results['bot_info']:
            bot_info = test_results['bot_info']
            logger.info(f"   Бот: @{bot_info['username']} ({bot_info['first_name']})")
        
        logger.info("   Каналы:")
        for channel in test_results['channels']:
            status = "✅" if channel['accessible'] else "❌"
            bot_member = "✅" if channel.get('bot_is_member', False) else "❌"
            logger.info(f"     {status} {channel['channel_username']} - доступен: {channel['accessible']}, бот участник: {bot_member}")
            
            if channel.get('error'):
                logger.warning(f"       Ошибка: {channel['error']}")
            
            if channel.get('bot_member_error'):
                logger.warning(f"       Ошибка бота: {channel['bot_member_error']}")
        
        if test_results['errors']:
            logger.warning("   Ошибки:")
            for error in test_results['errors']:
                logger.warning(f"     - {error}")
        
        # Тестируем проверку подписки для тестового пользователя
        logger.info("👤 Тестирование проверки подписки для тестового пользователя...")
        test_user_id = 123456789  # Замените на реальный ID для тестирования
        
        try:
            subscription_status = await subscription_checker.check_user_subscription(test_user_id)
            logger.info(f"   Результат проверки для пользователя {test_user_id}:")
            logger.info(f"     Подписан: {'✅' if subscription_status.is_subscribed else '❌'}")
            logger.info(f"     Отсутствующие каналы: {subscription_status.missing_channels}")
            if subscription_status.error_message:
                logger.warning(f"     Ошибки: {subscription_status.error_message}")
        except Exception as e:
            logger.error(f"   Ошибка при проверке подписки: {e}")
        
        # Проверяем обязательные каналы
        logger.info("📋 Обязательные каналы:")
        required_channels = subscription_checker.get_required_channels()
        for channel in required_channels:
            logger.info(f"   - {channel.channel_title} (@{channel.channel_username})")
            logger.info(f"     URL: {channel.channel_url}")
        
        logger.info("✅ Тестирование системы проверки подписки завершено")
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при тестировании: {e}")
        return False
    
    finally:
        try:
            await bot.shutdown()
        except:
            pass

async def main():
    """Главная функция"""
    logger.info("🎯 Запуск тестирования исправленной системы проверки подписки")
    
    success = await test_subscription_system()
    
    if success:
        logger.info("🎉 Тестирование завершено успешно!")
        return 0
    else:
        logger.error("💥 Тестирование завершено с ошибками!")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("⏹️ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Неожиданная ошибка: {e}")
        sys.exit(1)
