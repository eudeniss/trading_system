#application/services/risk/types.py
"""Tipos para gerenciamento de risco."""
from enum import Enum
from typing import Dict, List, TypedDict, Optional
from datetime import datetime


class RiskLevel(str, Enum):
    """Níveis de risco."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalQuality(str, Enum):
    """Qualidade do sinal."""
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


class CircuitBreakerState(TypedDict):
    """Estado de um circuit breaker."""
    active: bool
    triggered_at: Optional[datetime]
    reason: str
    cooldown_seconds: int


class RiskMetrics(TypedDict):
    """Métricas de risco."""
    total_signals: int
    signals_approved: int
    signals_rejected: int
    consecutive_losses: int
    daily_pnl: float
    peak_pnl: float
    current_drawdown: float
    risk_level: RiskLevel


class SignalAssessment(TypedDict):
    """Avaliação de um sinal."""
    approved: bool
    risk_level: RiskLevel
    quality: SignalQuality
    reasons: List[str]
    recommendations: List[str]
    timestamp: datetime


class QualityEvaluation(TypedDict):
    """Resultado da avaliação de qualidade."""
    score: float
    rating: SignalQuality
    criteria: List[str]
    improvements: List[str]
    passed: bool


class ContextualRisk(TypedDict):
    """Risco contextual."""
    level: RiskLevel
    score: int
    factors: List[str]
    reason: str