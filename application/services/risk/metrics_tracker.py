# application/services/risk/metrics_tracker.py
"""Rastreador de métricas para risk management."""
from typing import Dict, Any
from datetime import datetime, timedelta
from collections import deque
import logging

from core.entities.signal import Signal
from .types import RiskMetrics, RiskLevel

logger = logging.getLogger(__name__)


class RiskMetricsTracker:
    """
    Rastreia e gerencia métricas de risco.
    Centraliza todo o tracking de performance e estatísticas.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Tracking de timestamps
        self.signal_timestamps = {
            'all': deque(maxlen=500),
            'confluence': deque(maxlen=100),
            'arbitrage': deque(maxlen=200),
            'tape_reading': deque(maxlen=300)
        }
        
        # Sinais ativos
        self.active_signals = {}
        
        # Histórico
        self.signal_history = deque(maxlen=1000)
        
        # Métricas principais
        self.metrics: RiskMetrics = {
            'total_signals': 0,
            'signals_approved': 0,
            'signals_rejected': 0,
            'consecutive_losses': 0,
            'daily_pnl': 0.0,
            'peak_pnl': 0.0,
            'current_drawdown': 0.0,
            'risk_level': RiskLevel.LOW
        }
        
        logger.info("RiskMetricsTracker inicializado")
    
    def record_signal_approval(self, signal: Signal) -> str:
        """
        Registra aprovação de sinal e retorna ID único.
        
        Returns:
            ID único do sinal
        """
        self.metrics['total_signals'] += 1
        self.metrics['signals_approved'] += 1
        
        now = datetime.now()
        self.signal_timestamps['all'].append(now)
        
        # Adiciona por tipo
        source_key = signal.source.value.lower()
        if source_key in self.signal_timestamps:
            self.signal_timestamps[source_key].append(now)
        
        # Gera ID único
        signal_id = f"{signal.source.value}_{now.timestamp()}"
        
        # Adiciona aos ativos
        self.active_signals[signal_id] = {
            'signal': signal,
            'timestamp': now,
            'timeout': now + timedelta(seconds=self.config.get('signal_timeout', 60))
        }
        
        # Histórico
        self.signal_history.append({
            'signal': signal,
            'timestamp': now,
            'approved': True
        })
        
        return signal_id
    
    def record_signal_rejection(self, signal: Signal, reasons: list):
        """Registra rejeição de sinal."""
        self.metrics['total_signals'] += 1
        self.metrics['signals_rejected'] += 1
        
        # Histórico
        self.signal_history.append({
            'signal': signal,
            'timestamp': datetime.now(),
            'approved': False,
            'reasons': reasons
        })
    
    def update_pnl(self, pnl: float):
        """Atualiza PnL e métricas relacionadas."""
        # PnL diário
        self.metrics['daily_pnl'] += pnl
        
        # Peak e drawdown
        if self.metrics['daily_pnl'] > self.metrics['peak_pnl']:
            self.metrics['peak_pnl'] = self.metrics['daily_pnl']
        
        drawdown = self.metrics['peak_pnl'] - self.metrics['daily_pnl']
        drawdown_pct = (drawdown / self.metrics['peak_pnl'] * 100) if self.metrics['peak_pnl'] > 0 else 0
        self.metrics['current_drawdown'] = drawdown_pct
        
        # Consecutive losses
        if pnl < 0:
            self.metrics['consecutive_losses'] += 1
        else:
            self.metrics['consecutive_losses'] = 0
    
    def check_signal_frequency(self, signal: Signal, limits: Dict[str, int]) -> Dict[str, Any]:
        """Verifica limites de frequência de sinais."""
        now = datetime.now()
        
        # Último minuto
        one_minute_ago = now - timedelta(minutes=1)
        signals_last_minute = sum(1 for ts in self.signal_timestamps['all'] if ts > one_minute_ago)
        
        if signals_last_minute >= limits['max_signals_per_minute']:
            return {
                'within_limits': False,
                'reason': f"{signals_last_minute} sinais/min (máx: {limits['max_signals_per_minute']})"
            }
        
        # Última hora
        one_hour_ago = now - timedelta(hours=1)
        signals_last_hour = sum(1 for ts in self.signal_timestamps['all'] if ts > one_hour_ago)
        
        if signals_last_hour >= limits['max_signals_per_hour']:
            return {
                'within_limits': False,
                'reason': f"{signals_last_hour} sinais/hora (máx: {limits['max_signals_per_hour']})"
            }
        
        # Confluência específica
        if signal.source.value == 'CONFLUENCE':
            confluence_last_hour = sum(
                1 for ts in self.signal_timestamps['confluence'] if ts > one_hour_ago
            )
            if confluence_last_hour >= limits['max_confluence_per_hour']:
                return {
                    'within_limits': False,
                    'reason': f"{confluence_last_hour} confluências/hora (máx: {limits['max_confluence_per_hour']})"
                }
        
        return {'within_limits': True, 'reason': 'OK'}
    
    def cleanup_expired_signals(self, timeout_seconds: int):
        """Remove sinais expirados e retorna quantidade de ativos."""
        now = datetime.now()
        expired = []
        
        for signal_id, data in self.active_signals.items():
            if now > data['timeout']:
                expired.append(signal_id)
        
        for signal_id in expired:
            del self.active_signals[signal_id]
        
        return len(self.active_signals)
    
    def reset_daily_metrics(self):
        """Reseta métricas diárias."""
        logger.info("Resetando métricas diárias")
        
        self.metrics['daily_pnl'] = 0.0
        self.metrics['peak_pnl'] = 0.0
        self.metrics['current_drawdown'] = 0.0
        
        # Limpa timestamps antigos
        cutoff = datetime.now() - timedelta(hours=24)
        for key in self.signal_timestamps:
            self.signal_timestamps[key] = deque(
                (ts for ts in self.signal_timestamps[key] if ts > cutoff),
                maxlen=self.signal_timestamps[key].maxlen
            )
        
        self.active_signals.clear()
    
    def get_metrics(self) -> RiskMetrics:
        """Retorna cópia das métricas atuais."""
        return self.metrics.copy()
    
    def get_active_signals_count(self) -> int:
        """Retorna quantidade de sinais ativos."""
        return len(self.active_signals)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas."""
        total = self.metrics['total_signals']
        approval_rate = (
            self.metrics['signals_approved'] / total * 100
        ) if total > 0 else 0
        
        return {
            'total_signals': total,
            'approved': self.metrics['signals_approved'],
            'rejected': self.metrics['signals_rejected'],
            'approval_rate': approval_rate,
            'active_signals': len(self.active_signals),
            'consecutive_losses': self.metrics['consecutive_losses'],
            'daily_pnl': self.metrics['daily_pnl'],
            'current_drawdown': self.metrics['current_drawdown']
        }