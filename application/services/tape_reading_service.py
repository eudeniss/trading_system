# application/services/tape_reading_service.py (REFATORADO COM CACHE CENTRALIZADO)
from typing import Any, List, Optional, Dict
import logging

from domain.entities.trade import Trade
from domain.entities.signal import Signal
from domain.entities.book import OrderBook
from domain.repositories.trade_cache import ITradeCache
from analyzers.patterns.absorption_detector import AbsorptionDetector
from analyzers.patterns.iceberg_detector import IcebergDetector
from analyzers.patterns.momentum_analyzer import MomentumAnalyzer
from analyzers.patterns.pressure_detector import PressureDetector
from analyzers.patterns.volume_spike_detector import VolumeSpikeDetector
from analyzers.patterns.defensive_filter import DefensiveSignalFilter
from analyzers.statistics.cvd_calculator import CvdCalculator
from analyzers.statistics.pace_analyzer import PaceAnalyzer
from analyzers.statistics.volume_profile_analyzer import VolumeProfileAnalyzer
from analyzers.formatters.signal_formatter import SignalFormatter
from application.interfaces.system_event_bus import ISystemEventBus
from config import settings

logger = logging.getLogger(__name__)

class TapeReadingService:
    """
    Serviço que orquestra a análise de tape reading.
    Versão refatorada usando cache centralizado.
    """
    def __init__(self, event_bus: ISystemEventBus, trade_cache: ITradeCache):
        """
        Args:
            event_bus: Barramento de eventos do sistema
            trade_cache: Cache centralizado de trades
        """
        self.config = settings.TAPE_READING_CONFIG
        self.event_bus = event_bus
        self.trade_cache = trade_cache  # USA CACHE EXTERNO!
        
        # NÃO TEM MAIS trades_history interno!
        
        self.current_books: Dict[str, Optional[OrderBook]] = {
            'WDO': None, 
            'DOL': None
        }
        
        self.analyzers = {
            'WDO': self._create_analyzers(),
            'DOL': self._create_analyzers()
        }
        
        self.formatter = SignalFormatter()
        self.defensive_filter = DefensiveSignalFilter()
        self.volume_profile = VolumeProfileAnalyzer()
        
        # Cache de trades processados (apenas IDs para evitar duplicação)
        self.processed_trade_ids: Dict[str, set] = {
            'WDO': set(), 
            'DOL': set()
        }
        
        logger.info("TapeReadingService inicializado com cache centralizado")

    def _create_analyzers(self) -> dict:
        """Cria uma nova instância de analisadores para um símbolo."""
        return {
            'cvd_calc': CvdCalculator(state_manager=None),
            'pace_analyzer': PaceAnalyzer(),
            'absorption_detector': AbsorptionDetector(
                concentration_threshold=self.config.get('concentration_threshold', 0.4),
                min_volume_threshold=self.config.get('absorption_threshold', 100) * 2
            ),
            'iceberg_detector': IcebergDetector(
                repetitions=self.config.get('iceberg_repetitions', 3)
            ),
            'momentum_analyzer': MomentumAnalyzer(
                divergence_roc_threshold=self.config.get('divergence_threshold', 50),
                extreme_roc_threshold=self.config.get('extreme_threshold', 100)
            ),
            'pressure_detector': PressureDetector(
                threshold=self.config.get('pressure_threshold', 0.8)
            ),
            'volume_spike_detector': VolumeSpikeDetector()
        }
    
    def update_book(self, symbol: str, book: OrderBook):
        """Atualiza o book atual para análise de manipulação."""
        self.current_books[symbol] = book

    def process_new_trades(self, trades: List[Trade]) -> List[Signal]:
        """Processa uma lista de novos trades e gera sinais."""
        all_signals = []
        raw_signals = []
        
        # Primeiro, adiciona todos os trades válidos ao cache
        trades_by_symbol = {}
        for trade in trades:
            if not isinstance(trade, Trade) or not hasattr(trade, 'timestamp') or not trade.timestamp:
                logger.warning(f"Trade inválido ou sem timestamp recebido. Pulando.")
                continue

            symbol = trade.symbol
            if symbol not in ['WDO', 'DOL']:
                logger.warning(f"Símbolo desconhecido '{symbol}' recebido no trade. Pulando.")
                continue
            
            # Agrupa trades por símbolo para adicionar em batch
            if symbol not in trades_by_symbol:
                trades_by_symbol[symbol] = []
            trades_by_symbol[symbol].append(trade)
            
            # Atualiza CVD e volume profile
            self.analyzers[symbol]['cvd_calc'].update_cumulative(trade)
            self.volume_profile.update_profile([trade])
            
            # Análise que requer apenas o trade atual
            signals_from_trade = self._analyze_single_trade(trade)
            raw_signals.extend(signals_from_trade)
        
        # Adiciona trades ao cache em batch (mais eficiente)
        for symbol, symbol_trades in trades_by_symbol.items():
            self.trade_cache.add_trades(symbol, symbol_trades)
        
        # Análises agregadas por símbolo
        for symbol in trades_by_symbol.keys():
            aggregated_signals = self._analyze_aggregated_patterns(symbol)
            raw_signals.extend(aggregated_signals)
        
        # Filtro defensivo em todos os sinais
        for signal in raw_signals:
            symbol = signal.details.get('symbol', 'WDO')
            book = self.current_books.get(symbol)
            
            # Busca trades recentes do CACHE CENTRALIZADO
            recent_trades = self.trade_cache.get_recent_trades(symbol, 50)
            
            is_safe, risk_info = self.defensive_filter.is_signal_safe(
                signal, book, recent_trades
            )
            
            if is_safe:
                all_signals.append(signal)
            elif self.event_bus:
                self.event_bus.publish('MANIPULATION_DETECTED', {
                    'signal': signal, 
                    'risk_info': risk_info, 
                    'symbol': symbol
                })

        return all_signals

    def _analyze_single_trade(self, trade: Trade) -> List[Signal]:
        """Analisa padrões que podem ser detectados a partir de um único trade."""
        symbol = trade.symbol
        analyzers = self.analyzers[symbol]
        signals = []
        
        # Busca histórico do CACHE CENTRALIZADO
        history = self.trade_cache.get_recent_trades(symbol, 100)
        
        # Garante que tem dados suficientes
        if len(history) < 2:
            return signals
        
        # Detecção de Iceberg
        iceberg_result = analyzers['iceberg_detector'].detect(trade, history)
        if iceberg_result:
            signals.append(self.formatter.format(iceberg_result, symbol))

        return signals
        
    def _analyze_aggregated_patterns(self, symbol: str) -> List[Signal]:
        """Analisa padrões que dependem de um conjunto de trades recentes."""
        signals = []
        analyzers = self.analyzers[symbol]
        
        # Busca diferentes janelas do CACHE CENTRALIZADO
        recent_trades_100 = self.trade_cache.get_recent_trades(symbol, 100)
        recent_trades_50 = self.trade_cache.get_recent_trades(symbol, 50)
        recent_trades_20 = self.trade_cache.get_recent_trades(symbol, 20)
        
        if not recent_trades_50:
            return []

        # Pace Analysis
        pace_result = analyzers['pace_analyzer'].update_and_check_anomaly()
        if pace_result:
            buy_volume = sum(t.volume for t in recent_trades_50 if t.side.name == 'BUY')
            sell_volume = sum(t.volume for t in recent_trades_50 if t.side.name == 'SELL')
            
            if buy_volume > sell_volume * 1.3:
                pace_result['direction'] = "COMPRA AGRESSIVA"
            elif sell_volume > buy_volume * 1.3:
                pace_result['direction'] = "VENDA AGRESSIVA"
            else:
                pace_result['direction'] = "BATALHA"
            
            pace_result['pattern'] = 'PACE_ANOMALY'
            signals.append(self.formatter.format(pace_result, symbol))

        # Momentum Analysis
        roc_period = self.config.get('cvd_roc_period', 10)
        cvd_roc = analyzers['cvd_calc'].update_and_get_roc(recent_trades_50, roc_period)
        momentum_result = analyzers['momentum_analyzer'].detect_divergence(recent_trades_50, cvd_roc)
        if momentum_result:
            signals.append(self.formatter.format(momentum_result, symbol))
            
        # Absorption Detection
        absorption_result = analyzers['absorption_detector'].detect(recent_trades_100)
        if absorption_result:
            signals.append(self.formatter.format(absorption_result, symbol))
        
        # Pressure Detection
        pressure_result = analyzers['pressure_detector'].detect(recent_trades_20)
        if pressure_result:
            signals.append(self.formatter.format(pressure_result, symbol))
        
        # Volume Spike Detection
        spike_result = analyzers['volume_spike_detector'].detect(recent_trades_50)
        if spike_result:
            signals.append(self.formatter.format(spike_result, symbol))

        return signals
        
    def get_market_summary(self, symbol: str) -> dict:
        """Retorna um resumo do estado atual do tape reading para um símbolo."""
        default_summary = {
            "symbol": symbol, 
            "cvd": 0, 
            "cvd_roc": 0.0, 
            "cvd_total": 0,
            "poc": None, 
            "supports": [], 
            "resistances": [],
            "cache_size": 0
        }
        
        # Busca trades recentes do CACHE
        recent_trades = self.trade_cache.get_recent_trades(symbol, 50)
        
        if not recent_trades:
            return default_summary

        # Calcula métricas
        cvd_calc = self.analyzers[symbol]['cvd_calc']
        cvd = cvd_calc.calculate_cvd_for_trades(recent_trades)
        roc = cvd_calc.update_and_get_roc(recent_trades, self.config.get('cvd_roc_period', 10))
        cvd_total = cvd_calc.get_cumulative_total(symbol)
        
        # Volume Profile
        poc = self.volume_profile.find_poc(symbol)
        current_price = recent_trades[-1].price
        sup_res = self.volume_profile.find_support_resistance(symbol, current_price)

        # Monta resumo completo
        summary = default_summary.copy()
        summary.update({
            "cvd": cvd, 
            "cvd_roc": roc, 
            "cvd_total": cvd_total,
            "poc": poc,
            "supports": sup_res.get('support', []),
            "resistances": sup_res.get('resistance', []),
            "cache_size": self.trade_cache.get_size(symbol)
        })
        
        return summary
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache (delegado ao cache centralizado)."""
        return self.trade_cache.get_stats()
    
    def clear_processed_trades(self, symbol: Optional[str] = None):
        """Limpa o registro de trades processados."""
        if symbol:
            self.processed_trade_ids[symbol].clear()
        else:
            for s in self.processed_trade_ids:
                self.processed_trade_ids[s].clear()
        
        logger.info(f"Registro de trades processados limpo para: {symbol or 'todos os símbolos'}")