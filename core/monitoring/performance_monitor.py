# core/monitoring/performance_monitor.py
"""Monitor de performance do sistema, ajustado para contabilizar totais."""
import time
import threading
import logging
from collections import defaultdict
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Monitora a performance do sistema, focando em contabilizar
    o total de trades processados de forma segura (thread-safe).
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Contadores para totais de trades
        self.counters = defaultdict(int)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Thread de monitoramento (mantida para futuras expansões)
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("PerformanceMonitor inicializado - modo TOTAIS")
        
    def record_trades_processed(self, count: int):
        """Registra o número de trades novos que foram processados."""
        # Garante que a atualização dos contadores é atômica e segura
        with self._lock:
            self.counters['total_trades'] += count

    def get_trade_totals(self) -> Dict[str, int]:
        """
        Retorna um dicionário com os totais de trades processados.
        Este método será usado pela interface gráfica.
        """
        with self._lock:
            # Retorna uma cópia para evitar condições de corrida
            return {
                'total': self.counters.get('total_trades', 0)
            }
            
    def get_performance_report(self) -> Dict[str, Any]:
        """Retorna um relatório simples de performance."""
        with self._lock:
            return {
                'counters': dict(self.counters)
            }
    
    def _monitor_loop(self):
        """Loop de monitoramento em background."""
        while self._running:
            # Este loop pode ser usado no futuro para coletar outras métricas
            # como uso de CPU/memória, sem impactar o loop principal.
            time.sleep(5) 

    def stop(self):
        """Para a thread de monitoramento de forma segura."""
        self._running = False
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)
        logger.info(
            f"PerformanceMonitor encerrado - "
            f"Total de trades processados na sessão: {self.counters.get('total_trades', 0):,}"
        )