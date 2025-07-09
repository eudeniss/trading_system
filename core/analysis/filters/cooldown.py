#core/analysis/filters/cooldown.py
"""Sistema de cooldown para evitar sinais repetitivos."""
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PatternCooldown:
    """Sistema de cooldown para evitar sinais repetitivos do mesmo tipo."""
    
    __slots__ = ['cooldown_seconds', 'last_pattern_time', 'blocked_count']
    
    def __init__(self, cooldown_seconds: Dict[str, int]):
        self.cooldown_seconds = cooldown_seconds
        self.last_pattern_time: Dict[str, datetime] = {}
        self.blocked_count: Dict[str, int] = {}
    
    def can_emit_pattern(self, pattern: str, symbol: str) -> bool:
        """Verifica se pode emitir o padrão baseado no cooldown."""
        key = f"{symbol}_{pattern}"
        
        if key not in self.last_pattern_time:
            self.last_pattern_time[key] = datetime.now()
            return True
        
        cooldown = self.cooldown_seconds.get(pattern, self.cooldown_seconds.get('default', 30))
        elapsed = (datetime.now() - self.last_pattern_time[key]).seconds
        
        if elapsed >= cooldown:
            self.last_pattern_time[key] = datetime.now()
            return True
        
        # Conta bloqueios para estatísticas
        self.blocked_count[key] = self.blocked_count.get(key, 0) + 1
        
        # Log periódico de bloqueios
        if self.blocked_count[key] % 10 == 0:
            remaining = cooldown - elapsed
            logger.debug(f"Padrão {pattern} em {symbol} bloqueado ({self.blocked_count[key]}x). Aguarde {remaining}s")
            
        return False
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas de bloqueios."""
        total_blocked = sum(self.blocked_count.values())
        return {
            'total_blocked': total_blocked,
            'by_pattern': dict(self.blocked_count),
            'active_cooldowns': len(self.last_pattern_time)
        }