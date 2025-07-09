#core/entities/init.py
"""
Entidades do domínio - representam conceitos do negócio.
Todas são imutáveis (frozen=True) para garantir integridade.
"""

from .trade import Trade, TradeSide
from .signal import Signal, SignalSource, SignalLevel
from .book import OrderBook, BookLevel
from .market_data import MarketData, MarketSymbolData

__all__ = [
    'Trade', 'TradeSide',
    'Signal', 'SignalSource', 'SignalLevel',
    'OrderBook', 'BookLevel',
    'MarketData', 'MarketSymbolData'
]