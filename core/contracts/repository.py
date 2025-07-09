#core/contracts/repository.py
"""Interface para repositórios de sinais."""
from abc import ABC, abstractmethod
from typing import Dict, Any
from core.entities.signal import Signal


class ISignalRepository(ABC):
    """Interface para repositórios de sinais."""

    @abstractmethod
    def save(self, signal: Signal) -> None:
        """Salva um sinal."""
        pass

    @abstractmethod
    def save_arbitrage_check(self, arbitrage_data: Dict[str, Any]) -> None:
        """Salva uma verificação de arbitragem."""
        pass

    @abstractmethod
    def save_tape_reading_pattern(self, tape_data: Dict[str, Any]) -> None:
        """Salva um padrão de tape reading."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Garante que todos os dados em buffer sejam salvos."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Fecha o repositório e libera recursos."""
        pass
    
    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas sobre o repositório."""
        pass