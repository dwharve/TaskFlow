import threading
import queue
import logging
from typing import Dict, Set, Callable, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Message:
    """Message passed through the pub/sub system"""
    topic: str
    data: Any
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class PubSub:
    """Thread-safe in-memory publish/subscribe system"""
    
    def __init__(self):
        self._subscribers: Dict[str, Set[queue.Queue]] = {}
        self._lock = threading.RLock()
        
    def subscribe(self, topic: str) -> queue.Queue:
        """Subscribe to a topic
        
        Args:
            topic: Topic to subscribe to
            
        Returns:
            Queue that will receive messages for this topic
        """
        message_queue = queue.Queue()
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = set()
            self._subscribers[topic].add(message_queue)
        logger.debug(f"New subscription to topic {topic}")
        return message_queue
    
    def unsubscribe(self, topic: str, message_queue: queue.Queue):
        """Unsubscribe from a topic
        
        Args:
            topic: Topic to unsubscribe from
            message_queue: Queue to unsubscribe
        """
        with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(message_queue)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
        logger.debug(f"Unsubscribed from topic {topic}")
    
    def publish(self, topic: str, data: Any):
        """Publish a message to a topic
        
        Args:
            topic: Topic to publish to
            data: Data to publish
        """
        message = Message(topic=topic, data=data)
        with self._lock:
            if topic in self._subscribers:
                dead_queues = set()
                for message_queue in self._subscribers[topic]:
                    try:
                        message_queue.put_nowait(message)
                    except queue.Full:
                        dead_queues.add(message_queue)
                        logger.warning(f"Queue full for topic {topic}, dropping subscriber")
                
                # Clean up any dead queues
                for dead_queue in dead_queues:
                    self.unsubscribe(topic, dead_queue)
                    
        logger.debug(f"Published message to topic {topic}")

# Global pub/sub instance
pubsub = PubSub() 