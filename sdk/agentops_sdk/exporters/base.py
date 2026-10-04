import abc
from typing import List
from agentops_sdk.events import TelemetryEvent

class BaseExporter(abc.ABC):
    """Abstract base class for exporters."""
    
    @abc.abstractmethod
    def export(self, events: List[TelemetryEvent]) -> bool:
        """
        Export a batch of events.
        
        Returns:
            bool: True if successful, False if failed.
        """
        pass
    
    def shutdown(self):
        """Clean up any resources."""
        pass
