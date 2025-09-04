# СЛЕДУЮЩИЕ ШАГИ - CS2 TEAMMEET BOT

## 🚀 НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ (СЕГОДНЯ)

### 1. Настройка окружения разработки
**Время:** 30 минут

#### Установка зависимостей
```bash
# Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Установить основные пакеты
pip install python-telegram-bot>=20.7
pip install python-dotenv>=1.0.0
pip install aiosqlite>=0.19.0
```

#### Создание структуры проекта
```bash
mkdir bot bot\handlers bot\database bot\matching bot\utils data logs
echo. > bot\__init__.py
echo. > bot\handlers\__init__.py
echo. > bot\database\__init__.py
echo. > bot\matching\__init__.py
echo. > bot\utils\__init__.py
```

### 2. Получение токена бота
**Время:** 10 минут

1. Открыть Telegram, найти @BotFather
2. Отправить команду `/newbot`
3. Указать имя бота: "CS2 Teammeet Bot"
4. Указать username: "@cs2teammeet_bot" (или доступный)
5. Скопировать токен и сохранить в `.env` файл

```bash
# .env
BOT_TOKEN=your_token_here
BOT_USERNAME=cs2teammeet_bot
DATABASE_PATH=data/bot.db
LOG_LEVEL=INFO
```

### 3. Создание базового бота
**Время:** 2 часа

#### Файл: `bot/main.py`
```python
import logging
import os
from telegram.ext import Application, CommandHandler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def start(update, context):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🎮 Добро пожаловать в CS2 Teammeet Bot!\n\n"
        "Найдите идеальных тиммейтов для Counter-Strike 2\n"
        "Используйте /help для просмотра команд"
    )

async def help_command(update, context):
    """Обработчик команды /help"""
    help_text = """
🎯 Доступные команды:

/start - Начать работу с ботом
/profile - Управление профилем
/search - Поиск тиммейтов
/matches - Мои матчи
/settings - Настройки
/help - Помощь

🚀 Начните с создания профиля: /profile
    """
    await update.message.reply_text(help_text)

def main():
    """Главная функция запуска бота"""
    token = os.getenv('BOT_TOKEN')
    if not token:
        raise ValueError("BOT_TOKEN не найден в переменных окружения")
    
    # Создание приложения
    application = Application.builder().token(token).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    logger.info("Бот запущен и готов к работе!")
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
```

## 📅 ПЛАН НА ПЕРВУЮ НЕДЕЛЮ

### День 1 (Сегодня) - Основы
- [x] Настройка окружения
- [x] Создание базового бота  
- [x] Тестирование `/start` и `/help`
- [x] Настройка логирования
- [x] Создание репозитория Git

### День 2 - База данных и модели
- [ ] Создание схемы базы данных
- [ ] Модели данных (`bot/database/models.py`)
- [ ] Базовые операции с БД (`bot/database/operations.py`)
- [ ] Тестирование подключения к БД

### День 3 - Система профилей
- [ ] Обработчик создания профиля
- [ ] Пошаговый диалог создания анкеты
- [ ] Валидация данных профиля
- [ ] Сохранение в базу данных

### День 4 - Основное меню и навигация
- [ ] Inline клавиатуры для навигации
- [ ] Команда `/profile` - управление профилем
- [ ] Просмотр и редактирование профиля
- [ ] Улучшение UX и сообщений

### День 5 - Базовый поиск
- [ ] Показ анкет других игроков
- [ ] Кнопки лайк/пропустить
- [ ] Сохранение лайков в БД
- [ ] Логика исключения уже просмотренных

### День 6 - Система матчей
- [ ] Проверка взаимных лайков
- [ ] Создание матчей
- [ ] Уведомления о новых матчах
- [ ] Просмотр списка матчей

### День 7 - Тестирование и улучшения
- [ ] Комплексное тестирование всех функций
- [ ] Исправление багов
- [ ] Улучшение сообщений и интерфейса
- [ ] Подготовка к деплою

## 🛠 ТЕХНИЧЕСКАЯ ПОДГОТОВКА

### Настройка Git репозитория
```bash
git init
echo "venv/" > .gitignore
echo ".env" >> .gitignore
echo "*.pyc" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.log" >> .gitignore
echo "data/*.db" >> .gitignore

git add .
git commit -m "Initial project structure"
```

