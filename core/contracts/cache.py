# core/contracts/cache.py
"""Interface para cache de trades - FASE 2 IMPLEMENTADA."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from core.entities.trade import Trade


class ITradeCache(ABC):
    """Interface para cache de trades com métodos da Fase 2."""
    
    @abstractmethod
    def add_trades(self, symbol: str, trades: List[Trade]) -> None:
        """
        Adiciona trades ao cache.
        
        Args:
            symbol: Símbolo do ativo (WDO, DOL)
            trades: Lista de trades para adicionar
        """
        pass
    
    @abstractmethod
    def get_recent_trades(self, symbol: str, count: int) -> List[Trade]:
        """
        Retorna os N trades mais recentes.
        
        Args:
            symbol: Símbolo do ativo
            count: Número de trades para retornar
            
        Returns:
            Lista dos trades mais recentes (até 'count' trades)
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # FASE 2.1 - MÉTODOS ADICIONAIS DO CACHE
    # ═══════════════════════════════════════════════════════════════
    
    @abstractmethod
    def get_all_trades(self, symbol: str) -> List[Trade]:
        """
        Retorna TODOS os trades em cache para um símbolo.
        Útil para análises que precisam do histórico completo.
        
        Args:
            symbol: Símbolo do ativo
            
        Returns:
            Lista com todos os trades em cache
        """
        pass
    
    @abstractmethod
    def get_trades_by_time_window(self, symbol: str, seconds: int) -> List[Trade]:
        """
        Retorna trades dos últimos N segundos.
        Útil para análises temporais específicas.
        
        Args:
            symbol: Símbolo do ativo
            seconds: Janela temporal em segundos
            
        Returns:
            Lista de trades dentro da janela temporal
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # MÉTODOS UTILITÁRIOS
    # ═══════════════════════════════════════════════════════════════
    
    @abstractmethod
    def get_size(self, symbol: str) -> int:
        """
        Retorna o tamanho atual do cache para um símbolo.
        
        Args:
            symbol: Símbolo do ativo
            
        Returns:
            Número de trades em cache
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache.
        
        Returns:
            Dicionário com estatísticas (hits, misses, tamanhos, etc)
        """
        pass
    
    @abstractmethod
    def clear(self, symbol: Optional[str] = None) -> None:
        """
        Limpa o cache.
        
        Args:
            symbol: Se especificado, limpa apenas este símbolo.
                   Se None, limpa todo o cache.
        """
        pass