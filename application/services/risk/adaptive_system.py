# application/services/risk/adaptive_system.py
"""Sistema adaptativo de regime para risk management - FASE 3.2."""
from typing import Dict, Any
from datetime import datetime
import logging

from core.analysis.regime.types import MarketRegime
from .types import RiskLevel

logger = logging.getLogger(__name__)


class AdaptiveRiskSystem:
    """
    Gerencia adaptação dinâmica de parâmetros baseada em regime de mercado.
    FASE 3.2: Sistema de risco adaptativo por regime.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Limites base
        self.base_max_signals_per_minute = config.get('max_signals_per_minute', 10)
        self.base_max_signals_per_hour = config.get('max_signals_per_hour', 100)
        self.base_max_confluence_per_hour = config.get('max_confluence_per_hour', 20)
        self.base_max_concurrent_signals = config.get('max_concurrent_signals', 5)
        self.base_signal_timeout = config.get('signal_timeout', 60)
        self.base_quality_threshold = config.get('signal_quality_threshold', 0.35)
        
        # Limites atuais (adaptados)
        self.current_limits = self._copy_base_limits()
        
        # Regime atual
        self.current_market_regime = {
            'WDO': MarketRegime.RANGING,
            'DOL': MarketRegime.RANGING
        }
        
        # Fatores de ajuste
        self.regime_adjustment_factors = {}
        self._calculate_regime_adjustments()
        
        logger.info(f"AdaptiveRiskSystem inicializado com limites base")
    
    def _copy_base_limits(self) -> Dict[str, Any]:
        """Copia limites base para limites atuais."""
        return {
            'max_signals_per_minute': self.base_max_signals_per_minute,
            'max_signals_per_hour': self.base_max_signals_per_hour,
            'max_confluence_per_hour': self.base_max_confluence_per_hour,
            'max_concurrent_signals': self.base_max_concurrent_signals,
            'signal_timeout': self.base_signal_timeout,
            'quality_threshold': self.base_quality_threshold
        }
    
    def update_market_regime(self, symbol: str, new_regime: MarketRegime) -> Dict[str, Any]:
        """
        Atualiza o regime de mercado e retorna ajustes aplicados.
        
        Returns:
            Dict com informações sobre a mudança e ajustes
        """
        old_regime = self.current_market_regime.get(symbol)
        
        if old_regime != new_regime:
            logger.info(f"🔄 Mudança de regime em {symbol}: {old_regime} → {new_regime}")
            self.current_market_regime[symbol] = new_regime
            
            # Recalcula e aplica ajustes
            self._calculate_regime_adjustments()
            self._apply_regime_adjustments()
            
            return {
                'changed': True,
                'symbol': symbol,
                'old_regime': old_regime,
                'new_regime': new_regime,
                'adjustments': self.regime_adjustment_factors,
                'new_limits': self.current_limits.copy()
            }
        
        return {'changed': False}
    
    def _calculate_regime_adjustments(self):
        """Calcula fatores de ajuste baseados nos regimes atuais."""
        adjustments = {
            'signal_frequency': 1.0,
            'quality_threshold': 1.0,
            'concurrent_signals': 1.0,
            'timeout': 1.0,
            'circuit_breaker_sensitivity': 1.0
        }
        
        # Analisa regimes de ambos os símbolos
        for symbol, regime in self.current_market_regime.items():
            # TRENDING (UP ou DOWN)
            if regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
                adjustments['signal_frequency'] *= 1.2
                adjustments['quality_threshold'] *= 0.9
                adjustments['concurrent_signals'] *= 1.3
                
            # VOLATILE
            elif regime == MarketRegime.VOLATILE:
                adjustments['signal_frequency'] *= 0.7
                adjustments['quality_threshold'] *= 1.3
                adjustments['concurrent_signals'] *= 0.6
                adjustments['timeout'] *= 0.8
                adjustments['circuit_breaker_sensitivity'] *= 1.5
                
            # QUIET
            elif regime == MarketRegime.QUIET:
                adjustments['signal_frequency'] *= 0.5
                adjustments['quality_threshold'] *= 1.5
                adjustments['concurrent_signals'] *= 0.5
                
            # BREAKOUT
            elif regime == MarketRegime.BREAKOUT:
                adjustments['signal_frequency'] *= 1.5
                adjustments['quality_threshold'] *= 0.8
                adjustments['concurrent_signals'] *= 1.5
                adjustments['timeout'] *= 1.2
                
            # REVERSAL
            elif regime == MarketRegime.REVERSAL:
                adjustments['signal_frequency'] *= 0.8
                adjustments['quality_threshold'] *= 1.2
                adjustments['concurrent_signals'] *= 0.8
                adjustments['circuit_breaker_sensitivity'] *= 1.3
        
        # Se regimes divergem, ser mais conservador
        if self.current_market_regime['WDO'] != self.current_market_regime['DOL']:
            adjustments['quality_threshold'] *= 1.1
            adjustments['concurrent_signals'] *= 0.9
        
        # Normaliza ajustes
        for key in adjustments:
            adjustments[key] = max(0.3, min(2.0, adjustments[key]))
        
        self.regime_adjustment_factors = adjustments
    
    def _apply_regime_adjustments(self):
        """Aplica os ajustes calculados aos limites."""
        factors = self.regime_adjustment_factors
        
        # Frequência
        self.current_limits['max_signals_per_minute'] = int(
            self.base_max_signals_per_minute * factors['signal_frequency']
        )
        self.current_limits['max_signals_per_hour'] = int(
            self.base_max_signals_per_hour * factors['signal_frequency']
        )
        self.current_limits['max_confluence_per_hour'] = int(
            self.base_max_confluence_per_hour * factors['signal_frequency']
        )
        
        # Concurrent signals
        self.current_limits['max_concurrent_signals'] = max(1, int(
            self.base_max_concurrent_signals * factors['concurrent_signals']
        ))
        
        # Timeout
        self.current_limits['signal_timeout'] = int(
            self.base_signal_timeout * factors['timeout']
        )
        
        # Quality threshold
        self.current_limits['quality_threshold'] = min(0.9, 
            self.base_quality_threshold * factors['quality_threshold']
        )
        
        logger.info(
            f"✅ Limites ajustados - Sinais/min: {self.current_limits['max_signals_per_minute']}, "
            f"Concurrent: {self.current_limits['max_concurrent_signals']}, "
            f"Quality: {self.current_limits['quality_threshold']:.2f}"
        )
    
    def get_current_limits(self) -> Dict[str, Any]:
        """Retorna limites atuais ajustados."""
        return self.current_limits.copy()
    
    def get_adjustment_factors(self) -> Dict[str, float]:
        """Retorna fatores de ajuste atuais."""
        return self.regime_adjustment_factors.copy()
    
    def get_circuit_breaker_sensitivity(self) -> float:
        """Retorna sensibilidade atual dos circuit breakers."""
        return self.regime_adjustment_factors.get('circuit_breaker_sensitivity', 1.0)
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status completo do sistema adaptativo."""
        return {
            'current_regime': self.current_market_regime.copy(),
            'adjustment_factors': self.regime_adjustment_factors.copy(),
            'base_limits': {
                'max_signals_per_minute': self.base_max_signals_per_minute,
                'max_signals_per_hour': self.base_max_signals_per_hour,
                'max_concurrent_signals': self.base_max_concurrent_signals,
                'quality_threshold': self.base_quality_threshold
            },
            'current_limits': self.current_limits.copy()
        }