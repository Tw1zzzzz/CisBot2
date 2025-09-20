"""
Интеграция с Faceit Analyser API для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import aiohttp
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Tuple, Set, List
from datetime import datetime, timedelta
import re
import io
import base64
import time

from bot.config import Config
from bot.utils.cs2_data import extract_faceit_nickname
from bot.utils.background_processor import get_background_processor, TaskPriority
from .faceit_cache import FaceitCacheManager

# Инициализируем logger до импортов
logger = logging.getLogger(__name__)

# Импортируем библиотеки для создания графиков
# Импорты диаграмм отключены

try:
    # Scipy для анализа пиков и трендов
    from scipy.signal import find_peaks
    from scipy import stats
    SCIPY_AVAILABLE = True
    
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy не установлен - продвинутая аналитика недоступна")

try:
    # Pandas для работы с данными
    import pandas as pd
    PANDAS_AVAILABLE = True
    
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("pandas не установлен - некоторые функции недоступны")

class FaceitAnalyzer:
    """Класс для работы с Faceit Analyser API с поддержкой фонового процессора"""
    
    def __init__(self, cache_manager: Optional['FaceitCacheManager'] = None, db_manager: Optional['DatabaseManager'] = None):
        self.api_key = Config.FACEIT_ANALYSER_API_KEY
        self.base_url = Config.FACEIT_ANALYSER_BASE_URL
        self.cache_ttl = Config.FACEIT_ANALYSER_CACHE_TTL
        self.cache_manager = cache_manager  # Accept injected cache manager
        self.db_manager = db_manager  # Accept injected database manager
        self._request_deduplication: Set[str] = set()  # Active request tracking
        self._dedup_lock = asyncio.Lock()
        
        # Performance monitoring integration
        self.performance_monitor = None
        
        # Cache statistics integrated with persistent cache
        self._cache_stats = {
            'background_requests': 0,
            'failed_requests': 0,
            'user_network_warmed': 0
        }
        
        # Circuit breaker tracking
        self._failure_count = 0
        self._last_failure_time = None
        self._circuit_open = False
        
        if not self.api_key:
            logger.warning("FACEIT_ANALYSER_API_KEY не установлен в конфигурации")
    
    def set_performance_monitor(self, performance_monitor):
        """Set performance monitor instance for tracking API performance"""
        self.performance_monitor = performance_monitor
        logger.debug("Performance monitor integrated into FaceitAnalyzer")
    
    def _get_cache_manager(self) -> Optional['FaceitCacheManager']:
        """Lazy binding to get cache manager - use injected instance or fall back to shared global instance"""
        if self.cache_manager is not None:
            return self.cache_manager
            
        # Try to get shared cache manager from main
        try:
            from bot.main import get_shared_cache_manager
            shared_manager = get_shared_cache_manager()
            if shared_manager is not None:
                self.cache_manager = shared_manager
                logger.debug("FaceitAnalyzer: Using shared cache manager from main")
                return shared_manager
        except ImportError:
            logger.debug("Could not import shared cache manager from main")
            
        # Fallback: create a new instance (should be rare)  
        logger.warning("FaceitAnalyzer: Creating fallback cache manager instance - no shared manager available")
        self.cache_manager = FaceitCacheManager()
        # Note: Fallback cache manager will auto-initialize when first used
        # This is acceptable since it means main.py isn't managing the lifecycle
        return self.cache_manager
    
    def _get_db_manager(self) -> Optional['DatabaseManager']:
        """Lazy binding to get database manager - use injected instance or fall back to shared instance"""
        if self.db_manager is not None:
            return self.db_manager
            
        # Try to get shared database manager from main
        try:
            from bot.main import get_shared_db_manager
            shared_manager = get_shared_db_manager()
            if shared_manager is not None:
                self.db_manager = shared_manager
                logger.debug("FaceitAnalyzer: Using shared database manager from main")
                return shared_manager
        except ImportError:
            logger.debug("Could not import shared database manager from main")
            
        # No fallback for database manager - it requires proper configuration
        logger.warning("FaceitAnalyzer: No database manager available for user network warming")
        return None
    
    # TTL validation is now handled by cache manager internally
    
    def _get_player_id_from_faceit_url(self, faceit_url: str) -> Optional[str]:
        """Извлекает player ID из Faceit URL"""
        try:
            # Извлекаем никнейм из URL
            nickname = extract_faceit_nickname(faceit_url)
            if not nickname:
                logger.debug(f"URL не содержит валидный никнейм Faceit: {faceit_url}")
                return None
            
            # Проверяем что никнейм не является тестовым/недействительным
            if nickname.lower() in ['bottest', 'test', 'example', 'demo']:
                logger.debug(f"Пропуск тестового никнейма: {nickname}")
                return None
            
            # В Faceit Analyser API используется nickname как player ID
            return nickname
            
        except Exception as e:
            logger.error(f"Ошибка извлечения player ID из {faceit_url}: {e}")
            return None
    
    async def _make_api_request(self, endpoint: str, player_id: str) -> Optional[Dict[str, Any]]:
        """Выполняет запрос к Faceit Analyser API с поддержкой circuit breaker и мониторинга производительности"""
        if not self.api_key:
            logger.warning("API ключ Faceit Analyser не установлен")
            return None
        
        # Check circuit breaker state
        if self._circuit_open:
            # Check if enough time has passed to reset circuit breaker
            if (self._last_failure_time and 
                datetime.now().timestamp() - self._last_failure_time > Config.FACEIT_CIRCUIT_BREAKER_RESET_TIME):
                logger.info("Пытаемся сбросить circuit breaker после таймаута")
                self._circuit_open = False
                self._failure_count = 0
            else:
                logger.warning(f"Circuit breaker открыт - пропускаем запрос для {player_id}")
                return None
        
        url = f"{self.base_url}{endpoint}/{player_id}"
        params = {"key": self.api_key}
        
        # Start performance tracking
        start_time = time.time()
        success = False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=Config.FACEIT_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Reset failure count on successful request
                        self._failure_count = 0
                        success = True
                        logger.debug(f"Успешный запрос к {endpoint} для {player_id}")
                        return data
                    elif response.status == 404:
                        logger.warning(f"Игрок {player_id} не найден в Faceit Analyser")
                        success = True  # 404 is not a failure for monitoring purposes
                        return None
                    elif response.status == 401:
                        logger.error(f"Неверный API ключ для Faceit Analyser")
                        return None
                    elif response.status == 429:
                        logger.warning(f"Превышен лимит запросов к Faceit Analyser API")
                        return None
                    else:
                        logger.error(f"Ошибка API Faceit Analyser: {response.status}")
                        self._track_failure()
                        return None
                        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут запроса к Faceit Analyser для {player_id}")
            self._track_failure()
            return None
        except Exception as e:
            logger.error(f"Исключение при запросе к Faceit Analyser для {player_id}: {e}")
            self._track_failure()
            return None
        finally:
            # Record performance metrics
            duration = time.time() - start_time
            if self.performance_monitor:
                try:
                    self.performance_monitor.record_api_response(
                        endpoint=f"faceit_analyzer_{endpoint}",
                        duration=duration,
                        success=success
                    )
                except Exception as e:
                    logger.debug(f"Error recording API performance: {e}")
            
            # Log slow requests
            if duration > getattr(Config, 'API_SLOW_ENDPOINT_THRESHOLD', 3.0):
                logger.warning(f"Slow API request: {endpoint} for {player_id} took {duration:.3f}s")
    
    def _track_failure(self):
        """Отслеживает неудачные запросы и управляет circuit breaker"""
        self._failure_count += 1
        self._last_failure_time = datetime.now().timestamp()
        self._cache_stats['failed_requests'] += 1
        
        if self._failure_count >= Config.FACEIT_CIRCUIT_BREAKER_THRESHOLD:
            if not self._circuit_open:
                logger.warning(f"Circuit breaker открыт после {self._failure_count} неудачных попыток")
            self._circuit_open = True
    
    async def get_player_overview(self, faceit_url: str) -> Optional[Dict[str, Any]]:
        """Получает общую информацию о игроке с использованием постоянного кеша"""
        player_id = self._get_player_id_from_faceit_url(faceit_url)
        if not player_id:
            return None
        
        # Проверяем постоянный кеш
        cache_manager = self._get_cache_manager()
        if cache_manager:
            cached_data = await cache_manager.get(player_id, 'overview')
            if cached_data:
                logger.debug(f"Возвращаем cached overview для {player_id}")
                return cached_data
        
        # Запрашиваем данные из API
        data = await self._make_api_request("overview", player_id)
        if data and cache_manager:
            # Сохраняем в постоянный кеш с умным TTL
            await cache_manager.set(player_id, 'overview', data)
        
        return data
    
    async def get_player_stats(self, faceit_url: str) -> Optional[Dict[str, Any]]:
        """Получает подробную статистику игрока с использованием постоянного кеша"""
        player_id = self._get_player_id_from_faceit_url(faceit_url)
        if not player_id:
            return None
        
        # Проверяем постоянный кеш
        cache_manager = self._get_cache_manager()
        if cache_manager:
            cached_data = await cache_manager.get(player_id, 'stats')
            if cached_data:
                logger.debug(f"Возвращаем cached stats для {player_id}")
                return cached_data
        
        # Запрашиваем данные из API
        data = await self._make_api_request("stats", player_id)
        if data and cache_manager:
            # Сохраняем в постоянный кеш с умным TTL
            await cache_manager.set(player_id, 'stats', data)
        
        return data
    
    # get_player_graphs удалена - диаграммы отключены
    
    def create_elo_diagram(self, graph_data: Dict[str, Any]) -> Optional[str]:
        """Создание диаграмм отключено"""
        return None
    
    def _old_create_elo_diagram_disabled(self, graph_data: Dict[str, Any]) -> Optional[str]:
        """Создает красивую текстовую диаграмму ELO из данных API"""
        try:
            if not graph_data or 'graph_data' not in graph_data:
                return None
            
            elo_data = graph_data['graph_data'].get('elo')
            if not elo_data or 'values' not in elo_data:
                return None
            
            values = elo_data['values']
            dates = elo_data.get('dates', [])
            
            if not values or len(values) == 0:
                return None
            
            # Берем последние 8 значений для компактности
            recent_values = values[-8:] if len(values) >= 8 else values
            recent_dates = dates[-8:] if dates and len(dates) >= 8 else []
            
            if not recent_values:
                return None
            
            # Находим минимальное и максимальное значения для масштабирования
            min_elo = min(recent_values)
            max_elo = max(recent_values)
            current_elo = recent_values[-1]
            
            # Если разница слишком мала, добавляем отступы
            if max_elo - min_elo < 100:
                padding = 50
                min_elo -= padding
                max_elo += padding
            
            # Создаем красивую вертикальную диаграмму
            diagram_lines = []
            diagram_lines.append("📊 <b>График ELO (последние матчи):</b>")
            diagram_lines.append("")
            
            # Создаем вертикальную диаграмму (снизу вверх)
            height = 8  # Высота диаграммы
            width = len(recent_values)
            
            # Массив для хранения диаграммы
            grid = []
            for _ in range(height + 2):  # +2 для оси и значений
                grid.append([" "] * (width * 3 + 5))  # *3 для ширины колонок
            
            # Заполняем диаграмму
            for i, elo in enumerate(recent_values):
                # Вычисляем высоту столбца (0-height)
                if max_elo > min_elo:
                    bar_height = int(((elo - min_elo) / (max_elo - min_elo)) * height)
                else:
                    bar_height = height // 2
                
                # Определяем цвет/символ столбца
                if i == len(recent_values) - 1:  # Последнее значение
                    bar_char = "🟦"  # Синий для текущего
                elif i > 0:
                    if recent_values[i] > recent_values[i-1]:
                        bar_char = "🟩"  # Зеленый для роста
                    elif recent_values[i] < recent_values[i-1]:
                        bar_char = "🟥"  # Красный для падения
                    else:
                        bar_char = "⬜"  # Белый для без изменений
                else:
                    bar_char = "⬜"
                
                # Заполняем столбец снизу вверх
                col_pos = i * 3 + 2
                for row in range(max(0, height - bar_height), height):
                    if row < len(grid) - 2:
                        grid[row][col_pos] = bar_char
                
                # Добавляем значение ELO под столбцом
                elo_str = str(elo)
                for j, char in enumerate(elo_str):
                    if col_pos + j < len(grid[height]):
                        grid[height][col_pos + j] = char
                
                # Добавляем индекс матча
                match_num = f"#{i+1}"
                for j, char in enumerate(match_num):
                    if col_pos + j < len(grid[height + 1]):
                        grid[height + 1][col_pos + j] = char
            
            # Преобразуем сетку в строки
            for row in grid:
                line = "".join(row).rstrip()
                if line.strip():  # Только не пустые строки
                    diagram_lines.append(f"<code>{line}</code>")
            
            diagram_lines.append("")
            
            # Статистика
            diagram_lines.append(f"🎯 <b>Текущий ELO:</b> {current_elo}")
            
            # Пик и минимум
            peak_elo = max(values)
            lowest_elo = min(values)
            diagram_lines.append(f"📈 <b>Пик:</b> {peak_elo} | 📉 <b>Минимум:</b> {lowest_elo}")
            
            # Тренд за последние матчи
            if len(recent_values) >= 2:
                trend = recent_values[-1] - recent_values[0]
                if trend > 0:
                    trend_emoji = "🚀"
                    trend_text = f"+{trend}"
                    trend_desc = "Растет"
                elif trend < 0:
                    trend_emoji = "📉"
                    trend_text = str(trend)
                    trend_desc = "Падает"
                else:
                    trend_emoji = "➡️"
                    trend_text = "±0"
                    trend_desc = "Стабилен"
                
                diagram_lines.append(f"{trend_emoji} <b>Тренд:</b> {trend_text} ({trend_desc})")
            
            # Средний ELO за последние матчи
            avg_elo = sum(recent_values) // len(recent_values)
            diagram_lines.append(f"📊 <b>Средний ELO:</b> {avg_elo}")
            
            return "\n".join(diagram_lines)
            
        except Exception as e:
            logger.error(f"Ошибка создания ELO диаграммы: {e}")
            return None
    
    def create_interactive_elo_graph(self, graph_data: Dict[str, Any]) -> Optional[io.BytesIO]:
        """Создание диаграмм отключено"""
        return None
    
    def _old_create_interactive_elo_graph_disabled(self, graph_data: Dict[str, Any]) -> Optional[io.BytesIO]:
        """Создает интерактивную диаграмму ELO с Plotly - профессионального уровня"""
        if not PLOTLY_AVAILABLE:
            logger.warning("Plotly недоступен для создания интерактивных диаграмм")
            return self.create_elo_graph_image(graph_data)  # Fallback к matplotlib
        
        try:
            if not graph_data or 'graph_data' not in graph_data:
                return None
            
            elo_data = graph_data['graph_data'].get('elo')
            if not elo_data or 'values' not in elo_data:
                return None
            
            values = elo_data['values']
            dates = elo_data.get('dates', [])
            
            if not values or len(values) == 0:
                return None
            
            # Берем данные для анализа (до 30 последних матчей)
            recent_values = values[-30:] if len(values) >= 30 else values
            recent_dates = dates[-30:] if dates and len(dates) >= 30 else []
            
            # Подготавливаем данные
            if PANDAS_AVAILABLE and recent_dates:
                # Используем реальные даты если есть
                try:
                    df = pd.DataFrame({
                        'match': range(1, len(recent_values) + 1),
                        'elo': recent_values,
                        'date': pd.to_datetime(recent_dates) if recent_dates else None
                    })
                    x_values = df['date'] if recent_dates else df['match']
                    x_title = "Дата матча" if recent_dates else "Номер матча"
                except:
                    # Fallback если даты некорректные
                    df = pd.DataFrame({
                        'match': range(1, len(recent_values) + 1),
                        'elo': recent_values
                    })
                    x_values = df['match']
                    x_title = "Номер матча"
            else:
                # Без pandas - простые данные
                x_values = list(range(1, len(recent_values) + 1))
                x_title = "Номер матча"
            
            # Создаем figure
            fig = go.Figure()
            
            # Аналитика и детекция пиков
            peaks_indices = []
            valleys_indices = []
            
            if SCIPY_AVAILABLE and len(recent_values) >= 5:
                # Детекция пиков (высокие точки)
                peaks, _ = find_peaks(recent_values, distance=2)
                # Детекция провалов (низкие точки)
                valleys, _ = find_peaks([-x for x in recent_values], distance=2)
                
                peaks_indices = peaks.tolist()
                valleys_indices = valleys.tolist()
            
            # Скользящее среднее
            if PANDAS_AVAILABLE and len(recent_values) >= 5:
                df = pd.DataFrame({'elo': recent_values})
                rolling_mean = df['elo'].rolling(window=min(5, len(recent_values)//2), center=True).mean()
            else:
                # Простое скользящее среднее без pandas
                window = min(5, len(recent_values)//2)
                rolling_mean = []
                for i in range(len(recent_values)):
                    start_idx = max(0, i - window//2)
                    end_idx = min(len(recent_values), i + window//2 + 1)
                    rolling_mean.append(sum(recent_values[start_idx:end_idx]) / (end_idx - start_idx))
            
            # Определяем цвета для точек
            colors = []
            for i, elo in enumerate(recent_values):
                if i in peaks_indices:
                    colors.append('#FFD700')  # Золотой для пиков
                elif i in valleys_indices:
                    colors.append('#FF4444')  # Красный для провалов
                elif i == len(recent_values) - 1:
                    colors.append('#00E5FF')  # Яркий голубой для текущего
                elif i > 0:
                    if recent_values[i] > recent_values[i-1]:
                        colors.append('#4CAF50')  # Зеленый для роста
                    elif recent_values[i] < recent_values[i-1]:
                        colors.append('#F44336')  # Красный для падения
                    else:
                        colors.append('#9E9E9E')  # Серый для стабильности
                else:
                    colors.append('#9E9E9E')
            
            # Основная линия ELO
            fig.add_trace(go.Scatter(
                x=x_values,
                y=recent_values,
                mode='lines+markers',
                name='ELO',
                line=dict(color='#81C784', width=3),
                marker=dict(
                    color=colors,
                    size=10,
                    line=dict(color='white', width=2)
                ),
                text=[f"Матч {i+1}<br>ELO: {elo}<br>{'Пик!' if i in peaks_indices else 'Провал!' if i in valleys_indices else 'Рост' if i > 0 and recent_values[i] > recent_values[i-1] else 'Падение' if i > 0 and recent_values[i] < recent_values[i-1] else 'Начало'}" for i, elo in enumerate(recent_values)],
                hovertemplate='<b>%{text}</b><br>%{x}<extra></extra>',
                connectgaps=True
            ))
            
            # Скользящее среднее
            fig.add_trace(go.Scatter(
                x=x_values,
                y=rolling_mean,
                mode='lines',
                name='Тренд (среднее)',
                line=dict(color='#FF9800', width=2, dash='dash'),
                opacity=0.8,
                hovertemplate='<b>Тренд</b><br>ELO: %{y:.0f}<extra></extra>'
            ))
            
            # Заливка области
            min_y = min(recent_values)
            fig.add_trace(go.Scatter(
                x=x_values + x_values[::-1],
                y=recent_values + [min_y] * len(recent_values),
                fill='toself',
                fillcolor='rgba(76, 175, 80, 0.1)',
                line=dict(color='rgba(255,255,255,0)'),
                name='Область ELO',
                showlegend=False,
                hoverinfo='skip'
            ))
            
            # Аннотации для важных точек
            current_elo = recent_values[-1]
            max_elo = max(values)  # Пик за всю историю
            min_elo = min(values)  # Минимум за всю историю
            
            # Аннотация текущего ELO
            fig.add_annotation(
                x=x_values[-1],
                y=current_elo,
                text=f"<b>Сейчас: {current_elo}</b>",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#00E5FF",
                arrowwidth=2,
                bgcolor="#00E5FF",
                bordercolor="white",
                font=dict(color="white", size=12)
            )
            
            # Аннотации пиков
            for peak_idx in peaks_indices[:3]:  # Показываем максимум 3 пика
                if peak_idx < len(recent_values):
                    fig.add_annotation(
                        x=x_values[peak_idx],
                        y=recent_values[peak_idx],
                        text=f"📈 {recent_values[peak_idx]}",
                        showarrow=True,
                        arrowhead=1,
                        arrowcolor="#FFD700",
                        bgcolor="#FFD700",
                        font=dict(color="black", size=10),
                        yshift=15
                    )
            
            # Настройка layout
            trend = recent_values[-1] - recent_values[0] if len(recent_values) > 1 else 0
            trend_symbol = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
            
            fig.update_layout(
                title=dict(
                    text=f'<b>Faceit ELO Анализ {trend_symbol}</b><br><sub>Текущий: {current_elo} | Тренд: {int(trend):+d} | Пик: {max_elo}</sub>',
                    x=0.5,
                    font=dict(size=18, color='white')
                ),
                paper_bgcolor='#1a1a1a',
                plot_bgcolor='#1a1a1a',
                font=dict(color='white', family='Arial, sans-serif'),
                
                xaxis=dict(
                    title=dict(text=x_title, font=dict(size=14)),
                    gridcolor='rgba(255,255,255,0.1)',
                    showgrid=True,
                    zeroline=False,
                    color='white',
                    # Range selector для навигации
                    rangeslider=dict(visible=True, bgcolor='#2a2a2a'),
                    rangeselector=dict(
                        buttons=list([
                            dict(count=5, label="5M", step="all", stepmode="backward"),
                            dict(count=10, label="10M", step="all", stepmode="backward"),
                            dict(count=15, label="15M", step="all", stepmode="backward"),
                            dict(step="all", label="ВСЕ")
                        ]),
                        bgcolor='#2a2a2a',
                        font=dict(color='white')
                    )
                ),
                
                yaxis=dict(
                    title=dict(text='ELO Rating', font=dict(size=14)),
                    gridcolor='rgba(255,255,255,0.1)',
                    showgrid=True,
                    zeroline=False,
                    color='white'
                ),
                
                legend=dict(
                    bgcolor='rgba(0,0,0,0.5)',
                    font=dict(color='white'),
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='right',
                    x=1
                ),
                
                hovermode='x unified',
                
                annotations=[
                    # Статистика в углу
                    dict(
                        xref='paper', yref='paper',
                        x=0.02, y=0.98,
                        text=f'''<b>📊 Статистика:</b><br>
Матчей: {len(recent_values)}<br>
Макс: {max_elo}<br>
Мин: {min_elo}<br>
Средний: {sum(recent_values)//len(recent_values)}<br>
Пиков: {len(peaks_indices)}<br>
Провалов: {len(valleys_indices)}''',
                        showarrow=False,
                        bgcolor='rgba(0,0,0,0.7)',
                        font=dict(color='white', size=10),
                        align='left',
                        valign='top'
                    )
                ],
                
                # Адаптивный размер
                autosize=True,
                width=1200,
                height=800,
                margin=dict(l=60, r=60, t=100, b=80)
            )
            
            # Сохраняем как изображение
            img_buffer = io.BytesIO()
            fig.write_image(img_buffer, format='PNG', width=1200, height=800, scale=2)
            img_buffer.seek(0)
            
            logger.debug("Интерактивная Plotly диаграмма создана успешно")
            return img_buffer
            
        except Exception as e:
            logger.error(f"Ошибка создания интерактивной Plotly диаграммы: {e}")
            # Fallback к matplotlib версии
            return self.create_elo_graph_image(graph_data)
    
    def create_elo_graph_image(self, graph_data: Dict[str, Any]) -> Optional[io.BytesIO]:
        """Создание диаграмм отключено"""
        return None
    
    def _old_create_elo_graph_image_disabled(self, graph_data: Dict[str, Any]) -> Optional[io.BytesIO]:
        """Создает красивую графическую диаграмму ELO как изображение"""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib недоступен для создания графических диаграмм")
            return None
        
        try:
            if not graph_data or 'graph_data' not in graph_data:
                return None
            
            elo_data = graph_data['graph_data'].get('elo')
            if not elo_data or 'values' not in elo_data:
                return None
            
            values = elo_data['values']
            dates = elo_data.get('dates', [])
            
            if not values or len(values) == 0:
                return None
            
            # Берем последние 15 матчей для графика
            recent_values = values[-15:] if len(values) >= 15 else values
            
            # Создаем figure с красивым дизайном
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(12, 8), facecolor='#1a1a1a')
            ax.set_facecolor('#1a1a1a')
            
            # Создаем x-координаты (номера матчей)
            x = list(range(1, len(recent_values) + 1))
            
            # Определяем цвета для точек
            colors = []
            for i, elo in enumerate(recent_values):
                if i == len(recent_values) - 1:  # Последнее значение
                    colors.append('#4FC3F7')  # Голубой
                elif i > 0:
                    if recent_values[i] > recent_values[i-1]:
                        colors.append('#66BB6A')  # Зеленый
                    elif recent_values[i] < recent_values[i-1]:
                        colors.append('#EF5350')  # Красный
                    else:
                        colors.append('#9E9E9E')  # Серый
                else:
                    colors.append('#9E9E9E')
            
            # Рисуем линию графика
            ax.plot(x, recent_values, color='#81C784', linewidth=3, alpha=0.8, zorder=2)
            
            # Добавляем точки на график
            ax.scatter(x, recent_values, c=colors, s=100, alpha=0.9, zorder=3, edgecolors='white', linewidth=2)
            
            # Заливаем область под графиком
            ax.fill_between(x, recent_values, alpha=0.3, color='#4CAF50', zorder=1)
            
            # Настройка осей
            ax.set_xlabel('Матч', fontsize=14, color='white', fontweight='bold')
            ax.set_ylabel('ELO Rating', fontsize=14, color='white', fontweight='bold')
            
            # Заголовок
            current_elo = recent_values[-1]
            trend = recent_values[-1] - recent_values[0] if len(recent_values) > 1 else 0
            trend_symbol = "↗️" if trend > 0 else "↘️" if trend < 0 else "→"
            
            ax.set_title(f'Faceit ELO График {trend_symbol} Текущий: {current_elo} ({int(trend):+d})', 
                        fontsize=16, color='white', fontweight='bold', pad=20)
            
            # Сетка
            ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
            
            # Настройка цвета осей и делений
            ax.tick_params(colors='white', which='both', labelsize=12)
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white') 
            ax.spines['right'].set_color('white')
            ax.spines['left'].set_color('white')
            
            # Добавляем аннотации для текущего и максимального ELO
            max_elo = max(recent_values)
            max_idx = recent_values.index(max_elo) + 1
            
            # Аннотация для пика
            ax.annotate(f'Пик: {max_elo}', 
                       xy=(max_idx, max_elo), 
                       xytext=(max_idx, max_elo + 50),
                       arrowprops=dict(arrowstyle='->', color='#FFD54F', lw=2),
                       fontsize=12, color='#FFD54F', fontweight='bold',
                       ha='center')
            
            # Аннотация для текущего ELO
            current_idx = len(recent_values)
            ax.annotate(f'Сейчас: {current_elo}', 
                       xy=(current_idx, current_elo), 
                       xytext=(current_idx + 0.5, current_elo + 30),
                       arrowprops=dict(arrowstyle='->', color='#4FC3F7', lw=2),
                       fontsize=12, color='#4FC3F7', fontweight='bold',
                       ha='center')
            
            # Добавляем статистику в правый нижний угол
            stats_text = f"""Матчей: {len(recent_values)}
