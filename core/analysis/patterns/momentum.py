#core/analysis/patterns/momentum.py
"""Analisador de momentum e divergências."""
from typing import List, Optional, Dict
from core.entities.trade import Trade


class MomentumAnalyzer:
    """Detecta divergências e momentum extremo."""

    __slots__ = ['divergence_roc_threshold', 'extreme_roc_threshold']

    def __init__(self, divergence_roc_threshold: float = 50, extreme_roc_threshold: float = 100):
        self.divergence_roc_threshold = divergence_roc_threshold
        self.extreme_roc_threshold = extreme_roc_threshold

    def detect_divergence(self, recent_trades: List[Trade], cvd_roc: float) -> Optional[Dict]:
        """Detecta divergências entre preço e fluxo (CVD ROC)."""
        if not recent_trades or abs(cvd_roc) < self.divergence_roc_threshold:
            return None

        prices = [t.price for t in recent_trades]
        price_trend = prices[-1] - prices[0]
        current_price = prices[-1]

        # DIVERGÊNCIA BAIXISTA: Preço SOBE (+) mas CVD CAI (-)
        # Isso é bearish porque indica que apesar do preço subir, 
        # há mais vendedores (fluxo negativo)
        if price_trend > 1.0 and cvd_roc < -self.divergence_roc_threshold:
            return {
                "pattern": "DIVERGENCIA_BAIXA",
                "price": current_price,
                "cvd_roc": cvd_roc,
                "price_direction": "SUBINDO",
                "flow_direction": "CAINDO"
            }
        
        # DIVERGÊNCIA ALTISTA: Preço CAI (-) mas CVD SOBE (+)
        # Isso é bullish porque indica que apesar do preço cair,
        # há mais compradores (fluxo positivo)
        if price_trend < -1.0 and cvd_roc > self.divergence_roc_threshold:
            return {
                "pattern": "DIVERGENCIA_ALTA",
                "price": current_price,
                "cvd_roc": cvd_roc,
                "price_direction": "CAINDO",
                "flow_direction": "SUBINDO"
            }

        # Momentum Extremo (sem divergência, apenas força direcional)
        if abs(cvd_roc) > self.extreme_roc_threshold:
            return {
                "pattern": "MOMENTUM_EXTREMO",
                "price": current_price,
                "cvd_roc": cvd_roc,
                "direction": "COMPRA" if cvd_roc > 0 else "VENDA"
            }
            
        return None