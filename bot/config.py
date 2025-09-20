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
    FACEIT_REQUEST_TIMEOUT = int(os.getenv('FACEIT_REQUEST_TIMEOUT', '10'))  # Timeout for individual API requests
    FACEIT_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv('FACEIT_CIRCUIT_BREAKER_THRESHOLD', '5'))  # Failures before circuit breaker opens
    FACEIT_CIRCUIT_BREAKER_RESET_TIME = int(os.getenv('FACEIT_CIRCUIT_BREAKER_RESET_TIME', '60'))  # Time before circuit breaker reset attempt
    
    # Background Processing settings
    BG_MAX_WORKERS = int(os.getenv('BG_MAX_WORKERS', '3'))  # Maximum number of concurrent worker coroutines
    BG_MAX_QUEUE_SIZE = int(os.getenv('BG_MAX_QUEUE_SIZE', '1000'))  # Maximum size of the task queue
    BG_MAX_RETRIES = int(os.getenv('BG_MAX_RETRIES', '2'))  # Maximum retry attempts for failed tasks
    BG_TASK_TIMEOUT = int(os.getenv('BG_TASK_TIMEOUT', '30'))  # Timeout for individual tasks in seconds
    BG_SEMAPHORE_LIMIT = int(os.getenv('BG_SEMAPHORE_LIMIT', '3'))  # Maximum concurrent API requests
    BG_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv('BG_CIRCUIT_BREAKER_THRESHOLD', '5'))  # Failures before circuit breaker opens
    BG_CIRCUIT_BREAKER_RESET_TIME = int(os.getenv('BG_CIRCUIT_BREAKER_RESET_TIME', '60'))  # Time before circuit breaker reset attempt
    
    # Persistent Cache Settings - SQLite-based cache for improved performance and persistence
    FACEIT_CACHE_DB_PATH = os.getenv('FACEIT_CACHE_DB_PATH', 'data/faceit_cache.db')  # Path to cache database file
    FACEIT_CACHE_ACTIVE_PLAYER_TTL = int(os.getenv('FACEIT_CACHE_ACTIVE_PLAYER_TTL', '3600'))  # TTL for active players (1 hour) - increased for better performance
    FACEIT_CACHE_INACTIVE_PLAYER_TTL = int(os.getenv('FACEIT_CACHE_INACTIVE_PLAYER_TTL', '21600'))  # TTL for inactive players (6 hours) - increased for better performance
    FACEIT_CACHE_ACTIVITY_THRESHOLD = int(os.getenv('FACEIT_CACHE_ACTIVITY_THRESHOLD', '7'))  # Days to consider player active
    FACEIT_CACHE_MAX_ENTRIES = int(os.getenv('FACEIT_CACHE_MAX_ENTRIES', '15000'))  # Maximum cache entries before cleanup - increased for better hit ratio
    
    # Cache Warming Settings - Background cache preloading for improved responsiveness
    FACEIT_CACHE_WARMING_ENABLED = os.getenv('FACEIT_CACHE_WARMING_ENABLED', 'True').lower() == 'true'  # Enable background cache warming
    FACEIT_CACHE_WARMING_BATCH_SIZE = int(os.getenv('FACEIT_CACHE_WARMING_BATCH_SIZE', '100'))  # Number of profiles to warm per batch - increased for better coverage
    FACEIT_CACHE_WARMING_INTERVAL = int(os.getenv('FACEIT_CACHE_WARMING_INTERVAL', '1800'))  # Interval between warming cycles (30 minutes) - more frequent warming
    FACEIT_CACHE_POPULAR_THRESHOLD = int(os.getenv('FACEIT_CACHE_POPULAR_THRESHOLD', '3'))  # Minimum access count to be considered popular - lowered for more aggressive warming
    
    # Cache Maintenance Settings - Automated cache cleanup and optimization
    FACEIT_CACHE_CLEANUP_INTERVAL = int(os.getenv('FACEIT_CACHE_CLEANUP_INTERVAL', '7200'))  # Cleanup interval (2 hours)
    FACEIT_CACHE_VACUUM_INTERVAL = int(os.getenv('FACEIT_CACHE_VACUUM_INTERVAL', '86400'))  # Database vacuum interval (24 hours)
    FACEIT_CACHE_STATS_RETENTION = int(os.getenv('FACEIT_CACHE_STATS_RETENTION', '30'))  # Days to keep cache statistics
    
    # Advanced Cache Performance Settings - Optimized for maximum speed
    FACEIT_CACHE_PRELOAD_ON_STARTUP = os.getenv('FACEIT_CACHE_PRELOAD_ON_STARTUP', 'True').lower() == 'true'  # Preload popular profiles on bot startup
    FACEIT_CACHE_PRELOAD_BATCH_SIZE = int(os.getenv('FACEIT_CACHE_PRELOAD_BATCH_SIZE', '200'))  # Number of profiles to preload on startup
    FACEIT_CACHE_AGGRESSIVE_WARMING = os.getenv('FACEIT_CACHE_AGGRESSIVE_WARMING', 'True').lower() == 'true'  # Enable aggressive cache warming for better hit ratio
    FACEIT_CACHE_PREDICTIVE_LOADING = os.getenv('FACEIT_CACHE_PREDICTIVE_LOADING', 'True').lower() == 'true'  # Enable predictive loading based on user patterns
    
    # Progressive Loading Settings - Enhanced user experience with progressive data loading
    PROGRESSIVE_LOADING_ENABLED = os.getenv('PROGRESSIVE_LOADING_ENABLED', 'True').lower() == 'true'  # Enable/disable progressive loading feature
    PROGRESSIVE_SEARCH_TIMEOUT = int(os.getenv('PROGRESSIVE_SEARCH_TIMEOUT', '5'))  # Timeout for search ELO updates in seconds - reduced for faster response
    PROGRESSIVE_PROFILE_TIMEOUT = int(os.getenv('PROGRESSIVE_PROFILE_TIMEOUT', '6'))  # Timeout for profile ELO updates in seconds - reduced for faster response
    PROGRESSIVE_TEAMMATES_TIMEOUT = int(os.getenv('PROGRESSIVE_TEAMMATES_TIMEOUT', '4'))  # Timeout for teammates ELO updates in seconds - reduced for faster response
    PROGRESSIVE_MESSAGE_RETENTION = int(os.getenv('PROGRESSIVE_MESSAGE_RETENTION', '3600'))  # How long to keep message references in seconds
    
    # Progressive Loading Performance Settings
    PROGRESSIVE_CLEANUP_INTERVAL = int(os.getenv('PROGRESSIVE_CLEANUP_INTERVAL', '300'))  # Interval for cleaning up expired messages in seconds
    PROGRESSIVE_CONTEXT_CLEANUP_INTERVAL = int(os.getenv('PROGRESSIVE_CONTEXT_CLEANUP_INTERVAL', '600'))  # Interval for cleaning up stale contexts in seconds
    PROGRESSIVE_METRICS_INTERVAL = int(os.getenv('PROGRESSIVE_METRICS_INTERVAL', '900'))  # Interval for collecting metrics in seconds
    PROGRESSIVE_MAX_CONCURRENT_UPDATES = int(os.getenv('PROGRESSIVE_MAX_CONCURRENT_UPDATES', '50'))  # Maximum concurrent progressive updates
    
    # Progressive Loading UI Settings
    PROGRESSIVE_LOADING_EMOJI = os.getenv('PROGRESSIVE_LOADING_EMOJI', '⏳')  # Emoji for loading indicators
    PROGRESSIVE_ELO_LOADING_TEXT = os.getenv('PROGRESSIVE_ELO_LOADING_TEXT', 'загружается...')  # Text for ELO loading placeholder
    PROGRESSIVE_UPDATE_DEBOUNCE = int(os.getenv('PROGRESSIVE_UPDATE_DEBOUNCE', '100'))  # Debounce time for updates in milliseconds
    PROGRESSIVE_RETRY_ATTEMPTS = int(os.getenv('PROGRESSIVE_RETRY_ATTEMPTS', '2'))  # Number of retry attempts for failed updates
    
    # Progressive Loading Monitoring Settings
    PROGRESSIVE_METRICS_ENABLED = os.getenv('PROGRESSIVE_METRICS_ENABLED', 'True').lower() == 'true'  # Enable progressive loading metrics collection
    PROGRESSIVE_PERFORMANCE_LOGGING = os.getenv('PROGRESSIVE_PERFORMANCE_LOGGING', 'False').lower() == 'true'  # Enable detailed performance logging
    PROGRESSIVE_ERROR_THRESHOLD = float(os.getenv('PROGRESSIVE_ERROR_THRESHOLD', '0.1'))  # Error rate threshold for alerts
    PROGRESSIVE_SUCCESS_RATE_TARGET = float(os.getenv('PROGRESSIVE_SUCCESS_RATE_TARGET', '0.95'))  # Target success rate for progressive updates
    
    # Performance Monitoring Core Settings - Comprehensive performance monitoring and alerting system
    PERFORMANCE_MONITORING_ENABLED = os.getenv('PERFORMANCE_MONITORING_ENABLED', 'True').lower() == 'true'  # Enable/disable performance monitoring
    PERFORMANCE_METRICS_RETENTION_DAYS = int(os.getenv('PERFORMANCE_METRICS_RETENTION_DAYS', '30'))  # How long to keep performance metrics in days
    PERFORMANCE_COLLECTION_INTERVAL = int(os.getenv('PERFORMANCE_COLLECTION_INTERVAL', '60'))  # Interval for collecting metrics in seconds
    PERFORMANCE_ANALYSIS_INTERVAL = int(os.getenv('PERFORMANCE_ANALYSIS_INTERVAL', '300'))  # Interval for performance analysis in seconds
    PERFORMANCE_REPORT_INTERVAL = int(os.getenv('PERFORMANCE_REPORT_INTERVAL', '3600'))  # Interval for generating reports in seconds
    
    # API Response Time Monitoring - Track and analyze API performance metrics
    API_RESPONSE_TIME_ALERT_THRESHOLD = float(os.getenv('API_RESPONSE_TIME_ALERT_THRESHOLD', '5.0'))  # Response time threshold for alerts in seconds
    API_RESPONSE_TIME_CRITICAL_THRESHOLD = float(os.getenv('API_RESPONSE_TIME_CRITICAL_THRESHOLD', '10.0'))  # Critical response time threshold in seconds
    API_RESPONSE_TIME_PERCENTILE_WINDOW = int(os.getenv('API_RESPONSE_TIME_PERCENTILE_WINDOW', '3600'))  # Time window for percentile calculations in seconds
    API_SLOW_ENDPOINT_THRESHOLD = float(os.getenv('API_SLOW_ENDPOINT_THRESHOLD', '3.0'))  # Threshold for identifying slow endpoints in seconds
    API_TIMEOUT_ALERT_THRESHOLD = float(os.getenv('API_TIMEOUT_ALERT_THRESHOLD', '0.05'))  # Timeout rate threshold for alerts
    
    # Cache Performance Monitoring - Monitor cache efficiency and optimization opportunities
    CACHE_HIT_RATIO_WARNING_THRESHOLD = float(os.getenv('CACHE_HIT_RATIO_WARNING_THRESHOLD', '0.7'))  # Cache hit ratio warning threshold
    CACHE_HIT_RATIO_CRITICAL_THRESHOLD = float(os.getenv('CACHE_HIT_RATIO_CRITICAL_THRESHOLD', '0.5'))  # Cache hit ratio critical threshold
    CACHE_SIZE_WARNING_THRESHOLD = float(os.getenv('CACHE_SIZE_WARNING_THRESHOLD', '0.8'))  # Cache size warning threshold as percentage of max
    CACHE_EFFICIENCY_ALERT_THRESHOLD = float(os.getenv('CACHE_EFFICIENCY_ALERT_THRESHOLD', '0.6'))  # Cache efficiency alert threshold
    CACHE_WARMING_EFFECTIVENESS_THRESHOLD = float(os.getenv('CACHE_WARMING_EFFECTIVENESS_THRESHOLD', '0.3'))  # Cache warming effectiveness threshold
    
    # Background Processor Monitoring - Track background processing performance and queue health
    BG_QUEUE_SIZE_WARNING_THRESHOLD = int(os.getenv('BG_QUEUE_SIZE_WARNING_THRESHOLD', '100'))  # Background queue size warning threshold
    BG_QUEUE_SIZE_CRITICAL_THRESHOLD = int(os.getenv('BG_QUEUE_SIZE_CRITICAL_THRESHOLD', '500'))  # Background queue size critical threshold
    BG_PROCESSING_TIME_ALERT_THRESHOLD = float(os.getenv('BG_PROCESSING_TIME_ALERT_THRESHOLD', '30.0'))  # Processing time alert threshold in seconds
    BG_FAILURE_RATE_WARNING_THRESHOLD = float(os.getenv('BG_FAILURE_RATE_WARNING_THRESHOLD', '0.1'))  # Background task failure rate warning threshold
    BG_FAILURE_RATE_CRITICAL_THRESHOLD = float(os.getenv('BG_FAILURE_RATE_CRITICAL_THRESHOLD', '0.2'))  # Background task failure rate critical threshold
    
    # Alerting System Configuration - Intelligent alerting with suppression and escalation
    ALERT_SUPPRESSION_WINDOW = int(os.getenv('ALERT_SUPPRESSION_WINDOW', '300'))  # Time window for alert suppression in seconds
    ALERT_ESCALATION_THRESHOLD = int(os.getenv('ALERT_ESCALATION_THRESHOLD', '3'))  # Number of repeated alerts before escalation
    ALERT_RECOVERY_CONFIRMATION_TIME = int(os.getenv('ALERT_RECOVERY_CONFIRMATION_TIME', '180'))  # Time to confirm alert recovery in seconds
    ALERT_LOG_LEVEL = os.getenv('ALERT_LOG_LEVEL', 'WARNING')  # Log level for alerts
    ALERT_EXTERNAL_WEBHOOK_URL = os.getenv('ALERT_EXTERNAL_WEBHOOK_URL')  # Optional webhook URL for external alert delivery
    
    # Configuration Tuning Settings - Automated configuration optimization based on usage patterns
    CONFIG_TUNING_ENABLED = os.getenv('CONFIG_TUNING_ENABLED', 'True').lower() == 'true'  # Enable automatic configuration tuning recommendations
    CONFIG_TUNING_ANALYSIS_WINDOW = int(os.getenv('CONFIG_TUNING_ANALYSIS_WINDOW', '86400'))  # Time window for tuning analysis in seconds
    CONFIG_TUNING_MIN_SAMPLE_SIZE = int(os.getenv('CONFIG_TUNING_MIN_SAMPLE_SIZE', '100'))  # Minimum sample size for tuning recommendations
    CONFIG_TUNING_CONFIDENCE_THRESHOLD = float(os.getenv('CONFIG_TUNING_CONFIDENCE_THRESHOLD', '0.8'))  # Confidence threshold for recommendations
    CONFIG_TUNING_MAX_CHANGE_PERCENT = float(os.getenv('CONFIG_TUNING_MAX_CHANGE_PERCENT', '0.2'))  # Maximum percentage change for auto-tuning
    
    # Performance Analysis Settings - Advanced performance analysis and anomaly detection
    PERFORMANCE_BASELINE_WINDOW = int(os.getenv('PERFORMANCE_BASELINE_WINDOW', '604800'))  # Time window for establishing performance baseline in seconds
    PERFORMANCE_ANOMALY_THRESHOLD = float(os.getenv('PERFORMANCE_ANOMALY_THRESHOLD', '2.0'))  # Threshold for anomaly detection
    PERFORMANCE_TREND_ANALYSIS_WINDOW = int(os.getenv('PERFORMANCE_TREND_ANALYSIS_WINDOW', '86400'))  # Time window for trend analysis in seconds
    PERFORMANCE_CORRELATION_THRESHOLD = float(os.getenv('PERFORMANCE_CORRELATION_THRESHOLD', '0.7'))  # Threshold for performance correlation analysis
    
    # Data Storage and Cleanup - Efficient data management for performance metrics
    PERFORMANCE_DATA_CLEANUP_INTERVAL = int(os.getenv('PERFORMANCE_DATA_CLEANUP_INTERVAL', '86400'))  # Interval for cleaning old performance data in seconds
    PERFORMANCE_AGGREGATION_INTERVALS = [60, 300, 3600, 86400]  # List of aggregation intervals in seconds
    PERFORMANCE_MAX_MEMORY_USAGE_MB = int(os.getenv('PERFORMANCE_MAX_MEMORY_USAGE_MB', '100'))  # Maximum memory usage for performance data in MB
    PERFORMANCE_DISK_USAGE_WARNING_THRESHOLD = float(os.getenv('PERFORMANCE_DISK_USAGE_WARNING_THRESHOLD', '0.8'))  # Disk usage warning threshold for performance data

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