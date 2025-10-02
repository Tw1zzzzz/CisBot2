# Система проверки подписки на каналы

## Обзор

Система проверки подписки на каналы обеспечивает обязательную подписку пользователей на указанные телеграм каналы перед использованием основных функций бота.

## Обязательные каналы

- **@cisfinder** - CIS FINDER / Поиск игроков CS2
- **@tw1zzV** - Twizzик

## Архитектура

### Компоненты системы

1. **SubscriptionChecker** (`bot/utils/subscription_checker.py`)
   - Основная логика проверки подписки
   - Взаимодействие с Telegram API
   - Формирование сообщений и клавиатур

2. **SubscriptionMiddleware** (`bot/utils/subscription_middleware.py`)
   - Middleware для автоматической проверки
   - Декоратор `@subscription_required`
   - Блокировка доступа для неподписанных пользователей

3. **Database Support** (`bot/database/models.py`, `bot/database/operations.py`)
   - Хранение статуса подписки в `user_settings.subscription_status`
   - Методы для работы с подписками

4. **Integration** (`bot/main.py`, `bot/handlers/`)
   - Инициализация системы
   - Интеграция с обработчиками команд

## Использование

### Инициализация

Система автоматически инициализируется в `main.py`:

```python
# Инициализация Subscription Systems
self.subscription_checker = SubscriptionChecker(self.application.bot)
self.subscription_middleware = SubscriptionMiddleware(self.subscription_checker)

# Установка глобальных экземпляров
set_subscription_checker(self.subscription_checker)
set_subscription_middleware(self.subscription_middleware)
```

### Применение декоратора

Для защиты обработчиков используйте декоратор `@subscription_required`:

```python
from bot.utils.subscription_middleware import subscription_required

@subscription_required
async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - управление профилем"""
    # Логика обработчика
```

### Проверка подписки в коде

```python
from bot.utils.subscription_checker import get_subscription_checker

# Получение checker'а
checker = get_subscription_checker()
if checker:
    # Проверка подписки пользователя
    status = await checker.check_user_subscription(user_id)
    
    if status.is_subscribed:
        # Пользователь подписан
        pass
    else:
        # Пользователь не подписан
        missing_channels = status.missing_channels
```

### Работа с базой данных

```python
# Обновление статуса подписки
await db.update_subscription_status(
    user_id=user_id,
    is_subscribed=True,
    missing_channels=[],
    last_checked="2024-01-01T00:00:00"
)

# Получение статуса подписки
status = await db.get_subscription_status(user_id)

# Проверка подписки
is_subscribed = await db.is_user_subscribed(user_id)
```

## Освобожденные команды

Следующие команды не требуют проверки подписки:

- `/start` - команда запуска
- `/help` - справка
- `back_to_main` - возврат в главное меню
- `check_subscription` - проверка подписки

## Пользовательский интерфейс

### Сообщения

Система автоматически показывает пользователям:

1. **Сообщение о необходимости подписки** при первом запуске
2. **Кнопки подписки** на каналы
3. **Кнопку проверки подписки** после подписки
4. **Сообщение об успешной подписке** при прохождении проверки

### Клавиатуры

- Кнопки подписки на каналы (с прямыми ссылками)
- Кнопка "Проверить подписку"
- Кнопка возврата в главное меню

## Обработка ошибок

### Telegram API ошибки

- **BadRequest**: Канал не найден или пользователь не найден
- **Forbidden**: Нет доступа к каналу
- **NetworkError**: Проблемы с сетью

### Стратегия обработки

1. **При ошибке API**: Считаем пользователя неподписанным
2. **При критических ошибках**: Разрешаем доступ (не блокируем пользователей)
3. **Логирование**: Все ошибки записываются в лог

## Конфигурация

### Обязательные каналы

Каналы настраиваются в `SubscriptionChecker.REQUIRED_CHANNELS`:

```python
REQUIRED_CHANNELS = [
    RequiredChannel(
        channel_id="@cisfinder",
        channel_username="cisfinder", 
        channel_title="CIS FINDER / Поиск игроков CS2",
        channel_url="https://t.me/cisfinder"
    ),
    # ... другие каналы
]
```

### Освобожденные команды

Команды настраиваются в `SubscriptionMiddleware.exempt_commands`:

```python
self.exempt_commands = {
    '/start',
    '/help', 
    'back_to_main',
    'check_subscription'
}
```

## Тестирование

Запустите тестовый скрипт:

```bash
python test_subscription_system.py
```

Тест проверяет:
- Работу SubscriptionChecker
- Операции с базой данных
- Функциональность middleware

## Мониторинг

### Логирование

Система записывает в лог:
- Результаты проверки подписки
- Ошибки API
- Статистику использования

### Метрики

В базе данных сохраняется:
- Статус подписки
- Время последней проверки
- Количество проверок

## Безопасность

### Валидация данных

- Все входные данные валидируются
- JSON поля проверяются по схеме
- SQL инъекции предотвращены

### Обработка ошибок

- Graceful degradation при ошибках
- Не блокируем пользователей при сбоях
- Подробное логирование для отладки

## Развертывание

### Миграция базы данных

Система автоматически добавляет поле `subscription_status` в таблицу `user_settings` при первом запуске.

### Обновление каналов

Для добавления новых обязательных каналов:

1. Обновите `REQUIRED_CHANNELS` в `SubscriptionChecker`
2. Перезапустите бота
3. Пользователи увидят новые каналы при следующей проверке

## Устранение неполадок

### Пользователь не может подписаться

1. Проверьте правильность ID каналов
2. Убедитесь, что бот добавлен в каналы как администратор
3. Проверьте права бота на чтение участников

### Ошибки API

1. Проверьте токен бота
2. Убедитесь в стабильности интернет-соединения
3. Проверьте лимиты Telegram API

### Проблемы с базой данных

1. Проверьте права доступа к файлу БД
2. Убедитесь в корректности миграций
3. Проверьте логи на ошибки SQL

## Поддержка

При возникновении проблем:

1. Проверьте логи бота
2. Запустите тестовый скрипт
3. Обратитесь к разработчикам проекта

---

**Создано организацией Twizz_Project**
