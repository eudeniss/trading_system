#application/services/risk/circuit_breaker.py
"""Sistema de circuit breakers para proteção."""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from .types import CircuitBreakerState

logger = logging.getLogger(__name__)


class CircuitBreakerSystem:
    """Gerencia circuit breakers do sistema."""
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Configura breakers
        self.cooldown = config.get('circuit_breaker_cooldown', 300)
        
        self.breakers: Dict[str, CircuitBreakerState] = {
            'frequency': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': self.cooldown
            },
            'quality': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': self.cooldown
            },
            'drawdown': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': self.cooldown
            },
            'consecutive_losses': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': self.cooldown
            },
            'emergency': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': self.cooldown
            },
            'exposure': {
                'active': False, 
                'triggered_at': None, 
                'reason': '', 
                'cooldown_seconds': 60  # Menor cooldown
            }
        }
        
        logger.info(f"CircuitBreakerSystem inicializado - cooldown padrão: {self.cooldown}s")
    
    def check_all(self) -> Dict:
        """Verifica estado de todos os breakers."""
        result = {
            'all_clear': True,
            'triggered': []
        }
        
        now = datetime.now()
        
        for name, state in self.breakers.items():
            if state['active']:
                if state['triggered_at']:
                    elapsed = (now - state['triggered_at']).seconds
                    if elapsed < state['cooldown_seconds']:
                        result['all_clear'] = False
                        remaining = state['cooldown_seconds'] - elapsed
                        result['triggered'].append(
                            f"{name}: {state['reason']} ({remaining}s restantes)"
                        )
                    else:
                        # Cooldown expirado, reset
                        self._reset_breaker(name)
                        logger.info(f"Circuit breaker {name} resetado após cooldown")
                else:
                    result['all_clear'] = False
                    result['triggered'].append(f"{name}: {state['reason']}")
        
        return result
    
    def trigger(self, name: str, reason: str):
        """Ativa um circuit breaker."""
        if name not in self.breakers:
            logger.warning(f"Circuit breaker desconhecido: {name}")
            return
        
        if not self.breakers[name]['active']:
            self.breakers[name]['active'] = True
            self.breakers[name]['triggered_at'] = datetime.now()
            self.breakers[name]['reason'] = reason
            logger.warning(f"⚡ Circuit breaker {name} acionado: {reason}")
    
    def reset(self, name: str):
        """Reseta um circuit breaker manualmente."""
        if name in self.breakers:
            self._reset_breaker(name)
            logger.info(f"Circuit breaker {name} resetado manualmente")
    
    def reset_all(self):
        """Reseta todos os circuit breakers."""
        for name in self.breakers:
            self._reset_breaker(name)
        logger.info("Todos os circuit breakers foram resetados")
    
    def _reset_breaker(self, name: str):
        """Reseta estado de um breaker."""
        self.breakers[name]['active'] = False
        self.breakers[name]['triggered_at'] = None
        self.breakers[name]['reason'] = ''
    
    def get_active_breakers(self) -> List[str]:
        """Retorna lista de breakers ativos."""
        return [name for name, state in self.breakers.items() if state['active']]
    
    def get_status(self) -> Dict:
        """Retorna status detalhado dos breakers."""
        now = datetime.now()
        status = {}
        
        for name, state in self.breakers.items():
            if state['active'] and state['triggered_at']:
                elapsed = (now - state['triggered_at']).seconds
                remaining = max(0, state['cooldown_seconds'] - elapsed)
                status[name] = {
                    'active': True,
                    'reason': state['reason'],
                    'remaining_seconds': remaining
                }
            else:
                status[name] = {
                    'active': state['active'],
                    'reason': state['reason'] if state['active'] else None,
                    'remaining_seconds': 0
                }
        
        return status
    
    def update_from_metrics(self, metrics: Dict):
        """Atualiza breakers baseado em métricas."""
        # Consecutive losses
        if metrics.get('consecutive_losses', 0) >= 5:
            self.trigger('consecutive_losses', f"{metrics['consecutive_losses']} perdas consecutivas")
        
        # Drawdown
        if metrics.get('current_drawdown', 0) >= 2.0:
            self.trigger('drawdown', f"Drawdown {metrics['current_drawdown']:.1f}%")
        
        # Emergency stop
        if metrics.get('daily_pnl', 0) <= -1000:
            self.trigger('emergency', f"PnL diário: R${metrics['daily_pnl']:.2f}")