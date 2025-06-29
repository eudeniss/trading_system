# infrastructure/data_sources/simple_cache.py
import time
from collections import OrderedDict
import hashlib
import logging

logger = logging.getLogger(__name__)

class SimpleCache:
    """Cache simples e eficiente com TTL (Time To Live)."""
    
    def __init__(self, max_size=1000, ttl=5):
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
        self.hits = 0
        self.misses = 0

    def _make_key(self, *args, **kwargs) -> str:
        """Cria uma chave hash única para os argumentos."""
        # A kwargs são ordenadas por chave para garantir consistência
        sorted_kwargs = sorted(kwargs.items())
        key_string = str(args) + str(sorted_kwargs)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, key: str):
        """Recupera um valor do cache se ele for válido."""
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                self.hits += 1
                self.cache.move_to_end(key)
                return self.cache[key]
            else:
                del self.cache[key]
                del self.timestamps[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, value):
        """Armazena um valor no cache."""
        if len(self.cache) >= self.max_size:
            oldest_key, _ = self.cache.popitem(last=False)
            del self.timestamps[oldest_key]
        
        self.cache[key] = value
        self.timestamps[key] = time.time()
    
    def clear_expired(self):
        """Remove entradas que expiraram."""
        now = time.time()
        expired_keys = [k for k, t in self.timestamps.items() if now - t >= self.ttl]
        
        for key in expired_keys:
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
        
        if expired_keys:
            logger.debug(f"Cache: Removidas {len(expired_keys)} entradas expiradas.")