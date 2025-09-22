"""
SQLite-based persistent cache system for Faceit data
Создано организацией Twizz_Project

Implements intelligent caching with activity-based TTL, cache warming,
and comprehensive maintenance routines for improved performance.
"""
import json
import logging
import aiosqlite
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple, Set
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import sqlite3
import os

from ..config import Config
from .security_validator import security_validator

logger = logging.getLogger(__name__)
secure_logger = security_validator.get_secure_logger(__name__)

@dataclass
class CacheEntry:
    """Структурированное представление записи кеша"""
    nickname: str
    data_type: str
    data: Dict[str, Any]
    created_at: datetime
    accessed_at: datetime
    access_count: int
    last_match_date: Optional[datetime]
    is_active: bool
    ttl_seconds: int

@dataclass 
class CacheStats:
    """Метрики производительности кеша"""
    date: datetime
    hits: int
    misses: int
    size: int
    cleanup_count: int
    warming_count: int
    avg_response_time: float

class FaceitCacheManager:
    """SQLite-based cache manager with intelligent TTL and warming capabilities"""
    
    def __init__(self, db_manager=None):
        self.cache_db_path = Config.FACEIT_CACHE_DB_PATH
        self.active_player_ttl = Config.FACEIT_CACHE_ACTIVE_PLAYER_TTL
        self.inactive_player_ttl = Config.FACEIT_CACHE_INACTIVE_PLAYER_TTL
        self.activity_threshold = Config.FACEIT_CACHE_ACTIVITY_THRESHOLD
        self.max_entries = Config.FACEIT_CACHE_MAX_ENTRIES
        
        # Cache warming settings
        self.warming_enabled = Config.FACEIT_CACHE_WARMING_ENABLED
        self.warming_batch_size = Config.FACEIT_CACHE_WARMING_BATCH_SIZE
        self.warming_interval = Config.FACEIT_CACHE_WARMING_INTERVAL
        self.popular_threshold = Config.FACEIT_CACHE_POPULAR_THRESHOLD
        
        # Maintenance settings
        self.cleanup_interval = Config.FACEIT_CACHE_CLEANUP_INTERVAL
        self.vacuum_interval = Config.FACEIT_CACHE_VACUUM_INTERVAL
        self.stats_retention = Config.FACEIT_CACHE_STATS_RETENTION
        
        # Database manager for efficient connection pooling
        if db_manager:
            self.db_manager = db_manager
            logger.info("FaceitCacheManager using shared DatabaseManager")
        else:
            # Create standalone DatabaseManager for cache database
            from ..database.operations import DatabaseManager
            self.db_manager = DatabaseManager(databases={'cache': self.cache_db_path})
            logger.info("FaceitCacheManager created standalone DatabaseManager")
        
        # Runtime state
        self._lock = asyncio.Lock()
        self._initialized = False
        self._maintenance_tasks: Set[asyncio.Task] = set()
        self._preload_callback = None  # Callback for actual ELO preloading
        
        # Performance tracking
        self._stats = {
            'hits': 0,
            'misses': 0,
            'total_requests': 0,
            'response_times': [],
            'last_cleanup': None,
            'last_warming': None
        }
        
        # Performance monitoring integration
        self.performance_monitor = None
        
        logger.info(f"Initializing FaceitCacheManager with database: {self.cache_db_path}")
    
    async def _get_cache_size_mb(self) -> float:
        """Get current cache size in MB"""
        try:
            if not os.path.exists(self.cache_db_path):
                return 0.0
            
            size_bytes = os.path.getsize(self.cache_db_path)
            return size_bytes / (1024 * 1024)  # Convert to MB
            
        except Exception as e:
            logger.debug(f"Error getting cache size: {e}")
            return 0.0
    
    def _calculate_cache_efficiency(self) -> float:
        """Calculate cache efficiency based on hit ratio and access patterns"""
        try:
            total_requests = self._stats['hits'] + self._stats['misses']
            if total_requests == 0:
                return 1.0
            
            hit_ratio = self._stats['hits'] / total_requests
            
            # Base efficiency on hit ratio
            efficiency = hit_ratio
            
            # Adjust for response times if available
            if self._stats['response_times']:
                avg_response_time = sum(self._stats['response_times']) / len(self._stats['response_times'])
                # Lower response times increase efficiency
                time_factor = max(0, 1 - (avg_response_time / 1000))  # Assume 1000ms baseline
                efficiency = (efficiency + time_factor) / 2
            
            return min(1.0, max(0.0, efficiency))
            
        except Exception as e:
            logger.debug(f"Error calculating cache efficiency: {e}")
            return 0.0
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics for monitoring"""
        try:
            total_requests = self._stats['hits'] + self._stats['misses']
            
            metrics = {
                'hit_ratio': self._stats['hits'] / total_requests if total_requests > 0 else 0,
                'miss_ratio': self._stats['misses'] / total_requests if total_requests > 0 else 0,
                'total_requests': total_requests,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'efficiency': self._calculate_cache_efficiency(),
                'avg_response_time': (
                    sum(self._stats['response_times']) / len(self._stats['response_times'])
                    if self._stats['response_times'] else 0
                ),
                'last_cleanup': self._stats['last_cleanup'],
                'last_warming': self._stats['last_warming']
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    def set_preload_callback(self, callback) -> None:
        """Set callback function for ELO preloading during cache warming"""
        self._preload_callback = callback
        logger.debug("ELO preload callback registered")
    
    def set_performance_monitor(self, performance_monitor):
        """Set performance monitor instance for tracking cache performance"""
        self.performance_monitor = performance_monitor
        logger.debug("Performance monitor integrated into FaceitCacheManager")

    async def initialize(self) -> None:
        """Initialize cache database and start maintenance tasks"""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            try:
                # Create data directory if it doesn't exist
                dirpath = os.path.dirname(self.cache_db_path)
                if dirpath:
                    os.makedirs(dirpath, exist_ok=True)
                
                # Initialize database manager connection pools
                await self.db_manager.connect()
                
                # Create database tables
                await self._create_tables()
                
                # Start maintenance tasks
                await self._start_maintenance_tasks()
                
                self._initialized = True
                logger.info("FaceitCacheManager initialized successfully with pooled connections")
                
            except Exception as e:
                logger.error(f"Failed to initialize cache manager: {e}", exc_info=True)
                raise

    async def _create_tables(self) -> None:
        """Create cache database tables with optimized indexes using pooled connections"""
        async with self.db_manager.acquire_connection(db_type='cache') as conn:
            # WAL mode and other optimizations are now handled in _create_connection
            
            # Check if migration is needed for existing table
            await self._migrate_cache_table(conn)
            
            # Create faceit_cache table with fixed expires_at generation
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS faceit_cache (
                    nickname TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1,
                    last_match_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT FALSE,
                    ttl_seconds INTEGER DEFAULT 3600,
                    expires_at TIMESTAMP GENERATED ALWAYS AS (
                        datetime(created_at, '+' || ttl_seconds || ' seconds')
                    ) STORED,
                    PRIMARY KEY (nickname, data_type)
                )
            """)
            
            # Create cache_stats table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    size INTEGER DEFAULT 0,
                    cleanup_count INTEGER DEFAULT 0,
                    warming_count INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create optimized indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON faceit_cache(expires_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_accessed ON faceit_cache(accessed_at DESC)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_active ON faceit_cache(is_active, access_count DESC)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_last_match ON faceit_cache(last_match_date DESC)")
            await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stats_date ON cache_stats(date)")
            
            await conn.commit()

    async def _migrate_cache_table(self, conn: aiosqlite.Connection) -> None:
        """Migrate existing cache table to fix expires_at generation from accessed_at to created_at"""
        try:
            # Check if table exists and has the old expires_at generation
            cursor = await conn.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name='faceit_cache'
            """)
            table_sql = await cursor.fetchone()
            
            if table_sql and 'accessed_at' in table_sql[0] and 'expires_at' in table_sql[0]:
                logger.info("Migrating cache table to fix TTL extension issue")
                
                # Create temporary table with correct expires_at generation
                await conn.execute("""
                    CREATE TABLE faceit_cache_new (
                        nickname TEXT NOT NULL,
                        data_type TEXT NOT NULL,
                        data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        access_count INTEGER DEFAULT 1,
                        last_match_date TIMESTAMP,
                        is_active BOOLEAN DEFAULT FALSE,
                        ttl_seconds INTEGER DEFAULT 3600,
                        expires_at TIMESTAMP GENERATED ALWAYS AS (
                            datetime(created_at, '+' || ttl_seconds || ' seconds')
                        ) STORED,
                        PRIMARY KEY (nickname, data_type)
                    )
                """)
                
                # Copy data from old table to new table
                await conn.execute("""
                    INSERT INTO faceit_cache_new 
                    (nickname, data_type, data, created_at, accessed_at, access_count, 
                     last_match_date, is_active, ttl_seconds)
                    SELECT nickname, data_type, data, created_at, accessed_at, access_count, 
                           last_match_date, is_active, ttl_seconds
                    FROM faceit_cache
                """)
                
                # Drop old table
                await conn.execute("DROP TABLE faceit_cache")
                
                # Rename new table
                await conn.execute("ALTER TABLE faceit_cache_new RENAME TO faceit_cache")
                
                logger.info("Cache table migration completed successfully")
                
        except Exception as e:
            # If migration fails, we'll create a fresh table (handled by the IF NOT EXISTS)
            logger.warning(f"Cache table migration failed, will create fresh table: {e}")

    async def get(self, nickname: str, data_type: str) -> Optional[Dict[str, Any]]:
        """Get cached data with automatic TTL validation and access tracking using pooled connections"""
        if not self._initialized:
            await self.initialize()
            
        start_time = datetime.now()
        
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Check for valid cached entry
                cursor = await conn.execute("""
                    SELECT data, expires_at, access_count 
                    FROM faceit_cache 
                    WHERE nickname = ? AND data_type = ? AND expires_at > datetime('now')
                """, (nickname, data_type))
                
                row = await cursor.fetchone()
                
                if row:
                    data_json, expires_at, access_count = row
                    
                    # Update access statistics
                    await conn.execute("""
                        UPDATE faceit_cache 
                        SET accessed_at = datetime('now'), access_count = access_count + 1
                        WHERE nickname = ? AND data_type = ?
                    """, (nickname, data_type))
                    
                    await conn.commit()
                    
                    # Update performance stats
                    self._stats['hits'] += 1
                    self._record_response_time(start_time)
                    
                    # Report cache hit to performance monitor
                    if self.performance_monitor:
                        try:
                            hit_ratio = self._stats['hits'] / (self._stats['hits'] + self._stats['misses'])
                            miss_ratio = self._stats['misses'] / (self._stats['hits'] + self._stats['misses'])
                            self.performance_monitor.update_cache_metrics(
                                hit_ratio=hit_ratio,
                                miss_ratio=miss_ratio,
                                size_mb=await self._get_cache_size_mb(),
                                efficiency=self._calculate_cache_efficiency()
                            )
                        except Exception as e:
                            logger.debug(f"Error updating cache performance metrics: {e}")
                    
                    secure_logger.debug(f"Cache hit for {nickname}:{data_type} (access_count: {access_count + 1})")
                    
                    # Безопасный парсинг JSON данных из кеша
                    faceit_data_schema = {
                        "type": "object",
                        "properties": {
                            "player_id": {"type": "string"},
                            "nickname": {"type": "string"},
                            "games": {"type": "object"},
                            "stats": {"type": "object"}
                        }
                    }
                    
                    parsed_data, validation_result = security_validator.safe_json_loads(
                        data_json, 
                        schema=faceit_data_schema, 
                        default=None
                    )
                    
                    if validation_result.is_valid:
                        return parsed_data
                    else:
                        secure_logger.error(f"Ошибка валидации кешированных данных для {nickname}:{data_type}: {validation_result.error_message}")
                        return None
                    
                else:
                    # Cache miss
                    self._stats['misses'] += 1
                    self._record_response_time(start_time)
                    
                    # Report cache miss to performance monitor
                    if self.performance_monitor:
                        try:
                            hit_ratio = self._stats['hits'] / (self._stats['hits'] + self._stats['misses'])
                            miss_ratio = self._stats['misses'] / (self._stats['hits'] + self._stats['misses'])
                            self.performance_monitor.update_cache_metrics(
                                hit_ratio=hit_ratio,
                                miss_ratio=miss_ratio,
                                size_mb=await self._get_cache_size_mb(),
                                efficiency=self._calculate_cache_efficiency()
                            )
                        except Exception as e:
                            logger.debug(f"Error updating cache performance metrics: {e}")
                    
                    secure_logger.debug(f"Cache miss for {nickname}:{data_type}")
                    return None
                    
        except Exception as e:
            logger.error(f"Cache get error for {nickname}:{data_type}: {e}", exc_info=True)
            self._stats['misses'] += 1
            return None

    async def set(self, nickname: str, data_type: str, data: Dict[str, Any]) -> bool:
        """Store data in cache with intelligent TTL based on player activity using pooled connections"""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Calculate intelligent TTL
            ttl_seconds, is_active = await self._calculate_ttl(data)
            
            # Extract last match date for activity tracking
            last_match_date = self._extract_last_match_date(data)
            
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Insert or update cache entry
                # Безопасная сериализация данных в JSON
                try:
                    json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                except (TypeError, ValueError) as e:
                    secure_logger.error(f"Ошибка сериализации данных для {nickname}:{data_type}: {e}")
                    return False
                
                await conn.execute("""
                    INSERT OR REPLACE INTO faceit_cache 
                    (nickname, data_type, data, created_at, accessed_at, access_count, 
                     last_match_date, is_active, ttl_seconds)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'), 
                           COALESCE((SELECT access_count FROM faceit_cache 
                                   WHERE nickname = ? AND data_type = ?), 0) + 1,
                           ?, ?, ?)
                """, (nickname, data_type, json_data, nickname, data_type,
                      last_match_date, is_active, ttl_seconds))
                
                await conn.commit()
                
                logger.debug(f"Cached {nickname}:{data_type} with TTL {ttl_seconds}s (active: {is_active})")
                return True
                
        except Exception as e:
            logger.error(f"Cache set error for {nickname}:{data_type}: {e}", exc_info=True)
            return False

    async def _calculate_ttl(self, data: Dict[str, Any]) -> Tuple[int, bool]:
        """Calculate intelligent TTL based on player activity patterns"""
        try:
            last_match_date = self._extract_last_match_date(data)
            
            if last_match_date:
                # Use timezone-aware UTC datetime for consistent comparison
                now = datetime.now(timezone.utc)
                days_since_last_match = (now - last_match_date).days
                is_active = days_since_last_match <= self.activity_threshold
                
                logger.debug(f"TTL calculation: now={now.isoformat()}, last_match={last_match_date.isoformat()}, "
                           f"days_since={days_since_last_match}, activity_threshold={self.activity_threshold}, "
                           f"is_active={is_active}")
                
                if is_active:
                    # Active player: shorter TTL for fresh data
                    return self.active_player_ttl, True
                else:
                    # Inactive player: longer TTL to reduce API load
                    return self.inactive_player_ttl, False
            else:
                # No match data available: use longer TTL
                logger.debug("No last match date found, using inactive player TTL")
                return self.inactive_player_ttl, False
                
        except Exception as e:
            logger.warning(f"Error calculating TTL: {e}")
            return self.inactive_player_ttl, False

    def _extract_last_match_date(self, data: Dict[str, Any]) -> Optional[datetime]:
        """Extract last match date from API data for activity detection"""
        try:
            # Try different possible paths in the API data
            if 'stats' in data and isinstance(data['stats'], dict):
                stats = data['stats']
                if 'last_match' in stats:
                    dt = datetime.fromisoformat(stats['last_match'].replace('Z', '+00:00'))
                    return dt.astimezone(timezone.utc)
                    
            if 'last_match_date' in data:
                dt = datetime.fromisoformat(data['last_match_date'].replace('Z', '+00:00'))
                return dt.astimezone(timezone.utc)
                
            if 'games' in data and isinstance(data['games'], dict):
                # Look for CS2/CSGO game data
                for game_name in ['cs2', 'csgo']:
                    if game_name in data['games']:
                        game_stats = data['games'][game_name]
                        if isinstance(game_stats, dict) and 'last_match' in game_stats:
                            dt = datetime.fromisoformat(game_stats['last_match'].replace('Z', '+00:00'))
                            return dt.astimezone(timezone.utc)
            
            return None
            
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Could not extract last match date: {e}")
            return None

    async def exists(self, nickname: str, data_type: str) -> bool:
        """Check if valid cached entry exists using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                cursor = await conn.execute("""
                    SELECT 1 FROM faceit_cache 
                    WHERE nickname = ? AND data_type = ? AND expires_at > datetime('now')
                """, (nickname, data_type))
                
                return await cursor.fetchone() is not None
                
        except Exception as e:
            logger.error(f"Cache exists check error: {e}")
            return False

    async def invalidate(self, nickname: str, data_type: Optional[str] = None) -> bool:
        """Manually invalidate cache entries using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                if data_type:
                    await conn.execute("DELETE FROM faceit_cache WHERE nickname = ? AND data_type = ?",
                                     (nickname, data_type))
                else:
                    await conn.execute("DELETE FROM faceit_cache WHERE nickname = ?", (nickname,))
                
                await conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return False

    async def get_multiple(self, requests: List[Tuple[str, str]]) -> Dict[Tuple[str, str], Optional[Dict[str, Any]]]:
        """Batch retrieve multiple cache entries using pooled connections"""
        results = {}
        
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                for nickname, data_type in requests:
                    cursor = await conn.execute("""
                        SELECT data FROM faceit_cache 
                        WHERE nickname = ? AND data_type = ? AND expires_at > datetime('now')
                    """, (nickname, data_type))
                    
                    row = await cursor.fetchone()
                    if row:
                        # Безопасный парсинг JSON данных
                        parsed_data, validation_result = security_validator.safe_json_loads(
                            row[0], 
                            default=None
                        )
                        if validation_result.is_valid:
                            results[(nickname, data_type)] = parsed_data
                            self._stats['hits'] += 1
                        else:
                            secure_logger.error(f"Ошибка валидации данных в batch get для {nickname}:{data_type}: {validation_result.error_message}")
                            results[(nickname, data_type)] = None
                            self._stats['misses'] += 1
                    else:
                        results[(nickname, data_type)] = None
                        self._stats['misses'] += 1
                        
                # Update access stats for hits
                hit_queries = [(nickname, data_type) for (nickname, data_type), data in results.items() if data is not None]
                for nickname, data_type in hit_queries:
                    await conn.execute("""
                        UPDATE faceit_cache 
                        SET accessed_at = datetime('now'), access_count = access_count + 1
                        WHERE nickname = ? AND data_type = ?
                    """, (nickname, data_type))
                
                if hit_queries:
                    await conn.commit()
                    
        except Exception as e:
            logger.error(f"Batch cache get error: {e}")
            
        return results

    async def warm_popular_profiles(self) -> List[str]:
        """Warm cache for popular profiles based on access patterns using pooled connections - returns list of nicknames to warm"""
        if not self.warming_enabled:
            return []
            
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Get popular profiles that need warming
                cursor = await conn.execute("""
                    SELECT DISTINCT nickname FROM faceit_cache 
                    WHERE access_count >= ? AND is_active = 1
                    AND (expires_at <= datetime('now', '+30 minutes') OR expires_at <= datetime('now'))
                    ORDER BY access_count DESC, accessed_at DESC
                    LIMIT ?
                """, (self.popular_threshold, self.warming_batch_size))
                
                profiles_to_warm = [row[0] for row in await cursor.fetchall()]
                
                # Update performance monitoring with warming effectiveness
                if self.performance_monitor and profiles_to_warm:
                    try:
                        warming_effectiveness = len(profiles_to_warm) / self.warming_batch_size
                        current_hit_ratio = self._stats['hits'] / (self._stats['hits'] + self._stats['misses']) if (self._stats['hits'] + self._stats['misses']) > 0 else 0
                        self.performance_monitor.update_cache_metrics(
                            hit_ratio=current_hit_ratio,
                            miss_ratio=1 - current_hit_ratio,
                            size_mb=await self._get_cache_size_mb(),
                            efficiency=self._calculate_cache_efficiency(),
                            warming_effectiveness=warming_effectiveness
                        )
                    except Exception as e:
                        logger.debug(f"Error updating cache warming metrics: {e}")
                
                logger.info(f"Identified {len(profiles_to_warm)} popular profiles for warming")
                return profiles_to_warm
                
        except Exception as e:
            logger.error(f"Cache warming error: {e}")
            return []

    async def warm_user_network(self, user_id: int) -> int:
        """Warm cache for user's teammates and recent interactions by delegating to FaceitAnalyzer"""
        if not self.warming_enabled:
            return 0
            
        try:
            # Delegate to FaceitAnalyzer for orchestration
            from .faceit_analyzer import faceit_analyzer
            
            warmed_count = await faceit_analyzer.warm_user_network(user_id)
            
            # Update local cache statistics
            if warmed_count > 0:
                # Find today's stats record and increment warming_count
                from datetime import date
                today = date.today()
                
                async with self.db_manager.acquire_connection(db_type='cache') as conn:
                    await conn.execute("""
                        INSERT OR IGNORE INTO cache_stats (date, warming_count) 
                        VALUES (?, 0)
                    """, (today,))
                    
                    await conn.execute("""
                        UPDATE cache_stats 
                        SET warming_count = warming_count + ?
                        WHERE date = ?
                    """, (warmed_count, today))
                    
                    await conn.commit()
            
            logger.info(f"User network warming completed for user {user_id}: {warmed_count} profiles warmed")
            return warmed_count
            
        except Exception as e:
            logger.error(f"User network warming error for user {user_id}: {e}", exc_info=True)
            return 0

    async def cleanup_expired(self) -> int:
        """Remove expired cache entries and return count of cleaned entries using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Count expired entries
                cursor = await conn.execute("SELECT COUNT(*) FROM faceit_cache WHERE expires_at <= datetime('now')")
                expired_count = (await cursor.fetchone())[0]
                
                # Delete expired entries
                await conn.execute("DELETE FROM faceit_cache WHERE expires_at <= datetime('now')")
                
                # Clean up old statistics
                await conn.execute("""
                    DELETE FROM cache_stats 
                    WHERE date < date('now', '-' || ? || ' days')
                """, (self.stats_retention,))
                
                await conn.commit()
                
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired cache entries")
                    
                self._stats['last_cleanup'] = datetime.now()
                return expired_count
                
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            return 0

    async def vacuum_database(self) -> bool:
        """Optimize database by running VACUUM using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                await conn.execute("VACUUM")
                await conn.commit()
                
                logger.info("Cache database vacuumed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Database vacuum error: {e}")
            return False

    async def update_statistics(self) -> None:
        """Update daily cache statistics using pooled connections"""
        try:
            today = datetime.now().date()
            
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Get current cache size
                cursor = await conn.execute("SELECT COUNT(*) FROM faceit_cache")
                cache_size = (await cursor.fetchone())[0]
                
                # Calculate average response time
                avg_response_time = sum(self._stats['response_times']) / len(self._stats['response_times']) if self._stats['response_times'] else 0.0
                
                # Insert or update statistics
                await conn.execute("""
                    INSERT OR REPLACE INTO cache_stats 
                    (date, hits, misses, size, avg_response_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (today, self._stats['hits'], self._stats['misses'], cache_size, avg_response_time))
                
                await conn.commit()
                
                # Reset daily counters
                self._stats['response_times'] = []
                
        except Exception as e:
            logger.error(f"Statistics update error: {e}")

    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache performance statistics using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Current cache size
                cursor = await conn.execute("SELECT COUNT(*) FROM faceit_cache")
                current_size = (await cursor.fetchone())[0]
                
                # Active vs inactive entries
                cursor = await conn.execute("SELECT is_active, COUNT(*) FROM faceit_cache GROUP BY is_active")
                activity_stats = {bool(row[0]): row[1] for row in await cursor.fetchall()}
                
                # Hit ratio
                total_requests = self._stats['hits'] + self._stats['misses']
                hit_ratio = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
                
                # Recent performance
                cursor = await conn.execute("""
                    SELECT hits, misses, avg_response_time 
                    FROM cache_stats 
                    WHERE date >= date('now', '-7 days')
                    ORDER BY date DESC
                """)
                recent_stats = await cursor.fetchall()
                
                return {
                    'current_size': current_size,
                    'active_entries': activity_stats.get(True, 0),
                    'inactive_entries': activity_stats.get(False, 0),
                    'hit_ratio': round(hit_ratio, 2),
                    'total_hits': self._stats['hits'],
                    'total_misses': self._stats['misses'],
                    'last_cleanup': self._stats['last_cleanup'],
                    'last_warming': self._stats['last_warming'],
                    'recent_performance': recent_stats[:7]  # Last 7 days
                }
                
        except Exception as e:
            logger.error(f"Statistics retrieval error: {e}")
            return {'error': str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive cache system health check using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Database connectivity test
                await conn.execute("SELECT 1")
                
                # Check table integrity
                cursor = await conn.execute("PRAGMA integrity_check")
                integrity_result = await cursor.fetchone()
                
                # Cache performance metrics
                stats = await self.get_statistics()
                
                # Maintenance task status
                active_tasks = len([task for task in self._maintenance_tasks if not task.done()])
                
                return {
                    'status': 'healthy',
                    'database_accessible': True,
                    'integrity_check': integrity_result[0] if integrity_result else 'unknown',
                    'cache_size': stats.get('current_size', 0),
                    'hit_ratio': stats.get('hit_ratio', 0),
                    'active_maintenance_tasks': active_tasks,
                    'initialization_status': self._initialized
                }
                
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'database_accessible': False
            }

    async def clear_all(self) -> bool:
        """Clear all cache entries (for testing/debugging) using pooled connections"""
        try:
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                await conn.execute("DELETE FROM faceit_cache")
                await conn.commit()
                
                logger.info("All cache entries cleared")
                return True
                
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False

    def _record_response_time(self, start_time: datetime) -> None:
        """Record response time for performance tracking"""
        response_time = (datetime.now() - start_time).total_seconds() * 1000  # ms
        self._stats['response_times'].append(response_time)
        
        # Keep only last 1000 response times to prevent memory growth
        if len(self._stats['response_times']) > 1000:
            self._stats['response_times'] = self._stats['response_times'][-500:]

    async def _start_maintenance_tasks(self) -> None:
        """Start background maintenance tasks"""
        try:
            # Cleanup task
            cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self._maintenance_tasks.add(cleanup_task)
            
            # Vacuum task
            vacuum_task = asyncio.create_task(self._periodic_vacuum())
            self._maintenance_tasks.add(vacuum_task)
            
            # Statistics task
            stats_task = asyncio.create_task(self._periodic_stats_update())
            self._maintenance_tasks.add(stats_task)
            
            # Cache warming task
            if self.warming_enabled:
                warming_task = asyncio.create_task(self._periodic_warming())
                self._maintenance_tasks.add(warming_task)
                
            logger.info(f"Started {len(self._maintenance_tasks)} maintenance tasks")
            
        except Exception as e:
            logger.error(f"Failed to start maintenance tasks: {e}")

    async def _periodic_cleanup(self) -> None:
        """Periodic cache cleanup task"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")

    async def _periodic_vacuum(self) -> None:
        """Periodic database vacuum task"""
        while True:
            try:
                await asyncio.sleep(self.vacuum_interval)
                await self.vacuum_database()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic vacuum error: {e}")

    async def _periodic_stats_update(self) -> None:
        """Periodic statistics update task"""
        while True:
            try:
                await asyncio.sleep(900)  # Update every 15 minutes
                await self.update_statistics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic stats update error: {e}")

    async def _periodic_warming(self) -> None:
        """Periodic cache warming task with callback support for actual ELO preloading"""
        while True:
            try:
                await asyncio.sleep(self.warming_interval)
                profiles_to_warm = await self.warm_popular_profiles()
                self._stats['last_warming'] = datetime.now()
                
                if profiles_to_warm:
                    logger.info(f"Cache warming identified {len(profiles_to_warm)} profiles")
                    
                    # Trigger actual ELO preloading through FaceitAnalyzer
                    if hasattr(self, '_preload_callback') and self._preload_callback:
                        try:
                            await self._preload_callback(profiles_to_warm)
                            logger.info(f"ELO preloading triggered for {len(profiles_to_warm)} profiles")
                        except Exception as callback_error:
                            logger.error(f"ELO preloading callback failed: {callback_error}")
                    else:
                        logger.debug("No preload callback registered, skipping ELO preloading")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic warming error: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown of cache manager"""
        logger.info("Shutting down FaceitCacheManager...")
        
        # Cancel all maintenance tasks
        for task in self._maintenance_tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete with timeout
        if self._maintenance_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._maintenance_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Maintenance tasks didn't complete within timeout")
                
        # Final statistics update
        try:
            await self.update_statistics()
        except Exception as e:
            logger.error(f"Final statistics update failed: {e}")
            
        # Disconnect database manager if we own it
        try:
            if hasattr(self, 'db_manager'):
                await self.db_manager.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting database manager: {e}")
            
        self._maintenance_tasks.clear()
        self._initialized = False
        
        logger.info("FaceitCacheManager shutdown completed")

    async def validate_ttl_fix(self, nickname: str, data_type: str, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validation method to confirm expires_at doesn't move forward on repeated reads using pooled connections.
        Returns validation results for testing purposes.
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            # First, store test data
            await self.set(nickname, data_type, test_data)
            
            async with self.db_manager.acquire_connection(db_type='cache') as conn:
                # Get initial expires_at value
                cursor = await conn.execute("""
                    SELECT expires_at, created_at, accessed_at, access_count 
                    FROM faceit_cache 
                    WHERE nickname = ? AND data_type = ?
                """, (nickname, data_type))
                
                initial_row = await cursor.fetchone()
                if not initial_row:
                    return {"error": "No cache entry found after set operation"}
                
                initial_expires_at, initial_created_at, initial_accessed_at, initial_access_count = initial_row
                
                # Perform multiple reads
                read_results = []
                for i in range(3):
                    await asyncio.sleep(0.1)  # Small delay between reads
                    
                    # Read from cache
                    cached_data = await self.get(nickname, data_type)
                    
                    # Check expires_at after read
                    cursor = await conn.execute("""
                        SELECT expires_at, accessed_at, access_count 
                        FROM faceit_cache 
                        WHERE nickname = ? AND data_type = ?
                    """, (nickname, data_type))
                    
                    row = await cursor.fetchone()
                    if row:
                        expires_at, accessed_at, access_count = row
                        read_results.append({
                            "read_number": i + 1,
                            "expires_at": expires_at,
                            "accessed_at": accessed_at,
                            "access_count": access_count,
                            "data_retrieved": cached_data is not None
                        })
                
                # Validation results
                expires_at_values = [result["expires_at"] for result in read_results]
                expires_at_unchanged = len(set(expires_at_values)) == 1  # All values should be the same
                
                accessed_at_values = [result["accessed_at"] for result in read_results]
                accessed_at_changed = len(set(accessed_at_values)) > 1  # Should change with each read
                
                access_counts = [result["access_count"] for result in read_results]
                access_count_increasing = all(access_counts[i] < access_counts[i + 1] for i in range(len(access_counts) - 1))
                
                return {
                    "validation_passed": expires_at_unchanged and accessed_at_changed and access_count_increasing,
                    "initial_state": {
                        "expires_at": initial_expires_at,
                        "created_at": initial_created_at,
                        "accessed_at": initial_accessed_at,
                        "access_count": initial_access_count
                    },
                    "read_results": read_results,
                    "analysis": {
                        "expires_at_unchanged": expires_at_unchanged,
                        "accessed_at_changed": accessed_at_changed,
                        "access_count_increasing": access_count_increasing,
                        "expires_at_values": expires_at_values,
                        "unique_expires_at_count": len(set(expires_at_values))
                    }
                }
                
        except Exception as e:
            logger.error(f"TTL validation error: {e}", exc_info=True)
            return {"error": str(e)}
            
    async def validate_timezone_fix(self) -> Dict[str, Any]:
        """
        Validate the timezone fix by testing TTL calculations with different scenarios.
        Returns validation results to confirm active/inactive boundary works correctly.
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            results = []
            now_utc = datetime.now(timezone.utc)
            
            # Test scenarios with different last match dates
            test_scenarios = [
                {
                    "name": "Active player (1 day ago)",
                    "last_match": (now_utc - timedelta(days=1)).isoformat().replace('+00:00', 'Z'),
                    "expected_active": True
                },
                {
                    "name": "Active player (threshold day)",
                    "last_match": (now_utc - timedelta(days=self.activity_threshold)).isoformat().replace('+00:00', 'Z'),
                    "expected_active": True
                },
                {
                    "name": "Inactive player (threshold + 1 day)",
                    "last_match": (now_utc - timedelta(days=self.activity_threshold + 1)).isoformat().replace('+00:00', 'Z'),
                    "expected_active": False
                },
                {
                    "name": "Inactive player (30 days ago)",
                    "last_match": (now_utc - timedelta(days=30)).isoformat().replace('+00:00', 'Z'),
                    "expected_active": False
                },
                {
                    "name": "No last match data",
                    "data": {},
                    "expected_active": False
                }
            ]
            
            for scenario in test_scenarios:
                try:
                    # Create test data
                    if scenario["name"] == "No last match data":
                        test_data = scenario["data"]
                    else:
                        test_data = {
                            "stats": {
                                "last_match": scenario["last_match"]
                            }
                        }
                    
                    # Test TTL calculation
                    ttl_seconds, is_active = await self._calculate_ttl(test_data)
                    expected_active = scenario["expected_active"]
                    
                    # Extract last match date for verification
                    extracted_date = self._extract_last_match_date(test_data)
                    
                    # Calculate days since last match manually for verification
                    if extracted_date:
                        days_since = (now_utc - extracted_date).days
                    else:
                        days_since = None
                    
                    # Verify timezone awareness
                    timezone_info = None
                    if extracted_date:
                        timezone_info = {
                            "is_aware": extracted_date.tzinfo is not None,
                            "timezone": str(extracted_date.tzinfo) if extracted_date.tzinfo else "naive",
                            "utc_offset": extracted_date.utcoffset().total_seconds() if extracted_date.utcoffset() else None
                        }
                    
                    result = {
                        "scenario": scenario["name"],
                        "test_passed": is_active == expected_active,
                        "expected_active": expected_active,
                        "actual_active": is_active,
                        "ttl_seconds": ttl_seconds,
                        "extracted_date": extracted_date.isoformat() if extracted_date else None,
                        "days_since_last_match": days_since,
                        "activity_threshold": self.activity_threshold,
                        "timezone_info": timezone_info
                    }
                    
                    results.append(result)
                    
                    logger.info(f"Timezone validation - {scenario['name']}: "
                              f"expected_active={expected_active}, actual_active={is_active}, "
                              f"days_since={days_since}, test_passed={result['test_passed']}")
                              
                except Exception as scenario_error:
                    results.append({
                        "scenario": scenario["name"],
                        "test_passed": False,
                        "error": str(scenario_error)
                    })
            
            # Overall validation result
            all_tests_passed = all(result.get("test_passed", False) for result in results)
            
            validation_summary = {
                "overall_passed": all_tests_passed,
                "current_time_utc": now_utc.isoformat(),
                "activity_threshold_days": self.activity_threshold,
                "active_player_ttl": self.active_player_ttl,
                "inactive_player_ttl": self.inactive_player_ttl,
                "total_scenarios_tested": len(test_scenarios),
                "passed_scenarios": len([r for r in results if r.get("test_passed", False)]),
                "failed_scenarios": len([r for r in results if not r.get("test_passed", False)]),
                "detailed_results": results
            }
            
            if all_tests_passed:
                logger.info("Timezone fix validation PASSED - All scenarios working correctly")
            else:
                logger.error("Timezone fix validation FAILED - Some scenarios not working correctly")
                
            return validation_summary
            
        except Exception as e:
            logger.error(f"Timezone validation error: {e}", exc_info=True)
            return {"error": str(e), "overall_passed": False}
