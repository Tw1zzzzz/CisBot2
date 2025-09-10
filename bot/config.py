"""
Конфигурация CIS FINDER Bot
Создано организацией Twizz_Project
"""
import os
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class Config:
    """Основная конфигурация бота"""
    
    # Bot settings
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'cis_finder_bot')
    
    # Database settings
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/bot.db')
    
    # Connection pool settings
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '5'))  # Размер пула соединений с БД
    DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))  # Таймаут получения соединения из пула (сек)
    DB_CONNECTION_TIMEOUT = int(os.getenv('DB_CONNECTION_TIMEOUT', '30'))  # Таймаут операций с БД (сек)
    
    # Logging settings
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')
    
    # Matching algorithm settings
    MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '20'))
    COMPATIBILITY_THRESHOLD = int(os.getenv('COMPATIBILITY_THRESHOLD', '30'))
    MAX_DAILY_LIKES = int(os.getenv('MAX_DAILY_LIKES', '50'))
    COOLDOWN_BETWEEN_LIKES = int(os.getenv('COOLDOWN_BETWEEN_LIKES', '1'))
    
    # Faceit Analyser API settings
    FACEIT_ANALYSER_API_KEY = os.getenv('FACEIT_ANALYSER_API_KEY')
    FACEIT_ANALYSER_BASE_URL = os.getenv('FACEIT_ANALYSER_BASE_URL', 'https://faceitanalyser.com/api/')
    FACEIT_ANALYSER_CACHE_TTL = int(os.getenv('FACEIT_ANALYSER_CACHE_TTL', '3600'))  # 1 час кеш

def setup_logging():
    """Настройка системы логирования"""
    
    # Создаем папку для логов если её нет
    os.makedirs('logs', exist_ok=True)
    
    # Формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=log_format,
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Настройка логирования для сетевых компонентов
    # Уменьшаем количество технических логов httpx, но оставляем важные ошибки
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram.ext.Updater').setLevel(logging.INFO)
    
    # Создаем специальный logger для сетевых проблем
    network_logger = logging.getLogger('bot.network')
    network_handler = logging.FileHandler('logs/network.log', encoding='utf-8')
    network_handler.setFormatter(logging.Formatter(log_format))
    network_logger.addHandler(network_handler)
    network_logger.setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("Логирование настроено успешно")
    
    return logger