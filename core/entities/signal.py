#core/entities/signal.py
"""Entidade Signal - representa sinais de trading."""
from datetime import datetime
from enum import Enum
from typing import Dict, Any
from pydantic import BaseModel, Field


class SignalSource(str, Enum):
    """Fonte do sinal."""
    ARBITRAGE = "ARBITRAGE"
    TAPE_READING = "TAPE_READING"
    CONFLUENCE = "CONFLUENCE"
    SYSTEM = "SYSTEM"
    MANIPULATION = "MANIPULATION"


class SignalLevel(str, Enum):
    """Nível de importância do sinal."""
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"


class Signal(BaseModel):
    """Representa um sinal de trading gerado pelo sistema."""
    source: SignalSource
    level: SignalLevel
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    details: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        frozen = True