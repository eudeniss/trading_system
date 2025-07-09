# application/orchestration/handlers.py
"""Handlers de eventos com integração Frajola + Tape Reading"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from core.contracts.messaging import ISystemEventBus
from core.contracts.repository import ISignalRepository
from core.entities.market_data import MarketData
from core.entities.signal import Signal, SignalSource, SignalLevel

logger = logging.getLogger(__name__)


class OrchestrationHandlers:
    """
    Handlers para eventos do sistema com análise de confluência.
    Integra Tape Reading com Mercado Calculado (Frajola).
    """
    
    def __init__(self, event_bus: ISystemEventBus, signal_repo: ISignalRepository,
                 display: Any, services: Dict):
        self.event_bus = event_bus
        self.signal_repo = signal_repo
        self.display = display
        self.services = services
        
        # Pega referências aos serviços
        self.performance_monitor = services.get('performance_monitor')
        self.tape_reading = services['tape_reading']
        self.risk = services['risk']
        self.regime = services['regime']
        
        # NOVO: Referência ao mercado calculado
        self.calculated_market = services.get('calculated_market')
        
        # Tracking de trades processados
        self.processed_trades = {'WDO': set(), 'DOL': set()}
        
        # Tracking de direção do fluxo
        self.flow_direction = {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'}
        self.flow_history = {'WDO': [], 'DOL': []}
        self.last_flow_alert = {'WDO': None, 'DOL': None}
        
        # Tracking de regime de mercado
        self.previous_regime = {'WDO': None, 'DOL': None}
        
        # NOVO: Tracking de níveis próximos
        self.nearby_levels = {'WDO': None, 'DOL': None}
        self.last_level_alert = {'WDO': None, 'DOL': None}
    
    def subscribe_to_events(self):
        """Inscreve handlers nos eventos do sistema."""
        # Eventos principais
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self.handle_market_data)
        self.event_bus.subscribe("SIGNAL_GENERATED", self.handle_signal)
        
        # Eventos de manipulação
        self.event_bus.subscribe("MANIPULATION_DETECTED", self.handle_manipulation)
        
        # NOVO: Evento de padrão detectado para análise de confluência
        self.event_bus.subscribe("PATTERN_DETECTED", self.handle_pattern_detected)
        
        logger.info("Handlers inscritos em todos os eventos (incluindo confluência)")
    
    def handle_market_data(self, market_data: MarketData):
        """Processa dados de mercado - ponto central de orquestração."""
        try:
            # 1. Atualiza books para detecção de manipulação
            for symbol in ['WDO', 'DOL']:
                if symbol in market_data.data:
                    self.tape_reading.update_book(
                        symbol, 
                        market_data.data[symbol].book
                    )
            
            # 2. NOVO: Verifica proximidade com níveis calculados
            self._check_level_proximity(market_data)
            
            # 3. Processa novos trades
            new_trades = self._get_new_trades(market_data)
            if new_trades:
                signals = self.tape_reading.process_new_trades(new_trades)
                for signal in signals:
                    # Tenta analisar confluência antes de publicar
                    confluence_signal = self._analyze_confluence(signal, market_data)
                    if confluence_signal:
                        self.event_bus.publish("SIGNAL_GENERATED", confluence_signal)
                    else:
                        self.event_bus.publish("SIGNAL_GENERATED", signal)
            
            # 4. Atualiza detector de regime
            self.regime.update(market_data)
            
            # 5. Verifica mudanças de regime
            self._check_regime_changes()
            
            # 6. Verifica reversão de fluxo
            self._check_flow_direction(market_data)
            
            # 7. Atualiza display com análise completa
            analysis_data = self._build_analysis(market_data)
            self.display.update(market_data, analysis_data)
            
        except Exception as e:
            logger.error(f"Erro ao processar market data: {e}", exc_info=True)
    
    def handle_pattern_detected(self, pattern_data: Dict):
        """
        NOVO: Handler para padrões detectados pelo tape reading.
        Analisa confluência com níveis calculados.
        """
        if not self.calculated_market:
            return
        
        try:
            symbol = pattern_data.get('symbol', 'WDO')
            pattern = pattern_data.get('pattern')
            price = pattern_data.get('price')
            strength = pattern_data.get('strength', 5)
            volume = pattern_data.get('volume', 0)
            timestamp = pattern_data.get('timestamp', datetime.now())
            
            # Analisa confluência com mercado calculado
            confluence_signal = self.calculated_market.analyze_confluence(
                tape_pattern=pattern,
                price=price,
                symbol=symbol,
                strength=strength,
                volume=volume,
                timestamp=timestamp
            )
            
            if confluence_signal:
                # Sinal de alta confluência detectado!
                logger.info(f"💎 CONFLUÊNCIA DETECTADA: {pattern} @ {price} próximo a nível Frajola")
                
                # Valida com risk management
                if self.risk.validate_signal(confluence_signal):
                    self.event_bus.publish("SIGNAL_GENERATED", confluence_signal)
                else:
                    logger.warning("Sinal de confluência bloqueado pelo risk management")
                    
        except Exception as e:
            logger.error(f"Erro ao analisar confluência: {e}", exc_info=True)
    
    def _check_level_proximity(self, market_data: MarketData):
        """
        NOVO: Verifica proximidade com níveis calculados e gera alertas.
        """
        if not self.calculated_market:
            return
        
        for symbol in ['WDO', 'DOL']:
            if symbol not in market_data.data:
                continue
                
            current_price = market_data.data[symbol].last_price
            if not current_price:
                continue
            
            # Verifica proximidade
            proximity = self.calculated_market.check_proximity(current_price)
            
            if proximity:
                level_name, level_info = proximity
                
                # Evita alertas repetidos
                can_alert = True
                if self.last_level_alert[symbol]:
                    time_since_last = (datetime.now() - self.last_level_alert[symbol]).seconds
                    if time_since_last < 30:  # 30 segundos de cooldown
                        can_alert = False
                
                # Se mudou de nível ou pode alertar
                if (self.nearby_levels[symbol] != level_name) or can_alert:
                    # Cria alerta de proximidade
                    alert_signal = Signal(
                        source=SignalSource.TAPE_READING,
                        level=SignalLevel.INFO,
                        message=(
                            f"📍 {symbol} aproximando {level_name} {level_info.price:.2f} "
                            f"({level_info.position} {level_info.distance:.2f} pts)"
                        ),
                        details={
                            'symbol': symbol,
                            'level': level_name,
                            'level_price': level_info.price,
                            'current_price': current_price,
                            'distance': level_info.distance,
                            'position': level_info.position,
                            'type': 'LEVEL_PROXIMITY'
                        }
                    )
                    
                    self.event_bus.publish("SIGNAL_GENERATED", alert_signal)
                    self.last_level_alert[symbol] = datetime.now()
                
                self.nearby_levels[symbol] = level_name
            else:
                self.nearby_levels[symbol] = None
    
    def _analyze_confluence(self, signal: Signal, market_data: MarketData) -> Optional[Signal]:
        """
        NOVO: Analisa se um sinal do tape tem confluência com níveis calculados.
        """
        if not self.calculated_market or signal.source != SignalSource.TAPE_READING:
            return None
        
        details = signal.details
        if not details:
            return None
        
        pattern = details.get('pattern')
        symbol = details.get('symbol', 'WDO')
        price = details.get('price')
        strength = details.get('strength', 5)
        volume = details.get('volume', 0)
        
        if not all([pattern, price]):
            return None
        
        # Tenta criar sinal de confluência
        return self.calculated_market.analyze_confluence(
            tape_pattern=pattern,
            price=price,
            symbol=symbol,
            strength=strength,
            volume=volume,
            timestamp=datetime.now()
        )
    
    def _get_new_trades(self, market_data: MarketData) -> List:
        """Filtra trades novos e conta por símbolo."""
        new_trades = []
        trades_by_symbol_count = {'WDO': 0, 'DOL': 0}
        
        for symbol, data in market_data.data.items():
            symbol_new_count = 0
            
            for trade in data.trades:
                trade_id = f"{trade.time_str}_{trade.price}_{trade.volume}"
                
                if trade_id not in self.processed_trades[symbol]:
                    self.processed_trades[symbol].add(trade_id)
                    new_trades.append(trade)
                    symbol_new_count += 1
            
            # Registra por símbolo
            if self.performance_monitor and symbol_new_count > 0:
                self.performance_monitor.record_trades_processed(symbol_new_count)
                trades_by_symbol_count[symbol] = symbol_new_count
            
            # Limpa cache antigo
            if len(self.processed_trades[symbol]) > 500:
                old_trades = list(self.processed_trades[symbol])
                self.processed_trades[symbol] = set(old_trades[-250:])
        
        # Log se houver muitos trades
        total_new = sum(trades_by_symbol_count.values())
        if total_new > 100:
            logger.debug(f"Processados {total_new} trades novos - WDO: {trades_by_symbol_count['WDO']}, DOL: {trades_by_symbol_count['DOL']}")
        
        return new_trades
    
    def _check_regime_changes(self):
        """Verifica e notifica mudanças de regime."""
        for symbol in ['WDO', 'DOL']:
            current_regime_data = self.regime.get_regime_summary(symbol)
            current_regime = current_regime_data.get('regime')
            
            if self.previous_regime[symbol] is not None and self.previous_regime[symbol] != current_regime:
                self.event_bus.publish("REGIME_CHANGE", {
                    'symbol': symbol,
                    'old_regime': self.previous_regime[symbol],
                    'new_regime': current_regime,
                    'confidence': current_regime_data.get('confidence', 0.5),
                    'timestamp': datetime.now()
                })
                
                self.risk.update_market_regime(symbol, current_regime)
                logger.info(f"🔄 Regime mudou em {symbol}: {self.previous_regime[symbol]} → {current_regime}")
            
            self.previous_regime[symbol] = current_regime
    
    def _check_flow_direction(self, market_data: MarketData):
        """Detecta reversões significativas na direção do fluxo (CVD)."""
        for symbol in ['WDO', 'DOL']:
            summary = self.tape_reading.get_market_summary(symbol)
            cvd = summary.get('cvd', 0)
            cvd_total = summary.get('cvd_total', 0)
            
            # Determina direção atual
            if cvd > 50:
                current_direction = 'COMPRA'
            elif cvd < -50:
                current_direction = 'VENDA'
            else:
                current_direction = 'NEUTRO'
            
            # Adiciona ao histórico
            self.flow_history[symbol].append({
                'direction': current_direction,
                'cvd': cvd,
                'cvd_total': cvd_total,
                'timestamp': datetime.now()
            })
            
            # Mantém apenas últimos 10 registros
            if len(self.flow_history[symbol]) > 10:
                self.flow_history[symbol] = self.flow_history[symbol][-10:]
            
            # Verifica reversão
            previous_direction = self.flow_direction[symbol]
            
            if (previous_direction != current_direction and 
                previous_direction != 'NEUTRO' and 
                current_direction != 'NEUTRO' and
                previous_direction != current_direction):
                
                # Verifica cooldown
                can_alert = True
                if self.last_flow_alert[symbol]:
                    time_since_last = (datetime.now() - self.last_flow_alert[symbol]).seconds
                    if time_since_last < 20:
                        can_alert = False
                
                if can_alert:
                    strength = "FORTE" if abs(cvd) > 150 else "MODERADA"
                    
                    if current_direction == 'COMPRA':
                        emoji = "📈"
                        action = "possível FUNDO"
                    else:
                        emoji = "📉"
                        action = "possível TOPO"
                    
                    reversal_signal = Signal(
                        source=SignalSource.TAPE_READING,
                        level=SignalLevel.WARNING if strength == "MODERADA" else SignalLevel.ALERT,
                        message=(
                            f"🔀 REVERSÃO {strength} {symbol}: "
                            f"{previous_direction} → {current_direction} "
                            f"(CVD: {cvd:+d}, Total: {cvd_total:+,}) - {action} {emoji}"
                        ),
                        details={
                            'symbol': symbol,
                            'pattern': 'FLOW_REVERSAL',
                            'previous_direction': previous_direction,
                            'current_direction': current_direction,
                            'strength': strength,
                            'cvd': cvd,
                            'cvd_total': cvd_total,
                            'flow_history': self.flow_history[symbol][-5:]
                        }
                    )
                    
                    self.event_bus.publish("SIGNAL_GENERATED", reversal_signal)
                    self.last_flow_alert[symbol] = datetime.now()
                    
                    logger.info(
                        f"🔀 Reversão de fluxo detectada em {symbol}: "
                        f"{previous_direction} → {current_direction}"
                    )
            
            self.flow_direction[symbol] = current_direction
    
    def handle_signal(self, signal: Signal):
        """Handler para sinais aprovados e prontos para exibição."""
        # Adiciona ao display
        self.display.add_signal(signal)
        
        # Salva no repositório
        self.signal_repo.save(signal)
        
        # Log especial para sinais de confluência
        if signal.source == SignalSource.CONFLUENCE:
            logger.warning(f"💎 {signal.message}")
        elif signal.level == SignalLevel.ALERT:
            logger.info(f"⚠️ ALERTA: {signal.message}")
    
    def handle_manipulation(self, data: Dict):
        """Handler para alertas de manipulação detectada."""
        signal = data.get('signal')
        risk_info = data.get('risk_info', {})
        symbol = data.get('symbol', 'UNKNOWN')
        
        manipulation_types = risk_info.get('risks', [])
        action_required = risk_info.get('action_required', 'Opere com extrema cautela')
        
        # Formata mensagem
        if 'LAYERING' in manipulation_types:
            emoji = "🧱"
            desc = "LAYERING (ordens falsas em camadas)"
        elif 'SPOOFING' in manipulation_types:
            emoji = "👻"
            desc = "SPOOFING (ordens fantasma)"
        else:
            emoji = "🚨"
            desc = "MANIPULAÇÃO"
        
        manipulation_signal = Signal(
            source=SignalSource.MANIPULATION,
            level=SignalLevel.ALERT,
            message=f"{emoji} {desc} em {symbol}: {action_required}",
            details={
                'original_signal': signal.dict() if signal else None,
                'manipulation_types': manipulation_types,
                'risk_details': risk_info.get('details', []),
                'symbol': symbol,
                'confidence_reduction': risk_info.get('confidence', 1.0),
                'timestamp': datetime.now()
            }
        )
        
        # Envia direto para display
        self.display.add_signal(manipulation_signal)
        self.signal_repo.save(manipulation_signal)
        
        logger.warning(
            f"🚨 Manipulação detectada em {symbol}: {manipulation_types} - "
            f"Ação: {action_required}"
        )
        
        self.event_bus.publish("MANIPULATION_ALERT", {
            'symbol': symbol,
            'types': manipulation_types,
            'timestamp': datetime.now(),
            'severity': 'HIGH' if len(manipulation_types) > 1 else 'MEDIUM'
        })
    
    def _build_analysis(self, market_data: MarketData) -> Dict[str, Any]:
        """Constrói dados de análise completos incluindo níveis calculados."""
        logger.debug("Construindo análise para display...")
        
        tape_summaries = {}
        
        # Pega totais do performance monitor
        trade_totals = {}
        if self.performance_monitor and hasattr(self.performance_monitor, 'get_trade_totals'):
            trade_totals = self.performance_monitor.get_trade_totals()
        
        # Dados do tape reading
        for symbol in ['WDO', 'DOL']:
            try:
                summary = self.tape_reading.get_market_summary(symbol)
                
                # Adiciona total de trades
                if trade_totals:
                    summary['total_trades'] = trade_totals.get(symbol, 0)
                else:
                    summary['total_trades'] = summary.get('cache_size', 0)
                
                # NOVO: Adiciona nível próximo se houver
                if self.nearby_levels[symbol]:
                    summary['nearby_level'] = self.nearby_levels[symbol]
                
                tape_summaries[symbol] = summary
                
            except Exception as e:
                logger.error(f"Erro ao obter resumo de {symbol}: {e}")
                tape_summaries[symbol] = self._get_empty_summary()
        
        # NOVO: Dados do mercado calculado
        calculated_levels = {}
        if self.calculated_market:
            calculated_levels = {
                'valor_justo': self.calculated_market.get_fair_value(),
                'niveis': self.calculated_market.get_current_levels(),
                'is_ptax_window': self.calculated_market.is_ptax_window()
            }
        
        # Total geral de trades
        if trade_totals:
            total_geral = trade_totals.get('total', 0)
        else:
            total_geral = sum(s.get('total_trades', 0) for s in tape_summaries.values())
        
        analysis = {
            'tape_summaries': tape_summaries,
            'risk_status': self.risk.get_risk_status(),
            'regime': {
                'WDO': self.regime.get_regime_summary('WDO'),
                'DOL': self.regime.get_regime_summary('DOL')
            },
            'flow_direction': self.flow_direction.copy(),
            'calculated_levels': calculated_levels,  # NOVO
            'total_trades_processed': total_geral,
            'timestamp': datetime.now()
        }
        
        logger.debug(f"Análise construída - Total de trades: {total_geral}")
        
        return analysis
    
    def _get_empty_summary(self) -> Dict[str, Any]:
        """Retorna um resumo vazio para casos de erro."""
        return {
            'cvd': 0,
            'cvd_total': 0,
            'cvd_roc': 0.0,
            'poc': None,
            'supports': [],
            'resistances': [],
            'cache_size': 0,
            'total_trades': 0,
            'pending_patterns': 0,
            'hidden_levels': 0,
            'trap_risk': 'MINIMAL',
            'nearby_level': None
        }