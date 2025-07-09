#infrastructure/messaging/event_bus.py
"""Barramento de eventos local."""
import logging
from collections import defaultdict
from typing import Callable, Any, List
from core.contracts.messaging import ISystemEventBus

logger = logging.getLogger(__name__)


class LocalEventBus(ISystemEventBus):
    """Implementação simples de um barramento de eventos em memória."""

    __slots__ = ['handlers']

    def __init__(self):
        self.handlers: defaultdict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Inscreve um handler para um tipo de evento."""
        self.handlers[event_type].append(handler)
        logger.debug(f"Handler {handler.__name__} inscrito para o evento '{event_type}'.")

    def publish(self, event_type: str, data: Any) -> None:
        """Publica um evento, acionando todos os handlers inscritos."""
        if event_type in self.handlers:
            logger.debug(f"Publicando evento '{event_type}' com dados: {data}")
            for handler in self.handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(
                        f"Erro ao executar o handler {handler.__name__} para o evento '{event_type}': {e}",
                        exc_info=True
                    )

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Remove um handler de um tipo de evento."""
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            logger.debug(f"Handler {handler.__name__} removido do evento '{event_type}'.")