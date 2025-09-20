"""
Операции с базой данных для CIS FINDER Bot
Создано организацией Twizz_Project
"""
import json
import logging
import aiosqlite
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any
import sqlite3
import time
import random
from typing import List, Optional, Dict, Any
from .models import User, Profile, Like, Match, UserSettings, Moderator
from ..config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = None, databases: Dict[str, str] = None):
        """
        Initialize DatabaseManager with support for multiple databases.
        
        Args:
            db_path: Legacy parameter for main database path (backward compatibility)
            databases: Dictionary mapping database types to paths, e.g. {'main': '/path/main.db', 'cache': '/path/cache.db'}
        """
        # Backward compatibility: if db_path provided, use as main database
        if db_path and not databases:
            databases = {'main': db_path}
        elif not databases:
            raise ValueError("Either db_path or databases parameter must be provided")
        
        self.databases = databases
        self.db_path = databases.get('main', db_path)  # For backward compatibility
        
        # Connection pools for each database type
        self._pools = {}
        self._pool_size = Config.DB_POOL_SIZE
        self._is_connected = False
        self._closing = False
        self._lock = asyncio.Lock()
        
        db_info = ", ".join([f"{k}: {v}" for k, v in databases.items()])
        logger.info(f"Инициализация DatabaseManager с базами данных: {db_info} (размер пула: {self._pool_size})")

    async def _execute_with_retry(self, func, *args, max_retries=3, **kwargs):
        """
        Выполняет функцию с повторными попытками при блокировке базы данных.
        Использует экспоненциальный backoff: 50ms, 100ms, 200ms.
        """
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except (sqlite3.OperationalError, aiosqlite.OperationalError) as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    # Экспоненциальный backoff с небольшим джиттером
                    delay = (50 * (2 ** attempt)) / 1000  # 50ms, 100ms, 200ms
                    jitter = random.uniform(0.8, 1.2)  # ±20% джиттер
                    sleep_time = delay * jitter
                    
                    logger.warning(f"Database locked, retry {attempt + 1}/{max_retries} after {sleep_time:.3f}s: {e}")
                    await asyncio.sleep(sleep_time)
                    continue
                else:
                    # Исчерпаны попытки или другая ошибка
                    raise
            except Exception as e:
                # Для других типов ошибок не повторяем
                raise
        
        # Этот код никогда не должен выполняться, но добавлен для безопасности
        raise sqlite3.OperationalError("Max retries exceeded for database operation")

    async def connect(self):
        """Создает пулы соединений для всех баз данных"""
        async with self._lock:
            if self._is_connected:
                return
            
            # Сбрасываем флаг закрытия при переподключении
            self._closing = False
            
            try:
                # Создаем пулы для каждой базы данных
                for db_type, db_path in self.databases.items():
                    pool = asyncio.Queue(maxsize=self._pool_size)
                    
                    # Создаем соединения для пула
                    for _ in range(self._pool_size):
                        conn = await self._create_connection(db_path=db_path, db_type=db_type)
                        await pool.put(conn)
                    
                    self._pools[db_type] = pool
                
                self._is_connected = True
                logger.info(f"Пулы соединений созданы успешно для {len(self._pools)} баз данных ({self._pool_size} соединений каждый)")
            except Exception as e:
                logger.error(f"Ошибка создания пулов соединений: {e}")
                await self._drain_and_close_pools()
                raise

    async def _drain_and_close_pools(self):
        """
        Дренирует и закрывает все соединения во всех пулах.
        Использует get_nowait() для неблокирующего дренажа.
        """
        if not self._pools:
            return
        
        try:
            # Устанавливаем флаг закрытия перед дренированием очередей
            self._closing = True
            
            # Дренируем все пулы
            for db_type, pool in self._pools.items():
                logger.info(f"Закрываем пул соединений для {db_type}")
                
                # Итерируемся по пулу до опустошения с неблокирующим get_nowait()
                while not pool.empty():
                    try:
                        conn = pool.get_nowait()
                        await conn.close()
                    except asyncio.QueueEmpty:
                        # Пул опустошен
                        break
                    except Exception as e:
                        # Логируем ошибки закрытия отдельных соединений
                        logger.warning(f"Ошибка закрытия соединения в {db_type}: {e}")
            
            # После дренажа очищаем состояние
            self._pools = {}
            self._is_connected = False
            self._closing = False
            logger.info("Все пулы соединений закрыты и очищены")
        except Exception as e:
            logger.error(f"Ошибка закрытия пулов соединений: {e}")

    async def disconnect(self):
        """
        Закрывает все соединения во всех пулах и очищает состояние.
        Обеспечивает корректное закрытие с помощью _drain_and_close_pools().
        """
        async with self._lock:
            if not self._pools:
                return
            
            await self._drain_and_close_pools()

    async def _create_connection(self, db_path: str = None, db_type: str = 'main') -> aiosqlite.Connection:
        """Создает одно соединение с настройками для указанной базы данных"""
        if not db_path:
            db_path = self.db_path  # Fallback для обратной совместимости
        
        conn = await aiosqlite.connect(
            db_path, 
            timeout=Config.DB_CONNECTION_TIMEOUT
        )
        
        # Базовые настройки для всех типов БД
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA temp_store = memory")
        
        # Специфичные настройки в зависимости от типа БД
        if db_type == 'main':
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA cache_size = 1000")
        elif db_type == 'cache':
            # Оптимизации для кеш-базы
            await conn.execute("PRAGMA cache_size = 10000")
            await conn.execute("PRAGMA locking_mode = NORMAL")  # Лучше для кеша
        
        logger.debug(f"Создано соединение для {db_type} ({db_path})")
        return conn

    @asynccontextmanager
    async def acquire_connection(self, db_type: str = 'main'):
        """Контекстный менеджер для получения соединения из соответствующего пула с проверкой здоровья"""
        if self._closing:
            raise RuntimeError("DatabaseManager is closing, cannot acquire connection")
        
        if not self._is_connected:
            logger.warning("Pools not initialized; calling connect() implicitly. Consider explicit db.connect() in startup.")
            if self._closing:
                raise RuntimeError("Cannot auto-connect while DatabaseManager is closing")
            await self.connect()
        
        if db_type not in self._pools:
            raise ValueError(f"Database type '{db_type}' not configured. Available: {list(self._pools.keys())}")
        
        pool = self._pools[db_type]
        
        try:
            # Получаем соединение из соответствующего пула с таймаутом
            conn = await asyncio.wait_for(
                pool.get(), 
                timeout=Config.DB_POOL_TIMEOUT
            )
        except asyncio.TimeoutError:
            # Логируем загруженность пула при таймауте
            pool_size = pool.qsize() if pool else 0
            pool_max_size = self._pool_size
            pool_usage = f"{pool_max_size - pool_size}/{pool_max_size}"
            logger.error(
                f"{db_type} pool timeout after {Config.DB_POOL_TIMEOUT}s. "
                f"Pool occupancy: {pool_usage} connections in use. "
                f"Available: {pool_size}/{pool_max_size}. "
                f"Pool may be exhausted or connections are not being released properly."
            )
            raise RuntimeError(
                f"{db_type} database connection timeout after {Config.DB_POOL_TIMEOUT} seconds. "
                f"Pool occupancy: {pool_usage}. Pool may be exhausted."
            )
        
        # Логируем загруженность пула после получения соединения
        available = pool.qsize() if pool else 0
        in_use = self._pool_size - available + 1  # +1 для текущего соединения
        logger.debug(f"Connection acquired from {db_type} pool. Pool status: {in_use}/{self._pool_size} in use, {available} available")
        
        # Проверяем здоровье соединения
        try:
            # Легкая проверка здоровья - SELECT 1 (универсально для всех типов БД)
            await conn.execute('SELECT 1')
            logger.debug(f"{db_type} connection health check passed")
        except Exception as e:
            logger.warning(f"{db_type} connection health check failed: {e}. Creating fresh connection.")
            # Закрываем неработающее соединение
            try:
                await conn.close()
            except Exception as close_e:
                logger.warning(f"Failed to close broken {db_type} connection: {close_e}")
            
            # Создаем новое соединение для соответствующей БД
            db_path = self.databases[db_type]
            conn = await self._create_connection(db_path=db_path, db_type=db_type)
            logger.info(f"Fresh {db_type} connection created after health check failure")
        
        # Устанавливаем row_factory в None по умолчанию
        conn.row_factory = None
        connection_is_healthy = True
        
        try:
            yield conn
        except Exception as e:
            # Если возникла ошибка во время использования соединения, помечаем его как нездоровое
            if any(error_msg in str(e).lower() for error_msg in ['database is locked', 'cannot operate on a closed database', 'closed']):
                connection_is_healthy = False
                logger.warning(f"Connection marked as unhealthy due to error: {e}")
            raise
        finally:
            try:
                # Откатываем только если есть активная транзакция
                try:
                    if getattr(conn, "in_transaction", False):
                        await conn.rollback()
                except Exception as e:
                    logger.debug(f"No rollback needed or rollback failed: {e}")
                    # НЕ помечаем соединение нездоровым из-за отката
            finally:
                # Сбрасываем row_factory перед возвратом в пул (гарантируем сброс)
                conn.row_factory = None
                
                # Если пул закрывается или был закрыт/уничтожен во время работы, закрываем соединение
                if self._closing or db_type not in self._pools or self._pools[db_type] is None:
                    try:
                        await conn.close()
                    except Exception as e:
                        logger.warning(f"Ошибка закрытия {db_type} соединения: {e}")
                elif connection_is_healthy:
                    # Возвращаем здоровое соединение в соответствующий пул
                    await pool.put(conn)
                    # Логируем текущее состояние пула после возврата
                    available = pool.qsize()
                    in_use = self._pool_size - available
                    logger.debug(f"{db_type} connection returned to pool. Pool status: {in_use}/{self._pool_size} in use, {available} available")
                else:
                    # Соединение нездорово - закрываем его и создаем новое для пула
                    logger.info(f"Replacing unhealthy {db_type} connection in pool")
                    try:
                        await conn.close()
                    except Exception as e:
                        logger.warning(f"Failed to close unhealthy {db_type} connection: {e}")
                    
                    # Создаем новое соединение для пула, если не закрываемся
                    if not self._closing:
                        try:
                            db_path = self.databases[db_type]
                            fresh_conn = await self._create_connection(db_path=db_path, db_type=db_type)
                            await pool.put(fresh_conn)
                            logger.info(f"Added fresh {db_type} connection to pool")
                        except Exception as e:
                            logger.error(f"Failed to create replacement {db_type} connection: {e}")

    async def init_database(self):
        """
        Инициализирует базу данных и создает таблицы.
        Оборачивает DDL операции в транзакционный блок для WAL режима.
        """
        try:
            async with self.acquire_connection() as db:
                try:
                    # Начинаем транзакцию для DDL операций
                    await db.execute("BEGIN")
                    
                    # Создаем таблицы
                    await self._create_tables(db)
                    await self._create_indexes(db)
                    
                    # Фиксируем изменения
                    await db.commit()
                    logger.info("База данных инициализирована успешно")
                except Exception as init_error:
                    # Откатываем изменения при ошибке
                    try:
                        await db.rollback()
                    except Exception as rollback_error:
                        logger.warning(f"Ошибка отката транзакции: {rollback_error}")
                    raise init_error
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise

    async def _create_tables(self, db: aiosqlite.Connection):
        """Создает все таблицы"""
        
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        # Таблица профилей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                game_nickname TEXT NOT NULL DEFAULT '',
                faceit_elo INTEGER NOT NULL,
                faceit_url TEXT NOT NULL,
                role TEXT NOT NULL,
                favorite_maps TEXT NOT NULL,
                playtime_slots TEXT NOT NULL,
                categories TEXT NOT NULL DEFAULT '[]',
                description TEXT,
                media_type TEXT,
                media_file_id TEXT,
                moderation_status TEXT NOT NULL DEFAULT 'pending',
                moderation_reason TEXT,
                moderated_by INTEGER,
                moderated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (moderated_by) REFERENCES users (user_id)
            )
        """)
        
        # Добавляем колонку game_nickname если её нет (для существующих БД)
        try:
            await db.execute("ALTER TABLE profiles ADD COLUMN game_nickname TEXT NOT NULL DEFAULT ''")
        except Exception:
            # Колонка уже существует или другая ошибка
            pass
        
        # Добавляем поля модерации для существующих БД
        moderation_fields = [
            "moderation_status TEXT NOT NULL DEFAULT 'pending'",
            "moderation_reason TEXT",
            "moderated_by INTEGER",
            "moderated_at TIMESTAMP"
        ]
        
        for field in moderation_fields:
            try:
                field_name = field.split()[0]
                await db.execute(f"ALTER TABLE profiles ADD COLUMN {field}")
            except Exception:
                # Колонка уже существует
                pass
        
        # Добавляем поля медиа для существующих БД
        media_fields = [
            "media_type TEXT",
            "media_file_id TEXT"
        ]
        
        for field in media_fields:
            try:
                await db.execute(f"ALTER TABLE profiles ADD COLUMN {field}")
            except Exception:
                # Колонка уже существует
                pass
        
        # Добавляем поле categories для существующих БД
        try:
            await db.execute("ALTER TABLE profiles ADD COLUMN categories TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            # Колонка уже существует
            pass

        # Таблица лайков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                liker_id INTEGER NOT NULL,
                liked_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                viewed_at TIMESTAMP,
                FOREIGN KEY (liker_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (liked_id) REFERENCES users (user_id) ON DELETE CASCADE,
                UNIQUE(liker_id, liked_id)
            )
        """)
        
        # Добавляем поле viewed_at для существующих БД (для persistent skip functionality)
        try:
            await db.execute("ALTER TABLE likes ADD COLUMN viewed_at TIMESTAMP")
            logger.info("Добавлена колонка viewed_at в таблицу likes")
        except Exception:
            # Колонка уже существует
            pass

        # Таблица тиммейтов (взаимные лайки)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user1_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (user2_id) REFERENCES users (user_id) ON DELETE CASCADE,
                UNIQUE(user1_id, user2_id)
            )
        """)

        # Таблица настроек пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                notifications_enabled BOOLEAN DEFAULT 1,
                search_filters TEXT,
                privacy_settings TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)
        
        # Таблица модераторов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS moderators (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'moderator',
                permissions TEXT,
                appointed_by INTEGER,
                appointed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (appointed_by) REFERENCES users (user_id)
            )
        """)

    async def _create_indexes(self, db: aiosqlite.Connection):
        """Создает индексы для оптимизации запросов"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_profiles_elo ON profiles (faceit_elo)",
            "CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles (role)",
            "CREATE INDEX IF NOT EXISTS idx_profiles_moderation ON profiles (moderation_status)",
            "CREATE INDEX IF NOT EXISTS idx_likes_liker ON likes (liker_id)",
            "CREATE INDEX IF NOT EXISTS idx_likes_liked ON likes (liked_id)",
            "CREATE INDEX IF NOT EXISTS idx_likes_viewed ON likes (viewed_at)",
            "CREATE INDEX IF NOT EXISTS idx_matches_users ON matches (user1_id, user2_id)",
            "CREATE INDEX IF NOT EXISTS idx_matches_active ON matches (is_active)",
            "CREATE INDEX IF NOT EXISTS idx_moderators_active ON moderators (is_active)"
        ]
        
        for index_sql in indexes:
            await db.execute(index_sql)

    # === ПОЛЬЗОВАТЕЛИ ===

    async def create_user(self, user_id: int, username: Optional[str], first_name: str) -> bool:
        """Создает нового пользователя или обновляет существующего"""
        try:
            async with self.acquire_connection() as db:
                # 🔥 ИСПРАВЛЕНИЕ: Используем безопасный UPSERT вместо INSERT OR REPLACE
                # INSERT OR REPLACE удаляет запись (CASCADE удаляет профиль), затем вставляет новую
                # UPSERT просто обновляет существующую запись без удаления
                await db.execute("""
                    INSERT INTO users (user_id, username, first_name, created_at, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        is_active = 1
                """, (user_id, username, first_name, datetime.now()))
                await db.commit()
                logger.info(f"Пользователь {user_id} создан/обновлен")
                return True
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {user_id}: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[User]:
        """Получает данные пользователя"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row:
                    return User(**dict(row))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {user_id}: {e}")
            return None

    # === ПРОФИЛИ ===

    async def has_profile(self, user_id: int) -> bool:
        """Проверяет существование профиля пользователя"""
        try:
            async with self.acquire_connection() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM profiles WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                result = row is not None
                
                # DEBUG: Логируем результат проверки
                logger.info(f"has_profile: user_id={user_id}, result={result}")
                
                return result
        except Exception as e:
            logger.error(f"Ошибка проверки профиля {user_id}: {e}")
            return False

    async def has_approved_profile(self, user_id: int) -> bool:
        """Проверяет существование одобренного профиля пользователя"""
        try:
            async with self.acquire_connection() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM profiles WHERE user_id = ? AND moderation_status = 'approved'", (user_id,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                return row is not None
        except Exception as e:
            logger.error(f"Ошибка проверки одобренного профиля {user_id}: {e}")
            return False

    async def create_profile(self, user_id: int, game_nickname: str, faceit_elo: int, faceit_url: str, 
                           role: str, favorite_maps: List[str], playtime_slots: List[str], 
                           categories: List[str], description: Optional[str] = None, 
                           media_type: Optional[str] = None, media_file_id: Optional[str] = None) -> bool:
        """Создает новый профиль пользователя (требует модерации)"""
        try:
            # DEBUG: Логируем входные данные
            logger.info(f"create_profile: Начало создания профиля для user_id={user_id}, nickname={game_nickname}")
            
            async with self.acquire_connection() as db:
                # Преобразуем списки в JSON
                maps_json = json.dumps(favorite_maps)
                slots_json = json.dumps(playtime_slots)
                categories_json = json.dumps(categories)
                
                # DEBUG: Логируем SQL запрос
                logger.info(f"create_profile: Выполняем INSERT для user_id={user_id}")
                
                await db.execute("""
                    INSERT OR REPLACE INTO profiles 
                    (user_id, game_nickname, faceit_elo, faceit_url, role, favorite_maps, playtime_slots, 
                     categories, description, media_type, media_file_id, moderation_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """, (user_id, game_nickname, faceit_elo, faceit_url, role, maps_json, slots_json, 
                      categories_json, description, media_type, media_file_id, datetime.now(), datetime.now()))
                
                # DEBUG: Логируем коммит
                logger.info(f"create_profile: Выполняем commit для user_id={user_id}")
                await db.commit()
                
                # КРИТИЧЕСКИ ВАЖНО: Принудительно финализируем транзакцию в WAL mode
                await db.execute("PRAGMA wal_checkpoint(FULL)")
                
                # Дополнительная проверка что профиль действительно сохранился
                cursor = await db.execute("SELECT 1 FROM profiles WHERE user_id = ?", (user_id,))
                verification = await cursor.fetchone()
                await cursor.close()
                
                if not verification:
                    logger.error(f"create_profile: КРИТИЧЕСКАЯ ОШИБКА - профиль {user_id} НЕ НАЙДЕН после commit!")
                    return False
                
                media_info = f" (медиа: {media_type})" if media_type else ""
                logger.info(f"create_profile: Профиль создан и ПРОВЕРЕН для пользователя {user_id} (ник: {game_nickname}){media_info} - статус: pending")
                return True
        except Exception as e:
            logger.error(f"create_profile: КРИТИЧЕСКАЯ ОШИБКА создания профиля для {user_id}: {e}", exc_info=True)
            return False

    async def get_profile(self, user_id: int) -> Optional[Profile]:
        """Получает профиль пользователя"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                
                # 🔥 ОТЛАДКА: Проверяем что БД вернула
                logger.info(f"🔥 get_profile: user_id={user_id}, row found={row is not None}")
                
                if row:
                    try:
                        # Попытка создать объект Profile с детальным логированием
                        profile_dict = dict(row)
                        logger.info(f"🔥 get_profile: Данные профиля для user_id={user_id}")
                        logger.info(f"🔥 favorite_maps: {profile_dict.get('favorite_maps', 'ОТСУТСТВУЕТ')}")
                        logger.info(f"🔥 playtime_slots: {profile_dict.get('playtime_slots', 'ОТСУТСТВУЕТ')}")
                        logger.info(f"🔥 categories: {profile_dict.get('categories', 'ОТСУТСТВУЕТ')}")
                        
                        profile = Profile(**profile_dict)
                        logger.info(f"🔥 get_profile: Профиль УСПЕШНО создан для user_id={user_id}")
                        return profile
                    except Exception as e:
                        logger.error(f"🔥 get_profile: ОШИБКА создания объекта Profile для user_id={user_id}: {e}")
                        logger.error(f"🔥 get_profile: Данные строки БД: {dict(row)}")
                        logger.error(f"🔥 get_profile: Тип ошибки: {type(e).__name__}")
                        # Возвращаем None вместо падения
                        return None
                else:
                    logger.info(f"🔥 get_profile: Запись в БД НЕ НАЙДЕНА для user_id={user_id}")
                return None
        except Exception as e:
            logger.error(f"get_profile: Ошибка получения профиля {user_id}: {e}")
            return None

    async def update_profile(self, user_id: int, **kwargs) -> bool:
        """Обновляет профиль пользователя"""
        try:
            async with self.acquire_connection() as db:
                # Строим динамический UPDATE запрос
                fields = []
                values = []
                
                for field, value in kwargs.items():
                    if field in ['favorite_maps', 'playtime_slots', 'categories'] and isinstance(value, list):
                        value = json.dumps(value)
                    fields.append(f"{field} = ?")
                    values.append(value)
                
                if not fields:
                    return False
                
                fields.append("updated_at = ?")
                values.append(datetime.now())
                values.append(user_id)
                
                query = f"UPDATE profiles SET {', '.join(fields)} WHERE user_id = ?"
                await db.execute(query, values)
                await db.commit()
                
                logger.info(f"Профиль обновлен для пользователя {user_id}")
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления профиля {user_id}: {e}")
            return False

    # === ЛАЙКИ ===

    async def add_like(self, liker_id: int, liked_id: int) -> bool:
        """Добавляет лайк"""
        try:
            async with self.acquire_connection() as db:
                await db.execute("""
                    INSERT OR IGNORE INTO likes (liker_id, liked_id, created_at)
                    VALUES (?, ?, ?)
                """, (liker_id, liked_id, datetime.now()))
                await db.commit()
                logger.info(f"Лайк добавлен: {liker_id} -> {liked_id}")
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления лайка {liker_id} -> {liked_id}: {e}")
            return False

    async def check_mutual_like(self, user1_id: int, user2_id: int) -> bool:
        """Проверяет взаимный лайк"""
        try:
            async with self.acquire_connection() as db:
                cursor = await db.execute("""
                    SELECT 1 FROM likes 
                    WHERE (liker_id = ? AND liked_id = ?) 
                    AND EXISTS (SELECT 1 FROM likes WHERE liker_id = ? AND liked_id = ?)
                """, (user1_id, user2_id, user2_id, user1_id))
                row = await cursor.fetchone()
                await cursor.close()
                return row is not None
        except Exception as e:
            logger.error(f"Ошибка проверки взаимного лайка {user1_id} <-> {user2_id}: {e}")
            return False

    # === ТИММЕЙТЫ ===

    async def create_match(self, user1_id: int, user2_id: int) -> bool:
        """Создает связь тиммейтов между пользователями"""
        try:
            async with self.acquire_connection() as db:
                # Убеждаемся что user1_id < user2_id для единообразия
                if user1_id > user2_id:
                    user1_id, user2_id = user2_id, user1_id
                
                await db.execute("""
                    INSERT OR IGNORE INTO matches (user1_id, user2_id, created_at, is_active)
                    VALUES (?, ?, ?, 1)
                """, (user1_id, user2_id, datetime.now()))
                await db.commit()
                logger.info(f"Тиммейты найдены: {user1_id} <-> {user2_id}")
                return True
        except Exception as e:
            logger.error(f"Ошибка создания связи тиммейтов {user1_id} <-> {user2_id}: {e}")
            return False

    async def get_user_matches(self, user_id: int, active_only: bool = True) -> List[Match]:
        """Получает тиммейтов пользователя"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                query = """
                    SELECT * FROM matches 
                    WHERE (user1_id = ? OR user2_id = ?)
                """
                params = [user_id, user_id]
                
                if active_only:
                    query += " AND is_active = 1"
                
                query += " ORDER BY created_at DESC"
                
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                return [Match(**dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения тиммейтов для {user_id}: {e}")
            return []

    # === ПОИСК ===

    async def find_candidates(self, user_id: int, limit: int = 20) -> List[Profile]:
        """Находит кандидатов для пользователя с применением фильтров и настроек приватности"""
        try:
            # Получаем настройки пользователя и его профиль
            user_settings = await self.get_user_settings(user_id)
            user_profile = await self.get_profile(user_id)
            
            if not user_profile:
                logger.warning(f"Профиль пользователя {user_id} не найден")
                return []
            
            # Получаем фильтры поиска
            filters = user_settings.get_search_filters() if user_settings else {}
            
            # Проверяем, требуется ли TOP 1000 фильтр
            elo_filter = filters.get('elo_filter', 'any')
            if elo_filter == 'top_1000':
                return await self._find_top_1000_candidates(user_id, limit)
            
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                # Базовый запрос с исключением уже лайкнутых, неактивных и немодерированных
                cursor = await db.execute("""
                    SELECT p.*, us.privacy_settings FROM profiles p
                    LEFT JOIN user_settings us ON p.user_id = us.user_id
                    WHERE p.user_id != ?
                    AND p.user_id NOT IN (
                        SELECT liked_id FROM likes WHERE liker_id = ?
                    )
                    AND p.moderation_status = 'approved'
                    AND EXISTS (SELECT 1 FROM users u WHERE u.user_id = p.user_id AND u.is_active = 1)
                    ORDER BY p.updated_at DESC
                """, (user_id, user_id))
                
                rows = await cursor.fetchall()
                candidates = []
                
                for row in rows:
                    candidate = Profile(**{k: v for k, v in dict(row).items() if k != 'privacy_settings'})
                    
                    # Проверяем настройки приватности кандидата
                    privacy = dict(row).get('privacy_settings')
                    if not await self._check_privacy_visibility(privacy, user_id, candidate.user_id):
                        continue
                    
                    # Применяем фильтры поиска
                    if not self._apply_search_filters(candidate, user_profile, filters):
                        continue
                    
                    candidates.append(candidate)
                    
                    # Ограничиваем количество
                    if len(candidates) >= limit:
                        break
                
                # Сортируем по совместимости если нужно
                if filters.get('min_compatibility', 30) > 0:
                    candidates = self._sort_by_compatibility(candidates, user_profile, filters)
                
                return candidates[:limit]
                
        except Exception as e:
            logger.error(f"Ошибка поиска кандидатов для {user_id}: {e}")
            return []

    async def _find_top_1000_candidates(self, user_id: int, limit: int = 20) -> List[Profile]:
        """Находит ТОП 1000 игроков по ELO"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                # Получаем топ игроков по ELO (исключая самого пользователя и уже лайкнутых)
                cursor = await db.execute("""
                    SELECT p.*, us.privacy_settings FROM profiles p
                    LEFT JOIN user_settings us ON p.user_id = us.user_id
                    WHERE p.user_id != ?
                    AND p.user_id NOT IN (
                        SELECT liked_id FROM likes WHERE liker_id = ?
                    )
                    AND p.moderation_status = 'approved'
                    AND EXISTS (SELECT 1 FROM users u WHERE u.user_id = p.user_id AND u.is_active = 1)
                    ORDER BY p.faceit_elo DESC
                    LIMIT 1000
                """, (user_id, user_id))
                
                rows = await cursor.fetchall()
                candidates = []
                
                for row in rows:
                    candidate = Profile(**{k: v for k, v in dict(row).items() if k != 'privacy_settings'})
                    
                    # Проверяем настройки приватности кандидата
                    privacy = dict(row).get('privacy_settings')
                    if not await self._check_privacy_visibility(privacy, user_id, candidate.user_id):
                        continue
                    
                    candidates.append(candidate)
                    
                    # Ограничиваем количество для показа
                    if len(candidates) >= limit:
                        break
                
                logger.info(f"Найдено {len(candidates)} кандидатов в TOP 1000 для пользователя {user_id}")
                return candidates
                
        except Exception as e:
            logger.error(f"Ошибка поиска TOP 1000 кандидатов для {user_id}: {e}")
            return []

    async def _check_privacy_visibility(self, privacy_settings_json: str, searcher_id: int, candidate_id: int) -> bool:
        """Проверяет видимость профиля согласно настройкам приватности"""
        try:
            logger.info(f"🔒 Проверяем приватность кандидата {candidate_id}")
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка входных данных
            if not privacy_settings_json or privacy_settings_json.strip() == '':
                logger.info(f"🔒 У кандидата {candidate_id} нет настроек приватности - показываем всем")
                return True  # Настройки по умолчанию - видимый всем
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный парсинг JSON с валидацией
            import json
            try:
                privacy_settings = json.loads(privacy_settings_json)
                if not isinstance(privacy_settings, dict):
                    logger.warning(f"Настройки приватности не являются dict для кандидата {candidate_id}")
                    return True  # По умолчанию показываем при некорректных данных
            except (json.JSONDecodeError, TypeError) as json_error:
                logger.warning(f"Ошибка парсинга JSON настроек приватности для кандидата {candidate_id}: {json_error}")
                return True  # По умолчанию показываем при ошибке парсинга
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасное получение настройки видимости с валидацией
            visibility = privacy_settings.get('profile_visibility', 'all')
            if not isinstance(visibility, str) or visibility not in ['all', 'hidden', 'matches_only']:
                logger.warning(f"Некорректная настройка видимости '{visibility}' для кандидата {candidate_id}, используем 'all'")
                visibility = 'all'  # Fallback к безопасному значению
            
            logger.info(f"🔒 Настройка видимости кандидата {candidate_id}: '{visibility}'")
            
            if visibility == 'all':
                logger.info(f"🔒 Кандидат {candidate_id} ВИДИМ ВСЕМ")
                return True
            elif visibility == 'hidden':
                logger.info(f"🔒 Кандидат {candidate_id} СКРЫТ ОТ ВСЕХ")
                return False
            elif visibility == 'matches_only':
                # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка взаимного лайка
                try:
                    mutual_like = await self._check_mutual_like_async(searcher_id, candidate_id)
                    logger.info(f"🔒 Кандидат {candidate_id} видим только матчам, взаимный лайк: {mutual_like}")
                    return mutual_like
                except Exception as mutual_like_error:
                    logger.warning(f"Ошибка проверки взаимного лайка для приватности {searcher_id} -> {candidate_id}: {mutual_like_error}")
                    return False  # При ошибке скрываем профиль для безопасности
            
            return True
        except Exception as e:
            logger.error(f"Критическая ошибка проверки приватности для кандидата {candidate_id}: {e}", exc_info=True)
            return True  # По умолчанию показываем при критических ошибках

    async def _check_mutual_like_async(self, user1_id: int, user2_id: int) -> bool:
        """
        Асинхронная проверка взаимного лайка для _check_privacy_visibility.
        Использует пул соединений для оптимальной производительности.
        """
        try:
            async with self.acquire_connection() as db:
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM likes 
                    WHERE (liker_id = ? AND liked_id = ?) 
                    AND EXISTS (
                        SELECT 1 FROM likes 
                        WHERE liker_id = ? AND liked_id = ?
                    )
                """, (user1_id, user2_id, user2_id, user1_id))
                row = await cursor.fetchone()
                await cursor.close()
                return row[0] > 0 if row else False
        except Exception as e:
            logger.error(f"Ошибка проверки взаимного лайка: {e}")
            return False

    def _apply_search_filters(self, candidate: Profile, user_profile: Profile, filters: dict) -> bool:
        """Применяет фильтры поиска к кандидату"""
        try:
            # 🔥 ИСПРАВЛЕНИЕ: Валидация входных данных
            if not candidate or not user_profile:
                logger.warning(f"Некорректные профили для фильтрации: candidate={candidate is not None}, user_profile={user_profile is not None}")
                return False  # Скрываем при некорректных данных
            
            if not isinstance(filters, dict):
                logger.warning(f"Фильтры не являются словарем: {type(filters)}")
                filters = {}  # Fallback к пустому словарю
            
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Добавляем детальное логирование фильтрации
            logger.info(f"🔍 Начинаем фильтрацию кандидата {candidate.user_id}")
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный фильтр по ELO
            try:
                elo_filter = filters.get('elo_filter', 'any')
                if not self._filter_by_elo(candidate, user_profile, elo_filter):
                    logger.info(f"🔥 Кандидат {candidate.user_id} отфильтрован по ELO: {elo_filter}")
                    return False
                else:
                    logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ ELO фильтр: {elo_filter}")
            except Exception as elo_error:
                logger.warning(f"Ошибка ELO фильтра для кандидата {candidate.user_id}: {elo_error}")
                # При ошибке ELO фильтра продолжаем проверку других критериев
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный фильтр по ролям
            try:
                preferred_roles = filters.get('preferred_roles', [])
                if isinstance(preferred_roles, list) and len(preferred_roles) > 0:
                    candidate_role = getattr(candidate, 'role', None)
                    if candidate_role not in preferred_roles:
                        logger.info(f"🔥 Кандидат {candidate.user_id} отфильтрован по роли: {candidate_role} не в {preferred_roles}")
                        return False
                    else:
                        logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ фильтр ролей")
                else:
                    logger.info(f"🔥 Фильтр ролей отключен для кандидата {candidate.user_id}")
            except Exception as role_error:
                logger.warning(f"Ошибка фильтра ролей для кандидата {candidate.user_id}: {role_error}")
                # При ошибке фильтра ролей продолжаем проверку
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный фильтр по совместимости карт
            try:
                maps_compatibility = filters.get('maps_compatibility', 'any')
                if not self._filter_by_maps_compatibility(candidate, user_profile, maps_compatibility):
                    logger.info(f"🔥 Кандидат {candidate.user_id} отфильтрован по совместимости карт: {maps_compatibility}")
                    return False
                else:
                    logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ фильтр карт: {maps_compatibility}")
            except Exception as maps_error:
                logger.warning(f"Ошибка фильтра карт для кандидата {candidate.user_id}: {maps_error}")
                # При ошибке фильтра карт продолжаем проверку
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный фильтр по совместимости времени
            try:
                time_compatibility = filters.get('time_compatibility', 'any')
                if not self._filter_by_time_compatibility(candidate, user_profile, time_compatibility):
                    logger.info(f"🔥 Кандидат {candidate.user_id} отфильтрован по совместимости времени: {time_compatibility}")
                    return False
                else:
                    logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ фильтр времени: {time_compatibility}")
            except Exception as time_error:
                logger.warning(f"Ошибка фильтра времени для кандидата {candidate.user_id}: {time_error}")
                # При ошибке фильтра времени продолжаем проверку
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасный фильтр по категориям
            try:
                categories_filter = filters.get('categories_filter', [])
                if isinstance(categories_filter, list) and len(categories_filter) > 0:
                    if not self._filter_by_categories(candidate, categories_filter):
                        logger.info(f"🔥 Кандидат {candidate.user_id} отфильтрован по категориям: {categories_filter}")
                        return False
                    else:
                        logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ фильтр категорий")
                else:
                    logger.info(f"🔥 Фильтр категорий отключен для кандидата {candidate.user_id}")
            except Exception as categories_error:
                logger.warning(f"Ошибка фильтра категорий для кандидата {candidate.user_id}: {categories_error}")
                # При ошибке фильтра категорий продолжаем проверку
            
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Безопасный фильтр по минимальной совместимости
            try:
                min_compat = filters.get('min_compatibility', 30)
                if isinstance(min_compat, (int, float)) and min_compat > 0:
                    from bot.utils.cs2_data import calculate_profile_compatibility
                    compatibility = calculate_profile_compatibility(user_profile, candidate)
                    if compatibility and 'total' in compatibility:
                        total_compat = compatibility['total']
                        logger.info(f"🔥 Совместимость кандидата {candidate.user_id}: {total_compat}%, минимум: {min_compat}%")
                        if total_compat < min_compat:
                            logger.info(f"🔥 Кандидат {candidate.user_id} ОТФИЛЬТРОВАН по совместимости: {total_compat}% < {min_compat}%")
                            return False
                        else:
                            logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ фильтр совместимости: {total_compat}% >= {min_compat}%")
                    else:
                        logger.warning(f"Некорректный результат расчета совместимости для кандидата {candidate.user_id}")
                        # При ошибке расчета совместимости не фильтруем
                        logger.info(f"🔥 Кандидат {candidate.user_id} пропущен через фильтр совместимости из-за ошибки расчета")
                else:
                    logger.info(f"🔥 Фильтр совместимости отключен для кандидата {candidate.user_id}")
            except Exception as compatibility_error:
                logger.warning(f"Ошибка фильтра совместимости для кандидата {candidate.user_id}: {compatibility_error}")
                # При ошибке фильтра совместимости продолжаем без фильтрации
                logger.info(f"🔥 Кандидат {candidate.user_id} пропущен через фильтр совместимости из-за ошибки")
            
            logger.info(f"🔥 Кандидат {candidate.user_id} ПРОШЕЛ ВСЕ ФИЛЬТРЫ!")
            return True
            
        except Exception as e:
            logger.error(f"Критическая ошибка применения фильтров для кандидата {getattr(candidate, 'user_id', 'неизвестен')}: {e}", exc_info=True)
            return True  # По умолчанию не фильтруем при критических ошибках

    def _filter_by_elo(self, candidate: Profile, user_profile: Profile, elo_filter: str) -> bool:
        """Фильтрует по ELO"""
        if elo_filter == 'any':
            return True
        
        user_elo = user_profile.faceit_elo
        candidate_elo = candidate.faceit_elo
        
        # Старые фильтры для обратной совместимости
        if elo_filter == 'similar':
            # ±300 ELO считается похожим уровнем
            return abs(user_elo - candidate_elo) <= 300
        elif elo_filter == 'lower':
            # Ищем игроков с более низким ELO
            return candidate_elo < user_elo
        elif elo_filter == 'higher':
            # Ищем игроков с более высоким ELO
            return candidate_elo > user_elo
        
        # Новые диапазонные фильтры
        from bot.utils.cs2_data import check_elo_in_filter
        return check_elo_in_filter(candidate_elo, elo_filter)

    def _filter_by_maps_compatibility(self, candidate: Profile, user_profile: Profile, maps_filter: str) -> bool:
        """Фильтрует по совместимости карт"""
        if maps_filter == 'any':
            return True
        
        user_maps = set(user_profile.favorite_maps)
        candidate_maps = set(candidate.favorite_maps)
        common_maps = len(user_maps & candidate_maps)
        
        if maps_filter == 'strict':
            # Минимум 3 общие карты
            return common_maps >= 3
        elif maps_filter == 'moderate':
            # Минимум 2 общие карты
            return common_maps >= 2
        elif maps_filter == 'soft':
            # Минимум 1 общая карта
            return common_maps >= 1
        
        return True

    def _filter_by_time_compatibility(self, candidate: Profile, user_profile: Profile, time_filter: str) -> bool:
        """Фильтрует по совместимости времени"""
        if time_filter == 'any':
            return True
        
        user_slots = set(user_profile.playtime_slots)
        candidate_slots = set(candidate.playtime_slots)
        common_slots = len(user_slots & candidate_slots)
        
        if time_filter == 'strict':
            # Минимум 2 общих временных слота
            return common_slots >= 2
        elif time_filter == 'soft':
            # Минимум 1 общий временной слот
            return common_slots >= 1
        
        return True

    def _filter_by_categories(self, candidate: Profile, categories_filter: list) -> bool:
        """Фильтрует по категориям"""
        try:
            # 🔥 ИСПРАВЛЕНИЕ: Валидация фильтра категорий
            if not categories_filter or not isinstance(categories_filter, list):
                return True  # Нет фильтра - показываем всех
            
            # Очищаем фильтр от пустых/некорректных значений
            valid_categories_filter = []
            for cat in categories_filter:
                if isinstance(cat, str) and cat.strip():
                    valid_categories_filter.append(cat.strip())
            
            if not valid_categories_filter:
                return True  # После очистки фильтр пуст - показываем всех
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка категорий кандидата
            if not hasattr(candidate, 'categories'):
                logger.debug(f"У кандидата {candidate.user_id} нет атрибута categories")
                return False
            
            candidate_categories_raw = getattr(candidate, 'categories', None)
            if not candidate_categories_raw:
                logger.debug(f"У кандидата {candidate.user_id} пустые категории")
                return False
            
            # Проверяем тип категорий кандидата
            if not isinstance(candidate_categories_raw, list):
                logger.warning(f"Категории кандидата {candidate.user_id} не являются списком: {type(candidate_categories_raw)}")
                return False
            
            # Очищаем категории кандидата от некорректных значений
            valid_candidate_categories = []
            for cat in candidate_categories_raw:
                if isinstance(cat, str) and cat.strip():
                    valid_candidate_categories.append(cat.strip())
            
            if not valid_candidate_categories:
                logger.debug(f"У кандидата {candidate.user_id} нет валидных категорий")
                return False
            
            # 🔥 ИСПРАВЛЕНИЕ: Безопасная проверка пересечения категорий
            try:
                candidate_categories = set(valid_candidate_categories)
                filter_categories = set(valid_categories_filter)
                
                # Если есть хотя бы одна общая категория, кандидат подходит
                common_categories = candidate_categories & filter_categories
                has_common = len(common_categories) > 0
                
                logger.debug(f"Кандидат {candidate.user_id} категории: {candidate_categories}, фильтр: {filter_categories}, общие: {common_categories}, подходит: {has_common}")
                return has_common
                
            except Exception as set_error:
                logger.warning(f"Ошибка создания множеств категорий для кандидата {candidate.user_id}: {set_error}")
                return False
            
        except Exception as e:
            logger.error(f"Критическая ошибка фильтрации по категориям для кандидата {getattr(candidate, 'user_id', 'неизвестен')}: {e}", exc_info=True)
            return True  # По умолчанию не фильтруем при критических ошибках

    def _sort_by_compatibility(self, candidates: List[Profile], user_profile: Profile, filters: dict) -> List[Profile]:
        """Сортирует кандидатов по совместимости"""
        try:
            from bot.utils.cs2_data import calculate_profile_compatibility
            
            def get_compatibility(candidate):
                compatibility = calculate_profile_compatibility(user_profile, candidate)
                return compatibility['total']
            
            return sorted(candidates, key=get_compatibility, reverse=True)
        except Exception as e:
            logger.error(f"Ошибка сортировки по совместимости: {e}")
            return candidates

    # === СТАТИСТИКА ===

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику пользователя"""
        try:
            async with self.acquire_connection() as db:
                stats = {}
                
                # Полученные лайки
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM likes WHERE liked_id = ?", (user_id,)
                )
                stats['received_likes'] = (await cursor.fetchone())[0]
                
                # Отправленные лайки
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM likes WHERE liker_id = ?", (user_id,)
                )
                stats['sent_likes'] = (await cursor.fetchone())[0]
                
                # Тиммейты
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM matches WHERE (user1_id = ? OR user2_id = ?) AND is_active = 1",
                    (user_id, user_id)
                )
                stats['matches'] = (await cursor.fetchone())[0]
                
                # Просмотры профиля (пока заглушка)
                stats['profile_views'] = stats['received_likes'] * 3  # Примерная оценка
                
                # Рейтинг профиля
                total_interactions = stats['received_likes'] + stats['matches'] * 2
                stats['rating'] = min(10, max(1, total_interactions // 2))
                
                return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики для {user_id}: {e}")
            return {}

    # === НАСТРОЙКИ ===

    async def get_user_settings(self, user_id: int) -> Optional[UserSettings]:
        """Получает настройки пользователя"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row:
                    return UserSettings(**dict(row))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения настроек {user_id}: {e}")
            return None

    async def update_user_settings(self, user_id: int, **kwargs) -> bool:
        """Обновляет настройки пользователя"""
        try:
            async with self.acquire_connection() as db:
                # Создаем настройки если их нет
                await db.execute("""
                    INSERT OR IGNORE INTO user_settings (user_id, created_at)
                    VALUES (?, ?)
                """, (user_id, datetime.now()))
                
                # Обновляем настройки
                fields = []
                values = []
                
                for field, value in kwargs.items():
                    if field in ['search_filters', 'privacy_settings'] and isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    fields.append(f"{field} = ?")
                    values.append(value)
                
                if fields:
                    fields.append("updated_at = ?")
                    values.append(datetime.now())
                    values.append(user_id)
                    
                    query = f"UPDATE user_settings SET {', '.join(fields)} WHERE user_id = ?"
                    await db.execute(query, values)
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления настроек {user_id}: {e}")
            return False

    # === МОДЕРАЦИЯ ===

    async def get_profiles_for_moderation(self, status: str = 'pending', limit: int = 10, exclude_user_id: Optional[int] = None) -> List[Dict]:
        """Получает профили для модерации"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                # 🔥 ИСПРАВЛЕНИЕ: добавляем поддержку exclude_user_id для корректного листания
                if exclude_user_id:
                    cursor = await db.execute("""
                        SELECT p.*, u.username, u.first_name 
                        FROM profiles p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.moderation_status = ? AND p.user_id != ?
                        ORDER BY p.created_at ASC
                        LIMIT ?
                    """, (status, exclude_user_id, limit))
                else:
                    cursor = await db.execute("""
                        SELECT p.*, u.username, u.first_name 
                        FROM profiles p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.moderation_status = ?
                        ORDER BY p.created_at ASC
                        LIMIT ?
                    """, (status, limit))
                    
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения профилей для модерации: {e}")
            return []

    async def moderate_profile(self, user_id: int, status: str, moderator_id: int, reason: Optional[str] = None) -> bool:
        """Модерирует профиль (approve/reject)"""
        try:
            async with self.acquire_connection() as db:
                await db.execute("""
                    UPDATE profiles 
                    SET moderation_status = ?, moderation_reason = ?, moderated_by = ?, moderated_at = ?, updated_at = ?
                    WHERE user_id = ?
                """, (status, reason, moderator_id, datetime.now(), datetime.now(), user_id))
                await db.commit()
                logger.info(f"Профиль {user_id} {status} модератором {moderator_id}")
                return True
        except Exception as e:
            logger.error(f"Ошибка модерации профиля {user_id}: {e}")
            return False

    async def get_approved_profiles(self, exclude_user_id: Optional[int] = None, limit: int = 20) -> List[Profile]:
        """Получает только одобренные профили для поиска"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                if exclude_user_id:
                    cursor = await db.execute("""
                        SELECT * FROM profiles 
                        WHERE moderation_status = 'approved' AND user_id != ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                    """, (exclude_user_id, limit))
                else:
                    cursor = await db.execute("""
                        SELECT * FROM profiles 
                        WHERE moderation_status = 'approved'
                        ORDER BY updated_at DESC
                        LIMIT ?
                    """, (limit,))
                
                rows = await cursor.fetchall()
                return [Profile(**dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения одобренных профилей: {e}")
            return []

    # === МОДЕРАТОРЫ ===

    async def add_moderator(self, user_id: int, role: str = 'moderator', appointed_by: Optional[int] = None) -> bool:
        """Добавляет модератора"""
        try:
            async with self.acquire_connection() as db:
                await db.execute("""
                    INSERT OR REPLACE INTO moderators (user_id, role, appointed_by, appointed_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, role, appointed_by, datetime.now()))
                await db.commit()
                logger.info(f"Модератор добавлен: {user_id} (роль: {role})")
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления модератора {user_id}: {e}")
            return False

    async def get_moderator(self, user_id: int) -> Optional[Moderator]:
        """Получает данные модератора"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM moderators WHERE user_id = ? AND is_active = 1", (user_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return Moderator(**dict(row))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения модератора {user_id}: {e}")
            return None

    async def is_moderator(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь модератором"""
        moderator = await self.get_moderator(user_id)
        return moderator is not None and moderator.can_moderate_profiles()

    async def update_moderator_status(self, user_id: int, is_active: bool) -> bool:
        """Обновляет статус модератора (активирует/деактивирует)"""
        try:
            async with self.acquire_connection() as db:
                await db.execute("""
                    UPDATE moderators 
                    SET is_active = ?
                    WHERE user_id = ?
                """, (is_active, user_id))
                await db.commit()
                
                action = "активирован" if is_active else "деактивирован"
                logger.info(f"Модератор {user_id} {action}")
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса модератора {user_id}: {e}")
            return False

    async def get_all_moderators(self) -> List[Moderator]:
        """Получает список всех модераторов"""
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT * FROM moderators 
                    ORDER BY appointed_at DESC
                """)
                rows = await cursor.fetchall()
                return [Moderator(**dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка модераторов: {e}")
            return []

    async def get_moderation_stats(self) -> Dict:
        """Получает статистику модерации"""
        try:
            async with self.acquire_connection() as db:
                stats = {}
                
                # Количество профилей по статусам
                cursor = await db.execute("""
                    SELECT moderation_status, COUNT(*) as count
                    FROM profiles
                    GROUP BY moderation_status
                """)
                rows = await cursor.fetchall()
                for row in rows:
                    stats[f"profiles_{row[0]}"] = row[1]
                
                # Общее количество модераторов
                cursor = await db.execute("SELECT COUNT(*) FROM moderators WHERE is_active = 1")
                row = await cursor.fetchone()
                stats['active_moderators'] = row[0] if row else 0
                
                return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики модерации: {e}")
            return {}

    # === ИСТОРИЯ ЛАЙКОВ ===

    async def get_received_likes(self, user_id: int, new_only: bool = False, limit: int = 10, offset: int = 0) -> List[dict]:
        """
        Получает лайки, полученные пользователем
        
        Args:
            user_id: ID пользователя
            new_only: Если True, возвращает только неотвеченные лайки
            limit: Максимальное количество лайков
            offset: Смещение для пагинации
            
        Returns:
            List[dict]: Список лайков с информацией о лайкере
        """
        try:
            async with self.acquire_connection() as db:
                db.row_factory = aiosqlite.Row
                
                # Базовый запрос для получения лайков с профилем лайкера
                base_query = """
                    SELECT 
                        l.liker_id,
                        l.created_at,
                        p.game_nickname,
                        p.faceit_elo,
                        p.role,
                        p.media_type,
                        p.media_file_id,
                        u.username,
                        u.first_name
                    FROM likes l
                    JOIN profiles p ON l.liker_id = p.user_id
                    LEFT JOIN users u ON l.liker_id = u.user_id
                    WHERE l.liked_id = ?
                """
                
                params = [user_id]
                
                # Фильтр для новых лайков (неотвеченных и непросмотренных)
                if new_only:
                    base_query += """
                        AND l.viewed_at IS NULL
                        AND l.liker_id NOT IN (
                            SELECT liked_id FROM likes 
                            WHERE liker_id = ? 
                            AND liked_id = l.liker_id
                        )
                    """
                    params.append(user_id)
                
                base_query += """
                    ORDER BY l.created_at DESC
                    LIMIT ? OFFSET ?
                """
                params.extend([limit, offset])
                
                cursor = await db.execute(base_query, params)
                rows = await cursor.fetchall()
                
                likes = []
                for row in rows:
                    like_data = dict(row)
                    # Проверяем статус ответа
                    like_data['response_status'] = await self._check_like_response_status_internal(
                        db, row['liker_id'], user_id
                    )
                    likes.append(like_data)
                
                logger.info(f"Получено {len(likes)} лайков для пользователя {user_id} (new_only={new_only})")
                return likes
                
        except Exception as e:
            logger.error(f"Ошибка получения полученных лайков для {user_id}: {e}")
            return []

    async def _check_like_response_status_internal(self, db: aiosqlite.Connection, liker_id: int, liked_id: int) -> str:
        """
        Внутренний метод для проверки статуса ответа на лайк
        
        Returns:
            str: 'pending', 'replied', 'mutual'
        """
        try:
            # Проверяем есть ли ответный лайк
            cursor = await db.execute("""
                SELECT COUNT(*) FROM likes 
                WHERE liker_id = ? AND liked_id = ?
            """, (liked_id, liker_id))
            row = await cursor.fetchone()
            
            if row and row[0] > 0:
                return 'mutual'  # Взаимный лайк
            else:
                return 'pending'  # Ожидает ответа
                
        except Exception as e:
            logger.error(f"Ошибка проверки статуса ответа на лайк {liker_id}->{liked_id}: {e}")
            return 'pending'

    async def mark_like_as_viewed(self, liker_id: int, liked_id: int) -> bool:
        """
        Отмечает лайк как просмотренный/пропущенный путем установки viewed_at timestamp
        
        Args:
            liker_id: ID пользователя, который поставил лайк
            liked_id: ID пользователя, который получил лайк
            
        Returns:
            bool: True если операция прошла успешно
        """
        try:
            async with self.acquire_connection() as db:
                # Обновляем viewed_at для пропуска лайка
                cursor = await db.execute("""
                    UPDATE likes 
                    SET viewed_at = CURRENT_TIMESTAMP 
                    WHERE liker_id = ? AND liked_id = ?
                """, (liker_id, liked_id))
                await db.commit()
                
                # Проверяем что запись была обновлена
                if cursor.rowcount > 0:
                    logger.info(f"Лайк от {liker_id} к {liked_id} отмечен как просмотренный с timestamp")
                    return True
                else:
                    logger.warning(f"Лайк от {liker_id} к {liked_id} не найден для обновления")
                    return False
                    
        except Exception as e:
            logger.error(f"Ошибка отметки лайка как просмотренного {liker_id}->{liked_id}: {e}")
            return False

    async def get_likes_statistics(self, user_id: int) -> dict:
        """
        Получает статистику лайков для пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: Словарь со статистикой
        """
        try:
            async with self.acquire_connection() as db:
                stats = {}
                
                # Общее количество полученных лайков
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM likes WHERE liked_id = ?
                """, (user_id,))
                row = await cursor.fetchone()
                stats['total_received'] = row[0] if row else 0
                
                # Количество новых (неотвеченных и непросмотренных) лайков
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM likes l1
                    WHERE l1.liked_id = ?
                    AND l1.viewed_at IS NULL
                    AND l1.liker_id NOT IN (
                        SELECT l2.liked_id FROM likes l2 
                        WHERE l2.liker_id = ? 
                        AND l2.liked_id = l1.liker_id
                    )
                """, (user_id, user_id))
                row = await cursor.fetchone()
                stats['new_likes'] = row[0] if row else 0
                
                # Количество взаимных лайков (тиммейтов)
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM matches WHERE user1_id = ? OR user2_id = ?
                """, (user_id, user_id))
                row = await cursor.fetchone()
                stats['mutual_likes'] = row[0] if row else 0
                
                # Количество отправленных лайков
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM likes WHERE liker_id = ?
                """, (user_id,))
                row = await cursor.fetchone()
                stats['sent_likes'] = row[0] if row else 0
                
                logger.info(f"Статистика лайков для {user_id}: {stats}")
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики лайков для {user_id}: {e}")
            return {
                'total_received': 0,
                'new_likes': 0,
                'mutual_likes': 0,
                'sent_likes': 0
            }

    async def check_like_response_status(self, liker_id: int, liked_id: int) -> str:
        """
        Проверяет статус ответа на лайк
        
        Args:
            liker_id: ID пользователя, который поставил лайк
            liked_id: ID пользователя, который получил лайк
            
        Returns:
            str: 'pending', 'replied', 'mutual'
        """
        try:
            async with self.acquire_connection() as db:
                return await self._check_like_response_status_internal(db, liker_id, liked_id)
        except Exception as e:
            logger.error(f"Ошибка проверки статуса ответа на лайк {liker_id}->{liked_id}: {e}")
            return 'pending' 

    # ===== CACHE-RELATED METHODS =====
    # Methods to support cache warming and maintenance
    
    async def get_popular_profiles(self, limit: int = 50) -> List[str]:
        """
        Получает популярные профили на основе активности пользователей
        
        Args:
            limit: Максимальное количество профилей для возврата
            
        Returns:
            List[str]: Список никнеймов популярных профилей
        """
        try:
            async with self.acquire_connection() as db:
                # Получаем популярные профили на основе лайков, матчей и активности
                # Используем game_nickname из profiles и created_at из users как индикатор активности
                cursor = await db.execute("""
                    SELECT p.game_nickname, 
                           COUNT(DISTINCT l.liker_id) as like_count,
                           COUNT(DISTINCT m.id) as match_count,
                           u.created_at
                    FROM profiles p
                    JOIN users u ON p.user_id = u.user_id
                    LEFT JOIN likes l ON p.user_id = l.liked_id
                    LEFT JOIN matches m ON p.user_id IN (m.user1_id, m.user2_id)
                    WHERE p.game_nickname IS NOT NULL 
                          AND p.game_nickname != ''
                          AND p.moderation_status = 'approved'
                          AND u.is_active = 1
                          AND (l.created_at >= datetime('now', '-30 days') OR m.created_at >= datetime('now', '-30 days'))
                    GROUP BY p.user_id, p.game_nickname
                    HAVING (like_count + match_count) > 0
                    ORDER BY (like_count * 2 + match_count) DESC, p.updated_at DESC
                    LIMIT ?
                """, (limit,))
                
                rows = await cursor.fetchall()
                profiles = [row[0] for row in rows if row[0]]
                
                logger.debug(f"Найдено {len(profiles)} популярных профилей для разогрева кеша")
                return profiles
                
        except Exception as e:
            logger.error(f"Ошибка получения популярных профилей: {e}")
            return []

    async def get_user_network_profiles(self, user_id: int, limit: int = 20) -> List[str]:
        """
        Получает профили из сети пользователя (тиммейты, недавние взаимодействия)
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество профилей
            
        Returns:
            List[str]: Список никнеймов из сети пользователя
        """
        try:
            async with self.acquire_connection() as db:
                # Получаем профили тиммейтов и недавних взаимодействий
                # Используем game_nickname из profiles, поскольку faceit_nickname отсутствует в users
                cursor = await db.execute("""
                    SELECT DISTINCT p.game_nickname
                    FROM profiles p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.game_nickname IS NOT NULL 
                          AND p.game_nickname != ''
                          AND p.moderation_status = 'approved'
                          AND u.is_active = 1
                          AND p.user_id IN (
                              -- Тиммейты из матчей
                              SELECT CASE 
                                  WHEN m.user1_id = ? THEN m.user2_id
                                  ELSE m.user1_id
                              END as teammate_id
                              FROM matches m
                              WHERE (m.user1_id = ? OR m.user2_id = ?)
                              AND m.created_at >= datetime('now', '-14 days')
                              AND m.is_active = 1
                              
                              UNION
                              
                              -- Пользователи, которых лайкнул или которые лайкнули
                              SELECT l.liked_id FROM likes l 
                              WHERE l.liker_id = ? AND l.created_at >= datetime('now', '-7 days')
                              
                              UNION
                              
                              SELECT l.liker_id FROM likes l 
                              WHERE l.liked_id = ? AND l.created_at >= datetime('now', '-7 days')
                          )
                    ORDER BY p.updated_at DESC
                    LIMIT ?
                """, (user_id, user_id, user_id, user_id, user_id, limit))
                
                rows = await cursor.fetchall()
                profiles = [row[0] for row in rows if row[0]]
                
                logger.debug(f"Найдено {len(profiles)} профилей сети для пользователя {user_id}")
                return profiles
                
        except Exception as e:
            logger.error(f"Ошибка получения профилей сети для {user_id}: {e}")
            return []

    async def get_recent_search_profiles(self, hours: int = 24, limit: int = 30) -> List[str]:
        """
        Получает профили из недавних результатов поиска
        
        Args:
            hours: Количество часов назад для поиска активности
            limit: Максимальное количество профилей
            
        Returns:
            List[str]: Список никнеймов из недавних поисков
        """
        try:
            async with self.acquire_connection() as db:
                # Получаем профили с недавней активностью (лайки или обновления)
                cursor = await db.execute("""
                    SELECT DISTINCT p.game_nickname
                    FROM profiles p
                    JOIN users u ON p.user_id = u.user_id
                    LEFT JOIN likes l ON p.user_id = l.liked_id
                    WHERE p.game_nickname IS NOT NULL 
                          AND p.game_nickname != ''
                          AND p.moderation_status = 'approved'
                          AND u.is_active = 1
                          AND (
                              p.updated_at >= datetime('now', '-' || ? || ' hours') OR
                              l.created_at >= datetime('now', '-' || ? || ' hours')
                          )
                    ORDER BY p.updated_at DESC
                    LIMIT ?
                """, (hours, hours, limit))
                
                rows = await cursor.fetchall()
                profiles = [row[0] for row in rows if row[0]]
                
                logger.debug(f"Найдено {len(profiles)} профилей из недавних поисков")
                return profiles
                
        except Exception as e:
            logger.error(f"Ошибка получения профилей недавних поисков: {e}")
            return []

    async def track_profile_access(self, nickname: str, access_type: str = 'view') -> None:
        """
        Отслеживает доступ к профилю для оптимизации кеша
        
        Args:
            nickname: Никнейм профиля
            access_type: Тип доступа ('view', 'search', 'match')
        """
        try:
            async with self.acquire_connection() as db:
                # В будущем можно добавить отдельную таблицу для отслеживания доступа к профилям
                # Пока просто логируем для дебага
                logger.debug(f"Профиль {nickname} был использован: {access_type}")
                
        except Exception as e:
            logger.error(f"Ошибка отслеживания доступа к профилю {nickname}: {e}")

    async def get_active_users(self, days: int = 7, limit: int = 100) -> List[int]:
        """
        Получает активных пользователей для разогрева кеша
        
        Args:
            days: Количество дней для определения активности
            limit: Максимальное количество пользователей
            
        Returns:
            List[int]: Список ID активных пользователей
        """
        try:
            async with self.acquire_connection() as db:
                # Определяем активность на основе недавних лайков или обновлений профиля
                cursor = await db.execute("""
                    SELECT DISTINCT u.user_id
                    FROM users u
                    LEFT JOIN likes l ON u.user_id = l.liker_id
                    LEFT JOIN profiles p ON u.user_id = p.user_id
                    WHERE u.is_active = 1
                    AND (
                        l.created_at >= datetime('now', '-' || ? || ' days') OR
                        p.updated_at >= datetime('now', '-' || ? || ' days')
                    )
                    ORDER BY COALESCE(l.created_at, p.updated_at, u.created_at) DESC
                    LIMIT ?
                """, (days, days, limit))
                
                rows = await cursor.fetchall()
                user_ids = [row[0] for row in rows]
                
                logger.debug(f"Найдено {len(user_ids)} активных пользователей")
                return user_ids
                
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []

    async def get_trending_profiles(self, days: int = 3, limit: int = 25) -> List[str]:
        """
        Получает профили с растущей популярностью
        
        Args:
            days: Количество дней для анализа трендов
            limit: Максимальное количество профилей
            
        Returns:
            List[str]: Список никнеймов трендовых профилей
        """
        try:
            async with self.acquire_connection() as db:
                # Находим профили с увеличивающимся количеством лайков
                cursor = await db.execute("""
                    SELECT p.game_nickname,
                           COUNT(l.liker_id) as recent_likes
                    FROM profiles p
                    JOIN users u ON p.user_id = u.user_id
                    JOIN likes l ON p.user_id = l.liked_id
                    WHERE p.game_nickname IS NOT NULL 
                          AND p.game_nickname != ''
                          AND p.moderation_status = 'approved'
                          AND u.is_active = 1
                          AND l.created_at >= datetime('now', '-' || ? || ' days')
                    GROUP BY p.user_id, p.game_nickname
                    HAVING recent_likes >= 2
                    ORDER BY recent_likes DESC
                    LIMIT ?
                """, (days, limit))
                
                rows = await cursor.fetchall()
                profiles = [row[0] for row in rows if row[0]]
                
                logger.debug(f"Найдено {len(profiles)} трендовых профилей")
                return profiles
                
        except Exception as e:
            logger.error(f"Ошибка получения трендовых профилей: {e}")
            return []

    async def get_stale_cache_candidates(self, days: int = 1) -> List[str]:
        """
        Получает профили, которые могут нуждаться в обновлении кеша
        
        Args:
            days: Количество дней для определения устаревания
            
        Returns:
            List[str]: Список никнеймов для обновления кеша
        """
        try:
            async with self.acquire_connection() as db:
                # Находим профили активных пользователей, которые недавно обновлялись
                cursor = await db.execute("""
                    SELECT DISTINCT p.game_nickname
                    FROM profiles p
                    JOIN users u ON p.user_id = u.user_id
                    LEFT JOIN likes l ON p.user_id = l.liked_id
                    WHERE p.game_nickname IS NOT NULL 
                          AND p.game_nickname != ''
                          AND p.moderation_status = 'approved'
                          AND u.is_active = 1
                          AND (
                              l.created_at >= datetime('now', '-' || ? || ' days')
                              OR p.updated_at >= datetime('now', '-' || ? || ' days')
                          )
                    ORDER BY p.updated_at DESC
                    LIMIT 50
                """, (days, days))
                
                rows = await cursor.fetchall()
                profiles = [row[0] for row in rows if row[0]]
                
                logger.debug(f"Найдено {len(profiles)} кандидатов для обновления кеша")
                return profiles
                
        except Exception as e:
            logger.error(f"Ошибка получения кандидатов для обновления кеша: {e}")
            return []