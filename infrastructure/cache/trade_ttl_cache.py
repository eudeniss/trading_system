from datetime import datetime, timedelta
import threading
from typing import Dict, List, Tuple

from domain.entities.trade import Trade
from domain.repositories.trade_cache import ITradeCache


class TradeTTLCache(ITradeCache):
    """Cache com Time To Live para trades."""
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, List[Tuple[Trade, datetime]]] = {}
        self.lock = threading.RLock()
    
    def add_trade(self, symbol: str, trade: Trade) -> None:
        with self.lock:
            if symbol not in self.cache:
                self.cache[symbol] = []
            
            # Remove trades expirados
            self._cleanup_expired(symbol)
            
            # Adiciona novo trade
            self.cache[symbol].append((trade, datetime.now()))
            
            # Mantém limite de tamanho
            if len(self.cache[symbol]) > self.max_size:
                self.cache[symbol] = self.cache[symbol][-self.max_size:]
    
    def _cleanup_expired(self, symbol: str) -> None:
        """Remove trades expirados."""
        now = datetime.now()
        self.cache[symbol] = [
            (trade, timestamp) for trade, timestamp in self.cache[symbol]
            if now - timestamp < self.ttl
        ]