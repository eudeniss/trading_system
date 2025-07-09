# application/services/risk/event_handlers.py
"""Handlers de eventos para risk management."""
from typing import Dict, Any, Callable
from datetime import datetime
import logging

from core.entities.signal import Signal
from core.contracts.messaging import ISystemEventBus
from core.analysis.regime.types import MarketRegime

logger = logging.getLogger(__name__)


class RiskEventHandlers:
    """
    Gerencia handlers de eventos para o RiskManager.
    Separa a lógica de tratamento de eventos.
    """
    
    def __init__(self, event_bus: ISystemEventBus, 
                 metrics_tracker: Any,
                 circuit_breakers: Any,
                 adaptive_system: Any,
                 signal_evaluator: Callable):
        self.event_bus = event_bus
        self.metrics_tracker = metrics_tracker
        self.circuit_breakers = circuit_breakers
        self.adaptive_system = adaptive_system
        self.signal_evaluator = signal_evaluator
        
        self._subscribe_events()
    
    def _subscribe_events(self):
        """Subscreve aos eventos relevantes."""
        self.event_bus.subscribe("SIGNAL_GENERATED", self.handle_signal_generated)
        self.event_bus.subscribe("TRADE_EXECUTED", self.handle_trade_executed)
        self.event_bus.subscribe("TRADE_CLOSED", self.handle_trade_closed)
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self.handle_market_update)
        self.event_bus.subscribe("REGIME_CHANGE", self.handle_regime_change)
        
        logger.info("RiskEventHandlers subscritos aos eventos do sistema")
    
    def handle_signal_generated(self, signal: Signal):
        """Handler para sinais gerados."""
        approved, assessment = self.signal_evaluator(signal)
        
        if not approved:
            self.metrics_tracker.record_signal_rejection(signal, assessment['reasons'])
            logger.debug(f"Sinal rejeitado: {assessment['reasons']}")
            
            self.event_bus.publish("SIGNAL_REJECTED", {
                'signal': signal,
                'assessment': assessment
            })
    
    def handle_trade_executed(self, trade_data: Dict):
        """Handler para trades executados."""
        # Reset consecutive losses se trade executado
        metrics = self.metrics_tracker.get_metrics()
        if metrics['consecutive_losses'] > 0:
            logger.info("Trade executado - resetando perdas consecutivas")
    
    def handle_trade_closed(self, trade_result: Dict):
        """Handler para trades fechados."""
        pnl = trade_result.get('pnl', 0)
        
        # Atualiza métricas
        self.metrics_tracker.update_pnl(pnl)
        
        # Atualiza circuit breakers
        metrics = self.metrics_tracker.get_metrics()
        self.circuit_breakers.update_from_metrics(metrics)
        
        # Log se significativo
        if abs(pnl) > 100:
            logger.info(f"Trade fechado - PnL: R${pnl:.2f}")
    
    def handle_market_update(self, market_data: Dict):
        """Handler para atualizações de mercado."""
        # Limpa sinais expirados
        limits = self.adaptive_system.get_current_limits()
        self.metrics_tracker.cleanup_expired_signals(limits['signal_timeout'])
    
    def handle_regime_change(self, data: Dict):
        """Handler para mudanças de regime (FASE 3.2)."""
        symbol = data.get('symbol')
        new_regime = data.get('new_regime')
        
        if symbol and new_regime:
            # Atualiza sistema adaptativo
            change_info = self.adaptive_system.update_market_regime(symbol, new_regime)
            
            if change_info['changed']:
                # Notifica mudança no sistema de risco
                self.event_bus.publish("RISK_REGIME_ADJUSTED", {
                    'symbol': symbol,
                    'old_regime': change_info['old_regime'],
                    'new_regime': change_info['new_regime'],
                    'adjustments': change_info['adjustments'],
                    'new_limits': change_info['new_limits'],
                    'timestamp': datetime.now()
                })
    
    def cleanup(self):
        """Remove subscrições de eventos."""
        self.event_bus.unsubscribe("SIGNAL_GENERATED", self.handle_signal_generated)
        self.event_bus.unsubscribe("TRADE_EXECUTED", self.handle_trade_executed)
        self.event_bus.unsubscribe("TRADE_CLOSED", self.handle_trade_closed)
        self.event_bus.unsubscribe("MARKET_DATA_UPDATED", self.handle_market_update)
        self.event_bus.unsubscribe("REGIME_CHANGE", self.handle_regime_change)