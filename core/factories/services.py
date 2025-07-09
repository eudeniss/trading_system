# core/factories/services.py
"""Factory para criar serviços com Mercado Calculado integrado."""
from typing import Dict, Any, Optional
from datetime import datetime

from core.contracts.cache import ITradeCache
from core.contracts.messaging import ISystemEventBus
from application.services.tape_reading import TapeReadingService
from application.services.risk.manager import RiskManager
# IMPORTANTE: Atualize o import para usar o novo módulo
from application.services.calculated_market.analyzer import CalculatedMarketAnalyzer
from core.analysis.regime.detector import MarketRegimeDetector
from core.analysis.statistics.aggregator import MarketStatsAggregator
from core.monitoring.performance_monitor import PerformanceMonitor


class ServiceFactory:
    """Factory para serviços de aplicação com Mercado Calculado."""
    
    def __init__(self, config: Dict[str, Any], event_bus: ISystemEventBus, 
                 cache: ITradeCache, target_date: Optional[datetime] = None):
        """
        Inicializa a factory.
        
        Args:
            config: Configurações do sistema
            event_bus: Barramento de eventos
            cache: Cache de trades
            target_date: Data alvo para replay (None = ao vivo)
        """
        self.config = config
        self.event_bus = event_bus
        self.cache = cache
        self.target_date = target_date
    
    def create_all_services(self) -> Dict[str, Any]:
        """Cria todos os serviços com integração completa."""
        services = {}
        
        # Serviços básicos
        services['tape_reading'] = self.create_tape_reading_service()
        services['risk'] = self.create_risk_service()
        services['regime'] = self.create_regime_detector()
        
        # NOVO: Mercado Calculado (Frajola) - agora modularizado
        services['calculated_market'] = self.create_calculated_market_analyzer()
        
        # Monitor de performance
        services['performance_monitor'] = self.create_performance_monitor()
        
        # Agregador de estatísticas
        services['stats_aggregator'] = self.create_stats_aggregator()
        
        return services
    
    def create_tape_reading_service(self) -> TapeReadingService:
        """Cria serviço de tape reading completo."""
        return TapeReadingService(
            event_bus=self.event_bus,
            cache=self.cache,
            config=self.config
        )
    
    def create_risk_service(self) -> RiskManager:
        """Cria serviço de risk management adaptativo."""
        return RiskManager(
            event_bus=self.event_bus,
            config=self.config['risk_management']
        )
    
    def create_regime_detector(self) -> MarketRegimeDetector:
        """Cria detector de regime de mercado."""
        return MarketRegimeDetector(self.config)
    
    def create_calculated_market_analyzer(self) -> CalculatedMarketAnalyzer:
        """
        Cria analisador de mercado calculado (Frajola) modularizado.
        Passa a data alvo se estiver em modo replay.
        """
        return CalculatedMarketAnalyzer(
            config=self.config,
            target_date=self.target_date
        )
    
    def create_performance_monitor(self) -> PerformanceMonitor:
        """Cria monitor de performance."""
        return PerformanceMonitor(self.config.get('performance', {}))
    
    def create_stats_aggregator(self) -> MarketStatsAggregator:
        """Cria agregador de estatísticas."""
        return MarketStatsAggregator(self.event_bus)