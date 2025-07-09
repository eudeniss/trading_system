#core/analysis/regime/metrics.py
"""Cálculos de métricas para análise de regime."""
import numpy as np
from typing import List, Dict, Tuple
from collections import deque
from datetime import datetime, timedelta

from .types import VolatilityLevel, LiquidityLevel, TrendAnalysis, VolatilityAnalysis, LiquidityAnalysis


class RegimeMetricsCalculator:
    """Calcula métricas para detecção de regime."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.adaptive_params = self.config.get('adaptive_params', {
            'trend_threshold': 0.001,
            'volatility_multiplier': 1.5,
            'volume_spike_threshold': 3.0,
            'liquidity_depth_levels': 5
        })
    
    def calculate_trend(self, prices: List[float]) -> TrendAnalysis:
        """Calcula métricas de tendência."""
        if len(prices) < 20:
            return {
                'strength': 0.0,
                'direction': 0,
                'slope': 0.0,
                'ma_confirmation': False
            }
        
        # Regressão linear
        x = np.arange(len(prices))
        slope, intercept = np.polyfit(x, prices, 1)
        
        # Normaliza slope
        avg_price = np.mean(prices)
        normalized_slope = slope / avg_price if avg_price > 0 else 0
        
        # R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((prices - y_pred) ** 2)
        ss_tot = np.sum((prices - np.mean(prices)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Média móvel para confirmação
        sma_20 = np.mean(prices[-20:])
        sma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else sma_20
        ma_signal = 1 if sma_20 > sma_50 else -1 if sma_20 < sma_50 else 0
        
        # Direção
        direction = 1 if normalized_slope > self.adaptive_params['trend_threshold'] else \
                   -1 if normalized_slope < -self.adaptive_params['trend_threshold'] else 0
        
        # Ajusta força com confirmação de MA
        if direction != 0 and ma_signal == direction:
            strength = min(r_squared * 1.2, 1.0)
        else:
            strength = r_squared * 0.8
        
        return {
            'strength': strength,
            'direction': direction,
            'slope': normalized_slope,
            'ma_confirmation': ma_signal == direction
        }
    
    def calculate_volatility(self, prices: List[float]) -> VolatilityAnalysis:
        """Calcula métricas de volatilidade."""
        if len(prices) < 20:
            return {
                'level': VolatilityLevel.NORMAL,
                'value': 0.0,
                'parkinson': 0.0,
                'atr_pct': 0.0
            }
        
        # Retornos
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns) * np.sqrt(252)
        
        # Volatilidade de Parkinson
        period_high_low = []
        for i in range(0, len(prices)-5, 5):
            period_prices = prices[i:i+5]
            if period_prices:
                hl_vol = (max(period_prices) - min(period_prices)) / np.mean(period_prices)
                period_high_low.append(hl_vol)
        
        parkinson_vol = np.mean(period_high_low) if period_high_low else 0
        
        # ATR-like
        true_ranges = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        atr = np.mean(true_ranges[-20:]) if true_ranges else 0
        atr_pct = (atr / np.mean(prices)) * 100 if prices else 0
        
        # Classifica
        if volatility < 0.15 and atr_pct < 0.5:
            level = VolatilityLevel.LOW
        elif volatility < 0.25 and atr_pct < 1.0:
            level = VolatilityLevel.NORMAL
        elif volatility < 0.40 and atr_pct < 2.0:
            level = VolatilityLevel.HIGH
        else:
            level = VolatilityLevel.EXTREME
        
        return {
            'level': level,
            'value': volatility,
            'parkinson': parkinson_vol,
            'atr_pct': atr_pct
        }
    
    def calculate_momentum(self, prices: List[float]) -> float:
        """Calcula o momentum do mercado."""
        if len(prices) < 20:
            return 0.0
        
        # RSI simplificado
        deltas = np.diff(prices)
        gains = deltas[deltas > 0]
        losses = -deltas[deltas < 0]
        
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0
        
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # ROC
        if len(prices) >= 10:
            roc = ((prices[-1] - prices[-10]) / prices[-10]) * 100
        else:
            roc = 0
        
        # MACD-like
        if len(prices) >= 26:
            ema_12 = self._calculate_ema(prices[-26:], 12)
            ema_26 = self._calculate_ema(prices[-26:], 26)
            macd = ema_12 - ema_26
            signal_line = self._calculate_ema([macd], 9)
            macd_histogram = macd - signal_line
        else:
            macd_histogram = 0
        
        # Normaliza
        rsi_momentum = (rsi - 50) / 50
        roc_momentum = np.tanh(roc / 10)
        macd_momentum = np.tanh(macd_histogram)
        
        return np.mean([rsi_momentum, roc_momentum, macd_momentum])
    
    def calculate_liquidity(self, volumes: List[float], spreads: List[float], 
                          depths: List[Dict]) -> LiquidityAnalysis:
        """Calcula métricas de liquidez."""
        # Volume médio
        avg_volume = np.mean(volumes) if volumes else 0
        
        # Spread médio
        avg_spread = np.mean(spreads) if spreads else 0
        
        # Profundidade média
        total_depths = []
        for depth in depths:
            total = depth.get('bid_size', 0) + depth.get('ask_size', 0)
            total_depths.append(total)
        avg_depth = np.mean(total_depths) if total_depths else 0
        
        # Kyle's Lambda (simplificado)
        price_impacts = []
        if len(volumes) > 1 and len(spreads) > 1:
            for i in range(1, min(len(volumes), len(spreads))):
                if volumes[i] > 0:
                    impact = spreads[i] / volumes[i]
                    price_impacts.append(impact)
        
        avg_impact = np.mean(price_impacts) if price_impacts else 0
        
        # Score de liquidez
        volume_score = min(avg_volume / 100, 1.0)
        spread_score = max(1 - (avg_spread / 2.0), 0)
        depth_score = min(avg_depth / 200, 1.0)
        impact_score = max(1 - (avg_impact * 1000), 0)
        
        liquidity_score = np.mean([volume_score, spread_score, depth_score, impact_score])
        
        # Classifica
        if liquidity_score < 0.3:
            level = LiquidityLevel.THIN
        elif liquidity_score < 0.7:
            level = LiquidityLevel.NORMAL
        else:
            level = LiquidityLevel.DEEP
        
        return {
            'level': level,
            'score': liquidity_score,
            'avg_volume': avg_volume,
            'avg_spread': avg_spread,
            'avg_depth': avg_depth,
            'price_impact': avg_impact
        }
    
    def _calculate_ema(self, data: List[float], period: int) -> float:
        """Calcula Exponential Moving Average."""
        if not data or period <= 0:
            return 0
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        
        for price in data[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema