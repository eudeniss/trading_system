# core/bootstrap/system.py
"""
Bootstrap do sistema com suporte para replay de mercado.
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from core.factories.services import ServiceFactory
from core.factories.infrastructure import InfrastructureFactory
from config.settings import load_config

logger = logging.getLogger(__name__)


class SystemBootstrap:
    """Inicializa e configura todo o sistema."""
    
    def __init__(self, config_path: str = "config/config.yaml", target_date: Optional[datetime] = None):
        """
        Inicializa o bootstrap.
        
        Args:
            config_path: Caminho do arquivo de configuração
            target_date: Data alvo para replay de mercado (None = mercado ao vivo)
        """
        self.config = load_config(config_path)
        self.target_date = target_date  # Armazena a data do replay
        self.infrastructure = None
        self.services = None
        self.orchestrator = None
        
        # Log do modo de operação
        if self.target_date:
            logger.info(f"🔄 Sistema iniciando em modo REPLAY para {self.target_date.strftime('%d/%m/%Y')}")
        else:
            logger.info("📊 Sistema iniciando em modo AO VIVO")
    
    def initialize(self) -> bool:
        """Inicializa todos os componentes do sistema."""
        try:
            logger.info("🚀 Iniciando bootstrap do sistema v8.0...")
            
            # Inicializa componentes na ordem correta
            if not self._init_infrastructure():
                return False
                
            if not self._init_services():
                return False
                
            if not self._init_orchestration():
                return False
                
            if not self._validate_system():
                return False
            
            logger.info("✅ Sistema inicializado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro no bootstrap: {e}", exc_info=True)
            return False
    
    def _init_infrastructure(self) -> bool:
        """Inicializa componentes de infraestrutura."""
        try:
            logger.info("🔧 Inicializando infraestrutura...")
            
            factory = InfrastructureFactory(self.config)
            
            self.infrastructure = {
                'cache': factory.create_cache(),
                'event_bus': factory.create_event_bus(),
                'provider': factory.create_market_provider(),
                'repository': factory.create_signal_repository()
            }
            
            # Conecta ao provider
            if self.infrastructure['provider'].connect():
                logger.info("✓ Provider conectado")
            else:
                logger.error("✗ Falha ao conectar provider")
                return False
            
            logger.info(f"✓ {len(self.infrastructure)} componentes de infraestrutura prontos")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao inicializar infraestrutura: {e}", exc_info=True)
            return False
    
    def _init_services(self) -> bool:
        """Inicializa todos os serviços, passando a data do replay."""
        try:
            logger.info("📊 Inicializando serviços...")
            
            factory = ServiceFactory(
                config=self.config,
                event_bus=self.infrastructure['event_bus'],
                cache=self.infrastructure['cache'],
                target_date=self.target_date  # Passa a data para a fábrica
            )
            
            self.services = factory.create_all_services()
            
            logger.info(f"✓ {len(self.services)} serviços prontos")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao inicializar serviços: {e}", exc_info=True)
            return False
    
    def _init_orchestration(self) -> bool:
        """Inicializa orquestração do sistema."""
        try:
            logger.info("🎯 Configurando orquestração...")
            
            from application.orchestration.coordinator import SystemCoordinator
            
            self.orchestrator = SystemCoordinator(
                config=self.config,
                infrastructure=self.infrastructure,
                services=self.services,
                performance_monitor=self.services.get('performance_monitor')
            )
            
            self.orchestrator.setup()
            
            logger.info("✓ Orquestração configurada")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao inicializar orquestração: {e}", exc_info=True)
            return False
    
    def _validate_system(self) -> bool:
        """Valida se o sistema está pronto."""
        try:
            logger.info("🔍 Validando sistema...")
            
            # Verifica componentes críticos
            if not self.infrastructure:
                logger.error("Infraestrutura não inicializada")
                return False
                
            if not self.services:
                logger.error("Serviços não inicializados")
                return False
                
            if not self.orchestrator:
                logger.error("Orquestrador não inicializado")
                return False
            
            # Testa comunicação básica
            test_event = "SYSTEM_TEST"
            received = []
            
            def test_handler(data):
                received.append(data)
            
            self.infrastructure['event_bus'].subscribe(test_event, test_handler)
            self.infrastructure['event_bus'].publish(test_event, {"test": True})
            
            if not received:
                logger.error("Falha no teste de eventos")
                return False
            
            logger.info("✓ Sistema validado e pronto")
            return True
            
        except Exception as e:
            logger.error(f"Erro na validação: {e}", exc_info=True)
            return False
    
    def run(self) -> None:
        """Executa o sistema."""
        if self.orchestrator:
            self.orchestrator.start()
        else:
            raise RuntimeError("Sistema não inicializado")
    
    def shutdown(self) -> None:
        """Encerra o sistema ordenadamente."""
        logger.info("🛑 Iniciando shutdown do sistema...")
        
        if self.orchestrator:
            self.orchestrator.stop()
        
        if self.infrastructure:
            if 'provider' in self.infrastructure:
                self.infrastructure['provider'].disconnect()
            
            if 'repository' in self.infrastructure:
                self.infrastructure['repository'].flush()
        
        logger.info("✅ Sistema encerrado com sucesso")