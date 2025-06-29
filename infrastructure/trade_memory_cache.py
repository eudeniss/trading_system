from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import threading

from domain.entities.trade import Trade
from domain.repositories.trade_cache import ITradeCache

class TradeMemoryCache(ITradeCache):
    """Implementação em memória do cache de trades."""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.cache: Dict[str, deque] = {}
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'additions': 0
        }
    
    def add_trade(self, symbol: str, trade: Trade) -> None:
        """Adiciona trade com thread safety."""
        with self.lock:
            if symbol not in self.cache:
                self.cache[symbol] = deque(maxlen=self.max_size)
            
            self.cache[symbol].append(trade)
            self.stats['additions'] += 1
    
    def get_recent_trades(self, symbol: str, count: int) -> List[Trade]:
        """Retorna últimos N trades de forma eficiente."""
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                return []
            
            self.stats['hits'] += 1
            trades = list(self.cache[symbol])
            return trades[-count:] if count < len(trades) else trades
    
    def get_trades_by_time_window(self, symbol: str, seconds: int) -> List[Trade]:
        """Retorna trades dos últimos N segundos."""
        with self.lock:
            if symbol not in self.cache:
                return []
            
            cutoff_time = datetime.now() - timedelta(seconds=seconds)
            return [t for t in self.cache[symbol] 
                   if t.timestamp > cutoff_time]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        with self.lock:
            total_trades = sum(len(trades) for trades in self.cache.values())
            return {
                **self.stats,
                'total_trades': total_trades,
                'symbols': list(self.cache.keys()),
                'cache_full': any(len(trades) == self.max_size 
                                for trades in self.cache.values())
            }