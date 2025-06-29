# orchestration/event_handlers.py (SEM STATE MANAGER)
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from application.interfaces.system_event_bus import ISystemEventBus
from application.interfaces.signal_repository import ISignalRepository
from application.services.arbitrage_service import ArbitrageService
from application.services.tape_reading_service import TapeReadingService
from application.services.confluence_service import ConfluenceService
from application.services.risk_management_service import RiskManagementService
from analyzers.regimes.market_regime_detector import MarketRegimeDetector
from analyzers.regimes.regime_translator import RegimeTranslator  # NOVO IMPORT
from analyzers.statistics.market_stats_aggregator import MarketStatsAggregator
from domain.entities.market_data import MarketData
from domain.entities.trade import Trade
from domain.entities.signal import Signal, SignalSource, SignalLevel
from presentation.display.monitor_display import MonitorDisplay
from config import settings

logger = logging.getLogger(__name__)

class OrchestrationHandlers:
    """
    Coordena o fluxo de trabalho do sistema SEM STATE MANAGER.
    """
    def __init__(
        self,
        event_bus: ISystemEventBus,
        signal_repo: ISignalRepository,
        display: MonitorDisplay,
        arbitrage_service: ArbitrageService,
        tape_reading_service: TapeReadingService,
        confluence_service: ConfluenceService,
        risk_management_service: RiskManagementService,
        market_regime_detector: MarketRegimeDetector,
        state_manager=None  # Ignora mesmo se passado
    ):
        self.event_bus = event_bus
        self.signal_repo = signal_repo
        self.display = display
        self.arbitrage_service = arbitrage_service
        self.tape_reading_service = tape_reading_service
        self.confluence_service = confluence_service
        self.risk_management_service = risk_management_service
        self.market_regime_detector = market_regime_detector
        
        # Market Stats Aggregator
        self.stats_aggregator = MarketStatsAggregator(event_bus)
        
        # Registra serviços no aggregator
        self.stats_aggregator.register_service('tape_reading', tape_reading_service)
        self.stats_aggregator.register_service('arbitrage', arbitrage_service)
        self.stats_aggregator.register_service('risk_management', risk_management_service)
        
        self.last_arbitrage_opp: Optional[Dict[str, Any]] = None
        self.last_arbitrage_time = datetime.min
        self.processed_trades: Dict[str, set] = {'WDO': set(), 'DOL': set()}
        
        # Controle de regime
        self.current_regime = 'NORMAL'
        self.last_regime_check = datetime.now()
        
        # NOVO: Rastreamento de direção do fluxo
        self.flow_direction = {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'}
        self.last_cvd = {'WDO': 0, 'DOL': 0}

    def subscribe_to_events(self):
        """Inscreve todos os handlers nos eventos apropriados."""
        # Eventos existentes
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self.handle_market_data)
        self.event_bus.subscribe("SIGNAL_GENERATED", self.handle_signal_generated)
        self.event_bus.subscribe("ARBITRAGE_OPPORTUNITY", self.handle_arbitrage_opportunity)
        
        # Eventos para risk management
        self.event_bus.subscribe("SIGNAL_APPROVED", self.handle_signal_approved)
        self.event_bus.subscribe("SIGNAL_REJECTED", self.handle_signal_rejected)
        self.event_bus.subscribe("RISK_OVERRIDE", self.handle_risk_override)
        
        # Eventos de regime e estatísticas
        self.event_bus.subscribe("REGIME_CHANGE", self.handle_regime_change)
        self.event_bus.subscribe("STATS_AGGREGATED", self.handle_stats_aggregated)
        
        # Eventos de manipulação
        self.event_bus.subscribe("MANIPULATION_DETECTED", self.handle_manipulation_detected)

    def handle_market_data(self, market_data: MarketData):
        """Handler para o evento de atualização de dados de mercado."""
        # 1. Atualiza books no tape reading service
        for symbol in ['WDO', 'DOL']:
            if symbol in market_data.data:
                self.tape_reading_service.update_book(symbol, market_data.data[symbol].book)
        
        # 2. Processar novos trades para Tape Reading
        new_trades = self._get_new_trades(market_data)
        if new_trades:
            tape_reading_signals = self.tape_reading_service.process_new_trades(new_trades)
            
            # Cada sinal passa pelo risk management antes de ser emitido
            for signal in tape_reading_signals:
                self._process_signal_with_risk(signal)
        
        # 3. Analisar Arbitragem
        dol_data = market_data.data.get('DOL')
        wdo_data = market_data.data.get('WDO')
        
        if dol_data and wdo_data:
            opportunities = self.arbitrage_service.calculate_opportunities(
                dol_data.book, 
                wdo_data.book
            )
            
            # Salva a verificação de arbitragem para logging
            if opportunities:
                self.signal_repo.save_arbitrage_check({
                    'spreads': opportunities, 
                    'opportunity_found': False
                })

            # 4. Verificar se há oportunidade real de arbitragem
            if opportunities:
                min_profit = settings.ARBITRAGE_CONFIG.get('min_profit', 15.0)
                best_opp = max(
                    opportunities.values(), 
                    key=lambda x: x.get('profit', 0),
                    default=None
                )
                if best_opp and best_opp['profit'] >= min_profit:
                    cooldown = settings.ARBITRAGE_CONFIG.get('signal_cooldown', 10)
                    if datetime.now() - self.last_arbitrage_time > timedelta(seconds=cooldown):
                        self.last_arbitrage_time = datetime.now()
                        self.event_bus.publish("ARBITRAGE_OPPORTUNITY", best_opp)
        
        # 5. Verifica regime de mercado periodicamente (MODIFICADO)
        if (datetime.now() - self.last_regime_check).seconds >= 30:
            self._check_market_regime(market_data)
            self._check_flow_direction_change(market_data)  # NOVO
            self.last_regime_check = datetime.now()
        
        # 6. Atualiza Display com contexto completo
        analysis_data = self._build_analysis_data()
        self.display.update(market_data, analysis_data)

    def _build_analysis_data(self) -> Dict[str, Any]:
        """Constrói dados de análise completos para o display."""
        analysis_data = {
            'arbitrage_stats': self.arbitrage_service.get_spread_statistics(),
            'tape_summaries': {
                'WDO': self.tape_reading_service.get_market_summary('WDO'),
                'DOL': self.tape_reading_service.get_market_summary('DOL')
            },
            'risk_status': self.risk_management_service.get_risk_status(),
            'market_context': self.stats_aggregator.get_market_context(),
            'current_regime': self.current_regime
        }
        
        return analysis_data

    def _get_new_trades(self, market_data: MarketData) -> List[Trade]:
        """Filtra trades que ainda não foram processados."""
        new_trades = []
        for symbol, data in market_data.data.items():
            for trade in data.trades:
                trade_key = f"{trade.time_str}_{trade.price}_{trade.volume}"
                if trade_key not in self.processed_trades[symbol]:
                    self.processed_trades[symbol].add(trade_key)
                    new_trades.append(trade)
            # Limpa o cache de trades processados para não crescer indefinidamente
            if len(self.processed_trades[symbol]) > 500:
                self.processed_trades[symbol] = set(list(self.processed_trades[symbol])[-250:])
        return new_trades

    def _process_signal_with_risk(self, signal: Signal):
        """Processa sinal através do risk management antes de emitir."""
        # Avalia sinal com risk management
        approved, assessment = self.risk_management_service.evaluate_signal(signal)
        
        if approved:
            # Sinal aprovado - emite normalmente
            self.event_bus.publish("SIGNAL_GENERATED", signal)
        else:
            # Sinal rejeitado - apenas loga, sem criar avisos
            reason = assessment['reasons'][0] if assessment['reasons'] else 'Qualidade insuficiente'
            logger.info(f"Sinal filtrado: {reason[:50]}")

    def handle_signal_generated(self, signal: Signal):
        """Handler para qualquer sinal gerado (já aprovado pelo risk)."""
        # logger.info(f"Sinal Gerado: {signal.message}") # Linha removida para evitar duplicidade
        self.display.add_signal(signal)
        self.signal_repo.save(signal)
        
        # NÃO SALVA MAIS NO STATE MANAGER!

    def handle_arbitrage_opportunity(self, opportunity: Dict[str, Any]):
        """Handler para uma oportunidade de arbitragem."""
        # Cria um sinal de arbitragem
        arb_signal = Signal(
            source=SignalSource.ARBITRAGE,
            level=SignalLevel.ALERT,
            message=f"Arbitragem: {opportunity['action']} | Lucro: R${opportunity['profit']:.2f}",
            details=opportunity
        )
        
        # Processa com risk management
        self._process_signal_with_risk(arb_signal)
        
        # Tenta a análise de confluência
        tape_summaries = {
            'WDO': self.tape_reading_service.get_market_summary('WDO'),
            'DOL': self.tape_reading_service.get_market_summary('DOL')
        }
        confluence_signal = self.confluence_service.analyze(opportunity, tape_summaries)
        
        if confluence_signal:
            # Confluência também passa pelo risk management
            self._process_signal_with_risk(confluence_signal)

    def handle_signal_approved(self, data: Dict):
        """Handler para sinais aprovados pelo risk management."""
        signal = data['signal']
        assessment = data['assessment']
        
        # NÃO adiciona recomendações automáticas para evitar spam
        # Apenas log para debug se necessário
        if assessment.get('recommendations'):
            logger.debug(f"Recomendações para sinal: {assessment['recommendations']}")

    def handle_signal_rejected(self, data: Dict):
        """Handler para sinais rejeitados pelo risk management."""
        signal = data['signal']
        assessment = data['assessment']
        
        # Cria sinal de aviso sobre rejeição
        warning_signal = Signal(
            source=SignalSource.SYSTEM,
            level=SignalLevel.WARNING,
            message=f"⚠️ Sinal bloqueado: {assessment['reasons'][0] if assessment['reasons'] else 'Risco elevado'}",
            details={'rejected_signal': signal.message}
        )
        
        self.display.add_signal(warning_signal)
        self.signal_repo.save(warning_signal)

    def handle_risk_override(self, data: Dict):
        """Handler para override manual de risk management."""
        breaker = data['breaker']
        new_state = data['new_state']
        reason = data['reason']
        
        override_signal = Signal(
            source=SignalSource.SYSTEM,
            level=SignalLevel.ALERT,
            message=f"🔧 Override: {breaker} {'ativado' if new_state else 'desativado'} - {reason}",
            details=data
        )
        
        self.display.add_signal(override_signal)
        self.signal_repo.save(override_signal)

    def _check_market_regime(self, market_data: MarketData):
        """Verifica e atualiza regime de mercado."""
        # Atualiza regime usando o detector
        new_regimes = self.market_regime_detector.update(market_data)
        
        # Verifica mudanças para cada símbolo
        for symbol, new_regime in new_regimes.items():
            if hasattr(self, f'_last_regime_{symbol}'):
                old_regime = getattr(self, f'_last_regime_{symbol}')
                if new_regime != old_regime:
                    # Emite evento de mudança
                    self.event_bus.publish("REGIME_CHANGE", {
                        'symbol': symbol,
                        'old_regime': old_regime,
                        'new_regime': new_regime,
                        'timestamp': datetime.now()
                    })
            setattr(self, f'_last_regime_{symbol}', new_regime)

    def handle_regime_change(self, data: Dict):
        """Handler para mudanças de regime de mercado (MODIFICADO)."""
        symbol = data.get('symbol', 'MARKET')
        old_regime = data['old_regime']
        new_regime = data['new_regime']
        
        # NOVO: Traduz os regimes
        old_name = RegimeTranslator.translate(old_regime)
        new_name = RegimeTranslator.translate(new_regime)
        description = RegimeTranslator.get_description(new_regime)
        
        regime_signal = Signal(
            source=SignalSource.SYSTEM,
            level=SignalLevel.WARNING,
            message=f"🔄 {symbol} - {old_name} → {new_name}",
            details={
                **data,
                'description': description
            }
        )
        
        self.display.add_signal(regime_signal)
        self.signal_repo.save(regime_signal)
        
        # Ajusta parâmetros baseado no novo regime
        self._adjust_parameters_for_regime(new_regime)
        
    def _check_flow_direction_change(self, market_data: MarketData):
        """NOVO: Detecta mudanças de direção do fluxo (compra→venda ou venda→compra)."""
        for symbol in ['WDO', 'DOL']:
            tape_summary = self.tape_reading_service.get_market_summary(symbol)
            current_cvd = tape_summary.get('cvd_total', 0)
            
            # Determina direção atual
            if current_cvd > 50:
                current_direction = 'COMPRA'
            elif current_cvd < -50:
                current_direction = 'VENDA'
            else:
                current_direction = 'NEUTRO'
            
            # Verifica mudança significativa
            if self.flow_direction[symbol] != current_direction:
                old_direction = self.flow_direction[symbol]
                
                # Só emite sinal se for mudança significativa (não de/para neutro)
                if old_direction != 'NEUTRO' and current_direction != 'NEUTRO' and old_direction != current_direction:
                    # Mudança de direção detectada!
                    direction_signal = Signal(
                        source=SignalSource.SYSTEM,
                        level=SignalLevel.ALERT,
                        message=f"🔀 {symbol} - REVERSÃO: Fluxo {old_direction} → {current_direction}",
                        details={
                            'symbol': symbol,
                            'old_direction': old_direction,
                            'new_direction': current_direction,
                            'old_cvd': self.last_cvd[symbol],
                            'new_cvd': current_cvd,
                            'timestamp': datetime.now()
                        }
                    )
                    
                    self.display.add_signal(direction_signal)
                    self.signal_repo.save(direction_signal)
                    
                    # Emite evento específico de reversão
                    self.event_bus.publish("FLOW_REVERSAL", {
                        'symbol': symbol,
                        'from': old_direction,
                        'to': current_direction,
                        'cvd_change': current_cvd - self.last_cvd[symbol]
                    })
                
                self.flow_direction[symbol] = current_direction
            
            self.last_cvd[symbol] = current_cvd

    def _adjust_parameters_for_regime(self, regime: str):
        """Ajusta parâmetros do sistema baseado no regime."""
        if regime in ['VOLATILE', 'VOLATILE_ACTIVE']:
            logger.info("Ajustando parâmetros para regime volátil")
        elif regime in ['QUIET', 'STABLE_ACTIVE']:
            logger.info("Ajustando parâmetros para regime calmo")

    def handle_stats_aggregated(self, data: Dict):
        """Handler para estatísticas agregadas."""
        stats = data['stats']
        
        # Verifica alertas
        alerts = stats.get('alerts', [])
        for alert in alerts:
            if alert['level'] == 'ALERT':
                alert_signal = Signal(
                    source=SignalSource.SYSTEM,
                    level=SignalLevel.ALERT,
                    message=f"🚨 {alert['message']}",
                    details=alert
                )
                self.display.add_signal(alert_signal)

    def handle_manipulation_detected(self, data: Dict):
        """Handler para detecção de manipulação com mensagens CLARAS."""
        risk_info = data.get('risk_info', {})
        symbol = data.get('symbol', 'UNKNOWN')
        
        # Pega a ação recomendada
        action = risk_info.get('action_required', '⚠️ CUIDADO! Possível manipulação')
        
        # Cria UMA ÚNICA mensagem principal com a AÇÃO CLARA
        main_message = f"🚨 {symbol} - {action}"
        
        # Adiciona detalhes na mesma mensagem se houver
        details_list = risk_info.get('details', [])
        if details_list and len(details_list) > 0:
            first_detail = details_list[0]
            if first_detail.get('description'):
                main_message += f" | {first_detail['description']}"
        
        manipulation_signal = Signal(
            source=SignalSource.MANIPULATION,
            level=SignalLevel.ALERT,
            message=main_message,
            details=data
        )
        
        self.display.add_signal(manipulation_signal)
        self.signal_repo.save(manipulation_signal)
        
        logger.warning(f"Manipulação em {symbol}: {risk_info.get('risks')} - Ação: {action}")