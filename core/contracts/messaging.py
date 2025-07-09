#core/contracts/messaging.py
"""Interface para sistema de mensagens/eventos."""
from abc import ABC, abstractmethod
from typing import Callable, Any


class ISystemEventBus(ABC):
    """Interface para o barramento de eventos do sistema."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Inscreve um handler para um tipo de evento."""
        pass

    @abstractmethod
    def publish(self, event_type: str, data: Any) -> None:
        """Publica um evento para todos os seus assinantes."""
        pass
    
    @abstractmethod
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Remove a inscrição de um handler."""
        pass