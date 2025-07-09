#core/analysis/regime/types.py
"""Tipos e enums para análise de regime de mercado."""
from enum import Enum
from typing import Dict, List, TypedDict
from datetime import datetime


class MarketRegime(str, Enum):
    """Tipos de regime de mercado."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    QUIET = "QUIET"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"


class VolatilityLevel(str, Enum):
    """Níveis de volatilidade."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class LiquidityLevel(str, Enum):
    """Níveis de liquidez."""
    THIN = "THIN"
    NORMAL = "NORMAL"
    DEEP = "DEEP"


class RegimeMetrics(TypedDict):
    """Métricas do regime de mercado."""
    trend_strength: float
    trend_direction: int
    volatility: VolatilityLevel
    volatility_value: float
    liquidity: LiquidityLevel
    liquidity_score: float
    momentum: float
    market_depth_imbalance: float
    price_acceleration: float
    volume_profile_skew: float
    microstructure_score: float


class TrendAnalysis(TypedDict):
    """Resultado da análise de tendência."""
    strength: float
    direction: int
    slope: float
    ma_confirmation: bool


class VolatilityAnalysis(TypedDict):
    """Resultado da análise de volatilidade."""
    level: VolatilityLevel
    value: float
    parkinson: float
    atr_pct: float


class LiquidityAnalysis(TypedDict):
    """Resultado da análise de liquidez."""
    level: LiquidityLevel
    score: float
    avg_volume: float
    avg_spread: float
    avg_depth: float
    price_impact: float


class MicrostructureAnalysis(TypedDict):
    """Resultado da análise de microestrutura."""
    score: float
    depth_imbalance: float
    order_flow_imbalance: float
    size_distribution: float
    price_discovery: float