#core/contracts/providers.py
"""Interface para provedores de dados de mercado."""
from abc import ABC, abstractmethod
from typing import Optional
from core.entities.market_data import MarketData


class IMarketDataProvider(ABC):
    """Interface para provedores de dados de mercado."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Conecta à fonte de dados."""
        pass
    
    @abstractmethod
    def get_market_data(self) -> Optional[MarketData]:
        """Retorna snapshot dos dados de mercado."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Fecha a conexão."""
        pass