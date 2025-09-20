import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple
from concurrent.futures import Future

from bot.config import Config

logger = logging.getLogger(__name__)

def _validate_config_ranges(max_workers: int, max_queue_size: int, max_retries: int, 
                           task_timeout: int, semaphore_limit: int) -> tuple[int, int, int, int, int]:
    """Validate and clamp config values to safe ranges"""
    workers = max(1, min(32, max_workers))
    queue_size = max(10, min(100_000, max_queue_size))
    retries = max(0, max_retries)
    timeout = max(1, task_timeout)
    semaphore = max(1, semaphore_limit)
    return workers, queue_size, retries, timeout, semaphore

class TaskPriority(Enum):
    """Priority levels for background tasks"""
    HIGH = 1
    NORMAL = 2
    LOW = 3

@dataclass
class BackgroundTask:
    """Represents a background task with priority and retry capabilities"""
    priority: TaskPriority
    function: Callable
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    future: asyncio.Future
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    
    def __lt__(self, other):
        """Enable priority queue ordering"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at

class BackgroundProcessor:
    """Async background processing system with priority queues and retry logic"""
    
    def __init__(self, max_workers: int, max_queue_size: int, max_retries: int):
        # Validate and clamp config values to safe ranges
        validated_workers, validated_queue_size, validated_retries, validated_timeout, validated_semaphore = _validate_config_ranges(
            max_workers, max_queue_size, max_retries, Config.BG_TASK_TIMEOUT, Config.BG_SEMAPHORE_LIMIT
        )
        
        self.max_workers = validated_workers
        self.max_queue_size = validated_queue_size
        self.max_retries = validated_retries
        self.task_timeout = validated_timeout
        
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=validated_queue_size)
        self._workers: list[asyncio.Task] = []
        self._semaphore = asyncio.Semaphore(validated_semaphore)
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self._stats = {
            'processed_tasks': 0,
            'failed_tasks': 0,
            'retried_tasks': 0,
            'queue_size': 0,
            'active_workers': 0,
            'total_processing_time': 0.0,
            'circuit_breaker_failures': 0,
            'last_failure_time': None
        }
        
        # Circuit breaker
        self._circuit_breaker_failures = 0
        self._circuit_breaker_threshold = Config.BG_CIRCUIT_BREAKER_THRESHOLD
        self._circuit_breaker_reset_time = Config.BG_CIRCUIT_BREAKER_RESET_TIME
        self._circuit_breaker_open = False
        self._circuit_breaker_last_failure = None
        
        # Dead letter queue for permanently failed tasks
        self._dead_letter_queue = []
        
    async def start(self) -> None:
        """Start the background processor and worker coroutines"""
        if self._running:
            logger.warning("Background processor is already running")
            return
            
        self._running = True
        self._shutdown_event.clear()
        
        # Create worker tasks
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._workers.append(worker)
            
        self._stats['active_workers'] = len(self._workers)
        logger.info(f"Background processor started with {self.max_workers} workers")
        
    async def stop(self, timeout: float = 30.0) -> None:
        """Gracefully stop the background processor"""
        if not self._running:
            return
            
        logger.info("Stopping background processor...")
        self._running = False
        self._shutdown_event.set()
        
        # Attempt to drain the queue gracefully before cancelling workers
        logger.info(f"Attempting to drain queue (current size: {self._queue.qsize()}) before shutdown...")
        drain_successful = await self.wait_for_empty_queue(timeout)
        
        if drain_successful:
            logger.info("Queue drained successfully - proceeding with clean worker shutdown")
            # Workers should complete naturally since queue is empty and _running is False
            
            # Wait for workers to finish naturally with a shorter timeout since queue is drained
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=5.0  # Shorter timeout since workers should exit cleanly
                )
            except asyncio.TimeoutError:
                logger.warning("Workers didn't exit cleanly after queue drain - forcing cancellation")
                # Cancel workers as fallback
                for worker in self._workers:
                    worker.cancel()
        else:
            logger.warning(f"Failed to drain queue within {timeout}s - falling back to immediate cancellation")
            # Cancel workers immediately as fallback
            for worker in self._workers:
                worker.cancel()
            
            # Wait for workers to finish with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Background processor shutdown timed out after {timeout}s")
            
        # Cancel any remaining tasks in queue
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                if not task.future.done():
                    task.future.set_exception(asyncio.CancelledError("Processor shutdown"))
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
                
        self._workers.clear()
        self._stats['active_workers'] = 0
        logger.info("Background processor stopped")
        
    async def enqueue(self, function: Callable, *args, priority: TaskPriority = TaskPriority.NORMAL, **kwargs) -> asyncio.Future:
        """Enqueue a task for background processing"""
        if not self._running:
            raise RuntimeError("Background processor is not running")
            
        # Check circuit breaker
        if self._is_circuit_breaker_open():
            future = asyncio.get_event_loop().create_future()
            future.set_exception(Exception("Circuit breaker is open - too many recent failures"))
            return future
            
        # Create future for the result
        future = asyncio.get_event_loop().create_future()
        
        # Create background task
        task = BackgroundTask(
            priority=priority,
            function=function,
            args=args,
            kwargs=kwargs,
            future=future
        )
        
        try:
            await self._queue.put(task)
            self._stats['queue_size'] = self._queue.qsize()
            logger.debug(f"Enqueued task with priority {priority.name}")
            return future
        except asyncio.QueueFull:
            future.set_exception(Exception("Background processor queue is full"))
            return future
            
    async def _worker_loop(self, worker_name: str) -> None:
        """Main worker loop that processes tasks from the priority queue"""
        logger.debug(f"Worker {worker_name} started")
        
        while self._running and not self._shutdown_event.is_set():
            try:
                # Get next task with timeout
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                
                # Process the task
                await self._process_task(task, worker_name)
                self._queue.task_done()
                
            except asyncio.TimeoutError:
                # No task available, continue loop
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_name} encountered error: {e}", exc_info=True)
                
        logger.debug(f"Worker {worker_name} stopped")
        
    async def _process_task(self, task: BackgroundTask, worker_name: str) -> None:
        """Process a single background task with retry logic"""
        start_time = time.time()
        
        try:
            async with self._semaphore:  # Limit concurrent operations
                # Set timeout for task execution
                result = await asyncio.wait_for(
                    task.function(*task.args, **task.kwargs),
                    timeout=self.task_timeout
                )
                
                # Task completed successfully
                if not task.future.done():
                    task.future.set_result(result)
                    
                self._stats['processed_tasks'] += 1
                processing_time = time.time() - start_time
                self._stats['total_processing_time'] += processing_time
                
                # Reset circuit breaker on success
                self._circuit_breaker_failures = 0
                self._circuit_breaker_open = False
                
                logger.debug(f"Task completed successfully by {worker_name} in {processing_time:.2f}s")
                
        except asyncio.TimeoutError:
            await self._handle_task_failure(task, f"Task timed out after {self.task_timeout}s", worker_name)
        except asyncio.CancelledError:
            if not task.future.done():
                task.future.set_exception(asyncio.CancelledError("Task was cancelled"))
        except Exception as e:
            await self._handle_task_failure(task, str(e), worker_name)
            
    async def _handle_task_failure(self, task: BackgroundTask, error_msg: str, worker_name: str) -> None:
        """Handle task failure with retry logic and circuit breaker"""
        task.retry_count += 1
        self._stats['failed_tasks'] += 1
        
        # Update circuit breaker
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()
        self._stats['circuit_breaker_failures'] = self._circuit_breaker_failures
        self._stats['last_failure_time'] = self._circuit_breaker_last_failure
        
        if self._circuit_breaker_failures >= self._circuit_breaker_threshold:
            self._circuit_breaker_open = True
            logger.warning(f"Circuit breaker opened after {self._circuit_breaker_failures} failures")
        
        # Retry logic with exponential backoff
        if task.retry_count <= self.max_retries and self._running:
            self._stats['retried_tasks'] += 1
            retry_delay = min(2 ** (task.retry_count - 1), 8)  # Cap at 8 seconds
            
            logger.warning(f"Task failed ({error_msg}), retrying in {retry_delay}s (attempt {task.retry_count}/{self.max_retries})")
            
            # Schedule retry
            await asyncio.sleep(retry_delay)
            if self._running:
                try:
                    await self._queue.put(task)
                except asyncio.QueueFull:
                    self._move_to_dead_letter_queue(task, "Queue full during retry")
        else:
            # Max retries exceeded or processor stopping
            self._move_to_dead_letter_queue(task, f"Max retries exceeded: {error_msg}")
            
    def _move_to_dead_letter_queue(self, task: BackgroundTask, reason: str) -> None:
        """Move permanently failed task to dead letter queue"""
        if not task.future.done():
            task.future.set_exception(Exception(f"Task permanently failed: {reason}"))
            
        self._dead_letter_queue.append({
            'task': task,
            'reason': reason,
            'failed_at': time.time()
        })
        
        # Limit dead letter queue size
        if len(self._dead_letter_queue) > 100:
            self._dead_letter_queue = self._dead_letter_queue[-50:]  # Keep last 50
            
        logger.error(f"Task moved to dead letter queue: {reason}")
        
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open"""
        if not self._circuit_breaker_open:
            return False
            
        # Check if it's time to attempt reset
        if (self._circuit_breaker_last_failure and 
            time.time() - self._circuit_breaker_last_failure > self._circuit_breaker_reset_time):
            logger.info("Attempting to reset circuit breaker")
            self._circuit_breaker_open = False
            self._circuit_breaker_failures = 0
            return False
            
        return True
        
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive processor statistics"""
        stats = self._stats.copy()
        stats.update({
            'queue_size': self._queue.qsize(),
            'is_running': self._running,
            'circuit_breaker_open': self._circuit_breaker_open,
            'dead_letter_queue_size': len(self._dead_letter_queue),
            'average_processing_time': (
                self._stats['total_processing_time'] / max(self._stats['processed_tasks'], 1)
            )
        })
        return stats
        
    def is_healthy(self) -> bool:
        """Check if the processor is in a healthy state"""
        if not self._running:
            return False
            
        # Check if workers are alive
        alive_workers = sum(1 for worker in self._workers if not worker.done())
        if alive_workers == 0:
            return False
            
        # Check circuit breaker
        if self._circuit_breaker_open:
            return False
            
        # Check queue backlog
        if self._queue.qsize() > self.max_queue_size * 0.8:  # 80% full
            return False
            
        return True
        
    async def wait_for_empty_queue(self, timeout: float = 30.0) -> bool:
        """Wait for the queue to be empty"""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

# Global singleton instance
bg_processor: Optional[BackgroundProcessor] = None

def get_background_processor() -> BackgroundProcessor:
    """Get the global background processor instance"""
    global bg_processor
    if bg_processor is None:
        bg_processor = BackgroundProcessor(
            max_workers=Config.BG_MAX_WORKERS,
            max_queue_size=Config.BG_MAX_QUEUE_SIZE,
            max_retries=Config.BG_MAX_RETRIES
        )
    return bg_processor
