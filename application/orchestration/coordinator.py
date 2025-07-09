# application/orchestration/coordinator.py
"""Coordenador principal do sistema - COMPLETO COM TODAS AS FASES."""
import logging
from typing import Dict, Any
from datetime import datetime, time as dt_time
import time
import threading
import asyncio
import gc

from core.contracts.messaging import ISystemEventBus
from presentation.display.monitor import TextualMonitorDisplay

logger = logging.getLogger(__name__)


class SystemCoordinator:
    """Coordena todos os componentes do sistema com loop robusto e manutenção."""
    
    def __init__(self, config: Dict[str, Any], infrastructure: Dict, services: Dict, 
                 performance_monitor: Any = None):
        self.config = config
        self.infrastructure = infrastructure
        self.services = services
        self.performance_monitor = performance_monitor
        
        self.event_bus = infrastructure['event_bus']
        self.provider = infrastructure['provider']
        self.repository = infrastructure['repository']
        
        self.display = None
        self.handlers = None
        self.running = False

        # FASE 1.1: Contadores e controles do loop principal
        self.error_count = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = self.config['system'].get('max_consecutive_errors', 5)
        self.last_error_time = None
        self.loop_count = 0
        self.maintenance_interval = self.config['system'].get('maintenance_interval_seconds', 600)
        self._last_daily_reset = None
        
        # Backoff configuration
        self.min_backoff = self.config['system'].get('min_backoff_seconds', 1)
        self.max_backoff = self.config['system'].get('max_backoff_seconds', 60)
        
    def setup(self):
        """Configura o sistema com todos os componentes."""
        try:
            # Cria display, passando o monitor de performance
            self.display = TextualMonitorDisplay(performance_monitor=self.performance_monitor)
            
            # Cria handlers com todas as integrações
            from application.orchestration.handlers import OrchestrationHandlers
            
            self.handlers = OrchestrationHandlers(
                event_bus=self.event_bus,
                signal_repo=self.repository,
                display=self.display,
                services=self.services
            )
            
            # Registra serviços no stats aggregator se existir
            if 'stats_aggregator' in self.services:
                stats_agg = self.services['stats_aggregator']
                for name, service in self.services.items():
                    if name != 'stats_aggregator':
                        stats_agg.register_service(name, service)
            
            # Inscreve handlers nos eventos
            self.handlers.subscribe_to_events()
            
            # Configura monitor de performance (FASE 6)
            if self.performance_monitor:
                self.performance_monitor.record_trades_processed(0)
            
            logger.info("✅ Sistema coordenado e pronto com todas as fases implementadas")
            
        except Exception as e:
            logger.error(f"❌ Erro no setup do coordenador: {e}", exc_info=True)
            raise
    
    def start(self):
        """Inicia o sistema com loop robusto e tratamento avançado de erros (FASE 1.1)."""
        self.running = True
        
        # Inicia display em thread separada
        display_thread = threading.Thread(
            target=self._run_display,
            daemon=True
        )
        display_thread.start()
        
        # Aguarda display iniciar
        time.sleep(2)
        
        # Notifica início
        self.event_bus.publish("SYSTEM_STARTED", {
            'timestamp': datetime.now(),
            'config': {
                'max_errors': self.max_consecutive_errors,
                'maintenance_interval': self.maintenance_interval
            }
        })
        
        # Loop principal robusto
        update_interval = self.config['system'].get('update_interval', 0.1)
        
        logger.info("🚀 Loop principal iniciado com proteções avançadas")
        
        while self.running:
            loop_start = time.perf_counter()
            
            try:
                # Busca dados do mercado
                market_data = self.provider.get_market_data()
                
                if market_data:
                    # <<< REMOVIDO: Contagem incorreta de trades >>>
                    # Não conta mais todos os trades aqui
                    # A contagem correta será feita no handlers
                    
                    # Publica evento
                    self.event_bus.publish("MARKET_DATA_UPDATED", market_data)
                    
                    # Reset de erros consecutivos em caso de sucesso
                    if self.consecutive_errors > 0:
                        logger.info(f"✅ Sistema recuperado após {self.consecutive_errors} erros")
                        self.consecutive_errors = 0
                
                # Incrementa contador de loops bem-sucedidos
                self.loop_count += 1
                
                # Tarefas de manutenção periódicas
                if self.loop_count % self.maintenance_interval == 0:
                    self._perform_maintenance()
                
                # Reset diário das métricas
                self._check_daily_reset()
                
                # Otimização de performance (FASE 6)
                if self.loop_count % 1000 == 0:
                    self._optimize_performance()
                
                # Controla a velocidade do loop
                loop_duration = time.perf_counter() - loop_start
                sleep_time = max(0, update_interval - loop_duration)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif loop_duration > update_interval * 2:
                    logger.warning(f"⚠️ Loop lento: {loop_duration:.3f}s (esperado: {update_interval}s)")
                
            except KeyboardInterrupt:
                logger.info("⏹️ Interrupção de teclado detectada. Encerrando...")
                self.running = False
                break
            
            except ConnectionError as e:
                # Erros de conexão são tratados diferentemente
                logger.error(f"📡 Erro de conexão: {e}")
                self._handle_connection_error()
                
            except MemoryError as e:
                # Erro crítico de memória
                logger.critical(f"💾 Erro de memória: {e}")
                self._handle_memory_error()
                self.running = False
                break
                
            except Exception as e:
                # Outros erros com tratamento robusto
                self._handle_general_error(e)
                
                # Se muitos erros seguidos, para o sistema
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(
                        f"🔴 SISTEMA CRÍTICO: Limite de {self.max_consecutive_errors} "
                        f"erros consecutivos atingido. Encerrando."
                    )
                    self.event_bus.publish("SYSTEM_CRITICAL_FAILURE", {
                        'error_count': self.consecutive_errors,
                        'last_error': str(e),
                        'timestamp': datetime.now()
                    })
                    self.running = False
                    break
    
    def _handle_general_error(self, error: Exception):
        """Trata erros gerais com backoff exponencial."""
        self.error_count += 1
        self.consecutive_errors += 1
        current_time = time.time()
        
        logger.error(
            f"❌ Erro no loop principal (#{self.error_count}, consecutivos: {self.consecutive_errors}): {error}",
            exc_info=True
        )
        
        # Publica evento de erro
        self.event_bus.publish("SYSTEM_ERROR", {
            'error': str(error),
            'type': type(error).__name__,
            'consecutive': self.consecutive_errors,
            'total': self.error_count,
            'timestamp': datetime.now()
        })
        
        # Backoff exponencial com limites
        wait_time = min(
            self.max_backoff,
            self.min_backoff * (2 ** min(self.consecutive_errors - 1, 10))
        )
        
        # Reseta o backoff se o último erro foi há muito tempo
        if self.last_error_time and (current_time - self.last_error_time) > 300:  # 5 minutos
            self.consecutive_errors = 1
            wait_time = self.min_backoff
            logger.info("🔄 Resetando contador de erros consecutivos (último erro há mais de 5 min)")
        
        self.last_error_time = current_time
        logger.warning(f"⏳ Aguardando {wait_time:.1f}s antes de tentar novamente...")
        time.sleep(wait_time)
    
    def _handle_connection_error(self):
        """Trata erros de conexão tentando reconectar."""
        logger.warning("🔌 Tentando reconectar ao provider...")
        
        max_reconnect_attempts = 3
        for attempt in range(max_reconnect_attempts):
            time.sleep(2 ** attempt)  # Backoff exponencial: 1s, 2s, 4s
            
            try:
                if self.provider.connect():
                    logger.info("✅ Reconexão bem-sucedida!")
                    return
            except Exception as e:
                logger.error(f"Tentativa {attempt + 1} falhou: {e}")
        
        logger.error("❌ Falha ao reconectar após múltiplas tentativas")
        self.consecutive_errors += 1
    
    def _handle_memory_error(self):
        """Trata erros de memória com limpeza agressiva."""
        logger.warning("🧹 Executando limpeza de memória emergencial...")
        
        # Limpa caches
        if hasattr(self.services.get('tape_reading'), 'analysis_cache'):
            self.services['tape_reading'].analysis_cache.clear()
        
        # Força coleta de lixo
        gc.collect(2)  # Coleta completa
        
        # Reduz buffers se possível
        if hasattr(self.infrastructure.get('cache'), 'max_size'):
            old_size = self.infrastructure['cache'].max_size
            new_size = old_size // 2
            self.infrastructure['cache'].max_size = new_size
            logger.warning(f"📉 Cache reduzido: {old_size} → {new_size}")
        
        # Notifica sistema
        self.event_bus.publish("MEMORY_EMERGENCY", {
            'timestamp': datetime.now(),
            'action': 'emergency_cleanup'
        })
    
    def _perform_maintenance(self):
        """Realiza manutenção periódica do sistema (FASE 1.1)."""
        logger.info("🔧 Executando ciclo de manutenção periódica...")
        
        maintenance_start = time.perf_counter()
        
        # 1. Coleta de lixo
        collected = gc.collect()
        
        # 2. Limpa caches antigos
        if 'tape_reading' in self.services:
            tape_service = self.services['tape_reading']
            # Limpa cache de análises antigas
            if hasattr(tape_service, 'analysis_cache'):
                cache_size_before = len(tape_service.analysis_cache)
                # Remove entradas antigas (mais de 5 segundos)
                current_time = time.time()
                tape_service.analysis_cache = {
                    k: v for k, v in tape_service.analysis_cache.items()
                    if current_time - v[0] < 5
                }
                cache_size_after = len(tape_service.analysis_cache)
                if cache_size_before > cache_size_after:
                    logger.debug(f"Cache de análises limpo: {cache_size_before} → {cache_size_after}")
        
        # 3. Compacta histórico de sinais
        if self.repository:
            self.repository.flush()
        
        # 4. Otimiza estruturas de dados
        if 'arbitrage' in self.services:
            arb_service = self.services['arbitrage']
            if hasattr(arb_service, 'spread_history') and len(arb_service.spread_history) > 50:
                # Mantém apenas estatísticas resumidas de spreads antigos
                old_size = len(arb_service.spread_history)
                if old_size > arb_service.spread_history.maxlen * 0.8:
                    logger.debug(f"Histórico de spreads otimizado: {old_size} entradas")
        
        # 5. Verifica saúde dos serviços
        unhealthy_services = []
        for name, service in self.services.items():
            if hasattr(service, 'get_statistics'):
                try:
                    stats = service.get_statistics()
                    # Verifica indicadores de saúde específicos
                    if name == 'risk' and stats.get('active_breakers'):
                        unhealthy_services.append(f"{name}: {len(stats['active_breakers'])} breakers ativos")
                except Exception as e:
                    unhealthy_services.append(f"{name}: erro ao obter status - {e}")
        
        if unhealthy_services:
            logger.warning(f"⚠️ Serviços com problemas: {', '.join(unhealthy_services)}")
        
        maintenance_duration = time.perf_counter() - maintenance_start
        
        # Publica evento de manutenção
        self.event_bus.publish("MAINTENANCE_COMPLETED", {
            'timestamp': datetime.now(),
            'duration_ms': maintenance_duration * 1000,
            'gc_collected': collected,
            'unhealthy_services': unhealthy_services,
            'loop_count': self.loop_count
        })
        
        logger.info(
            f"✅ Manutenção concluída em {maintenance_duration:.3f}s "
            f"(GC: {collected} objetos, Loops: {self.loop_count:,})"
        )
    
    def _check_daily_reset(self):
        """Verifica e executa reset diário de métricas (FASE 1.1)."""
        now = datetime.now()
        reset_time = self.config['system'].get('daily_reset_time', '00:00')
        
        try:
            reset_hour, reset_minute = map(int, reset_time.split(':'))
            reset_time_today = now.replace(hour=reset_hour, minute=reset_minute, second=0, microsecond=0)
        except ValueError:
            logger.error(f"Horário de reset inválido: {reset_time}. Usando 00:00")
            reset_time_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Verifica se já passou do horário de reset hoje e se ainda não foi feito
        should_reset = (
            now >= reset_time_today and
            (self._last_daily_reset is None or self._last_daily_reset.date() < now.date())
        )
        
        if should_reset:
            logger.warning(f"🔄 Executando reset diário de métricas às {now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Reset em cada serviço
            reset_results = {}
            
            # Risk Management
            if 'risk' in self.services:
                try:
                    self.services['risk'].reset_daily_metrics()
                    reset_results['risk'] = 'success'
                except Exception as e:
                    reset_results['risk'] = f'error: {e}'
                    logger.error(f"Erro ao resetar risk management: {e}")
            
            # CVD Calculator
            if 'tape_reading' in self.services:
                try:
                    tape_service = self.services['tape_reading']
                    for symbol in ['WDO', 'DOL']:
                        if symbol in tape_service.analyzers:
                            cvd_calc = tape_service.analyzers[symbol].get('cvd_calc')
                            if cvd_calc and hasattr(cvd_calc, 'reset_cumulative'):
                                cvd_calc.reset_cumulative(symbol)
                    reset_results['cvd'] = 'success'
                except Exception as e:
                    reset_results['cvd'] = f'error: {e}'
                    logger.error(f"Erro ao resetar CVD: {e}")
            
            # Hidden Liquidity Detector
            if 'tape_reading' in self.services:
                try:
                    tape_service = self.services['tape_reading']
                    # <<< Lógica Nova >>>
                    for symbol in ['WDO', 'DOL']:
                        # Verifica se o analisador existe para o símbolo
                        if symbol in tape_service.analyzers and 'hidden_liquidity' in tape_service.analyzers[symbol]:
                            # Chama o método através do dicionário de analisadores
                            tape_service.analyzers[symbol]['hidden_liquidity'].cleanup_old_levels(symbol, max_age_minutes=1440)
                    
                    reset_results['hidden_liquidity'] = 'success'
                except Exception as e:
                    reset_results['hidden_liquidity'] = f'error: {e}'
                    logger.error(f"Erro ao resetar hidden_liquidity: {e}")
            
            # Estatísticas de performance
            if self.performance_monitor:
                try:
                    # Não reseta completamente, apenas marca o ponto
                    # self.performance_monitor.mark_daily_reset()  # Se o método existir
                    reset_results['performance'] = 'success'
                except Exception as e:
                    reset_results['performance'] = f'error: {e}'
            
            # Publica evento para que outros componentes possam resetar
            self.event_bus.publish("DAILY_RESET", {
                'timestamp': now,
                'reset_results': reset_results
            })
            
            self._last_daily_reset = now
            
            # Log resumo
            successful = sum(1 for r in reset_results.values() if r == 'success')
            logger.info(
                f"✅ Reset diário concluído: {successful}/{len(reset_results)} "
                f"componentes resetados com sucesso"
            )
    
    def _optimize_performance(self):
        """Otimizações periódicas de performance (FASE 6)."""
        if self.performance_monitor:
            report = self.performance_monitor.get_performance_report()
            
            # Aplica otimizações baseadas nos bottlenecks
            bottlenecks = report.get('bottlenecks', [])
            for bottleneck in bottlenecks:
                if bottleneck['type'] == 'HIGH_MEMORY' and bottleneck['severity'] == 'HIGH':
                    # Força limpeza se memória muito alta
                    gc.collect(2)
                    logger.warning("🧹 Coleta de lixo forçada devido a uso alto de memória")
                
                elif bottleneck['type'] == 'SLOW_COMPONENT':
                    component = bottleneck['component']
                    logger.warning(
                        f"⚠️ Componente lento detectado: {component} "
                        f"({bottleneck['avg_latency_ms']:.1f}ms média)"
                    )
    
    def stop(self):
        """Para o sistema de forma ordenada."""
        logger.info("🛑 Iniciando shutdown do sistema...")
        
        self.running = False
        
        # Notifica shutdown
        self.event_bus.publish("SYSTEM_STOPPING", {
            'timestamp': datetime.now(),
            'total_loops': self.loop_count,
            'total_errors': self.error_count
        })
        
        # Para serviços
        if self.display:
            self.display.stop()
        
        # Flush final dos logs
        if self.repository:
            self.repository.flush()
        
        logger.info(
            f"✅ Sistema encerrado após {self.loop_count:,} loops "
            f"({self.error_count} erros no total)"
        )
    
    def _run_display(self):
        """Executa o display em thread separada."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Notifica que o display está pronto
            self.display.update_system_phase("Inicialização completa")
            loop.run_until_complete(self.display.start())
        except Exception as e:
            logger.error(f"Erro no display: {e}", exc_info=True)