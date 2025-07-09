#core/factories/infrastructure.py
"""Factory para criar componentes de infraestrutura."""
from typing import Dict, Any
from pathlib import Path

from core.contracts.cache import ITradeCache
from core.contracts.messaging import ISystemEventBus
from core.contracts.providers import IMarketDataProvider
from core.contracts.repository import ISignalRepository

from infrastructure.cache.memory import TradeMemoryCache
from infrastructure.messaging.event_bus import LocalEventBus
from infrastructure.data.excel_provider import ExcelMarketProvider
from infrastructure.persistence.json_logs import JsonLogRepository


class InfrastructureFactory:
    """Factory para componentes de infraestrutura."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def create_cache(self) -> ITradeCache:
        """
        Cria cache de trades.
        FASE 2: Cache já tem os métodos get_all_trades() e get_trades_by_time_window()
        """
        buffer_size = self.config['tape_reading'].get('buffer_size', 10000)
        return TradeMemoryCache(max_size=buffer_size)
    
    def create_event_bus(self) -> ISystemEventBus:
        """Cria barramento de eventos."""
        return LocalEventBus()
    
    def create_market_provider(self) -> IMarketDataProvider:
        """
        Cria provider de dados de mercado.
        FASE 2: Passa o config completo para o ExcelMarketProvider
        """
        excel_config = self.config['excel']
        
        # FASE 2: Agora passa o config completo para o provider
        return ExcelMarketProvider(
            file_path=excel_config['file'],
            sheet_name=excel_config['sheet'],
            config=self.config  # Passa todo o config para usar WDO/DOL ranges
        )
    
    def create_signal_repository(self) -> ISignalRepository:
        """Cria repositório de sinais."""
        log_dir = self.config['system'].get('log_dir', 'logs')
        
        # Pega configurações de logging se disponíveis
        logging_config = self.config.get('logging', {})
        flush_interval = logging_config.get('flush_interval', 5)
        
        return JsonLogRepository(
            log_dir=log_dir,
            flush_interval=flush_interval
        )