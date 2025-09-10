"""
Интеграция с Faceit Analyser API для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import aiohttp
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import re
import io
import base64

from bot.config import Config
from bot.utils.cs2_data import extract_faceit_nickname

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
    """Класс для работы с Faceit Analyser API"""
    
    def __init__(self):
        self.api_key = Config.FACEIT_ANALYSER_API_KEY
        self.base_url = Config.FACEIT_ANALYSER_BASE_URL
        self.cache_ttl = Config.FACEIT_ANALYSER_CACHE_TTL
        self.cache = {}  # Простой кеш в памяти
        
        if not self.api_key:
            logger.warning("FACEIT_ANALYSER_API_KEY не установлен в конфигурации")
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Проверяет актуальность кешированных данных"""
        if not cache_entry or 'timestamp' not in cache_entry:
            return False
        
        cache_time = cache_entry['timestamp']
        return datetime.now() - cache_time < timedelta(seconds=self.cache_ttl)
    
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
        """Выполняет запрос к Faceit Analyser API"""
        if not self.api_key:
            logger.warning("API ключ Faceit Analyser не установлен")
            return None
        
        url = f"{self.base_url}{endpoint}/{player_id}"
        params = {"key": self.api_key}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Успешный запрос к {endpoint} для {player_id}")
                        return data
                    elif response.status == 404:
                        logger.warning(f"Игрок {player_id} не найден в Faceit Analyser")
                        return None
                    elif response.status == 401:
                        logger.error(f"Неверный API ключ для Faceit Analyser")
                        return None
                    elif response.status == 429:
                        logger.warning(f"Превышен лимит запросов к Faceit Analyser API")
                        return None
                    else:
                        logger.error(f"Ошибка API Faceit Analyser: {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут запроса к Faceit Analyser для {player_id}")
            return None
        except Exception as e:
            logger.error(f"Исключение при запросе к Faceit Analyser для {player_id}: {e}")
            return None
    
    async def get_player_overview(self, faceit_url: str) -> Optional[Dict[str, Any]]:
        """Получает общую информацию о игроке"""
        player_id = self._get_player_id_from_faceit_url(faceit_url)
        if not player_id:
            return None
        
        # Проверяем кеш
        cache_key = f"overview_{player_id}"
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
            logger.debug(f"Возвращаем cached overview для {player_id}")
            return self.cache[cache_key]['data']
        
        # Запрашиваем данные
        data = await self._make_api_request("overview", player_id)
        if data:
            # Кешируем результат
            self.cache[cache_key] = {
                'data': data,
                'timestamp': datetime.now()
            }
        
        return data
    
    async def get_player_stats(self, faceit_url: str) -> Optional[Dict[str, Any]]:
        """Получает подробную статистику игрока"""
        player_id = self._get_player_id_from_faceit_url(faceit_url)
        if not player_id:
            return None
        
        # Проверяем кеш
        cache_key = f"stats_{player_id}"
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
            logger.debug(f"Возвращаем cached stats для {player_id}")
            return self.cache[cache_key]['data']
        
        # Запрашиваем данные
        data = await self._make_api_request("stats", player_id)
        if data:
            # Кешируем результат
            self.cache[cache_key] = {
                'data': data,
                'timestamp': datetime.now()
            }
        
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
            
            # Проверяем кеш
            cache_key = f"elo_stats_{player_id}"
            if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
                logger.debug(f"Возвращаем cached elo stats для {player_id}")
                return self.cache[cache_key]['data']
            
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
            
            # Извлекаем ELO данные с более подробным логированием
            current_elo = stats.get('_current_elo', 0)
            highest_elo = stats.get('_highest_elo', 0) 
            lowest_elo = stats.get('_lowest_elo', 0)
            matches = stats.get('_m', 0)
            
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
            
            # Кешируем результат
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
            
            logger.info(f"✅ Успешно получена ELO статистика для {nickname}: Мин:{result['lowest_elo']} Макс:{result['highest_elo']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка получения ELO статистики для {nickname}: {e}", exc_info=True)
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
            
            # Добавляем основную статистику если есть
            if stats:
                result['stats'] = {
                    'matches': stats.get('_m', 0),
                    'wins': stats.get('_w', 0),
                    'kills': stats.get('_k', 0),
                    'deaths': stats.get('_d', 0),
                    'kdr': stats.get('_kdr', 0),
                    'hltv_rating': stats.get('_hltv', 0),
                    'current_elo': stats.get('_current_elo', 0),
                    'highest_elo': stats.get('_highest_elo', 0),
                    'lowest_elo': stats.get('_lowest_elo', 0)
                }
            
            # Диаграммы отключены
            return result if result else None
            
        except Exception as e:
            logger.error(f"Ошибка получения расширенной информации профиля: {e}")
            return None
    
    def clear_cache(self):
        """Очищает кеш"""
        self.cache.clear()
        logger.info("Кеш Faceit Analyser очищен")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Возвращает статистику кеша"""
        total = len(self.cache)
        valid = sum(1 for entry in self.cache.values() if self._is_cache_valid(entry))
        return {
            'total_entries': total,
            'valid_entries': valid,
            'expired_entries': total - valid
        }

# Глобальный экземпляр для использования в проекте
faceit_analyzer = FaceitAnalyzer()
