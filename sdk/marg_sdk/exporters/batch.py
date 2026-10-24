import threading
import queue
import time
import logging
from typing import List, Optional
from marg_sdk.events import TelemetryEvent
from marg_sdk.exporters.base import BaseExporter
from marg_sdk.config import MargConfig, AgentOpsConfig

logger = logging.getLogger(__name__)

class AsyncBatchProcessor:
    """Processes telemetry events in a background thread."""
    
    def __init__(self, exporter: BaseExporter, config: MargConfig):
        self.exporter = exporter
        self.config = config
        self.queue = queue.Queue(maxsize=config.max_queue_size)
        self._dropped_events_count = 0
        self._count_lock = threading.Lock()
        
        self._stop_event = threading.Event()
        self._flush_trigger = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        
    @property
    def dropped_events_count(self) -> int:
        with self._count_lock:
            return self._dropped_events_count

    def add_event(self, event: TelemetryEvent):
        """Add an event to the queue safely (non-blocking)."""
        try:
            self.queue.put_nowait(event)
            if self.queue.qsize() >= self.config.max_batch_size:
                self._flush_trigger.set()
        except queue.Full:
            with self._count_lock:
                self._dropped_events_count += 1
            logger.debug("AgentOps telemetry queue full, dropping event.")

    def _drain_batch(self) -> List[TelemetryEvent]:
        batch: List[TelemetryEvent] = []
        while len(batch) < self.config.max_batch_size:
            try:
                batch.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _worker(self):
        while True:
            self._flush_trigger.wait(timeout=self.config.flush_interval_seconds)
            self._flush_trigger.clear()
            
            while True:
                batch = self._drain_batch()
                if not batch:
                    break
                self.exporter.export(batch)
                
            if self._stop_event.is_set():
                break

        # Flush any remaining events on shutdown
        while not self.queue.empty():
            batch = self._drain_batch()
            if not batch:
                break
            self.exporter.export(batch)
                
    def shutdown(self, timeout: float = 5.0):
        """Stop the background worker and flush remaining events."""
        self._stop_event.set()
        self._flush_trigger.set()
        self._thread.join(timeout=timeout)
        self.exporter.shutdown()
