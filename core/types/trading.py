#core/types/trading.py
"""Tipos customizados para o sistema de trading."""
from typing import TypedDict, Literal, Dict, List, Optional
from datetime import datetime


class ArbitrageOpportunity(TypedDict):
    """Estrutura de uma oportunidade de arbitragem."""
    spread: float
    profit: float
    action: str
    dol_price: float
    wdo_price: float
    is_profitable: bool
    profit_pct: float


class MarketSummary(TypedDict):
    """Resumo de mercado para um símbolo."""
    symbol: str
    cvd: int
    cvd_roc: float
    cvd_total: int
    poc: Optional[float]
    supports: List[float]
    resistances: List[float]
    cache_size: int


class RiskAssessment(TypedDict):
    """Avaliação de risco de um sinal."""
    approved: bool
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    quality: Literal['POOR', 'FAIR', 'GOOD', 'EXCELLENT']
    reasons: List[str]
    recommendations: List[str]
    timestamp: datetime


class RegimeMetrics(TypedDict):
    """Métricas do regime de mercado."""
    trend_strength: float
    trend_direction: int
    volatility: Literal['LOW', 'NORMAL', 'HIGH', 'EXTREME']
    volatility_value: float
    liquidity: Literal['THIN', 'NORMAL', 'DEEP']
    liquidity_score: float
    momentum: float
    market_depth_imbalance: float
    price_acceleration: float
    volume_profile_skew: float
    microstructure_score: float


class TradingContext(TypedDict):
    """Contexto completo de trading."""
    market_regime: str
    risk_level: str
    active_signals: int
    cvd_totals: Dict[str, int]
    flow_direction: Dict[str, str]
    last_update: datetime


# Type aliases
MarketRegimeType = Literal[
    'TRENDING_UP', 'TRENDING_DOWN', 'RANGING',
    'VOLATILE', 'QUIET', 'BREAKOUT', 'REVERSAL'
]

RiskLevelType = Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

SignalQualityType = Literal['POOR', 'FAIR', 'GOOD', 'EXCELLENT']

FlowDirectionType = Literal['COMPRA', 'VENDA', 'NEUTRO']