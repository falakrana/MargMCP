import threading
import queue
import time
import logging
from typing import List, Optional
from agentops_sdk.events import TelemetryEvent
from agentops_sdk.exporters.base import BaseExporter
from agentops_sdk.config import AgentOpsConfig

logger = logging.getLogger(__name__)

class AsyncBatchProcessor:
    """Processes telemetry events in a background thread."""
    
    def __init__(self, exporter: BaseExporter, config: AgentOpsConfig):
        self.exporter = exporter
        self.config = config
        self.queue = queue.Queue(maxsize=config.max_queue_size)
        
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        
    def add_event(self, event: TelemetryEvent):
        """Add an event to the queue safely (non-blocking)."""
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            logger.debug("AgentOps telemetry queue full, dropping event.")
            
    def _worker(self):
        batch: List[TelemetryEvent] = []
        last_flush_time = time.time()
        
        while True:
            try:
                # Wait for an event with a timeout
                timeout = max(0.1, self.config.flush_interval_seconds - (time.time() - last_flush_time))
                event = self.queue.get(timeout=timeout)
                batch.append(event)
            except queue.Empty:
                pass
                
            current_time = time.time()
            time_to_flush = (current_time - last_flush_time) >= self.config.flush_interval_seconds
            size_to_flush = len(batch) >= self.config.max_batch_size
            stopping = self._stop_event.is_set()
            
            if batch and (time_to_flush or size_to_flush or stopping):
                success = self.exporter.export(batch)
                if not success:
                    pass 
                batch = []
                last_flush_time = current_time
                
            if stopping and self.queue.empty():
                # Flush one last time if anything was left, then exit
                if batch:
                    self.exporter.export(batch)
                break
                
    def shutdown(self, timeout: float = 5.0):
        """Stop the background worker and flush remaining events."""
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self.exporter.shutdown()
