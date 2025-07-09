# application/services/tape_reading/service.py
"""Serviço principal de Tape Reading - orquestração."""
from typing import List, Dict, Optional, Any
import time
import logging

from core.entities.trade import Trade
from core.entities.signal import Signal
from core.entities.book import OrderBook
from core.contracts.cache import ITradeCache
from core.contracts.messaging import ISystemEventBus
from core.analysis.filters.defensive import DefensiveSignalFilter
from core.analysis.filters.cooldown import PatternCooldown
from core.analysis.filters.quality import SignalQualityFilter
from core.analysis.statistics.volume_profile import VolumeProfileAnalyzer
from core.formatters.signal_formatter import SignalFormatter

from .analyzer_factory import AnalyzerFactory
from .trade_flow_analyzer import PatternAnalyzer
from .pending_pattern_manager import PatternConfirmationSystem
from .signal_processor import SignalProcessor

logger = logging.getLogger(__name__)


class TapeReadingService:
    """
    Serviço principal de Tape Reading - apenas orquestração.
    Delega responsabilidades para módulos especializados.
    """
    
    def __init__(self, event_bus: ISystemEventBus, cache: ITradeCache, config: Dict):
        self.config = config
        self.event_bus = event_bus
        self.cache = cache
        
        # Books atuais
        self.current_books: Dict[str, Optional[OrderBook]] = {
            'WDO': None, 
            'DOL': None
        }
        
        # Cria analyzers para cada símbolo
        self.analyzers = {
            'WDO': AnalyzerFactory.create_analyzers(config),
            'DOL': AnalyzerFactory.create_analyzers(config)
        }
        
        # Componentes principais
        self._setup_components()
        
        # Cache de trades processados
        self.processed_trade_ids: Dict[str, set] = {
            'WDO': set(), 
            'DOL': set()
        }
        
        # Sistema de confirmação
        self._last_confirmation_check = time.time()
        
        # Estatísticas gerais
        self.stats = {
            'patterns_detected': {},
            'signals_emitted': 0,
            'signals_filtered': 0,
            'manipulation_detected': 0
        }
        
        logger.info(
            f"TapeReadingService inicializado - "
            f"Confirmação: {'ON' if self.confirmation_config['enabled'] else 'OFF'}"
        )
    
    def _setup_components(self):
        """Configura componentes do serviço."""
        # Configuração de manipulação
        manipulation_config = self.config.get('manipulation_detection', {
            'layering': {'enabled': True},
            'spoofing': {'enabled': True},
            'actions': {'block_signals': True, 'log_details': True},
            'confidence': {'layering_penalty': 0.4, 'spoofing_penalty': 0.3}
        })
        
        # Filtros
        self.defensive_filter = DefensiveSignalFilter(config=manipulation_config)
        
        pattern_cooldowns = self.config.get('pattern_cooldown', {
            'default': 30,
            'PRESSAO_COMPRA': 15,
            'PRESSAO_VENDA': 15,
            'MOMENTUM_EXTREMO': 20,
            'ESCORA_DETECTADA': 30,
            'DIVERGENCIA_ALTA': 25,
            'DIVERGENCIA_BAIXA': 25,
            'ICEBERG': 30,
            'VOLUME_SPIKE': 15,
            'PACE_ANOMALY': 20,
            'INSTITUTIONAL_FOOTPRINT': 60,
            'HIDDEN_LIQUIDITY': 45,
            'MULTIFRAME_DIVERGENCE': 40,
            'MULTIFRAME_CONFLUENCE': 35,
            'TRAP_DETECTED': 30,
            'BOOK_PULLING': 10,
            'BOOK_STACKING': 10,
            'FLASH_ORDER': 5,
            'IMBALANCE_SHIFT': 15
        })
        self.pattern_cooldown = PatternCooldown(pattern_cooldowns)
        
        min_quality = self.config.get('signal_quality_threshold', 0.35)
        self.quality_filter = SignalQualityFilter(min_quality)
        
        # Formatador e profile
        self.formatter = SignalFormatter()
        self.volume_profile = VolumeProfileAnalyzer()
        
        # Sistema de confirmação
        self.confirmation_config = self.config.get('pattern_confirmation', {
            'enabled': True,
            'max_pending': 50,
            'default_timeout': 30,
            'check_interval': 1.0,
            'patterns': {}
        })
        
        # Componentes modulares
        self.pattern_analyzer = PatternAnalyzer(
            self.analyzers, 
            self.cache, 
            self.config
        )
        
        self.pattern_confirmation = PatternConfirmationSystem(
            self.event_bus,
            self.cache,
            self.analyzers,
            self.confirmation_config,
            self.defensive_filter,
            self.pattern_cooldown,
            self.formatter
        )
        
        self.signal_processor = SignalProcessor(
            self.event_bus,
            self.cache,
            self.defensive_filter,
            self.pattern_cooldown,
            self.quality_filter,
            self.formatter
        )
    
    def update_book(self, symbol: str, book: OrderBook):
        """Atualiza book e detecta dinâmicas."""
        self.current_books[symbol] = book
        self.pattern_confirmation.update_book(symbol, book)
        self.signal_processor.update_book(symbol, book)
        
        # Analisa dinâmica do book
        book_signals = self.analyzers[symbol]['book_dynamics'].analyze_book_update(symbol, book)
        
        # Processa sinais do book
        for signal_data in book_signals:
            if self.quality_filter.should_emit_signal(signal_data):
                pattern = signal_data.get('pattern', 'UNKNOWN')
                if self.pattern_cooldown.can_emit_pattern(pattern, symbol):
                    signal = self.formatter.format(signal_data, symbol)
                    self._update_stats('book_dynamics', pattern)
                    
                    self.event_bus.publish("BOOK_DYNAMICS_ALERT", {
                        'signal': signal,
                        'pattern': pattern,
                        'symbol': symbol,
                        'details': signal_data
                    })
    
    def process_new_trades(self, trades: List[Trade]) -> List[Signal]:
        """Processa trades com sistema completo de análise."""
        if not trades:
            return []
        
        process_start = time.perf_counter()
        raw_signals = []
        
        # Processa trades por símbolo
        trades_by_symbol = self._organize_trades_by_symbol(trades)
        
        # Adiciona trades ao cache e atualiza estatísticas
        for symbol, symbol_trades in trades_by_symbol.items():
            self.cache.add_trades(symbol, symbol_trades)
            
            # Atualiza CVD e volume profile
            for trade in symbol_trades:
                self.analyzers[symbol]['cvd_calc'].update_cumulative(trade)
                self.volume_profile.update_profile([trade])
            
            # Análise de trades individuais
            for trade in symbol_trades:
                signals_from_trade = self.pattern_analyzer.analyze_single_trade(trade)
                raw_signals.extend(signals_from_trade)
            
            # Análises agregadas
            aggregated_signals = self.pattern_analyzer.analyze_aggregated_patterns(symbol)
            raw_signals.extend(aggregated_signals)
            
            # Análises especializadas
            book = self.current_books.get(symbol)
            specialized_signals = self.pattern_analyzer.analyze_specialized_patterns(
                symbol, symbol_trades, book
            )
            raw_signals.extend(specialized_signals)
        
        # Verifica padrões pendentes
        if self.confirmation_config['enabled']:
            self._check_pending_patterns_if_needed()
        
        # Processa sinais com filtros
        all_signals = self.signal_processor.process_raw_signals(
            raw_signals, 
            self.pattern_confirmation
        )
        
        # Atualiza estatísticas
        self._update_service_stats()
        
        # Log performance
        process_duration = (time.perf_counter() - process_start) * 1000
        if process_duration > 50:
            logger.warning(
                f"⚠️ Processamento lento: {process_duration:.1f}ms para "
                f"{len(trades)} trades ({len(all_signals)} sinais gerados)"
            )
        
        return all_signals
    
    def _organize_trades_by_symbol(self, trades: List[Trade]) -> Dict[str, List[Trade]]:
        """Organiza trades por símbolo e marca como processados."""
        trades_by_symbol = {}
        
        for trade in trades:
            if not isinstance(trade, Trade) or not hasattr(trade, 'timestamp') or not trade.timestamp:
                continue

            symbol = trade.symbol
            if symbol not in ['WDO', 'DOL']:
                continue
            
            # Cria ID único para o trade
            trade_id = f"{trade.time_str}_{trade.price}_{trade.volume}"
            
            # Evita reprocessar
            if trade_id not in self.processed_trade_ids[symbol]:
                self.processed_trade_ids[symbol].add(trade_id)
                
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []
                trades_by_symbol[symbol].append(trade)
            
            # Limpa cache antigo
            if len(self.processed_trade_ids[symbol]) > 500:
                old_trades = list(self.processed_trade_ids[symbol])
                self.processed_trade_ids[symbol] = set(old_trades[-250:])
        
        return trades_by_symbol
    
    def _check_pending_patterns_if_needed(self):
        """Verifica padrões pendentes no intervalo configurado."""
        current_time = time.time()
        if current_time - self._last_confirmation_check >= self.confirmation_config['check_interval']:
            self.pattern_confirmation.check_pending_patterns()
            self._last_confirmation_check = current_time
    
    def _update_stats(self, category: str, pattern: str):
        """Atualiza estatísticas internas."""
        key = f"{category}_{pattern}"
        if key not in self.stats['patterns_detected']:
            self.stats['patterns_detected'][key] = 0
        self.stats['patterns_detected'][key] += 1
    
    def _update_service_stats(self):
        """Atualiza estatísticas gerais do serviço."""
        # Agrega estatísticas dos componentes
        pattern_stats = self.pattern_analyzer.get_statistics()
        confirmation_stats = self.pattern_confirmation.get_statistics()
        processor_stats = self.signal_processor.get_statistics()
        
        # Atualiza contadores
        self.stats['signals_emitted'] = processor_stats['signals_emitted']
        self.stats['signals_filtered'] = processor_stats['signals_filtered']
        self.stats['manipulation_detected'] = processor_stats['manipulation_detected']
        
        # Merge patterns detected
        for key, count in pattern_stats['patterns_detected'].items():
            if key not in self.stats['patterns_detected']:
                self.stats['patterns_detected'][key] = 0
            self.stats['patterns_detected'][key] += count
    
    def get_market_summary(self, symbol: str) -> dict:
        """Retorna resumo completo do mercado."""
        default_summary = {
            "symbol": symbol, 
            "cvd": 0, 
            "cvd_roc": 0.0, 
            "cvd_total": 0,
            "poc": None, 
            "supports": [], 
            "resistances": [],
            "cache_size": 0,
            "pending_patterns": 0,
            "hidden_levels": 0,
            "trap_risk": "MINIMAL"
        }
        
        recent_trades = self.cache.get_recent_trades(symbol, 50)
        
        if not recent_trades:
            return default_summary

        # Calcula métricas básicas
        cvd_calc = self.analyzers[symbol]['cvd_calc']
        cvd = cvd_calc.calculate_cvd_for_trades(recent_trades)
        roc = cvd_calc.update_and_get_roc(recent_trades, self.config.get('cvd_roc_period', 15))
        cvd_total = cvd_calc.get_cumulative_total(symbol)
        
        # Volume Profile
        poc = self.volume_profile.find_poc(symbol)
        current_price = recent_trades[-1].price
        sup_res = self.volume_profile.find_support_resistance(symbol, current_price)

        # Conta padrões pendentes
        pending_count = self.pattern_confirmation.get_pending_count(symbol)
        
        # Informações dos detectores especializados
        hidden_levels_count = len(
            self.analyzers[symbol]['hidden_liquidity'].get_hidden_levels(symbol, current_price)
        )
        trap_assessment = self.analyzers[symbol]['trap_detector'].get_trap_risk_assessment(symbol)

        # Monta resumo
        summary = {
            "symbol": symbol,
            "cvd": cvd, 
            "cvd_roc": roc, 
            "cvd_total": cvd_total,
            "poc": poc,
            "supports": sup_res.get('support', []),
            "resistances": sup_res.get('resistance', []),
            "cache_size": self.cache.get_size(symbol),
            "pending_patterns": pending_count,
            "hidden_levels": hidden_levels_count,
            "trap_risk": trap_assessment.get('risk_level', 'MINIMAL')
        }
        # application/services/tape_reading/service.py - MÉTODO get_market_summary ATUALIZADO

    def get_market_summary(self, symbol: str) -> dict:
        """Retorna resumo completo do mercado - COM TOTAL DE TRADES."""
        default_summary = {
            "symbol": symbol, 
            "cvd": 0, 
            "cvd_roc": 0.0, 
            "cvd_total": 0,
            "poc": None, 
            "supports": [], 
            "resistances": [],
            "cache_size": 0,
            "total_trades": 0,  # NOVO: total de trades processados
            "pending_patterns": 0,
            "hidden_levels": 0,
            "trap_risk": "MINIMAL"
        }
        
        recent_trades = self.cache.get_recent_trades(symbol, 50)
        
        if not recent_trades:
            logger.warning(f"Sem trades recentes para {symbol}")
            return default_summary

        # Calcula métricas básicas
        cvd_calc = self.analyzers[symbol]['cvd_calc']
        cvd = cvd_calc.calculate_cvd_for_trades(recent_trades)
        roc = cvd_calc.update_and_get_roc(recent_trades, self.config.get('cvd_roc_period', 15))
        cvd_total = cvd_calc.get_cumulative_total(symbol)
        
        # Volume Profile
        poc = self.volume_profile.find_poc(symbol)
        current_price = recent_trades[-1].price
        sup_res = self.volume_profile.find_support_resistance(symbol, current_price)

        # Conta padrões pendentes
        pending_count = self.pattern_confirmation.get_pending_count(symbol)
        
        # Informações dos detectores especializados
        hidden_levels_count = len(
            self.analyzers[symbol]['hidden_liquidity'].get_hidden_levels(symbol, current_price)
        )
        trap_assessment = self.analyzers[symbol]['trap_detector'].get_trap_risk_assessment(symbol)

        # Monta resumo
        summary = {
            "symbol": symbol,
            "cvd": cvd, 
            "cvd_roc": roc, 
            "cvd_total": cvd_total,
            "poc": poc,
            "supports": sup_res.get('support', []),
            "resistances": sup_res.get('resistance', []),
            "cache_size": self.cache.get_size(symbol),
            "total_trades": self.cache.get_size(symbol),  # NOVO: usa cache_size como total
            "pending_patterns": pending_count,
            "hidden_levels": hidden_levels_count,
            "trap_risk": trap_assessment.get('risk_level', 'MINIMAL')
        }
        
        logger.debug(f"Market summary for {symbol}: {summary}")
        return summary
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas completas do serviço."""
        cache_stats = self.cache.get_stats()
        
        # Estatísticas dos componentes
        cache_stats['pattern_analyzer'] = self.pattern_analyzer.get_statistics()
        cache_stats['pattern_confirmation'] = self.pattern_confirmation.get_statistics()
        cache_stats['signal_processor'] = self.signal_processor.get_statistics()
        
        # Stats gerais do serviço
        cache_stats['service_stats'] = self.stats
        
        # Stats dos detectores especializados (agregados)
        specialized_stats = self._aggregate_specialized_stats()
        cache_stats['specialized_detectors'] = specialized_stats
        
        return cache_stats
    
    def _aggregate_specialized_stats(self) -> Dict:
        """Agrega estatísticas dos detectores especializados."""
        specialized_stats = {
            'institutional': {},
            'hidden_liquidity': {},
            'multiframe': {},
            'trap': {},
            'book_dynamics': {}
        }
        
        # Agrega estatísticas de todos os símbolos
        for symbol in ['WDO', 'DOL']:
            if symbol in self.analyzers:
                analyzers = self.analyzers[symbol]
                
                # Agrega cada tipo de detector
                for detector_type, stats_dict in specialized_stats.items():
                    if detector_type in analyzers:
                        detector_stats = analyzers[detector_type].get_statistics()
                        
                        # Merge stats
                        for k, v in detector_stats.items():
                            if k not in stats_dict:
                                stats_dict[k] = v
                            elif isinstance(v, (int, float)):
                                stats_dict[k] = stats_dict.get(k, 0) + v
        
        return specialized_stats