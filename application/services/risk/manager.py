# application/services/risk/manager.py
"""Gerenciador principal de risco - MODULARIZADO."""
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import logging

from core.entities.signal import Signal
from core.contracts.messaging import ISystemEventBus
from core.analysis.regime.types import MarketRegime

from .types import RiskLevel, SignalAssessment
from .circuit_breaker import CircuitBreakerSystem
from .evaluator import SignalEvaluator
from .adaptive_system import AdaptiveRiskSystem
from .metrics_tracker import RiskMetricsTracker
from .risk_listeners import RiskEventHandlers

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Gerencia risco do sistema de trading - VERSÃO MODULARIZADA.
    Orquestra componentes especializados para gestão de risco.
    """
    
    def __init__(self, event_bus: ISystemEventBus, config: Dict):
        self.event_bus = event_bus
        self.config = config
        
        # Componentes modularizados
        self.circuit_breakers = CircuitBreakerSystem(config)
        self.evaluator = SignalEvaluator(config)
        self.adaptive_system = AdaptiveRiskSystem(config)
        self.metrics_tracker = RiskMetricsTracker(config)
        
        # Event handlers
        self.event_handlers = RiskEventHandlers(
            event_bus=event_bus,
            metrics_tracker=self.metrics_tracker,
            circuit_breakers=self.circuit_breakers,
            adaptive_system=self.adaptive_system,
            signal_evaluator=self.evaluate_signal
        )
        
        # Limites financeiros (mantidos aqui por simplicidade)
        self.consecutive_losses_limit = config.get('consecutive_losses_limit', 5)
        self.max_drawdown_percent = config.get('max_drawdown_percent', 2.0)
        self.emergency_stop_loss = config.get('emergency_stop_loss', 1000.0)
        
        logger.info(
            f"RiskManager modularizado inicializado - "
            f"Max drawdown: {self.max_drawdown_percent}%, "
            f"Emergency stop: R${self.emergency_stop_loss}"
        )
    
    def evaluate_signal(self, signal: Signal) -> Tuple[bool, SignalAssessment]:
        """Avalia se um sinal deve ser aprovado."""
        assessment: SignalAssessment = {
            'approved': False,
            'risk_level': RiskLevel.LOW,
            'quality': 'POOR',
            'reasons': [],
            'recommendations': [],
            'timestamp': datetime.now()
        }
        
        # 1. Circuit breakers
        cb_check = self.circuit_breakers.check_all()
        if not cb_check['all_clear']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.CRITICAL
            assessment['reasons'] = cb_check['triggered']
            return False, assessment
        
        # 2. Limite de exposição
        current_limits = self.adaptive_system.get_current_limits()
        active_count = self.metrics_tracker.get_active_signals_count()
        
        if active_count >= current_limits['max_concurrent_signals']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.HIGH
            assessment['reasons'].append(
                f"Limite de sinais ativos ({current_limits['max_concurrent_signals']})"
            )
            
            # Adiciona contexto do regime
            regime_status = self.adaptive_system.get_status()
            regimes = [f"{s}: {r.value}" for s, r in regime_status['current_regime'].items()]
            assessment['reasons'].append(f"Regime atual: {', '.join(regimes)}")
            
            return False, assessment
        
        # 3. Frequência
        freq_check = self.metrics_tracker.check_signal_frequency(signal, current_limits)
        if not freq_check['within_limits']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.HIGH
            assessment['reasons'].append(freq_check['reason'])
            return False, assessment
        
        # 4. Qualidade (com threshold ajustado)
        self.evaluator.quality_threshold = current_limits['quality_threshold']
        quality = self.evaluator.evaluate_quality(signal)
        assessment['quality'] = quality['rating']
        
        if not quality['passed']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.MEDIUM
            assessment['reasons'].append(
                f"Qualidade insuficiente: {quality['score']:.2f} < {current_limits['quality_threshold']:.2f}"
            )
            assessment['recommendations'] = quality['improvements']
            
            # Menciona ajuste de regime se relevante
            factors = self.adaptive_system.get_adjustment_factors()
            if factors.get('quality_threshold', 1.0) > 1.1:
                assessment['reasons'].append("Threshold elevado devido ao regime de mercado")
            
            return False, assessment
        
        # 5. Risco contextual
        context = {
            'system_risk_level': self._calculate_current_risk_level(),
            'current_drawdown': self.metrics_tracker.get_metrics()['current_drawdown'],
            'consecutive_losses': self.metrics_tracker.get_metrics()['consecutive_losses'],
            'market_regime': self.adaptive_system.current_market_regime
        }
        
        context_risk = self.evaluator.evaluate_contextual_risk(signal, context)
        assessment['risk_level'] = context_risk['level']
        
        if context_risk['level'] in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            assessment['approved'] = False
            assessment['reasons'].append(f"Risco contextual alto: {context_risk['reason']}")
            return False, assessment
        
        # 6. Aprovado!
        assessment['approved'] = True
        assessment['recommendations'] = self._get_risk_recommendations(signal, quality, context_risk)
        
        # Registra aprovação
        self.metrics_tracker.record_signal_approval(signal)
        
        # Emite evento
        self.event_bus.publish("SIGNAL_APPROVED", {
            'signal': signal,
            'assessment': assessment
        })
        
        return True, assessment
    
    def update_market_regime(self, symbol: str, new_regime: MarketRegime):
        """Atualiza o regime de mercado (FASE 3.2)."""
        self.adaptive_system.update_market_regime(symbol, new_regime)
    
    def _calculate_current_risk_level(self) -> RiskLevel:
        """Calcula nível de risco atual."""
        metrics = self.metrics_tracker.get_metrics()
        
        # Circuit breakers
        active_breakers = len(self.circuit_breakers.get_active_breakers())
        
        if active_breakers >= 3:
            return RiskLevel.CRITICAL
        elif active_breakers >= 2:
            return RiskLevel.HIGH
        elif active_breakers >= 1:
            return RiskLevel.MEDIUM
        
        # Métricas financeiras
        if metrics['consecutive_losses'] >= self.consecutive_losses_limit:
            return RiskLevel.CRITICAL
        elif metrics['consecutive_losses'] >= self.consecutive_losses_limit * 0.6:
            return RiskLevel.HIGH
        
        if metrics['current_drawdown'] >= self.max_drawdown_percent:
            return RiskLevel.CRITICAL
        elif metrics['current_drawdown'] >= self.max_drawdown_percent * 0.7:
            return RiskLevel.HIGH
        
        if metrics['daily_pnl'] <= -self.emergency_stop_loss:
            return RiskLevel.CRITICAL
        elif metrics['daily_pnl'] <= -self.emergency_stop_loss * 0.5:
            return RiskLevel.HIGH
        
        # Considera regime volátil
        regime_status = self.adaptive_system.get_status()
        volatile_count = sum(1 for r in regime_status['current_regime'].values() 
                           if r == MarketRegime.VOLATILE)
        if volatile_count >= 2:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def _get_risk_recommendations(self, signal: Signal, quality: Dict, context: Dict) -> List[str]:
        """Gera recomendações baseadas na análise."""
        recommendations = []
        
        if quality['rating'] == 'EXCELLENT':
            recommendations.append("✅ Sinal de alta qualidade")
        elif quality['rating'] == 'GOOD':
            recommendations.append("⚡ Sinal bom")
        
        # Exposição
        active_count = self.metrics_tracker.get_active_signals_count()
        max_concurrent = self.adaptive_system.get_current_limits()['max_concurrent_signals']
        
        if active_count >= max_concurrent * 0.6:
            recommendations.append(f"📊 {active_count}/{max_concurrent} sinais ativos")
        
        # Regime
        symbol = signal.details.get('symbol', 'WDO')
        regime = self.adaptive_system.current_market_regime.get(symbol, MarketRegime.RANGING)
        
        if regime == MarketRegime.VOLATILE:
            recommendations.append("⚠️ Mercado volátil - use stops largos")
        elif regime == MarketRegime.TRENDING_UP:
            recommendations.append("📈 Tendência de alta - favoreça compras")
        elif regime == MarketRegime.TRENDING_DOWN:
            recommendations.append("📉 Tendência de baixa - favoreça vendas")
        
        return recommendations[:2]
    
    def get_risk_status(self) -> Dict:
        """Retorna status atual do risco."""
        metrics = self.metrics_tracker.get_metrics()
        current_risk = self._calculate_current_risk_level()
        metrics['risk_level'] = current_risk
        
        stats = self.metrics_tracker.get_statistics()
        current_limits = self.adaptive_system.get_current_limits()
        
        return {
            'risk_level': current_risk,
            'circuit_breakers': self.circuit_breakers.get_status(),
            'metrics': {
                'total_signals': stats['total_signals'],
                'approval_rate': f"{stats['approval_rate']:.1f}%",
                'consecutive_losses': metrics['consecutive_losses'],
                'daily_pnl': f"R${metrics['daily_pnl']:.2f}",
                'current_drawdown': f"{metrics['current_drawdown']:.1f}%",
                'active_signals': f"{stats['active_signals']}/{current_limits['max_concurrent_signals']}"
            },
            'active_breakers': self.circuit_breakers.get_active_breakers(),
            'market_regime': self.adaptive_system.get_status()['current_regime'],
            'regime_adjustments': self.adaptive_system.get_adjustment_factors()
        }
    
    def reset_daily_metrics(self):
        """Reset métricas diárias."""
        self.metrics_tracker.reset_daily_metrics()
        self.circuit_breakers.reset('emergency')
        logger.info("Métricas diárias resetadas")
    
    def manual_override(self, breaker: str, active: bool, reason: str = ""):
        """Override manual de circuit breakers."""
        if breaker == 'all':
            if not active:
                self.circuit_breakers.reset_all()
                logger.warning(f"Override manual: TODOS os breakers desativados. Razão: {reason}")
            else:
                logger.warning("Não é possível ativar todos os breakers manualmente")
        else:
            if active:
                self.circuit_breakers.trigger(breaker, reason or "Override manual")
            else:
                self.circuit_breakers.reset(breaker)
            
            logger.warning(f"Override manual: {breaker} {'ativado' if active else 'desativado'}. Razão: {reason}")
        
        self.event_bus.publish("RISK_OVERRIDE", {
            'breaker': breaker,
            'active': active,
            'reason': reason,
            'timestamp': datetime.now()
        })
    
    def get_detailed_status(self) -> Dict:
        """Status detalhado para debug."""
        return {
            'current_risk_level': self._calculate_current_risk_level().value,
            'metrics': self.metrics_tracker.get_metrics(),
            'circuit_breakers': self.circuit_breakers.get_status(),
            'evaluator_stats': self.evaluator.get_statistics(),
            'tracker_stats': self.metrics_tracker.get_statistics(),
            'adaptive_system': self.adaptive_system.get_status(),
            'thresholds': {
                'consecutive_losses_limit': self.consecutive_losses_limit,
                'max_drawdown_percent': self.max_drawdown_percent,
                'emergency_stop_loss': self.emergency_stop_loss
            }
        }