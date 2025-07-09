#core/types/init.py 
"""
Tipos customizados para o sistema de trading.
TypedDict e tipos complexos que não são entidades.
"""

from .trading import (
    ArbitrageOpportunity,
    MarketSummary,
    RiskAssessment,
    MarketRegimeType,
    RiskLevelType,
    RegimeMetrics,
    TradingContext
)

__all__ = [
    'ArbitrageOpportunity',
    'MarketSummary',
    'RiskAssessment',
    'MarketRegimeType',
    'RiskLevelType',
    'RegimeMetrics',
    'TradingContext'
]