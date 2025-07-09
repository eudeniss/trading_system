# application/services/tape_reading/signal_processor.py
"""Processador e filtro de sinais, com publicação de eventos para confluência."""
from typing import List, Dict
import logging
from datetime import datetime

from core.entities.signal import Signal, SignalLevel
from core.entities.book import OrderBook
from core.contracts.cache import ITradeCache
from core.contracts.messaging import ISystemEventBus
from core.analysis.filters.defensive import DefensiveSignalFilter
from core.analysis.filters.cooldown import PatternCooldown
from core.analysis.filters.quality import SignalQualityFilter
from core.formatters.signal_formatter import SignalFormatter

logger = logging.getLogger(__name__)


class SignalProcessor:
    """Processa, filtra e publica eventos de padrões detectados."""
    
    def __init__(self, event_bus: ISystemEventBus, cache: ITradeCache,
                 defensive_filter: DefensiveSignalFilter,
                 pattern_cooldown: PatternCooldown,
                 quality_filter: SignalQualityFilter,
                 formatter: SignalFormatter):
        self.event_bus = event_bus
        self.cache = cache
        self.defensive_filter = defensive_filter
        self.pattern_cooldown = pattern_cooldown
        self.quality_filter = quality_filter
        self.formatter = formatter
        
        self.current_books = {}
        
        self.stats = {
            'signals_filtered': 0,
            'signals_emitted': 0,
            'manipulation_detected': 0,
            'patterns_published_for_confluence': 0 # Nova estatística
        }
    
    def process_raw_signals(self, raw_signals: List[Dict], 
                          pattern_confirmation_system=None) -> List[Signal]:
        """Processa sinais brutos, publica eventos e aplica filtros."""
        final_signals_to_display = []
        
        quality_filtered_signals = []
        for signal_data in raw_signals:
            quality_eval = self.quality_filter.evaluate_signal_quality(signal_data)
            if quality_eval['passed']:
                quality_filtered_signals.append(signal_data)
            else:
                self.stats['signals_filtered'] += 1
        
        for signal_data in quality_filtered_signals:
            symbol = signal_data.get('symbol', 'WDO')
            pattern = signal_data.get('pattern', 'UNKNOWN')
            
            # --- NOVA LÓGICA DE CONFLUÊNCIA INTEGRADA AQUI ---
            
            # 1. Calcula a força do padrão
            strength = self._calculate_strength(pattern, signal_data)
            signal_data['strength'] = strength

            # 2. Publica o evento para o "super cérebro" (ConfluenceService) ouvir
            self.event_bus.publish("PATTERN_DETECTED", signal_data)
            self.stats['patterns_published_for_confluence'] += 1
            
            # --- FIM DA NOVA LÓGICA ---
            
            # FASE 4.1: Verifica se requer confirmação
            if pattern_confirmation_system and pattern_confirmation_system.requires_confirmation(pattern):
                pattern_confirmation_system.add_pending_pattern(pattern, symbol, signal_data)
                continue
            
            if not self.pattern_cooldown.can_emit_pattern(pattern, symbol):
                continue
            
            signal = self.formatter.format(signal_data, symbol)
            
            book = self.current_books.get(symbol)
            recent_trades = self.cache.get_recent_trades(symbol, 50)
            
            is_safe, risk_info = self.defensive_filter.is_signal_safe(
                signal, book, recent_trades
            )
            
            if is_safe:
                final_signals_to_display.append(signal)
                self.stats['signals_emitted'] += 1
            else:
                self.stats['manipulation_detected'] += 1
                self.event_bus.publish('MANIPULATION_DETECTED', {
                    'signal': signal, 
                    'risk_info': risk_info, 
                    'symbol': symbol
                })
        
        return final_signals_to_display

    def _calculate_strength(self, pattern: str, details: Dict) -> int:
        """Calcula uma força de 1 a 10 para o padrão detectado."""
        strength = 5 # Força base

        strong_patterns = ['ABSORPTION_DETECTED', 'EXHAUSTION_DETECTED', 'MOMENTUM_EXTREMO', 'INSTITUTIONAL_FOOTPRINT']
        medium_patterns = ['ICEBERG', 'DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA', 'TRAP_DETECTED']

        if pattern in strong_patterns:
            strength = 8
        elif pattern in medium_patterns:
            strength = 7

        # Ajuste fino por volume
        if details.get('volume', 0) > 2000:
            strength = min(strength + 2, 10)
        elif details.get('volume', 0) > 1000:
            strength = min(strength + 1, 10)
            
        return strength

    def update_book(self, symbol: str, book: OrderBook):
        self.current_books[symbol] = book
    
    def get_statistics(self) -> Dict:
        return {
            **self.stats,
            'quality_filter': self.quality_filter.get_statistics(),
            'cooldown_filter': self.pattern_cooldown.get_statistics()
        }