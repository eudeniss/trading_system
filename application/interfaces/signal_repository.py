# application/interfaces/signal_repository.py
from abc import ABC, abstractmethod
from domain.entities.signal import Signal

class ISignalRepository(ABC):
    """Interface para repositórios de sinais."""

    @abstractmethod
    def save(self, signal: Signal) -> None:
        """Salva um sinal."""
        pass

    @abstractmethod
    def save_arbitrage_check(self, arbitrage_data: dict) -> None:
        """Salva uma verificação de arbitragem."""
        pass

    @abstractmethod
    def save_tape_reading_pattern(self, tape_data: dict) -> None:
        """Salva um padrão de tape reading."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Garante que todos os dados em buffer sejam salvos."""
        pass