Пик: {max(values)}
Минимум: {min(values)}
Тренд: {int(trend):+d}"""
            
            ax.text(0.98, 0.02, stats_text, transform=ax.transAxes, 
                   fontsize=11, color='white', ha='right', va='bottom',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7))
            
            # Устанавливаем пределы осей
            padding = (max(recent_values) - min(recent_values)) * 0.1
            ax.set_ylim(min(recent_values) - padding, max(recent_values) + padding + 50)
            ax.set_xlim(0.5, len(recent_values) + 0.5)
            
            # Сохраняем в BytesIO
            img_buffer = io.BytesIO()
            plt.tight_layout()
            plt.savefig(img_buffer, format='PNG', facecolor='#1a1a1a', 
                       bbox_inches='tight', dpi=150)
            plt.close(fig)  # Очищаем память
            
            img_buffer.seek(0)
            return img_buffer
            
        except Exception as e:
            logger.error(f"Ошибка создания графической ELO диаграммы: {e}")
            if 'fig' in locals():
                plt.close(fig)  # Очищаем память при ошибке
            return None
    
    async def get_elo_stats_by_nickname(self, nickname: str) -> Optional[Dict[str, Any]]:
        """Получает статистику ELO по игровому никнейму"""
        if not nickname or not nickname.strip():
            logger.debug("Пустой никнейм, пропускаем запрос")
            return None
        
        try:
            # Используем никнейм напрямую как player_id для Faceit Analyser API
            player_id = nickname.strip()
            
            # Проверяем постоянный кеш
            cache_manager = self._get_cache_manager()
            if cache_manager:
                cached_data = await cache_manager.get(player_id, 'elo_stats')
                if cached_data:
                    logger.debug(f"Возвращаем cached elo stats для {player_id}")
                    return cached_data
            
            # УЛУЧШЕННАЯ ДИАГНОСТИКА: логируем попытку запроса
            logger.info(f"🔍 Запрашиваем ELO статистику для игрока: {player_id}")
            logger.info(f"🔑 API ключ установлен: {self.api_key is not None}")
            logger.info(f"🌐 Base URL: {self.base_url}")
            
            # Запрашиваем статистику
            stats = await self._make_api_request("stats", player_id)
            
            if not stats:
                logger.warning(f"❌ Не удалось получить статистику для никнейма: {nickname}")
                # Возвращаем частичные данные чтобы показать что функция работает
                return {
                    'nickname': nickname,
                    'current_elo': 0,
                    'highest_elo': 0,
                    'lowest_elo': 0,
                    'matches': 0,
                    'api_error': True
                }
            
            logger.info(f"✅ Получены данные API для {nickname}: {list(stats.keys())}")
            
            # Извлекаем ELO данные с более подробным логированием (ИСПРАВЛЕННЫЕ КЛЮЧИ)
            current_elo = stats.get('current_elo', 0)
            highest_elo = stats.get('highest_elo', 0) 
            lowest_elo = stats.get('lowest_elo', 0)
            matches = stats.get('m', 0)
            
            logger.info(f"📊 Извлеченные ELO данные для {nickname}:")
            logger.info(f"   Текущий ELO: {current_elo}")
            logger.info(f"   Максимальный ELO: {highest_elo}")
            logger.info(f"   Минимальный ELO: {lowest_elo}")
            logger.info(f"   Матчи: {matches}")
            
            result = {
                'nickname': nickname,
                'current_elo': current_elo,
                'highest_elo': highest_elo,
                'lowest_elo': lowest_elo,
                'matches': matches
            }
            
            # Сохраняем в постоянный кеш с умным TTL
            if cache_manager:
                await cache_manager.set(player_id, 'elo_stats', result)
            
            logger.info(f"✅ Успешно получена ELO статистика для {nickname}: Мин:{result['lowest_elo']} Макс:{result['highest_elo']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка получения ELO статистики для {nickname}: {e}", exc_info=True)
            self._cache_stats['failed_requests'] += 1
            # Возвращаем частичные данные с ошибкой
            return {
                'nickname': nickname,
                'current_elo': 0,
                'highest_elo': 0,
                'lowest_elo': 0,
                'matches': 0,
                'error': str(e)
            }

    async def get_enhanced_profile_info(self, faceit_url: str) -> Optional[Dict[str, Any]]:
        """Получает расширенную информацию о профиле для анкеты"""
        try:
            # Быстрая проверка валидности URL
            player_id = self._get_player_id_from_faceit_url(faceit_url)
            if not player_id:
                logger.debug(f"Невалидный Faceit URL, пропускаем: {faceit_url}")
                return None
            
            # Получаем все необходимые данные параллельно
            overview_task = self.get_player_overview(faceit_url)
            stats_task = self.get_player_stats(faceit_url)
            
            overview, stats = await asyncio.gather(
                overview_task, stats_task,
                return_exceptions=True
            )
            
            # Обрабатываем исключения
            if isinstance(overview, Exception):
                logger.error(f"Ошибка получения overview: {overview}")
                overview = None
            if isinstance(stats, Exception):
                logger.error(f"Ошибка получения stats: {stats}")
                stats = None
            
            if not any([overview, stats]):
                return None
            
            result = {}
            
            # Добавляем основную статистику если есть (ИСПРАВЛЕННЫЕ КЛЮЧИ)
            if stats:
                result['stats'] = {
                    'matches': stats.get('m', 0),
                    'wins': stats.get('w', 0),
                    'kills': stats.get('k', 0),
                    'deaths': stats.get('d', 0),
                    'kdr': stats.get('kdr', 0),
                    'hltv_rating': stats.get('hltv', 0),
                    'current_elo': stats.get('current_elo', 0),
                    'highest_elo': stats.get('highest_elo', 0),
                    'lowest_elo': stats.get('lowest_elo', 0)
                }
            
            # Диаграммы отключены
            return result if result else None
            
        except Exception as e:
            logger.error(f"Ошибка получения расширенной информации профиля: {e}")
            return None
    
    async def get_elo_stats_by_nickname_async(self, nickname: str) -> asyncio.Future:
        """Получает ELO статистику асинхронно через фоновый процессор (NORMAL priority)"""
        return await self.get_elo_stats_by_nickname_priority(nickname, TaskPriority.NORMAL)
    
    async def get_elo_stats_by_nickname_priority(self, nickname: str, priority: TaskPriority = TaskPriority.NORMAL) -> asyncio.Future:
        """Получает ELO статистику с указанным приоритетом через фоновый процессор"""
        if not nickname or not nickname.strip():
            future = asyncio.get_event_loop().create_future()
            future.set_result(None)
            return future
        
        try:
            # Check for active request deduplication
            dedup_key = f"elo_{nickname.strip()}"
            async with self._dedup_lock:
                if dedup_key in self._request_deduplication:
                    logger.debug(f"Запрос для {nickname} уже выполняется, создаем новую задачу")
                    # Still enqueue but with lower priority to avoid blocking
                    priority = TaskPriority.LOW
                else:
                    self._request_deduplication.add(dedup_key)
            
            # Get background processor and enqueue task
            bg_processor = get_background_processor()
            future = await bg_processor.enqueue(
                self._background_get_elo_stats,
                nickname.strip(),
                dedup_key,
                priority=priority
            )
            
            self._cache_stats['background_requests'] += 1
            logger.debug(f"ELO запрос для {nickname} добавлен в фоновую очередь с приоритетом {priority.name}")
            return future
            
        except Exception as e:
            logger.error(f"Ошибка создания фонового запроса ELO для {nickname}: {e}")
            self._cache_stats['failed_requests'] += 1
            # Remove dedup_key from deduplication set to prevent stale dedup state
            async with self._dedup_lock:
                self._request_deduplication.discard(dedup_key)
            # Fallback to direct API call
            future = asyncio.get_event_loop().create_future()
            try:
                result = await self.get_elo_stats_by_nickname(nickname)
                future.set_result(result)
            except Exception as direct_error:
                future.set_exception(direct_error)
            return future
    
    async def _background_get_elo_stats(self, nickname: str, dedup_key: str) -> Optional[Dict[str, Any]]:
        """Вспомогательный метод для фонового получения ELO статистики"""
        try:
            result = await self.get_elo_stats_by_nickname(nickname)
            return result
        except Exception as e:
            logger.error(f"Ошибка фонового получения ELO для {nickname}: {e}")
            raise
        finally:
            # Remove from deduplication set
            async with self._dedup_lock:
                self._request_deduplication.discard(dedup_key)
    
    async def preload_elo_stats(self, nicknames: list[str]) -> None:
        """Предзагрузка ELO статистики в фоновом режиме с LOW приоритетом"""
        if not nicknames:
            return
        
        logger.info(f"🚀 Запуск предзагрузки ELO для {len(nicknames)} игроков")
        tasks = []
        
        for nickname in nicknames:
            if nickname and nickname.strip():
                try:
                    future = await self.get_elo_stats_by_nickname_priority(nickname, TaskPriority.LOW)
                    tasks.append(future)
                except Exception as e:
                    logger.warning(f"Ошибка создания задачи предзагрузки для {nickname}: {e}")
        
        if tasks:
            # Don't wait for results, just start the background loading
            logger.info(f"✅ Запущена предзагрузка для {len(tasks)} игроков в фоновом режиме")
    
    async def preload_popular_profiles(self) -> int:
        """Предзагрузка популярных профилей при запуске бота"""
        try:
            cache_manager = self._get_cache_manager()
            if not cache_manager:
                logger.warning("Cache manager недоступен для предзагрузки популярных профилей")
                return 0
            
            # Получаем популярные профили из базы данных
            if not self.db_manager:
                logger.warning("Database manager недоступен для предзагрузки")
                return 0
            
            # Получаем топ популярных игроков из базы данных
            popular_nicknames = await self._get_popular_nicknames_from_db()
            
            if popular_nicknames:
                logger.info(f"🎯 Найдено {len(popular_nicknames)} популярных профилей для предзагрузки")
                await self.preload_elo_stats(popular_nicknames)
                return len(popular_nicknames)
            else:
                logger.info("📊 Популярные профили не найдены для предзагрузки")
                return 0
                
        except Exception as e:
            logger.error(f"Ошибка предзагрузки популярных профилей: {e}")
            return 0
    
    async def _get_popular_nicknames_from_db(self) -> list[str]:
        """Получает список популярных никнеймов из базы данных"""
        try:
            # Получаем профили с наибольшим количеством лайков и просмотров
            async with self.db_manager.acquire_connection() as conn:
                cursor = await conn.execute("""
                    SELECT DISTINCT p.game_nickname 
                    FROM profiles p
                    LEFT JOIN likes l ON p.user_id = l.liked_user_id
                    WHERE p.game_nickname IS NOT NULL 
                    AND p.game_nickname != ''
                    AND p.is_rejected = 0
                    GROUP BY p.user_id, p.game_nickname
                    HAVING COUNT(l.id) > 0 OR p.created_at > datetime('now', '-7 days')
                    ORDER BY COUNT(l.id) DESC, p.created_at DESC
                    LIMIT ?
                """, (Config.FACEIT_CACHE_PRELOAD_BATCH_SIZE,))
                
                rows = await cursor.fetchall()
                nicknames = [row[0] for row in rows if row[0] and row[0].strip()]
                
                logger.debug(f"Извлечено {len(nicknames)} популярных никнеймов из БД")
                return nicknames
                
        except Exception as e:
            logger.error(f"Ошибка получения популярных никнеймов из БД: {e}")
            return []
    
    async def warm_user_network(self, user_id: int) -> int:
        """Прогревание сети пользователя - загрузка ELO для тиммейтов и недавних взаимодействий"""
        try:
            if not self.db_manager:
                logger.warning("Database manager недоступен для прогревания сети пользователя")
                return 0
            
            # Получаем тиммейтов пользователя
            teammates_nicknames = await self._get_teammates_nicknames(user_id)
            
            # Получаем недавние взаимодействия
            recent_interactions = await self._get_recent_interactions_nicknames(user_id)
            
            # Объединяем и убираем дубликаты
            all_nicknames = list(set(teammates_nicknames + recent_interactions))
            
            if all_nicknames:
                logger.info(f"🔥 Прогревание сети для пользователя {user_id}: {len(all_nicknames)} профилей")
                await self.preload_elo_stats(all_nicknames)
                self._cache_stats['user_network_warmed'] += 1
                return len(all_nicknames)
            else:
                logger.debug(f"Нет профилей для прогревания сети пользователя {user_id}")
                return 0
                
        except Exception as e:
            logger.error(f"Ошибка прогревания сети пользователя {user_id}: {e}")
            return 0
    
    async def _get_teammates_nicknames(self, user_id: int) -> list[str]:
        """Получает никнеймы тиммейтов пользователя"""
        try:
            async with self.db_manager.acquire_connection() as conn:
                cursor = await conn.execute("""
                    SELECT DISTINCT p.game_nickname
                    FROM matches m
                    JOIN profiles p ON (m.user_id = p.user_id OR m.matched_user_id = p.user_id)
                    WHERE (m.user_id = ? OR m.matched_user_id = ?)
                    AND p.user_id != ?
                    AND p.game_nickname IS NOT NULL
                    AND p.game_nickname != ''
                    AND p.is_rejected = 0
                """, (user_id, user_id, user_id))
                
                rows = await cursor.fetchall()
                return [row[0] for row in rows if row[0] and row[0].strip()]
                
        except Exception as e:
            logger.error(f"Ошибка получения никнеймов тиммейтов: {e}")
            return []
    
    async def _get_recent_interactions_nicknames(self, user_id: int) -> list[str]:
        """Получает никнеймы недавних взаимодействий пользователя"""
        try:
            async with self.db_manager.acquire_connection() as conn:
                cursor = await conn.execute("""
                    SELECT DISTINCT p.game_nickname
                    FROM likes l
                    JOIN profiles p ON l.liked_user_id = p.user_id
                    WHERE l.user_id = ?
                    AND l.created_at > datetime('now', '-7 days')
                    AND p.game_nickname IS NOT NULL
                    AND p.game_nickname != ''
                    AND p.is_rejected = 0
                    ORDER BY l.created_at DESC
                    LIMIT 20
                """, (user_id,))
                
                rows = await cursor.fetchall()
                return [row[0] for row in rows if row[0] and row[0].strip()]
                
        except Exception as e:
            logger.error(f"Ошибка получения никнеймов недавних взаимодействий: {e}")
            return []
    
    def get_background_processor_stats(self) -> Dict[str, Any]:
        """Получает статистику фонового процессора"""
        try:
            bg_processor = get_background_processor()
            return bg_processor.get_stats()
        except Exception as e:
            logger.error(f"Ошибка получения статистики фонового процессора: {e}")
            return {}
    
    def is_healthy(self) -> bool:
        """Проверяет здоровье анализатора и фонового процессора"""
        try:
            bg_processor = get_background_processor()
            return bg_processor.is_healthy()
        except Exception:
            return False
    
    async def clear_cache(self):
        """Очищает постоянный кеш"""
        cache_manager = self._get_cache_manager()
        if not cache_manager:
            logger.error("Cache manager недоступен для очистки")
            return
        
        success = await cache_manager.clear_all()
        if success:
            self._cache_stats = {
                'background_requests': self._cache_stats['background_requests'],
                'failed_requests': self._cache_stats['failed_requests']
            }
            logger.info("Постоянный кеш Faceit Analyser очищен")
        else:
            logger.error("Ошибка очистки постоянного кеша")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Возвращает статистику постоянного кеша"""
        cache_manager = self._get_cache_manager()
        if not cache_manager:
            return self._cache_stats.copy()
        
        cache_stats = await cache_manager.get_statistics()
        stats = self._cache_stats.copy()
        stats.update(cache_stats)
        return stats
    
    async def cleanup_expired_cache(self):
        """Очистка просроченных записей постоянного кеша"""
        cache_manager = self._get_cache_manager()
        if not cache_manager:
            logger.error("Cache manager недоступен для очистки просроченных записей")
            return
        
        expired_count = await cache_manager.cleanup_expired()
        if expired_count > 0:
            logger.info(f"Очищено {expired_count} просроченных записей постоянного кеша")
    
    async def warm_cache(self, profiles: List[str] = None) -> int:
        """Предварительная загрузка популярных профилей в кеш"""
        if profiles:
            # Warm specific profiles
            warmed = 0
            for profile in profiles:
                if await self.get_elo_stats_by_nickname(profile):
                    warmed += 1
            return warmed
        else:
            # Warm popular profiles
            cache_manager = self._get_cache_manager()
            if not cache_manager:
                return 0
            return await cache_manager.warm_popular_profiles()
    
    async def get_cache_health(self) -> Dict[str, Any]:
        """Проверка здоровья системы кеша"""
        cache_manager = self._get_cache_manager()
        if not cache_manager:
            return {"status": "unavailable", "error": "Cache manager not available"}
        return await cache_manager.health_check()
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance overview for FaceitAnalyzer"""
        try:
            summary = {
                'cache_stats': self._cache_stats.copy(),
                'circuit_breaker': {
                    'failure_count': self._failure_count,
                    'is_open': self._circuit_open,
                    'last_failure': self._last_failure_time
                },
                'request_deduplication': {
                    'active_requests': len(self._request_deduplication)
                }
            }
            
            # Add cache manager performance if available
            cache_manager = self._get_cache_manager()
            if cache_manager and hasattr(cache_manager, 'get_performance_metrics'):
                try:
                    cache_performance = cache_manager.get_performance_metrics()
                    if cache_performance:
                        summary['cache_performance'] = cache_performance
                except Exception as e:
                    logger.debug(f"Error getting cache performance metrics: {e}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
    
    def analyze_api_performance(self) -> Dict[str, Any]:
        """Analyze API performance and identify optimization opportunities"""
        try:
            analysis = {
                'circuit_breaker_effectiveness': self._analyze_circuit_breaker_effectiveness(),
                'failure_patterns': self._analyze_failure_patterns(),
                'optimization_recommendations': []
            }
            
            # Circuit breaker recommendations
            if self._failure_count > Config.FACEIT_CIRCUIT_BREAKER_THRESHOLD / 2:
                analysis['optimization_recommendations'].append({
                    'type': 'circuit_breaker',
                    'priority': 'medium',
                    'message': 'Circuit breaker threshold approaching',
                    'suggestions': [
                        'Monitor API service health',
                        'Consider reducing request frequency',
                        'Review error handling patterns'
                    ]
                })
            
            # Cache optimization recommendations
            cache_hit_ratio = self._cache_stats.get('cache_hit_ratio', 0)
            if cache_hit_ratio < 0.7:
                analysis['optimization_recommendations'].append({
                    'type': 'cache_optimization',
                    'priority': 'high',
                    'message': 'Cache hit ratio below optimal threshold',
                    'suggestions': [
                        'Increase cache warming frequency',
                        'Review cache TTL settings',
                        'Implement more aggressive preloading'
                    ]
                })
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing API performance: {e}")
            return {}
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get performance-based optimization recommendations"""
        try:
            recommendations = []
            
            # Analyze request deduplication effectiveness
            if len(self._request_deduplication) > 10:
                recommendations.append({
                    'type': 'request_deduplication',
                    'priority': 'medium',
                    'message': 'High number of concurrent duplicate requests',
                    'action': 'Consider implementing request batching',
                    'expected_impact': 'Reduced API load and improved response times'
                })
            
            # Analyze circuit breaker patterns
            if self._circuit_open:
                recommendations.append({
                    'type': 'circuit_breaker',
                    'priority': 'high',
                    'message': 'Circuit breaker is currently open',
                    'action': 'Investigate API service health and connectivity',
                    'expected_impact': 'Restored API functionality'
                })
            
            # Cache-based recommendations
            failed_ratio = self._cache_stats.get('failed_requests', 0) / max(self._cache_stats.get('background_requests', 1), 1)
            if failed_ratio > 0.1:
                recommendations.append({
                    'type': 'error_handling',
                    'priority': 'high',
                    'message': f'High failure rate: {failed_ratio:.2%}',
                    'action': 'Review error handling and retry strategies',
                    'expected_impact': 'Improved reliability and user experience'
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting optimization recommendations: {e}")
            return []
    
    def _analyze_circuit_breaker_effectiveness(self) -> Dict[str, Any]:
        """Analyze circuit breaker effectiveness and patterns"""
        try:
            return {
                'current_failure_count': self._failure_count,
                'threshold': Config.FACEIT_CIRCUIT_BREAKER_THRESHOLD,
                'is_open': self._circuit_open,
                'effectiveness_score': max(0, 1 - (self._failure_count / Config.FACEIT_CIRCUIT_BREAKER_THRESHOLD)),
                'last_failure_age_seconds': (
                    datetime.now().timestamp() - self._last_failure_time 
                    if self._last_failure_time else None
                )
            }
        except Exception as e:
            logger.error(f"Error analyzing circuit breaker effectiveness: {e}")
            return {}
    
    def _analyze_failure_patterns(self) -> Dict[str, Any]:
        """Analyze failure patterns for insights"""
        try:
            # Basic failure pattern analysis
            patterns = {
                'total_failures': self._cache_stats.get('failed_requests', 0),
                'total_requests': self._cache_stats.get('background_requests', 0),
                'failure_rate': 0.0
            }
            
            if patterns['total_requests'] > 0:
                patterns['failure_rate'] = patterns['total_failures'] / patterns['total_requests']
            
            # Categorize failure severity
            if patterns['failure_rate'] > 0.2:
                patterns['severity'] = 'critical'
            elif patterns['failure_rate'] > 0.1:
                patterns['severity'] = 'high'
            elif patterns['failure_rate'] > 0.05:
                patterns['severity'] = 'medium'
            else:
                patterns['severity'] = 'low'
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing failure patterns: {e}")
            return {}
    
    async def optimize_cache(self) -> bool:
        """Оптимизация базы данных кеша"""
        cache_manager = self._get_cache_manager()
        if not cache_manager:
            logger.error("Cache manager недоступен для оптимизации")
            return False
        return await cache_manager.vacuum_database()
    
    async def warm_user_network(self, user_id: int) -> int:
        """Разогрев кеша для сети пользователя (тиммейты и недавние взаимодействия)"""
        try:
            # Получаем менеджер базы данных
            db_manager = self._get_db_manager()
            if not db_manager:
                logger.warning(f"Database manager недоступен для разогрева сети пользователя {user_id}")
                return 0
            
            # Получаем профили из сети пользователя
            nicknames = await db_manager.get_user_network_profiles(
                user_id, 
                limit=Config.FACEIT_CACHE_WARMING_BATCH_SIZE
            )
            
            if not nicknames:
                logger.debug(f"Нет профилей сети для разогрева для пользователя {user_id}")
                return 0
            
            # Предзагружаем ELO статистику для найденных никнеймов
            await self.preload_elo_stats(nicknames)
            
            # Обновляем статистику
            warmed_count = len(nicknames)
            self._cache_stats['user_network_warmed'] += warmed_count
            
            # Записываем статистику в cache manager если доступен
            cache_manager = self._get_cache_manager()
            if cache_manager:
                try:
                    # Обновляем warming_count в статистике кеша
                    await cache_manager.update_statistics()
                except Exception as stats_error:
                    logger.warning(f"Ошибка обновления статистики кеша: {stats_error}")
            
            logger.info(f"Разогрет кеш для {warmed_count} профилей из сети пользователя {user_id}")
            return warmed_count
            
        except Exception as e:
            logger.error(f"Ошибка разогрева сети пользователя {user_id}: {e}", exc_info=True)
            return 0

# Глобальный экземпляр для использования в проекте - будет использовать shared cache manager через lazy binding
faceit_analyzer = FaceitAnalyzer(cache_manager=None)
