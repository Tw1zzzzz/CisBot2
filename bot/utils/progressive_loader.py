"""
Progressive Loading utility for CIS FINDER Bot
Handles progressive display of profiles with ELO data loading in background
Создано организацией Twizz_Project
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Callable, Tuple, Set
from concurrent.futures import Future
import weakref

from telegram import Bot
from telegram.error import BadRequest, TimedOut

from bot.config import Config
from bot.utils.background_processor import get_background_processor, TaskPriority
from bot.utils.faceit_analyzer import FaceitAnalyzer

logger = logging.getLogger(__name__)

class LoadingState(Enum):
    """States for progressive loading messages"""
    PENDING = "pending"
    LOADING = "loading"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class ProgressiveMessage:
    """Represents a message that needs progressive ELO updates"""
    chat_id: int
    message_id: int
    is_media: bool
    is_photo: bool
    user_id: int
    profile_type: str  # 'search', 'profile', 'teammates'
    timestamp: float = field(default_factory=time.time)
    state: LoadingState = LoadingState.PENDING
    context_id: Optional[str] = None  # For race condition prevention
    retry_count: int = 0

class ProgressiveLoader:
    """Main progressive loading utility class"""
    
    def __init__(self, bot: Bot = None, faceit_analyzer: FaceitAnalyzer = None):
        self.bot = bot
        self.faceit_analyzer = faceit_analyzer
        
        # Message tracking
        self._pending_messages: Dict[str, ProgressiveMessage] = {}
        self._lock = asyncio.Lock()
        
        # Context tracking for race condition prevention
        self._active_contexts: Dict[int, str] = {}  # user_id -> current_context_id
        self._context_lock = asyncio.Lock()
        
        # Configuration from Config
        self.search_timeout = getattr(Config, 'PROGRESSIVE_SEARCH_TIMEOUT', 8)
        self.profile_timeout = getattr(Config, 'PROGRESSIVE_PROFILE_TIMEOUT', 10)
        self.teammates_timeout = getattr(Config, 'PROGRESSIVE_TEAMMATES_TIMEOUT', 6)
        self.message_retention = getattr(Config, 'PROGRESSIVE_MESSAGE_RETENTION', 3600)
        self.cleanup_interval = getattr(Config, 'PROGRESSIVE_CLEANUP_INTERVAL', 300)
        self.context_cleanup_interval = getattr(Config, 'PROGRESSIVE_CONTEXT_CLEANUP_INTERVAL', 600)
        self.max_concurrent_updates = getattr(Config, 'PROGRESSIVE_MAX_CONCURRENT_UPDATES', 50)
        self.retry_attempts = getattr(Config, 'PROGRESSIVE_RETRY_ATTEMPTS', 2)
        self.update_debounce = getattr(Config, 'PROGRESSIVE_UPDATE_DEBOUNCE', 100) / 1000.0  # Convert to seconds
        
        # UI Configuration
        self.loading_emoji = getattr(Config, 'PROGRESSIVE_LOADING_EMOJI', '⏳')
        self.elo_loading_text = getattr(Config, 'PROGRESSIVE_ELO_LOADING_TEXT', 'загружается...')
        
        # Statistics
        self._stats = {
            'messages_registered': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'timeout_updates': 0,
            'race_condition_prevented': 0,
            'context_mismatches': 0,
            'message_not_found_errors': 0,
            'total_update_time': 0.0
        }
        
        # Cleanup tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._context_cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self) -> None:
        """Start the progressive loader and cleanup tasks"""
        if self._running:
            logger.warning("Progressive loader is already running")
            return
            
        self._running = True
        
        # Start cleanup tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._context_cleanup_task = asyncio.create_task(self._context_cleanup_loop())
        
        logger.info("Progressive loader started")
        
    async def stop(self) -> None:
        """Stop the progressive loader and cleanup tasks"""
        if not self._running:
            return
            
        logger.info("Stopping progressive loader...")
        self._running = False
        
        # Cancel cleanup tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        if self._context_cleanup_task:
            self._context_cleanup_task.cancel()
            try:
                await self._context_cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all pending updates
        await self.cancel_pending_updates()
        
        logger.info("Progressive loader stopped")
        
    def register_message(self, chat_id: int, message_id: int, is_media: bool, is_photo: bool,
                        user_id: int, profile_type: str, context_id: Optional[str] = None) -> str:
        """Register a message for progressive ELO updates"""
        message_key = f"{chat_id}_{message_id}"
        
        progressive_message = ProgressiveMessage(
            chat_id=chat_id,
            message_id=message_id,
            is_media=is_media,
            is_photo=is_photo,
            user_id=user_id,
            profile_type=profile_type,
            context_id=context_id
        )
        
        self._pending_messages[message_key] = progressive_message
        self._stats['messages_registered'] += 1
        
        logger.debug(f"Registered message {message_key} for progressive loading (type: {profile_type})")
        return message_key
        
    async def update_message_with_elo(self, message_key: str, new_text: str, 
                                     reply_markup=None) -> bool:
        """Update a message with ELO data"""
        if not self.bot:
            logger.error("Bot instance not available for message updates")
            return False
            
        async with self._lock:
            if message_key not in self._pending_messages:
                logger.debug(f"Message {message_key} not found in pending messages")
                return False
                
            message = self._pending_messages[message_key]
            
        # Validate message context to prevent race conditions
        if not await self._validate_message_context(message):
            self._stats['race_condition_prevented'] += 1
            logger.debug(f"Race condition prevented for message {message_key}")
            return False
            
        message.state = LoadingState.LOADING
        start_time = time.time()
        
        try:
            if message.is_media:
                # For media messages, update caption
                if message.is_photo:
                    await self.bot.edit_message_caption(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        caption=new_text[:1020],  # Telegram caption limit
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    # For video messages
                    await self.bot.edit_message_caption(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        caption=new_text[:1020],  # Telegram caption limit
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            else:
                # For text messages
                await self.bot.edit_message_text(
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    text=new_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
            message.state = LoadingState.COMPLETED
            self._stats['successful_updates'] += 1
            
            update_time = time.time() - start_time
            self._stats['total_update_time'] += update_time
            
            # Clean up completed message
            await self._cleanup_message(message_key)
            
            logger.debug(f"Successfully updated message {message_key} in {update_time:.2f}s")
            return True
            
        except BadRequest as e:
            if "message not found" in str(e).lower() or "message to edit not found" in str(e).lower():
                self._stats['message_not_found_errors'] += 1
                logger.debug(f"Message {message_key} was deleted or not found")
                await self._cleanup_message(message_key)
                return False
            else:
                logger.error(f"Bad request updating message {message_key}: {e}")
                return await self._handle_update_failure(message_key, str(e))
        except TimedOut:
            logger.warning(f"Timeout updating message {message_key}")
            return await self._handle_update_failure(message_key, "Telegram API timeout")
        except Exception as e:
            logger.error(f"Error updating message {message_key}: {e}", exc_info=True)
            return await self._handle_update_failure(message_key, str(e))
            
    async def schedule_elo_update(self, message_key: str, faceit_data: Dict[str, Any],
                                 format_callback: Callable, priority: TaskPriority = TaskPriority.NORMAL) -> bool:
        """Schedule ELO data fetching and message update"""
        if not self._running:
            logger.warning("Progressive loader not running, cannot schedule update")
            return False
            
        # Get background processor
        bg_processor = get_background_processor()
        if not bg_processor or not bg_processor.is_healthy():
            logger.warning("Background processor not available or unhealthy")
            return False
            
        try:
            # Schedule the ELO update task
            future = await bg_processor.enqueue(
                self._perform_elo_update,
                message_key, faceit_data, format_callback, priority,
                priority=priority
            )
            
            # Don't await the future here - let it run in background
            logger.debug(f"Scheduled ELO update for message {message_key} with priority {priority.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule ELO update for {message_key}: {e}")
            return False
            
    async def _perform_elo_update(self, message_key: str, faceit_data: Dict[str, Any],
                                 format_callback: Callable, priority: TaskPriority) -> None:
        """Perform the actual ELO data fetching and message update"""
        try:
            if not self.faceit_analyzer:
                logger.error("FaceitAnalyzer not available for ELO updates")
                return
                
            # Get the message info
            async with self._lock:
                if message_key not in self._pending_messages:
                    logger.debug(f"Message {message_key} no longer tracked")
                    return
                message = self._pending_messages[message_key]
                
            # Determine timeout based on profile type
            timeout = self._get_timeout_for_profile_type(message.profile_type)
            
            # Fetch ELO data with timeout
            try:
                nickname = faceit_data.get('faceit_nickname')
                if not nickname:
                    logger.warning(f"No Faceit nickname available for message {message_key}")
                    return
                    
                # Use provided priority for user requests
                elo_future = await self.faceit_analyzer.get_elo_stats_by_nickname_priority(nickname, priority)
                elo_data = await asyncio.wait_for(elo_future, timeout=timeout)
                
                if elo_data:
                    # Update faceit_data with ELO information
                    faceit_data.update(elo_data)
                    
                    # Format new text with ELO data
                    new_text, reply_markup = await format_callback(faceit_data, include_elo=True)
                    
                    # Update the message
                    success = await self.update_message_with_elo(message_key, new_text, reply_markup)
                    if success:
                        logger.debug(f"ELO update completed for message {message_key}")
                    else:
                        logger.warning(f"Failed to update message {message_key} with ELO data")
                else:
                    logger.warning(f"No ELO data received for nickname {nickname}")
                    
            except asyncio.TimeoutError:
                self._stats['timeout_updates'] += 1
                logger.warning(f"ELO fetch timeout for message {message_key} after {timeout}s")
                await self._handle_update_timeout(message_key)
                
        except Exception as e:
            logger.error(f"Error performing ELO update for {message_key}: {e}", exc_info=True)
            await self._handle_update_failure(message_key, str(e))
            
    async def batch_elo_updates(self, message_keys: list[str], faceit_data_list: list[Dict[str, Any]],
                               format_callback: Callable) -> int:
        """Handle batch ELO updates for multiple messages"""
        if not message_keys or len(message_keys) != len(faceit_data_list):
            logger.error("Invalid batch update parameters")
            return 0
            
        successful_updates = 0
        
        # Create tasks for all updates
        update_tasks = []
        for message_key, faceit_data in zip(message_keys, faceit_data_list):
            task = asyncio.create_task(
                self._perform_elo_update(message_key, faceit_data, format_callback)
            )
            update_tasks.append(task)
            
        # Wait for all updates with timeout
        try:
            results = await asyncio.gather(*update_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Batch update failed for message {message_keys[i]}: {result}")
                else:
                    successful_updates += 1
                    
        except Exception as e:
            logger.error(f"Batch ELO update failed: {e}")
            
        logger.info(f"Batch ELO update completed: {successful_updates}/{len(message_keys)} successful")
        return successful_updates
        
    async def cancel_pending_updates(self, user_id: Optional[int] = None) -> int:
        """Cancel pending updates, optionally for a specific user"""
        cancelled_count = 0
        
        async with self._lock:
            messages_to_remove = []
            
            for message_key, message in self._pending_messages.items():
                if user_id is None or message.user_id == user_id:
                    message.state = LoadingState.FAILED
                    messages_to_remove.append(message_key)
                    cancelled_count += 1
                    
            for message_key in messages_to_remove:
                del self._pending_messages[message_key]
                
        if cancelled_count > 0:
            logger.debug(f"Cancelled {cancelled_count} pending updates" + 
                        (f" for user {user_id}" if user_id else ""))
                        
        return cancelled_count
        
    async def _validate_message_context(self, message: ProgressiveMessage) -> bool:
        """Validate that message update matches current user context"""
        if not message.context_id:
            return True  # No context tracking, allow update
            
        async with self._context_lock:
            current_context = self._active_contexts.get(message.user_id)
            
            if current_context != message.context_id:
                self._stats['context_mismatches'] += 1
                logger.debug(f"Context mismatch for user {message.user_id}: "
                           f"message context {message.context_id}, current context {current_context}")
                return False
                
        return True
        
    async def set_user_context(self, user_id: int, context_id: str) -> None:
        """Set current context for a user to prevent race conditions"""
        async with self._context_lock:
            self._active_contexts[user_id] = context_id
            
        logger.debug(f"Set context {context_id} for user {user_id}")
        
    async def clear_user_context(self, user_id: int) -> None:
        """Clear context for a user"""
        async with self._context_lock:
            if user_id in self._active_contexts:
                del self._active_contexts[user_id]
                
        logger.debug(f"Cleared context for user {user_id}")
        
    async def _handle_update_failure(self, message_key: str, error_msg: str) -> bool:
        """Handle update failure with retry logic"""
        async with self._lock:
            if message_key not in self._pending_messages:
                return False
                
            message = self._pending_messages[message_key]
            message.retry_count += 1
            
            # Check if we should retry
            if message.retry_count <= self.retry_attempts:
                logger.debug(f"Retrying update for message {message_key} "
                           f"(attempt {message.retry_count}/{self.retry_attempts})")
                message.state = LoadingState.PENDING
                return False  # Will be retried
            else:
                # Max retries exceeded
                message.state = LoadingState.FAILED
                self._stats['failed_updates'] += 1
                logger.warning(f"Message update failed permanently for {message_key}: {error_msg}")
                
                # Clean up failed message
                del self._pending_messages[message_key]
                return False
                
    async def _handle_update_timeout(self, message_key: str) -> None:
        """Handle update timeout"""
        async with self._lock:
            if message_key in self._pending_messages:
                message = self._pending_messages[message_key]
                message.state = LoadingState.TIMEOUT
                
                # Keep basic profile display, clean up tracking
                del self._pending_messages[message_key]
                
        logger.debug(f"Message {message_key} update timed out - keeping basic display")
        
    def _get_timeout_for_profile_type(self, profile_type: str) -> float:
        """Get appropriate timeout for profile type"""
        timeout_map = {
            'search': self.search_timeout,
            'profile': self.profile_timeout,
            'teammates': self.teammates_timeout
        }
        return timeout_map.get(profile_type, self.profile_timeout)
        
    async def _cleanup_message(self, message_key: str) -> None:
        """Clean up a specific message from tracking"""
        async with self._lock:
            if message_key in self._pending_messages:
                del self._pending_messages[message_key]
                
    async def cleanup_expired_messages(self) -> int:
        """Clean up expired message references"""
        current_time = time.time()
        expired_count = 0
        
        async with self._lock:
            expired_keys = []
            
            for message_key, message in self._pending_messages.items():
                if current_time - message.timestamp > self.message_retention:
                    expired_keys.append(message_key)
                    expired_count += 1
                    
            for key in expired_keys:
                del self._pending_messages[key]
                
        if expired_count > 0:
            logger.debug(f"Cleaned up {expired_count} expired messages")
            
        return expired_count
        
    async def cleanup_stale_contexts(self) -> int:
        """Clean up stale user contexts"""
        # Context cleanup logic - remove very old contexts
        current_time = time.time()
        cleanup_count = 0
        
        async with self._context_lock:
            # For now, keep contexts indefinitely unless explicitly cleared
            # Future enhancement: add timestamp tracking for contexts
            pass
            
        return cleanup_count
        
    async def _cleanup_loop(self) -> None:
        """Background cleanup task for expired messages"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if self._running:
                    await self.cleanup_expired_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                
    async def _context_cleanup_loop(self) -> None:
        """Background cleanup task for stale contexts"""
        while self._running:
            try:
                await asyncio.sleep(self.context_cleanup_interval)
                if self._running:
                    await self.cleanup_stale_contexts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in context cleanup loop: {e}")
                
    def format_with_loading_placeholder(self, text: str, field_name: str = "ELO") -> str:
        """Format text with loading placeholder for a specific field"""
        loading_text = f"{self.loading_emoji} {self.elo_loading_text}"
        if "ELO" in field_name.upper():
            return text.replace("🎯 ELO Faceit: N/A", f"🎯 ELO Faceit: {loading_text}")
        return text
        
    def extract_message_info(self, message) -> Tuple[int, int, bool, bool]:
        """Extract message info from Telegram Message object"""
        chat_id = message.chat_id
        message_id = message.message_id
        is_media = bool(message.photo or message.video or message.document)
        is_photo = bool(message.photo)
        
        return chat_id, message_id, is_media, is_photo
        
    def get_message_info(self, message_key: str) -> Optional[ProgressiveMessage]:
        """Get message information by key"""
        return self._pending_messages.get(message_key)
        
    def log_progressive_metrics(self) -> None:
        """Log progressive loading performance metrics"""
        stats = self._stats.copy()
        stats.update({
            'pending_messages_count': len(self._pending_messages),
            'active_contexts_count': len(self._active_contexts),
            'average_update_time': (
                stats['total_update_time'] / max(stats['successful_updates'], 1)
            )
        })
        
        logger.info(f"Progressive loading metrics: {stats}")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive progressive loading statistics"""
        stats = self._stats.copy()
        stats.update({
            'pending_messages_count': len(self._pending_messages),
            'active_contexts_count': len(self._active_contexts),
            'is_running': self._running,
            'average_update_time': (
                stats['total_update_time'] / max(stats['successful_updates'], 1)
            )
        })
        return stats
        
    def is_healthy(self) -> bool:
        """Check if progressive loader is healthy"""
        if not self._running:
            return False
            
        # Check if we have too many pending messages
        if len(self._pending_messages) > self.max_concurrent_updates:
            return False
            
        # Check cleanup tasks are running
        if self._cleanup_task and self._cleanup_task.done():
            return False
            
        if self._context_cleanup_task and self._context_cleanup_task.done():
            return False
            
        return True

# Global singleton instance
_progressive_loader: Optional[ProgressiveLoader] = None

def get_progressive_loader() -> Optional[ProgressiveLoader]:
    """Get the global progressive loader instance"""
    global _progressive_loader
    return _progressive_loader

def initialize_progressive_loader(bot: Bot, faceit_analyzer: FaceitAnalyzer) -> ProgressiveLoader:
    """Initialize the global progressive loader instance"""
    global _progressive_loader
    if _progressive_loader is None:
        _progressive_loader = ProgressiveLoader(bot=bot, faceit_analyzer=faceit_analyzer)
    return _progressive_loader
