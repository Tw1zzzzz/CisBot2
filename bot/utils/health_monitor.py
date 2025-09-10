"""
Система мониторинга состояния соединения бота
"""
import asyncio
import logging
import time
from typing import Optional
import httpx
from telegram import Bot
from telegram.error import NetworkError, TimedOut

logger = logging.getLogger(__name__)
network_logger = logging.getLogger('bot.network')

class HealthMonitor:
    """Монитор состояния соединения бота с Telegram API"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.is_healthy = True
        self.max_failures = 3
        
    async def check_connection(self) -> bool:
        """
        Проверка соединения с Telegram API
        Возвращает True если соединение работает
        """
        try:
            bot = Bot(token=self.bot_token)
            
            # Простая проверка - получение информации о боте
            await bot.get_me()
            
            # Успешная проверка
            self.last_success_time = time.time()
            if self.consecutive_failures > 0:
                network_logger.info(f"Соединение восстановлено после {self.consecutive_failures} неудачных попыток")
            
            self.consecutive_failures = 0
            self.is_healthy = True
            
            return True
            
        except (NetworkError, TimedOut, httpx.ConnectError, httpx.TimeoutException) as e:
            self.consecutive_failures += 1
            
            if self.consecutive_failures == 1:
                network_logger.warning(f"Первая неудачная проверка соединения: {e}")
            elif self.consecutive_failures >= self.max_failures:
                if self.is_healthy:  # логируем только при переходе из здорового состояния
                    network_logger.error(
                        f"Соединение нестабильно: {self.consecutive_failures} неудачных попыток подряд. "
                        f"Последняя успешная проверка: {time.time() - self.last_success_time:.1f} сек назад"
                    )
                self.is_healthy = False
            
            return False
            
        except Exception as e:
            logger.error(f"Неожиданная ошибка при проверке соединения: {e}", exc_info=True)
            self.consecutive_failures += 1
            return False
    
    def get_status_info(self) -> dict:
        """Получение информации о состоянии соединения"""
        return {
            'is_healthy': self.is_healthy,
            'consecutive_failures': self.consecutive_failures,
            'last_success_time': self.last_success_time,
            'time_since_last_success': time.time() - self.last_success_time
        }
    
    async def start_monitoring(self, check_interval: int = 60):
        """
        Запуск фонового мониторинга соединения
        
        Args:
            check_interval: интервал проверки в секундах
        """
        logger.info(f"Запуск мониторинга соединения (интервал: {check_interval}с)")
        
        while True:
            try:
                await self.check_connection()
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                logger.info("Мониторинг соединения остановлен")
                break
                
            except Exception as e:
                logger.error(f"Ошибка в мониторе соединения: {e}", exc_info=True)
                await asyncio.sleep(check_interval)
