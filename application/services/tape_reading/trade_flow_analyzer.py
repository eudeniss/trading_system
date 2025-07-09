# application/services/tape_reading/pattern_analyzer.py
"""Analisador de padrões de trades."""
from typing import List, Dict, Optional
import time
import logging

from core.entities.trade import Trade
from core.entities.book import OrderBook
from core.contracts.cache import ITradeCache
from core.analysis.statistics.volume_profile import VolumeProfileAnalyzer

logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """Responsável pela análise de padrões em trades."""
    
    def __init__(self, analyzers: Dict, cache: ITradeCache, config: Dict):
        self.analyzers = analyzers
        self.cache = cache
        self.config = config
        self.volume_profile = VolumeProfileAnalyzer()
        
        # Cache de análises
        self.analysis_cache = {}
        self.cache_ttl = config.get('analysis_cache_ttl', 0.5)
        
        # Estatísticas
        self.stats = {}
    
    def analyze_single_trade(self, trade: Trade) -> List[Dict]:
        """Analisa padrões em trade individual."""
        symbol = trade.symbol
        analyzers = self.analyzers[symbol]
        signals = []
        
        history = self.cache.get_recent_trades(symbol, 100)
        
        if len(history) < 10:
            return signals
        
        # Iceberg
        iceberg_result = analyzers['iceberg_detector'].detect(trade, history)
        if iceberg_result:
            signals.append({**iceberg_result, 'symbol': symbol})

        return signals
    
    def analyze_aggregated_patterns(self, symbol: str) -> List[Dict]:
        """Análise agregada com cache otimizado."""
        # Verifica cache
        cache_key = f"{symbol}_patterns"
        if cache_key in self.analysis_cache:
            cached_time, cached_result = self.analysis_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_result
        
        signals = []
        analyzers = self.analyzers[symbol]
        
        # Busca trades com diferentes janelas
        recent_trades_100 = self.cache.get_recent_trades(symbol, 100)
        
        if len(recent_trades_100) < 20:
            return []
        
        recent_trades_50 = recent_trades_100[-50:] if len(recent_trades_100) >= 50 else recent_trades_100
        recent_trades_20 = recent_trades_100[-20:] if len(recent_trades_100) >= 20 else recent_trades_100

        # Análises específicas...
        self._analyze_pace(symbol, recent_trades_50, signals)
        self._analyze_momentum(symbol, recent_trades_50, signals)
        self._analyze_absorption(symbol, recent_trades_100, signals)
        self._analyze_pressure(symbol, recent_trades_20, signals)
        self._analyze_volume_spike(symbol, recent_trades_50, signals)
        
        # Salva no cache
        self.analysis_cache[cache_key] = (time.time(), signals)
        return signals
    
    def analyze_specialized_patterns(self, symbol: str, trades: List[Trade], 
                                   current_book: Optional[OrderBook] = None) -> List[Dict]:
        """FASE 5: Análises com detectores especializados."""
        signals = []
        
        # 1. Pegada Institucional
        institutional_result = self.analyzers[symbol]['institutional'].detect(trades)
        if institutional_result:
            signals.append({**institutional_result, 'symbol': symbol})
            self._update_stats('institutional', institutional_result['pattern'])
        
        # 2. Liquidez Oculta
        if current_book:
            hidden_result = self.analyzers[symbol]['hidden_liquidity'].detect(symbol, trades, current_book)
            if hidden_result:
                signals.append({**hidden_result, 'symbol': symbol})
                self._update_stats('hidden_liquidity', hidden_result['pattern'])
        
        # 3. Delta Multi-timeframe
        delta_signals = self.analyzers[symbol]['multiframe_delta'].update(symbol, trades)
        for delta_signal in delta_signals:
            signals.append({**delta_signal, 'symbol': symbol})
            self._update_stats('multiframe', delta_signal['pattern'])
        
        # 4. Detector de Armadilhas
        if current_book:
            trap_signals = self.analyzers[symbol]['trap_detector'].detect(symbol, trades, current_book)
            for trap_signal in trap_signals:
                signals.append({**trap_signal, 'symbol': symbol})
                self._update_stats('trap', trap_signal['pattern'])
        
        return signals
    
    def _analyze_pace(self, symbol: str, trades: List[Trade], signals: List[Dict]):
        """Análise de pace."""
        pace_result = self.analyzers[symbol]['pace_analyzer'].update_and_check_anomaly()
        if pace_result:
            buy_volume = sum(t.volume for t in trades if t.side.value == 'BUY')
            sell_volume = sum(t.volume for t in trades if t.side.value == 'SELL')
            
            if buy_volume > sell_volume * 1.5:
                pace_result['direction'] = "COMPRA AGRESSIVA"
            elif sell_volume > buy_volume * 1.5:
                pace_result['direction'] = "VENDA AGRESSIVA"
            else:
                pace_result['direction'] = "BATALHA"
            
            pace_result['pattern'] = 'PACE_ANOMALY'
            signals.append({**pace_result, 'symbol': symbol})
    
    def _analyze_momentum(self, symbol: str, trades: List[Trade], signals: List[Dict]):
        """Análise de momentum."""
        roc_period = self.config.get('cvd_roc_period', 15)
        cvd_roc = self.analyzers[symbol]['cvd_calc'].update_and_get_roc(trades, roc_period)
        momentum_result = self.analyzers[symbol]['momentum_analyzer'].detect_divergence(trades, cvd_roc)
        if momentum_result:
            signals.append({**momentum_result, 'symbol': symbol})
    
    def _analyze_absorption(self, symbol: str, trades: List[Trade], signals: List[Dict]):
        """Análise de absorção."""
        absorption_result = self.analyzers[symbol]['absorption_detector'].detect(trades)
        if absorption_result:
            # Verifica se é exhaustion
            exhaustion_volume = self.config.get('exhaustion_volume', 314)
            if absorption_result['volume'] > exhaustion_volume:
                absorption_result['type'] = 'EXHAUSTION'
            signals.append({**absorption_result, 'symbol': symbol})
    
    def _analyze_pressure(self, symbol: str, trades: List[Trade], signals: List[Dict]):
        """Análise de pressão."""
        pressure_result = self.analyzers[symbol]['pressure_detector'].detect(trades)
        if pressure_result:
            signals.append({**pressure_result, 'symbol': symbol})
    
    def _analyze_volume_spike(self, symbol: str, trades: List[Trade], signals: List[Dict]):
        """Análise de spike de volume."""
        spike_result = self.analyzers[symbol]['volume_spike_detector'].detect(trades)
        if spike_result:
            signals.append({**spike_result, 'symbol': symbol})
    
    def _update_stats(self, category: str, pattern: str):
        """Atualiza estatísticas internas."""
        key = f"{category}_{pattern}"
        if key not in self.stats:
            self.stats[key] = 0
        self.stats[key] += 1
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do analisador."""
        return {
            'patterns_detected': dict(self.stats),
            'cache_entries': len(self.analysis_cache)
        }