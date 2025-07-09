# infrastructure/cache/memory.py
"""Cache em memória para trades - FASE 2 IMPLEMENTADA."""
from collections import deque
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import threading
import logging

from core.entities.trade import Trade
from core.contracts.cache import ITradeCache

logger = logging.getLogger(__name__)


class TradeMemoryCache(ITradeCache):
    """
    Implementação em memória do cache de trades.
    Thread-safe e otimizada para performance.
    FASE 2: Inclui get_all_trades() e get_trades_by_time_window()
    """
    
    __slots__ = ['max_size', 'cache', 'lock', 'stats', 'metadata']
    
    def __init__(self, max_size: int = 10000):
        """
        Inicializa o cache em memória.
        
        Args:
            max_size: Tamanho máximo do cache por símbolo
        """
        self.max_size = max_size
        self.cache: Dict[str, deque] = {}
        self.lock = threading.RLock()  # Reentrant lock para thread safety
        
        # Estatísticas de uso
        self.stats = {
            'hits': 0,
            'misses': 0,
            'additions': 0,
            'evictions': 0
        }
        
        # Metadados por símbolo
        self.metadata: Dict[str, Dict] = {}
        
        logger.info(f"TradeMemoryCache inicializado com max_size={max_size}")
    
    def add_trades(self, symbol: str, trades: List[Trade]) -> None:
        """
        Adiciona múltiplos trades de forma eficiente e thread-safe.
        
        Args:
            symbol: Símbolo do ativo
            trades: Lista de trades para adicionar
        """
        if not trades:
            return
            
        with self.lock:
            # Inicializa cache do símbolo se necessário
            if symbol not in self.cache:
                self.cache[symbol] = deque(maxlen=self.max_size)
                self.metadata[symbol] = {
                    'created_at': datetime.now(),
                    'last_update': datetime.now(),
                    'total_added': 0
                }
            
            # Calcula quantos serão removidos por eviction
            current_size = len(self.cache[symbol])
            new_trades_count = len(trades)
            if current_size + new_trades_count > self.max_size:
                evictions = min(current_size, current_size + new_trades_count - self.max_size)
                self.stats['evictions'] += evictions
            
            # Adiciona todos de uma vez (mais eficiente)
            self.cache[symbol].extend(trades)
            self.stats['additions'] += new_trades_count
            
            # Atualiza metadados
            self.metadata[symbol]['last_update'] = datetime.now()
            self.metadata[symbol]['total_added'] += new_trades_count
            
            # Log periódico
            if self.metadata[symbol]['total_added'] % 1000 == 0:
                logger.debug(
                    f"Cache {symbol}: {len(self.cache[symbol])} trades, "
                    f"total adicionados: {self.metadata[symbol]['total_added']}"
                )
    
    def get_recent_trades(self, symbol: str, count: int) -> List[Trade]:
        """
        Retorna últimos N trades de forma thread-safe.
        
        Args:
            symbol: Símbolo do ativo
            count: Número de trades desejados
            
        Returns:
            Lista com até 'count' trades mais recentes
        """
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                return []
            
            self.stats['hits'] += 1
            
            # IMPORTANTE: Cria uma CÓPIA da deque para evitar race conditions
            all_trades = list(self.cache[symbol])  # Cópia completa
            
            # Retorna apenas os últimos N trades
            if count >= len(all_trades):
                return all_trades  # Já é uma cópia
            else:
                return all_trades[-count:]  # Slice da cópia
    
    # ═══════════════════════════════════════════════════════════════
    # FASE 2.1 - MÉTODOS ADICIONAIS DO CACHE
    # ═══════════════════════════════════════════════════════════════
    
    def get_all_trades(self, symbol: str) -> List[Trade]:
        """
        Retorna TODOS os trades em cache para um símbolo (thread-safe).
        
        Útil para:
        - Análise de perfil de volume completo
        - Detecção de zonas de acumulação/distribuição
        - Backtesting de estratégias
        
        Args:
            symbol: Símbolo do ativo
            
        Returns:
            Lista com todos os trades em cache (cópia)
        """
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                logger.debug(f"get_all_trades: símbolo {symbol} não encontrado no cache")
                return []
            
            self.stats['hits'] += 1
            
            # Retorna uma CÓPIA completa para segurança
            all_trades = list(self.cache[symbol])
            
            logger.debug(f"get_all_trades: retornando {len(all_trades)} trades para {symbol}")
            return all_trades
    
    def get_trades_by_time_window(self, symbol: str, seconds: int) -> List[Trade]:
        """
        Retorna trades dos últimos N segundos (thread-safe).
        
        Útil para:
        - Análise de intensidade temporal
        - Comparação de liquidez em diferentes períodos
        - Detecção de padrões temporais
        
        Args:
            symbol: Símbolo do ativo
            seconds: Janela temporal em segundos
            
        Returns:
            Lista de trades dentro da janela temporal
        """
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                logger.debug(f"get_trades_by_time_window: símbolo {symbol} não encontrado")
                return []
            
            self.stats['hits'] += 1
            
            # Calcula o tempo de corte
            cutoff_time = datetime.now() - timedelta(seconds=seconds)
            
            # Itera de trás pra frente para eficiência
            # (trades mais recentes estão no final da deque)
            result = []
            for trade in reversed(self.cache[symbol]):
                if trade.timestamp > cutoff_time:
                    result.append(trade)
                else:
                    # Como os trades estão ordenados por tempo,
                    # podemos parar quando encontrar um fora da janela
                    break
            
            # Retorna na ordem cronológica correta
            result.reverse()
            
            logger.debug(
                f"get_trades_by_time_window: {len(result)} trades "
                f"nos últimos {seconds}s para {symbol}"
            )
            return result
    
    # ═══════════════════════════════════════════════════════════════
    # MÉTODOS UTILITÁRIOS
    # ═══════════════════════════════════════════════════════════════
    
    def get_size(self, symbol: str) -> int:
        """
        Retorna quantidade de trades em cache para um símbolo.
        
        Args:
            symbol: Símbolo do ativo
            
        Returns:
            Número de trades em cache
        """
        with self.lock:
            return len(self.cache.get(symbol, []))
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas detalhadas do cache.
        
        Returns:
            Dicionário com métricas de performance e uso
        """
        with self.lock:
            total_trades = sum(len(trades) for trades in self.cache.values())
            
            # Calcula taxa de hit
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            # Info por símbolo
            symbols_info = {}
            for symbol, trades in self.cache.items():
                meta = self.metadata.get(symbol, {})
                
                # Informações básicas
                info = {
                    'count': len(trades),
                    'is_full': len(trades) == self.max_size,
                    'total_added': meta.get('total_added', 0),
                    'last_update': meta.get('last_update', datetime.now()).isoformat()
                }
                
                # Adiciona timestamps se houver trades
                if trades:
                    info['oldest_trade'] = trades[0].timestamp.isoformat()
                    info['newest_trade'] = trades[-1].timestamp.isoformat()
                    
                    # Calcula janela temporal
                    time_span = trades[-1].timestamp - trades[0].timestamp
                    info['time_span_seconds'] = time_span.total_seconds()
                else:
                    info['oldest_trade'] = None
                    info['newest_trade'] = None
                    info['time_span_seconds'] = 0
                
                symbols_info[symbol] = info
            
            return {
                'basic_stats': {
                    'hits': self.stats['hits'],
                    'misses': self.stats['misses'],
                    'additions': self.stats['additions'],
                    'evictions': self.stats['evictions'],
                    'hit_rate': f"{hit_rate:.1f}%"
                },
                'cache_info': {
                    'total_trades': total_trades,
                    'max_size_per_symbol': self.max_size,
                    'symbols_cached': list(self.cache.keys()),
                    'memory_estimate_mb': (total_trades * 500) / (1024 * 1024)  # ~500 bytes por trade
                },
                'symbols': symbols_info
            }
    
    def clear(self, symbol: Optional[str] = None) -> None:
        """
        Limpa o cache (todos os símbolos ou apenas um).
        
        Args:
            symbol: Se especificado, limpa apenas este símbolo
        """
        with self.lock:
            if symbol:
                if symbol in self.cache:
                    trades_removed = len(self.cache[symbol])
                    del self.cache[symbol]
                    if symbol in self.metadata:
                        del self.metadata[symbol]
                    logger.info(f"Cache limpo para {symbol}: {trades_removed} trades removidos")
                else:
                    logger.warning(f"Tentativa de limpar cache inexistente para {symbol}")
            else:
                total_removed = sum(len(trades) for trades in self.cache.values())
                self.cache.clear()
                self.metadata.clear()
                
                # Reset estatísticas também
                self.stats = {
                    'hits': 0,
                    'misses': 0,
                    'additions': 0,
                    'evictions': 0
                }
                
                logger.info(f"Cache completamente limpo: {total_removed} trades removidos")