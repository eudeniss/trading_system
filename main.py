import logging
import sys
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
import signal
import time
from typing import Dict, Any

# --- CONFIGURAÇÃO DE LOGGING ---
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

console = Console()

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()

file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(log_dir / "system.log", mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(file_formatter)

rich_handler = RichHandler(
    console=console,
    level=logging.WARNING,
    show_time=False,
    markup=True,
    rich_tracebacks=True
)

root_logger.addHandler(file_handler)
root_logger.addHandler(rich_handler)

def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("EXCEÇÃO NÃO TRATADA", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_uncaught_exception

# Imports do sistema
from infrastructure.data_sources.excel_market_provider import ExcelMarketProvider
from infrastructure.logging.json_log_repository import JsonLogRepository
from infrastructure.event_bus.local_event_bus import LocalEventBus
from infrastructure.cache.trade_memory_cache import TradeMemoryCache  # NOVO!
from application.services.arbitrage_service import ArbitrageService
from application.services.tape_reading_service import TapeReadingService
from application.services.confluence_service import ConfluenceService
from application.services.risk_management_service import RiskManagementService
from analyzers.regimes.market_regime_detector import MarketRegimeDetector
from analyzers.statistics.market_stats_aggregator import MarketStatsAggregator
from presentation.display.monitor_app import TextualMonitorDisplay
from orchestration.trading_system import TradingSystem
from orchestration.event_handlers import OrchestrationHandlers
from config import settings

logger = logging.getLogger(__name__)

class TradingSystemV7:
    """Classe principal que gerencia todos os componentes do sistema v7.0 - COM CACHE CENTRALIZADO"""
    
    def __init__(self):
        self.console = console
        self.running = False
        self.components: Dict[str, Any] = {}
        self.operation_phase = "INITIALIZATION"
        
    def initialize_infrastructure(self) -> bool:
        """Fase 1: Inicializa componentes de infraestrutura."""
        try:
            self.console.print("[yellow]🔧 Inicializando infraestrutura...[/yellow]")
            
            # Event Bus
            self.event_bus = LocalEventBus()
            self.components['event_bus'] = self.event_bus
            
            # NOVO: Cache Centralizado de Trades
            buffer_size = settings.TAPE_READING_CONFIG.get('buffer_size', 10000)
            self.trade_cache = TradeMemoryCache(max_size=buffer_size)
            self.components['trade_cache'] = self.trade_cache
            self.console.print(f"[green]✓ Cache centralizado criado (max: {buffer_size} trades/símbolo)[/green]")
            
            # Market Provider
            self.market_provider = ExcelMarketProvider()
            if not self.market_provider.connect():
                raise Exception("Falha ao conectar com Excel")
            self.components['market_provider'] = self.market_provider
            
            # Signal Repository
            log_dir_config = settings.SYSTEM_CONFIG.get('log_dir', 'logs')
            self.signal_repo = JsonLogRepository(log_dir=log_dir_config)
            self.components['signal_repo'] = self.signal_repo
            
            self.console.print("[green]✓ Infraestrutura inicializada[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar infraestrutura: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na infraestrutura: {e}[/red]")
            return False
    
    def initialize_services(self) -> bool:
        """Fase 2: Inicializa serviços de aplicação."""
        try:
            self.console.print("[yellow]📊 Inicializando serviços...[/yellow]")
            
            # Arbitrage Service
            self.arbitrage_service = ArbitrageService()
            self.components['arbitrage_service'] = self.arbitrage_service
            
            # TapeReading Service COM CACHE
            self.tape_reading_service = TapeReadingService(
                event_bus=self.event_bus,
                trade_cache=self.trade_cache  # PASSA O CACHE!
            )
            self.components['tape_reading_service'] = self.tape_reading_service
            
            # Confluence Service
            self.confluence_service = ConfluenceService()
            self.components['confluence_service'] = self.confluence_service
            
            # Risk Management Service
            risk_config = settings.SYSTEM_CONFIG.get('risk_management', {})
            self.risk_management_service = RiskManagementService(
                event_bus=self.event_bus,
                state_manager=None,  # SEM STATE!
                config=settings.RISK_MANAGEMENT_CONFIG
            )
            self.components['risk_management_service'] = self.risk_management_service
            
            # Market Stats Aggregator
            self.market_stats_aggregator = MarketStatsAggregator(event_bus=self.event_bus)
            self.components['market_stats_aggregator'] = self.market_stats_aggregator
            
            # Market Regime Detector
            self.market_regime_detector = MarketRegimeDetector()
            self.components['market_regime_detector'] = self.market_regime_detector
            
            self.console.print("[green]✓ Serviços inicializados[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar serviços: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro nos serviços: {e}[/red]")
            return False
    
    def initialize_presentation(self) -> bool:
        """Fase 3: Inicializa camada de apresentação."""
        try:
            self.console.print("[yellow]🖥️  Inicializando interface...[/yellow]")
            
            self.display = TextualMonitorDisplay()
            self.components['display'] = self.display
            
            self.console.print("[green]✓ Interface inicializada[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar apresentação: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na interface: {e}[/red]")
            return False
    
    def initialize_orchestration(self) -> bool:
        """Fase 4: Inicializa orquestração e handlers."""
        try:
            self.console.print("[yellow]🎭 Inicializando orquestração...[/yellow]")
            
            self.handlers = OrchestrationHandlers(
                event_bus=self.event_bus, 
                signal_repo=self.signal_repo, 
                display=self.display,
                arbitrage_service=self.arbitrage_service, 
                tape_reading_service=self.tape_reading_service,
                confluence_service=self.confluence_service, 
                risk_management_service=self.risk_management_service,
                market_regime_detector=self.market_regime_detector, 
                state_manager=None  # SEM STATE!
            )
            
            self.trading_system = TradingSystem(
                console=self.console, 
                market_provider=self.market_provider, 
                event_bus=self.event_bus,
                display=self.display, 
                handlers=self.handlers,
                operation_phases={'risk_management': self.risk_management_service}
            )
            self.components['trading_system'] = self.trading_system
            
            self.console.print("[green]✓ Orquestração inicializada[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar orquestração: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na orquestração: {e}[/red]")
            return False
    
    def phase_initialization(self) -> bool:
        """FASE 1: Inicialização do sistema."""
        self.console.print("\n[bold cyan]🚀 SISTEMA DE TRADING v7.0 - CLEAN ARCHITECTURE[/bold cyan]")
        self.console.print("[dim]Zero Persistence + Centralized Cache[/dim]\n")
        
        if not self.initialize_infrastructure(): return False
        if not self.initialize_services(): return False
        if not self.initialize_presentation(): return False
        if not self.initialize_orchestration(): return False
        
        self.operation_phase = "NORMAL"
        return True
    
    def phase_normal_operation(self):
        """FASE 2: Operação normal do sistema."""
        try:
            self.console.print("\n[green]▶️  Sistema operacional[/green]")
            self.console.print("[dim]Pressione Ctrl+C para encerrar[/dim]\n")
            
            # Log estatísticas do cache periodicamente
            self._start_cache_monitoring()
            
            self.operation_phase = "NORMAL"
            
            if self.trading_system:
                self.trading_system.start()
        finally:
            self.operation_phase = "CLOSING"
    
    def _start_cache_monitoring(self):
        """Inicia monitoramento periódico do cache."""
        def log_cache_stats():
            while self.running:
                time.sleep(60)  # A cada minuto
                if hasattr(self, 'trade_cache'):
                    stats = self.trade_cache.get_stats()
                    basic = stats.get('basic_stats', {})
                    logger.info(
                        f"Cache Stats - Hits: {basic.get('hits', 0)}, "
                        f"Hit Rate: {basic.get('hit_rate', '0%')}, "
                        f"Total Trades: {stats.get('cache_info', {}).get('total_trades', 0)}"
                    )
        
        import threading
        monitor_thread = threading.Thread(target=log_cache_stats, daemon=True)
        monitor_thread.start()
    
    def phase_closing(self):
        """FASE 3: Encerramento ordenado do sistema."""
        self.console.print("\n[yellow]🔒 Encerrando sistema...[/yellow]")
        
        # Log estatísticas finais do cache
        if hasattr(self, 'trade_cache'):
            stats = self.trade_cache.get_stats()
            self.console.print("\n[cyan]📊 Estatísticas finais do cache:[/cyan]")
            
            basic = stats.get('basic_stats', {})
            self.console.print(f"  • Total de requisições: {basic.get('hits', 0) + basic.get('misses', 0)}")
            self.console.print(f"  • Taxa de acerto: {basic.get('hit_rate', '0%')}")
            self.console.print(f"  • Trades em cache: {stats.get('cache_info', {}).get('total_trades', 0)}")
            self.console.print(f"  • Evictions: {basic.get('evictions', 0)}")
        
        if hasattr(self, 'trading_system') and self.trading_system:
            self.trading_system.stop()

        if hasattr(self, 'signal_repo') and self.signal_repo:
            self.signal_repo.close()

        if hasattr(self, 'market_provider') and self.market_provider:
            self.market_provider.close()

        self.console.print("[green]✓ Sistema encerrado com sucesso[/green]")
    
    def run(self):
        """Executa o sistema completo através das fases operacionais."""
        self.running = True
        
        def signal_handler(sig, frame):
            if self.running:
                self.console.print("\n[yellow]⏹️  Interrupção detectada, encerrando...[/yellow]")
                self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            if self.phase_initialization():
                self.phase_normal_operation()
            else:
                self.console.print("[bold red]❌ Falha na inicialização do sistema.[/bold red]")
        
        except Exception as e:
            logger.critical(f"Erro fatal no sistema: {e}", exc_info=True)
            self.console.print(f"[bold red]💥 Erro fatal: {e}[/bold red]")
        
        finally:
            self.phase_closing()

def print_banner(console: Console):
    """Exibe o banner do sistema."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║     TRADING SYSTEM v7.0 - CLEAN ARCHITECTURE + CACHE     ║
    ║                                                           ║
    ║  📊 Zero Persistence + Centralized Trade Cache          ║
    ║  🎯 Risk Management + Market Analysis                   ║
    ║  🔍 Manipulation Detection + Defensive Filters          ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")

def verify_prerequisites(console: Console) -> bool:
    """Verifica pré-requisitos do sistema."""
    try:
        # Verifica configuração
        config_path = Path('config/config.yaml')
        if not config_path.exists():
            console.print(f"[bold red]❌ Arquivo de configuração não encontrado: {config_path}[/bold red]")
            return False
        
        excel_file = settings.EXCEL_CONFIG.get('file')
        if not excel_file:
            console.print("[bold red]❌ Caminho do Excel não configurado[/bold red]")
            return False
        
        # Info sobre cache
        buffer_size = settings.TAPE_READING_CONFIG.get('buffer_size', 10000)
        console.print(f"[green]✓ Cache configurado para {buffer_size:,} trades por símbolo[/green]")
        console.print("[yellow]📌 Sistema opera sem persistência - dados perdidos ao fechar[/yellow]")
        
        # Verifica diretório logs
        log_dir = Path('logs')
        if not log_dir.exists():
            console.print(f"[yellow]📁 Diretório logs será criado em: {log_dir.absolute()}[/yellow]")
        
        return True
        
    except Exception as e:
        console.print(f"[bold red]❌ Erro ao verificar pré-requisitos: {e}[/bold red]")
        return False

def main():
    """Ponto de entrada do sistema."""
    try:
        print_banner(console)
        
        if not verify_prerequisites(console):
            console.print("\n[yellow]Verifique a configuração e tente novamente.[/yellow]")
            return
        
        system = TradingSystemV7()
        system.run()
        
    except KeyboardInterrupt:
        console.print("\n[bold]Sistema finalizado pelo usuário.[/bold]")
    except Exception as e:
        logger.critical(f"Erro fatal não capturado no main: {e}", exc_info=True)
        console.print(f"[bold red]💥 Erro fatal. Verifique 'system.log'[/bold red]")
    finally:
        logging.shutdown()
        console.print("\n[bold]Aplicação finalizada.[/bold]")

if __name__ == "__main__":
    main()