### Файл requirements.txt
```txt
python-telegram-bot>=20.7
python-dotenv>=1.0.0
aiosqlite>=0.19.0
```

### Настройка логирования
```python
# bot/config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'cs2teammeet_bot')
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/bot.db')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')

def setup_logging():
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Создать папку для логов
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=log_format,
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
```

## 🎯 ПЕРВЫЕ ТЕСТЫ

### Ручное тестирование
1. Запустить бота: `python bot/main.py`
2. Найти бота в Telegram по username
3. Отправить `/start` - должно прийти приветствие
4. Отправить `/help` - должен прийти список команд
5. Проверить логи в файле `logs/bot.log`

### Тест базы данных (День 2)
```python
# test_db.py
import asyncio
from bot.database.operations import DatabaseManager

async def test_database():
    db = DatabaseManager('data/test.db')
    await db.init_database()
    
    # Тест создания пользователя
    user_data = {
        'user_id': 123456789,
        'username': 'test_user',
        'first_name': 'Test'
    }
    
    result = await db.create_user(user_data)
    print(f"Пользователь создан: {result}")
    
    # Тест получения пользователя
    user = await db.get_user(123456789)
    print(f"Пользователь получен: {user}")

if __name__ == '__main__':
    asyncio.run(test_database())
```

## 📋 ЧЕКЛИСТ ГОТОВНОСТИ К ДЕПЛОЮ

### Базовые функции
- [ ] Бот отвечает на команды
- [ ] База данных работает корректно
- [ ] Можно создать профиль
- [ ] Можно искать других игроков
- [ ] Система лайков работает
- [ ] Создаются матчи при взаимных лайках

### Качество кода
- [ ] Обработка всех возможных ошибок
- [ ] Логирование важных событий
- [ ] Валидация пользовательского ввода
- [ ] Комментарии к сложным функциям
- [ ] Соответствие PEP 8

### Безопасность
- [ ] Токен бота в переменных окружения
- [ ] Валидация всех входных данных
- [ ] Защита от SQL инъекций
- [ ] Rate limiting базовый
- [ ] Логирование подозрительной активности

### Производительность
- [ ] Оптимизированные запросы к БД
- [ ] Использование индексов
- [ ] Асинхронная обработка
- [ ] Кэширование частых запросов
- [ ] Время отклика < 3 секунд

## 🔍 ОТЛАДКА И МОНИТОРИНГ

### Логирование событий
```python
# В каждом обработчике
logger.info(f"User {user_id} started profile creation")
logger.warning(f"Invalid rank selected: {rank}")
logger.error(f"Database error: {str(e)}")
```

### Метрики для отслеживания
- Количество новых пользователей в день
- Количество созданных профилей
- Количество лайков и матчей
- Время отклика команд
- Количество ошибок

### Простой мониторинг
```python
# bot/utils/metrics.py
from datetime import datetime
import json

class SimpleMetrics:
    def __init__(self):
        self.data = {}
    
    def track_event(self, event_type, user_id=None):
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.data:
            self.data[today] = {}
        
        if event_type not in self.data[today]:
            self.data[today][event_type] = 0
        
        self.data[today][event_type] += 1
        
        # Сохранить в файл
        with open('data/metrics.json', 'w') as f:
            json.dump(self.data, f, indent=2)
```

## 🚀 КОМАНДЫ ДЛЯ ЗАПУСКА

### Разработка
```bash
# Активировать окружение
venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt

# Запустить бота
python bot/main.py
```

### Продакшн (будущее)
```bash
# Запуск с автоперезапуском
python bot/main.py --production

# Или через systemd/pm2/supervisor
```

## 📞 КОНТАКТЫ И ПОМОЩЬ

### Полезные ресурсы
- [Документация python-telegram-bot](https://docs.python-telegram-bot.org/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [SQLite документация](https://sqlite.org/docs.html)

### Сообщества для помощи
- Telegram: @pythontelegrambotchat
- Stack Overflow: тег `python-telegram-bot`
- Reddit: r/Telegram, r/Python

### Заметки
- Сохранять все токены в `.env` файле
- Регулярно делать бэкапы базы данных
- Тестировать каждую новую функцию отдельно
- Писать понятные commit сообщения в Git 