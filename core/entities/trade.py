#core/entities/trade.py
"""Entidade Trade - representa uma negociação no mercado."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class TradeSide(str, Enum):
    """Lado da negociação."""
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"

class Trade(BaseModel):
    """Representa um único negócio executado no mercado."""
    symbol: str
    price: float = Field(gt=0, description="Preço da negociação")
    volume: int = Field(gt=0, description="Volume negociado")
    side: TradeSide
    timestamp: datetime
    time_str: str
    
    class Config:
        frozen = True