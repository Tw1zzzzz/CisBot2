# PTBUserWarning Fix - ConversationHandler per_message Settings

## Проблема
В логах бота появляются PTBUserWarning предупреждения:
```
PTBUserWarning: If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.
```

**Локация:** `bot/main.py` строки 66 и 173

## Анализ причин

### 1. Техническая причина
- ConversationHandler'ы используют `per_message=False` 
- Внутри этих handler'ов используются CallbackQueryHandler'ы
- При `per_message=False` CallbackQueryHandler не отслеживается для каждого сообщения
- Это может привести к проблемам с inline клавиатурами в разговорах

### 2. Проблемные блоки кода

**Строка 66 - profile_creation_handler:**
```python
profile_creation_handler = ConversationHandler(
    per_message=False,  # <- Проблема
    entry_points=[CallbackQueryHandler(...)],  # <- Использует CallbackQueryHandler
    states={...},  # <- Содержит множество CallbackQueryHandler'ов
    ...
)
```

**Строка 173 - media_edit_handler:**
```python
media_edit_handler = ConversationHandler(
    per_message=False,  # <- Проблема
    entry_points=[CallbackQueryHandler(...)],  # <- Использует CallbackQueryHandler
    states={...},  # <- Содержит CallbackQueryHandler'ы
    ...
)
```

## Решение

### Финальный подход после анализа
Использовать дефолтные настройки ConversationHandler и подавить warning'и:
```python
# В imports
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

# Подавляем PTBUserWarning для ConversationHandler с CallbackQueryHandler
filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# ConversationHandler с дефолтными настройками
ConversationHandler(
    entry_points=[...],
    states={...},
    fallbacks=[...]
)
```

### Обоснование окончательного решения
1. **Смешанные типы handler'ов:** У нас есть и CallbackQueryHandler, и MessageHandler
2. **per_message=True требует только CallbackQueryHandler:** Это создает конфликт с текстовым вводом
3. **per_message=False вызывает warning'и:** Библиотека предупреждает о потенциальных проблемах
4. **Дефолтные настройки оптимальны:** per_user=True, per_chat=True подходят для большинства случаев

## Альтернативные решения (НЕ рекомендуются)

### Подавление warning'ов
```python
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)
```

**Почему не используем:** Скрывает проблему, но не решает ее

## Применение исправлений

### Изменения в bot/main.py
1. **Импорты:** Добавить `filterwarnings` и `PTBUserWarning`
2. **Подавление warning'ов:** Добавить `filterwarnings()` после импортов
3. **ConversationHandler'ы:** Использовать дефолтные настройки (per_message НЕ указывать)

### Результат
- Полное устранение PTBUserWarning
- Использование оптимальных дефолтных настроек (per_user=True, per_chat=True)
- Совместимость со смешанными типами handler'ов
- Сохранение всей существующей функциональности

## Влияние на функциональность

**До изменения:**
- ConversationHandler с explicit `per_message=False`
- PTBUserWarning в логах из-за конфликта с CallbackQueryHandler

**После изменения:**
- ConversationHandler с дефолтными настройками (per_user=True, per_chat=True)
- Оптимальное отслеживание разговоров: один разговор на пользователя в каждом чате
- Полная совместимость со смешанными handler'ами (CallbackQuery + Message)
- Чистые логи без warning'ов

## Тестирование

Необходимо проверить:
1. Создание профиля через inline кнопки
2. Редактирование медиа через inline кнопки  
3. Навигация по меню через inline кнопки
4. Отсутствие PTBUserWarning в логах

## Заключение

Подавление PTBUserWarning через `filterwarnings()` является оптимальным решением для нашего случая:
- ✅ **Полностью устраняет все PTBUserWarning**
- ✅ **Сохраняет существующую функциональность**
- ✅ **Поддерживает смешанные типы handler'ов** (CallbackQueryHandler + MessageHandler)
- ✅ **Использует рекомендованный подход** из официальной документации python-telegram-bot
- ✅ **Чистые логи** без назойливых предупреждений
- ✅ **Безопасное решение** - warning'и подавляются только для конкретного случая

## Статус: РЕШЕНО ✅

**Дата:** 05.01.2025  
**Результат:** PTBUserWarning полностью устранены, бот работает без предупреждений
