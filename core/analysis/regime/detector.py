#core/analysis/regime/detector.py
"""Detector principal de regime de mercado."""
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import deque
import logging

from core.entities.market_data import MarketData
from core.entities.trade import Trade
from core.entities.book import OrderBook
from .types import MarketRegime, RegimeMetrics
from .metrics import RegimeMetricsCalculator
from .analyzer import RegimeAnalyzer

logger = logging.getLogger(__name__)


class MarketRegimeDetector:
    """Detecta o regime atual do mercado."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        regime_config = self.config.get('market_regime', {})
        
        self.lookback_period = regime_config.get('lookback_period', 300)
        self.update_interval = regime_config.get('update_interval', 30)
        
        self.metrics_calculator = RegimeMetricsCalculator(self.config)
        self.analyzer = RegimeAnalyzer()
        
        # Histórico
        self.price_history = {
            'WDO': deque(maxlen=1000),
            'DOL': deque(maxlen=1000)
        }
        
        self.volume_history = {
            'WDO': deque(maxlen=1000),
            'DOL': deque(maxlen=1000)
        }
        
        self.spread_history = {
            'WDO': deque(maxlen=500),
            'DOL': deque(maxlen=500)
        }
        
        self.trade_flow = {
            'WDO': deque(maxlen=2000),
            'DOL': deque(maxlen=2000)
        }
        
        # Estado atual
        self.current_regime = {
            'WDO': MarketRegime.RANGING,
            'DOL': MarketRegime.RANGING
        }
        
        self.regime_confidence = {
            'WDO': 0.5,
            'DOL': 0.5
        }
        
        # Métricas
        self.metrics = {
            'WDO': self._create_empty_metrics(),
            'DOL': self._create_empty_metrics()
        }
        
        self.last_update = datetime.now()
        
        logger.info(f"MarketRegimeDetector inicializado - lookback: {self.lookback_period}s")
    
    def _create_empty_metrics(self) -> RegimeMetrics:
        """Cria estrutura vazia de métricas."""
        return {
            'trend_strength': 0.0,
            'trend_direction': 0,
            'volatility': 'NORMAL',
            'volatility_value': 0.0,
            'liquidity': 'NORMAL',
            'liquidity_score': 0.0,
            'momentum': 0.0,
            'market_depth_imbalance': 0.0,
            'price_acceleration': 0.0,
            'volume_profile_skew': 0.0,
            'microstructure_score': 0.0
        }
    
    def update(self, market_data: MarketData) -> Dict[str, MarketRegime]:
        """Atualiza a detecção de regime com novos dados."""
        now = datetime.now()
        
        # Atualiza apenas no intervalo definido
        if (now - self.last_update).seconds < self.update_interval:
            return self.current_regime
        
        for symbol, data in market_data.data.items():
            if data.trades:
                self._update_history(symbol, data.trades, data.book)
            
            # Analisa regime se houver dados suficientes
            if len(self.price_history[symbol]) >= 30:
                self._analyze_market_regime(symbol)
        
        self.last_update = now
        return self.current_regime
    
    def _update_history(self, symbol: str, trades: List[Trade], book: OrderBook):
        """Atualiza histórico de dados."""
        # Preços
        for trade in trades:
            self.price_history[symbol].append({
                'price': trade.price,
                'volume': trade.volume,
                'timestamp': trade.timestamp
            })
            
            self.trade_flow[symbol].append({
                'price': trade.price,
                'volume': trade.volume,
                'side': trade.side.value,
                'timestamp': trade.timestamp
            })
        
        # Volume
        total_volume = sum(t.volume for t in trades)
        if total_volume > 0:
            self.volume_history[symbol].append({
                'volume': total_volume,
                'timestamp': datetime.now()
            })
        
        # Spread
        if book and book.best_bid > 0 and book.best_ask > 0:
            self.spread_history[symbol].append({
                'spread': book.spread,
                'bid_size': book.bids[0].volume if book.bids else 0,
                'ask_size': book.asks[0].volume if book.asks else 0,
                'timestamp': datetime.now()
            })
    
    def _analyze_market_regime(self, symbol: str):
        """Analisa e determina o regime de mercado."""
        prices = [p['price'] for p in list(self.price_history[symbol])[-100:]]
        
        if len(prices) < 30:
            return
        
        # 1. Tendência
        trend = self.metrics_calculator.calculate_trend(prices)
        self.metrics[symbol]['trend_strength'] = trend['strength']
        self.metrics[symbol]['trend_direction'] = trend['direction']
        
        # 2. Volatilidade
        volatility = self.metrics_calculator.calculate_volatility(prices)
        self.metrics[symbol]['volatility'] = volatility['level']
        self.metrics[symbol]['volatility_value'] = volatility['value']
        
        # 3. Momentum
        momentum = self.metrics_calculator.calculate_momentum(prices)
        self.metrics[symbol]['momentum'] = momentum
        
        # 4. Liquidez
        volumes = [v['volume'] for v in list(self.volume_history[symbol])[-30:]]
        spreads = [s['spread'] for s in list(self.spread_history[symbol])[-30:]]
        depths = list(self.spread_history[symbol])[-30:]
        
        liquidity = self.metrics_calculator.calculate_liquidity(volumes, spreads, depths)
        self.metrics[symbol]['liquidity'] = liquidity['level']
        self.metrics[symbol]['liquidity_score'] = liquidity['score']
        
        # 5. Microestrutura
        trades = list(self.trade_flow[symbol])[-100:]
        spreads_data = list(self.spread_history[symbol])[-50:]
        
        microstructure = self.analyzer.analyze_microstructure(trades, spreads_data)
        self.metrics[symbol]['microstructure_score'] = microstructure['score']
        self.metrics[symbol]['market_depth_imbalance'] = microstructure['depth_imbalance']
        
        # 6. Determina regime
        regime, confidence = self.analyzer.determine_regime(
            trend=trend,
            volatility=volatility,
            momentum=momentum,
            current_regime=self.current_regime[symbol]
        )
        
        self.current_regime[symbol] = regime
        self.regime_confidence[symbol] = confidence
        
        # Log mudanças significativas
        if confidence > 0.7:
            logger.info(f"{symbol} - Regime: {regime.value} (Confiança: {confidence:.2f})")
    
    def get_regime_summary(self, symbol: str) -> Dict:
        """Retorna resumo completo do regime."""
        return {
            'regime': self.current_regime.get(symbol, MarketRegime.RANGING),
            'confidence': self.regime_confidence.get(symbol, 0.5),
            'metrics': self.metrics.get(symbol, self._create_empty_metrics()),
            'recommendations': self.analyzer.get_regime_recommendations(
                self.current_regime[symbol],
                self.metrics[symbol]
            )
        }
    
    def get_adaptive_parameters(self, symbol: str) -> Dict[str, float]:
        """Retorna parâmetros adaptados ao regime atual."""
        regime = self.current_regime.get(symbol, MarketRegime.RANGING)
        metrics = self.metrics.get(symbol, {})
        
        params = {
            'signal_threshold_multiplier': 1.0,
            'stop_loss_multiplier': 1.0,
            'position_size_multiplier': 1.0,
            'confirmation_requirement': 'NORMAL'
        }
        
        # Ajusta baseado no regime
        if regime == MarketRegime.TRENDING_UP:
            params['signal_threshold_multiplier'] = 0.9
            params['stop_loss_multiplier'] = 1.2
            params['position_size_multiplier'] = 1.1
        
        elif regime == MarketRegime.TRENDING_DOWN:
            params['signal_threshold_multiplier'] = 0.9
            params['stop_loss_multiplier'] = 0.8
            params['position_size_multiplier'] = 0.9
        
        elif regime == MarketRegime.VOLATILE:
            params['signal_threshold_multiplier'] = 1.3
            params['stop_loss_multiplier'] = 1.5
            params['position_size_multiplier'] = 0.5
            params['confirmation_requirement'] = 'HIGH'
        
        elif regime == MarketRegime.QUIET:
            params['signal_threshold_multiplier'] = 1.5
            params['position_size_multiplier'] = 0.7
        
        elif regime == MarketRegime.BREAKOUT:
            params['signal_threshold_multiplier'] = 0.8
            params['stop_loss_multiplier'] = 1.0
            params['position_size_multiplier'] = 1.2
            params['confirmation_requirement'] = 'LOW'
        
        # Ajusta por volatilidade
        if metrics.get('volatility') == 'EXTREME':
            params['position_size_multiplier'] *= 0.5
            params['stop_loss_multiplier'] *= 1.5
        
        # Ajusta por liquidez
        if metrics.get('liquidity') == 'THIN':
            params['position_size_multiplier'] *= 0.7
            params['signal_threshold_multiplier'] *= 1.2
        
        return params