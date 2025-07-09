# application/services/tape_reading/types.py
"""Tipos e classes de dados para o serviço de Tape Reading."""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

@dataclass
class PendingPattern:
    """Representa um padrão aguardando confirmação (FASE 4.1)."""
    id: str
    pattern: str
    symbol: str
    data: Dict
    created_at: datetime
    expires_at: datetime
    confirmation_criteria: Dict
    attempts: int = 0
    last_check: Optional[datetime] = None