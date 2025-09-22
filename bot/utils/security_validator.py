"""
Безопасный валидатор JSON схем и фильтрация логов
Создано организацией Twizz_Project

Обеспечивает строгую валидацию JSON данных и безопасное логирование
без утечки персональных данных.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib
import secrets


@dataclass
class ValidationResult:
    """Результат валидации с детальной информацией"""
    is_valid: bool
    error_message: Optional[str] = None
    sanitized_data: Optional[Any] = None
    validation_score: int = 0
    masked_value: Optional[str] = None
    strength_score: int = 0


class JSONSchemaValidator:
    """Строгий валидатор JSON схем с защитой от инъекций"""
    
    # Максимальные размеры для предотвращения DoS атак
    MAX_JSON_SIZE = 1024 * 1024  # 1MB
    MAX_STRING_LENGTH = 10000
    MAX_ARRAY_LENGTH = 1000
    MAX_OBJECT_KEYS = 100
    
    # Паттерны для обнаружения потенциально опасного контента
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript injection
        r'data:text/html',  # Data URI HTML
        r'vbscript:',  # VBScript injection
        r'on\w+\s*=',  # Event handlers
        r'expression\s*\(',  # CSS expressions
        r'url\s*\(',  # CSS URL functions
        r'@import',  # CSS imports
        r'/\*.*?\*/',  # CSS comments
        r'<!--.*?-->',  # HTML comments
    ]
    
    # Паттерны для обнаружения персональных данных
    PERSONAL_DATA_PATTERNS = [
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',  # Phone
        r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IP address
    ]
    
    def __init__(self):
        self.compiled_dangerous = [re.compile(pattern, re.IGNORECASE | re.DOTALL) 
                                 for pattern in self.DANGEROUS_PATTERNS]
        self.compiled_personal = [re.compile(pattern, re.IGNORECASE) 
                                for pattern in self.PERSONAL_DATA_PATTERNS]
    
    def validate_json_string(self, json_string: str, schema: Optional[Dict] = None) -> ValidationResult:
        """
        Безопасная валидация JSON строки с проверкой схемы
        
        Args:
            json_string: JSON строка для валидации
            schema: Опциональная JSON схема для валидации
            
        Returns:
            ValidationResult с результатами валидации
        """
        try:
            # Проверка размера
            if len(json_string) > self.MAX_JSON_SIZE:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"JSON слишком большой: {len(json_string)} байт (максимум: {self.MAX_JSON_SIZE})"
                )
            
            # Проверка на опасные паттерны
            for pattern in self.compiled_dangerous:
                if pattern.search(json_string):
                    return ValidationResult(
                        is_valid=False,
                        error_message="Обнаружен потенциально опасный контент в JSON"
                    )
            
            # Парсинг JSON
            try:
                parsed_data = json.loads(json_string)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Неверный JSON формат: {str(e)}"
                )
            
            # Валидация структуры
            structure_result = self._validate_structure(parsed_data)
            if not structure_result.is_valid:
                return structure_result
            
            # Валидация схемы если предоставлена
            if schema:
                schema_result = self._validate_schema(parsed_data, schema)
                if not schema_result.is_valid:
                    return schema_result
            
            # Санитизация данных
            sanitized_data = self._sanitize_data(parsed_data)
            
            return ValidationResult(
                is_valid=True,
                sanitized_data=sanitized_data,
                validation_score=100
            )
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Ошибка валидации: {str(e)}"
            )
    
    def _validate_structure(self, data: Any, depth: int = 0) -> ValidationResult:
        """Рекурсивная валидация структуры данных"""
        if depth > 10:  # Предотвращение глубокой рекурсии
            return ValidationResult(
                is_valid=False,
                error_message="Слишком глубокая структура данных"
            )
        
        if isinstance(data, str):
            if len(data) > self.MAX_STRING_LENGTH:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Строка слишком длинная: {len(data)} символов"
                )
            
            # Проверка на персональные данные
            for pattern in self.compiled_personal:
                if pattern.search(data):
                    return ValidationResult(
                        is_valid=False,
                        error_message="Обнаружены персональные данные в строке"
                    )
        
        elif isinstance(data, list):
            if len(data) > self.MAX_ARRAY_LENGTH:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Массив слишком большой: {len(data)} элементов"
                )
            
            for item in data:
                result = self._validate_structure(item, depth + 1)
                if not result.is_valid:
                    return result
        
        elif isinstance(data, dict):
            if len(data) > self.MAX_OBJECT_KEYS:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Объект содержит слишком много ключей: {len(data)}"
                )
            
            for key, value in data.items():
                # Проверка ключей
                if not isinstance(key, str) or len(key) > 100:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Недопустимый ключ объекта"
                    )
                
                # Рекурсивная проверка значений
                result = self._validate_structure(value, depth + 1)
                if not result.is_valid:
                    return result
        
        return ValidationResult(is_valid=True)
    
    def _validate_schema(self, data: Any, schema: Dict) -> ValidationResult:
        """Валидация данных по JSON схеме"""
        try:
            # Простая валидация схемы (можно расширить с помощью jsonschema)
            if 'type' in schema:
                expected_type = schema['type']
                if expected_type == 'array' and not isinstance(data, list):
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Ожидается массив, получен {type(data).__name__}"
                    )
                elif expected_type == 'object' and not isinstance(data, dict):
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Ожидается объект, получен {type(data).__name__}"
                    )
                elif expected_type == 'string' and not isinstance(data, str):
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Ожидается строка, получен {type(data).__name__}"
                    )
            
            # Валидация обязательных полей
            if 'required' in schema and isinstance(data, dict):
                for field in schema['required']:
                    if field not in data:
                        return ValidationResult(
                            is_valid=False,
                            error_message=f"Отсутствует обязательное поле: {field}"
                        )
            
            return ValidationResult(is_valid=True)
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Ошибка валидации схемы: {str(e)}"
            )
    
    def _sanitize_data(self, data: Any) -> Any:
        """Санитизация данных от потенциально опасного контента"""
        if isinstance(data, str):
            # Удаление HTML тегов
            sanitized = re.sub(r'<[^>]+>', '', data)
            # Экранирование специальных символов
            sanitized = sanitized.replace('<', '&lt;').replace('>', '&gt;')
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        elif isinstance(data, dict):
            return {key: self._sanitize_data(value) for key, value in data.items()}
        else:
            return data


class SecureLogger:
    """Безопасный логгер с фильтрацией персональных данных"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.personal_data_patterns = JSONSchemaValidator.PERSONAL_DATA_PATTERNS
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) 
                                for pattern in self.personal_data_patterns]
    
    def safe_log(self, level: int, message: str, *args, **kwargs) -> None:
        """
        Безопасное логирование с фильтрацией персональных данных
        
        Args:
            level: Уровень логирования
            message: Сообщение для логирования
            *args: Аргументы для форматирования
            **kwargs: Дополнительные аргументы
        """
        try:
            # Фильтрация сообщения
            safe_message = self._filter_personal_data(message)
            
            # Фильтрация аргументов
            safe_args = []
            for arg in args:
                if isinstance(arg, str):
                    safe_args.append(self._filter_personal_data(arg))
                else:
                    safe_args.append(arg)
            
            # Фильтрация kwargs
            safe_kwargs = {}
            for key, value in kwargs.items():
                if isinstance(value, str):
                    safe_kwargs[key] = self._filter_personal_data(value)
                else:
                    safe_kwargs[key] = value
            
            # Логирование
            self.logger.log(level, safe_message, *safe_args, **safe_kwargs)
            
        except Exception as e:
            # В случае ошибки логируем без фильтрации, но с предупреждением
            self.logger.warning(f"Ошибка безопасного логирования: {e}")
            self.logger.log(level, message, *args, **kwargs)
    
    def _filter_personal_data(self, text: str) -> str:
        """Фильтрация персональных данных из текста"""
        if not isinstance(text, str):
            return str(text)
        
        filtered_text = text
        
        # Замена персональных данных на маскированные версии
        for pattern in self.compiled_patterns:
            filtered_text = pattern.sub(self._mask_personal_data, filtered_text)
        
        return filtered_text
    
    def _mask_personal_data(self, match) -> str:
        """Маскирование найденных персональных данных"""
        matched_text = match.group(0)
        
        # Определение типа данных и соответствующее маскирование
        if '@' in matched_text:  # Email
            return f"***@***.***"
        elif re.match(r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}', matched_text):  # Credit card
            return "****-****-****-****"
        elif re.match(r'\d{3}-\d{2}-\d{4}', matched_text):  # SSN
            return "***-**-****"
        elif re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', matched_text):  # IP
            return "***.***.***.***"
        else:  # Phone or other
            return "***-***-****"
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Безопасное логирование уровня INFO"""
        self.safe_log(logging.INFO, message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Безопасное логирование уровня WARNING"""
        self.safe_log(logging.WARNING, message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Безопасное логирование уровня ERROR"""
        self.safe_log(logging.ERROR, message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """Безопасное логирование уровня DEBUG"""
        self.safe_log(logging.DEBUG, message, *args, **kwargs)


class SecurityValidator:
    """Главный класс для валидации безопасности"""
    
    def __init__(self):
        self.json_validator = JSONSchemaValidator()
        self._secure_loggers: Dict[str, SecureLogger] = {}
    
    def validate_json(self, json_string: str, schema: Optional[Dict] = None) -> ValidationResult:
        """Валидация JSON строки"""
        return self.json_validator.validate_json_string(json_string, schema)
    
    def safe_json_loads(self, json_string: str, schema: Optional[Dict] = None, 
                       default: Any = None) -> Tuple[Any, ValidationResult]:
        """
        Безопасный парсинг JSON с валидацией
        
        Args:
            json_string: JSON строка
            schema: Опциональная схема валидации
            default: Значение по умолчанию при ошибке
            
        Returns:
            Tuple[parsed_data, validation_result]
        """
        validation_result = self.validate_json(json_string, schema)
        
        if validation_result.is_valid:
            return validation_result.sanitized_data, validation_result
        else:
            return default, validation_result
    
    def get_secure_logger(self, name: str) -> SecureLogger:
        """Получение безопасного логгера"""
        if name not in self._secure_loggers:
            base_logger = logging.getLogger(name)
            self._secure_loggers[name] = SecureLogger(base_logger)
        return self._secure_loggers[name]
    
    def validate_environment_variables(self, env_vars: Dict[str, str]) -> Dict[str, ValidationResult]:
        """Валидация переменных окружения"""
        results = {}
        
        for key, value in env_vars.items():
            if not value:
                results[key] = ValidationResult(
                    is_valid=False,
                    error_message="Переменная окружения не установлена",
                    masked_value="NOT_SET"
                )
                continue
            
            # Проверка силы токена/ключа
            strength_score = self._calculate_token_strength(value)
            
            # Маскирование значения
            masked_value = self._mask_token(value)
            
            results[key] = ValidationResult(
                is_valid=True,
                masked_value=masked_value,
                strength_score=strength_score
            )
        
        return results
    
    def _calculate_token_strength(self, token: str) -> int:
        """Расчет силы токена/ключа"""
        score = 0
        
        # Длина
        if len(token) >= 32:
            score += 30
        elif len(token) >= 16:
            score += 20
        elif len(token) >= 8:
            score += 10
        
        # Разнообразие символов
        has_upper = any(c.isupper() for c in token)
        has_lower = any(c.islower() for c in token)
        has_digit = any(c.isdigit() for c in token)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in token)
        
        char_diversity = sum([has_upper, has_lower, has_digit, has_special])
        score += char_diversity * 15
        
        # Энтропия
        unique_chars = len(set(token))
        if unique_chars > 20:
            score += 20
        elif unique_chars > 10:
            score += 10
        
        return min(100, score)
    
    def _mask_token(self, token: str) -> str:
        """Маскирование токена для безопасного отображения"""
        if len(token) <= 8:
            return "***"
        
        # Показываем первые 4 и последние 4 символа
        return f"{token[:4]}...{token[-4:]}"
    
    def safe_log_value(self, key: str, value: str, level: int) -> None:
        """Безопасное логирование значения конфигурации"""
        secure_logger = self.get_secure_logger("config")
        
        # Определяем, нужно ли маскировать значение
        sensitive_keys = ['token', 'key', 'secret', 'password', 'auth']
        is_sensitive = any(sensitive in key.lower() for sensitive in sensitive_keys)
        
        if is_sensitive and value not in ['NOT_SET', '***MASKED***']:
            masked_value = self._mask_token(value)
            secure_logger.safe_log(level, f"{key}: {masked_value}")
        else:
            secure_logger.safe_log(level, f"{key}: {value}")


# Глобальный экземпляр валидатора
security_validator = SecurityValidator()