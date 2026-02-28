"""
Memory Buffer System for Batched I/O Operations
Reduces file write overhead by batching operations and writing periodically.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PendingWrite:
    """A pending file write operation."""
    file_path: str
    data: Dict[str, Any]
    timestamp: float
    merge_strategy: Optional[Callable] = None  # How to merge with existing data


class MemoryBuffer:
    """
    Batched memory operations for improved performance.
    
    Key features:
    - Batches multiple writes into single I/O operations
    - Configurable flush intervals and thresholds
    - Smart merging for frequently updated files
    - Graceful degradation (immediate writes if buffer full)
    """
    
    def __init__(
        self,
        flush_interval: float = 3.0,  # Flush every 3 seconds
        max_pending: int = 50,        # Or when 50 operations pending
        buffer_timeout: float = 10.0  # Force flush after 10 seconds
    ):
        self.flush_interval = flush_interval
        self.max_pending = max_pending
        self.buffer_timeout = buffer_timeout
        
        self.pending_writes: Dict[str, PendingWrite] = {}
        self.last_flush = time.time()
        self.flush_task: Optional[asyncio.Task] = None
        self.running = False
        
        # Statistics
        self.total_writes = 0
        self.batched_writes = 0
        self.immediate_writes = 0
    
    async def start(self):
        """Start the background flush task."""
        if self.running:
            return
        
        self.running = True
        self.flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Memory buffer started with %ds flush interval", self.flush_interval)
    
    async def stop(self):
        """Stop the buffer and flush all pending operations."""
        self.running = False
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        
        await self.flush_all()
        logger.info("Memory buffer stopped. Stats: %d total, %d batched, %d immediate", 
                   self.total_writes, self.batched_writes, self.immediate_writes)
    
    async def buffer_write(
        self, 
        file_path: str, 
        data: Dict[str, Any], 
        merge_strategy: Optional[Callable] = None,
        immediate: bool = False
    ):
        """
        Buffer a write operation.
        
        Args:
            file_path: Path to write to
            data: Data to write
            merge_strategy: Function to merge with existing buffered data
            immediate: Force immediate write (bypasses buffer)
        """
        self.total_writes += 1
        
        if immediate or len(self.pending_writes) >= self.max_pending:
            await self._write_immediate(file_path, data)
            self.immediate_writes += 1
            return
        
        # Buffer the operation
        if file_path in self.pending_writes and merge_strategy:
            # Merge with existing pending write
            existing = self.pending_writes[file_path]
            merged_data = merge_strategy(existing.data, data)
            self.pending_writes[file_path] = PendingWrite(
                file_path=file_path,
                data=merged_data,
                timestamp=time.time(),
                merge_strategy=merge_strategy
            )
        else:
            # New pending write
            self.pending_writes[file_path] = PendingWrite(
                file_path=file_path,
                data=data,
                timestamp=time.time(),
                merge_strategy=merge_strategy
            )
        
        logger.debug(f"Buffered write to {file_path} ({len(self.pending_writes)} pending)")
    
    async def flush_all(self):
        """Flush all pending writes immediately."""
        if not self.pending_writes:
            return
        
        pending_count = len(self.pending_writes)
        start_time = time.time()
        
        try:
            # Execute all pending writes
            for pending in self.pending_writes.values():
                await self._write_immediate(pending.file_path, pending.data)
            
            self.batched_writes += pending_count
            self.pending_writes.clear()
            self.last_flush = time.time()
            
            duration_ms = (time.time() - start_time) * 1000
            logger.debug(f"Flushed {pending_count} writes in {duration_ms:.1f}ms")
            
        except Exception as e:
            logger.error(f"Error during buffer flush: {e}")
            # Don't clear pending writes on error - they'll be retried
    
    def should_flush(self) -> bool:
        """Check if buffer should be flushed based on time/size thresholds."""
        if not self.pending_writes:
            return False
        
        now = time.time()
        time_since_flush = now - self.last_flush
        
        # Check for any writes that are too old
        oldest_write = min(w.timestamp for w in self.pending_writes.values())
        oldest_age = now - oldest_write
        
        return (
            time_since_flush >= self.flush_interval or
            len(self.pending_writes) >= self.max_pending or
            oldest_age >= self.buffer_timeout
        )
    
    async def _flush_loop(self):
        """Background task that flushes buffer periodically."""
        try:
            while self.running:
                await asyncio.sleep(1.0)  # Check every second
                
                if self.should_flush():
                    await self.flush_all()
                    
        except asyncio.CancelledError:
            logger.debug("Flush loop cancelled")
        except Exception as e:
            logger.error(f"Error in flush loop: {e}")
    
    async def _write_immediate(self, file_path: str, data: Dict[str, Any]):
        """Write data immediately to file using atomic temp-file rename (audit I-10)."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            tmp_path = file_path + ".tmp"
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)
                os.replace(tmp_path, file_path)  # atomic on POSIX and Win32
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.debug(f"Wrote to {file_path}")

        except Exception as e:
            logger.error(f"Failed to write {file_path}: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        return {
            "total_writes": self.total_writes,
            "batched_writes": self.batched_writes,
            "immediate_writes": self.immediate_writes,
            "pending_count": len(self.pending_writes),
            "batch_efficiency": (self.batched_writes / max(1, self.total_writes)) * 100,
            "running": self.running
        }


# Common merge strategies
def merge_dict_update(existing: Dict, new: Dict) -> Dict:
    """Simple dict update merge strategy."""
    result = existing.copy()
    result.update(new)
    return result


def merge_emotion_state(existing: Dict, new: Dict) -> Dict:
    """Smart merge for emotional state - blend values instead of overwrite."""
    result = existing.copy()
    
    for key, new_value in new.items():
        if key in existing and isinstance(existing[key], (int, float)) and isinstance(new_value, (int, float)):
            # Blend emotional values (weighted average favoring new)
            result[key] = existing[key] * 0.3 + new_value * 0.7
        else:
            result[key] = new_value
    
    return result


def merge_append_list(existing: Dict, new: Dict) -> Dict:
    """Merge strategy that appends to lists instead of replacing."""
    result = existing.copy()
    
    for key, new_value in new.items():
        if key in existing and isinstance(existing[key], list) and isinstance(new_value, list):
            result[key] = existing[key] + new_value
        else:
            result[key] = new_value
    
    return result