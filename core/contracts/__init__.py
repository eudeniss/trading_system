"""Contratos (interfaces) do domínio."""

from .cache import ITradeCache
from .messaging import ISystemEventBus
from .providers import IMarketDataProvider
from .repository import ISignalRepository

__all__ = [
    'ITradeCache',
    'ISystemEventBus',
    'IMarketDataProvider',
    'ISignalRepository'
]