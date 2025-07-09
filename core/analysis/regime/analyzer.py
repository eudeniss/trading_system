#core/analysis/regime/analyzer.py
"""Analisador de regime de mercado."""
from typing import Dict, List, Tuple
import numpy as np
import logging

from .types import MarketRegime, RegimeMetrics, MicrostructureAnalysis

logger = logging.getLogger(__name__)


class RegimeAnalyzer:
    """Analisa e determina o regime de mercado."""
    
    def __init__(self):
        self.regime_weights = {
            'trend': 0.4,
            'volatility': 0.3,
            'momentum': 0.2,
            'microstructure': 0.1
        }
    
    def determine_regime(self, trend: Dict, volatility: Dict, momentum: float,
                        current_regime: MarketRegime) -> Tuple[MarketRegime, float]:
        """Determina o regime baseado nas análises."""
        # Sistema de pontuação
        scores = {
            MarketRegime.TRENDING_UP: 0,
            MarketRegime.TRENDING_DOWN: 0,
            MarketRegime.RANGING: 0,
            MarketRegime.VOLATILE: 0,
            MarketRegime.QUIET: 0,
            MarketRegime.BREAKOUT: 0,
            MarketRegime.REVERSAL: 0
        }
        
        # Extrai valores
        trend_strength = trend['strength']
        trend_direction = trend['direction']
        vol_level = volatility['level']
        
        # TRENDING UP
        if trend_direction > 0:
            scores[MarketRegime.TRENDING_UP] = (
                trend_strength * 0.4 + 
                max(momentum, 0) * 0.3
            )
            if vol_level == 'NORMAL':
                scores[MarketRegime.TRENDING_UP] += 0.2
        
        # TRENDING DOWN
        if trend_direction < 0:
            scores[MarketRegime.TRENDING_DOWN] = (
                trend_strength * 0.4 + 
                abs(min(momentum, 0)) * 0.3
            )
            if vol_level == 'NORMAL':
                scores[MarketRegime.TRENDING_DOWN] += 0.2
        
        # RANGING
        if abs(trend_direction) == 0 or trend_strength < 0.3:
            scores[MarketRegime.RANGING] = (1 - trend_strength) * 0.5
            if vol_level == 'LOW':
                scores[MarketRegime.RANGING] += 0.3
            if abs(momentum) < 0.3:
                scores[MarketRegime.RANGING] += 0.2
        
        # VOLATILE
        if vol_level in ['HIGH', 'EXTREME']:
            scores[MarketRegime.VOLATILE] = 0.5
            if abs(momentum) > 0.5:
                scores[MarketRegime.VOLATILE] += 0.3
        
        # QUIET
        if vol_level == 'LOW' and abs(momentum) < 0.2:
            scores[MarketRegime.QUIET] = 0.6
            if trend_strength < 0.2:
                scores[MarketRegime.QUIET] += 0.2
        
        # BREAKOUT
        if abs(momentum) > 0.7 and trend_strength > 0.5:
            scores[MarketRegime.BREAKOUT] = (
                abs(momentum) * 0.5 + 
                trend_strength * 0.3
            )
            if vol_level in ['HIGH', 'EXTREME']:
                scores[MarketRegime.BREAKOUT] += 0.2
        
        # Determina regime com maior score
        best_regime = max(scores.items(), key=lambda x: x[1])
        regime = best_regime[0]
        confidence = min(best_regime[1], 1.0)
        
        # Ajusta confiança por consistência
        if regime == current_regime:
            confidence = min(confidence * 1.1, 1.0)
        else:
            confidence *= 0.9
        
        return regime, confidence
    
    def analyze_microstructure(self, trades: List[Dict], spreads: List[Dict]) -> MicrostructureAnalysis:
        """Analisa a microestrutura do mercado."""
        if len(trades) < 20 or len(spreads) < 10:
            return {
                'score': 0.5,
                'depth_imbalance': 0,
                'order_flow_imbalance': 0,
                'size_distribution': 0,
                'price_discovery': 0
            }
        
        # Order Flow Imbalance
        buy_volume = sum(t['volume'] for t in trades if t['side'] == 'BUY')
        sell_volume = sum(t['volume'] for t in trades if t['side'] == 'SELL')
        total_volume = buy_volume + sell_volume
        
        ofi = (buy_volume - sell_volume) / total_volume if total_volume > 0 else 0
        
        # Depth Imbalance
        imbalances = []
        for spread in spreads:
            total_depth = spread['bid_size'] + spread['ask_size']
            if total_depth > 0:
                imbalance = (spread['bid_size'] - spread['ask_size']) / total_depth
                imbalances.append(imbalance)
        
        avg_depth_imbalance = np.mean(imbalances) if imbalances else 0
        
        # Trade Size Distribution
        trade_sizes = [t['volume'] for t in trades]
        if trade_sizes:
            size_cv = np.std(trade_sizes) / np.mean(trade_sizes)
        else:
            size_cv = 0
        
        # Price Discovery
        price_changes = []
        for i in range(1, len(trades)):
            if trades[i]['price'] != trades[i-1]['price']:
                change = abs(trades[i]['price'] - trades[i-1]['price'])
                price_changes.append(change)
        
        avg_tick_size = np.mean(price_changes) if price_changes else 0
        
        # Score
        ofi_score = abs(ofi)
        depth_score = abs(avg_depth_imbalance)
        size_score = min(size_cv / 2, 1)
        discovery_score = min(avg_tick_size / 1.0, 1)
        
        microstructure_score = np.mean([ofi_score, depth_score, size_score, discovery_score])
        
        return {
            'score': microstructure_score,
            'depth_imbalance': avg_depth_imbalance,
            'order_flow_imbalance': ofi,
            'size_distribution': size_cv,
            'price_discovery': avg_tick_size
        }
    
    def get_regime_recommendations(self, regime: MarketRegime, metrics: RegimeMetrics) -> List[str]:
        """Retorna recomendações baseadas no regime."""
        recommendations = []
        
        if regime == MarketRegime.TRENDING_UP:
            recommendations.append("Favorecer sinais de compra em pullbacks")
            recommendations.append("Usar stops mais largos para não sair prematuramente")
            if metrics.get('volatility') == 'LOW':
                recommendations.append("Considerar aumentar tamanho de posição")
        
        elif regime == MarketRegime.TRENDING_DOWN:
            recommendations.append("Favorecer sinais de venda em rallies")
            recommendations.append("Ser mais agressivo com stops de proteção")
            if metrics.get('liquidity') == 'THIN':
                recommendations.append("Cuidado com slippage em saídas")
        
        elif regime == MarketRegime.RANGING:
            recommendations.append("Operar reversões nos extremos do range")
            recommendations.append("Usar stops apertados")
            recommendations.append("Evitar trades no meio do range")
        
        elif regime == MarketRegime.VOLATILE:
            recommendations.append("Reduzir tamanho de posição")
            recommendations.append("Aguardar confirmações extras")
            recommendations.append("Evitar stops muito próximos")
        
        elif regime == MarketRegime.QUIET:
            recommendations.append("Mercado sem direção clara")
            recommendations.append("Considerar ficar de fora")
            recommendations.append("Aguardar aumento de atividade")
        
        elif regime == MarketRegime.BREAKOUT:
            recommendations.append("Seguir a direção do breakout")
            recommendations.append("Usar stops técnicos")
            recommendations.append("Considerar adicionar em pullbacks")
        
        elif regime == MarketRegime.REVERSAL:
            recommendations.append("Aguardar confirmação da reversão")
            recommendations.append("Não apressar entrada")
            recommendations.append("Usar gestão de risco rigorosa")
        
        return recommendations