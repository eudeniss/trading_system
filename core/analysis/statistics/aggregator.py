#core/analysis/statistics/aggregator.py
"""Agregador de estatísticas otimizado."""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
import numpy as np
import logging

from core.entities.market_data import MarketData
from core.contracts.messaging import ISystemEventBus
from core.entities.signal import Signal

logger = logging.getLogger(__name__)


class MarketStatsAggregator:
    """
    Agrega estatísticas de todos os analyzers em um contexto unificado.
    Fornece métricas consolidadas para tomada de decisão.
    """
    
    __slots__ = ['event_bus', 'services', 'aggregated_stats', 'stats_history',
                 'update_interval', 'last_update']
    
    def __init__(self, event_bus: ISystemEventBus):
        self.event_bus = event_bus
        
        # Armazena referências aos serviços
        self.services = {}
        
        # Estatísticas agregadas
        self.aggregated_stats = {
            'market_profile': {},
            'flow_metrics': {},
            'pattern_frequencies': defaultdict(int),
            'signal_quality': {},
            'time_series': defaultdict(lambda: deque(maxlen=1000)),
            'correlations': {},
            'regime': 'NORMAL'
        }
        
        # Histórico para análise temporal
        self.stats_history = deque(maxlen=3600)  # 1 hora em segundos
        
        # Configurações
        self.update_interval = 1.0  # segundos
        self.last_update = datetime.now()
        
        # Subscrever a eventos
        self._subscribe_to_events()
        
        logger.info("MarketStatsAggregator inicializado")
    
    def _subscribe_to_events(self) -> None:
        """Subscreve aos eventos relevantes do sistema."""
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self._handle_market_update)
        self.event_bus.subscribe("SIGNAL_GENERATED", self._handle_signal)
        self.event_bus.subscribe("TAPE_READING_UPDATE", self._handle_tape_reading)
        self.event_bus.subscribe("ARBITRAGE_CHECK", self._handle_arbitrage)
    
    def register_service(self, name: str, service: Any) -> None:
        """Registra um serviço para agregação de dados."""
        self.services[name] = service
        logger.info(f"Serviço {name} registrado no aggregator")
    
    def _handle_market_update(self, market_data: MarketData) -> None:
        """Processa atualização de mercado."""
        now = datetime.now()
        
        # Limita frequência de atualizações
        if (now - self.last_update).total_seconds() < self.update_interval:
            return
        
        self.last_update = now
        
        # Agrega dados de todos os serviços
        aggregated = self._aggregate_all_stats()
        
        # Adiciona ao histórico
        self.stats_history.append({
            'timestamp': now,
            'stats': aggregated
        })
        
        # Atualiza estatísticas
        self._update_aggregated_stats(aggregated)
        
        # Detecta mudanças de regime
        self._detect_regime_changes()
        
        # Emite evento com estatísticas agregadas
        self.event_bus.publish("STATS_AGGREGATED", {
            'timestamp': now,
            'stats': self.aggregated_stats,
            'regime': self.aggregated_stats['regime']
        })
    
    def _aggregate_all_stats(self) -> Dict:
        """Agrega estatísticas de todos os serviços registrados."""
        aggregated = {
            'timestamp': datetime.now(),
            'services': {}
        }
        
        # Tape Reading Service
        if 'tape_reading' in self.services:
            tape_service = self.services['tape_reading']
            for symbol in ['WDO', 'DOL']:
                summary = tape_service.get_market_summary(symbol)
                aggregated['services'][f'tape_{symbol}'] = summary
        
        # Arbitrage Service
        if 'arbitrage' in self.services:
            arb_service = self.services['arbitrage']
            arb_stats = arb_service.get_spread_statistics()
            aggregated['services']['arbitrage'] = arb_stats
        
        # Risk Management Service
        if 'risk' in self.services:
            risk_service = self.services['risk']
            risk_status = risk_service.get_risk_status()  # <<< CORRETO: get_risk_status() ao invés de get_status()
            aggregated['services']['risk'] = risk_status
        
        return aggregated
    
    def _update_aggregated_stats(self, current_data: Dict) -> None:
        """Atualiza estatísticas agregadas com novos dados."""
        services = current_data.get('services', {})
        
        # 1. Market Profile
        self._update_market_profile(services)
        
        # 2. Flow Metrics
        self._update_flow_metrics(services)
        
        # 3. Time Series
        self._update_time_series(services)
        
        # 4. Correlations
        self._update_correlations()
        
        # 5. Signal Quality
        self._update_signal_quality(services)
    
    def _update_market_profile(self, services: Dict) -> None:
        """Atualiza perfil de mercado agregado."""
        profile = {}
        
        # Volume total por símbolo
        for symbol in ['WDO', 'DOL']:
            tape_key = f'tape_{symbol}'
            if tape_key in services and services[tape_key]:
                tape_data = services[tape_key]
                profile[f'{symbol}_volume'] = tape_data.get('total_volume', 0)
                profile[f'{symbol}_cvd'] = tape_data.get('cvd_total', 0)
                profile[f'{symbol}_momentum'] = tape_data.get('momentum', 'NEUTRO')
        
        # Spread médio de arbitragem
        arb = services.get('arbitrage')
        if arb:  # Verifica se arb não é None
            profile['spread_mean'] = arb.get('mean', 0)
            profile['spread_std'] = arb.get('std', 0)
            profile['spread_current'] = arb.get('current', 0)
        else:
            profile['spread_mean'] = 0
            profile['spread_std'] = 0
            profile['spread_current'] = 0
            
        self.aggregated_stats['market_profile'] = profile
    
    def _update_flow_metrics(self, services: Dict) -> None:
        """Atualiza métricas de fluxo agregadas."""
        flow = {}
        
        # CVD agregado
        total_cvd = 0
        for symbol in ['WDO', 'DOL']:
            tape_key = f'tape_{symbol}'
            if tape_key in services and services[tape_key]:
                cvd = services[tape_key].get('cvd_total', 0)
                flow[f'{symbol}_cvd'] = cvd
                total_cvd += cvd
        
        flow['net_cvd'] = total_cvd
        flow['cvd_divergence'] = abs(flow.get('WDO_cvd', 0) - flow.get('DOL_cvd', 0))
        
        # Pressão agregada
        pressures = []
        for symbol in ['WDO', 'DOL']:
            tape_key = f'tape_{symbol}'
            if tape_key in services and services[tape_key]:
                pressure = services[tape_key].get('pressure', 'EQUILIBRADO')
                if 'COMPRA' in pressure:
                    pressures.append(1)
                elif 'VENDA' in pressure:
                    pressures.append(-1)
                else:
                    pressures.append(0)
        
        flow['aggregate_pressure'] = sum(pressures)
        flow['pressure_alignment'] = 'ALIGNED' if len(set(pressures)) == 1 and len(pressures) > 1 else 'DIVERGENT'
        
        self.aggregated_stats['flow_metrics'] = flow
    
    def _update_time_series(self, services: Dict) -> None:
        """Atualiza séries temporais para análise."""
        timestamp = datetime.now()
        
        # CVD time series
        for symbol in ['WDO', 'DOL']:
            tape_key = f'tape_{symbol}'
            if tape_key in services and services[tape_key]:
                cvd = services[tape_key].get('cvd', 0)
                self.aggregated_stats['time_series'][f'{symbol}_cvd'].append({
                    'timestamp': timestamp,
                    'value': cvd
                })
        
        # Spread time series
        arb = services.get('arbitrage')
        if arb:
            spread = arb.get('current', 0)
            self.aggregated_stats['time_series']['spread'].append({
                'timestamp': timestamp,
                'value': spread
            })
        
        # Risk level time series
        risk_data = services.get('risk')
        if risk_data:
            risk_level = risk_data.get('risk_level', 'LOW')
            risk_value = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'CRITICAL': 3}.get(risk_level, 0)
            self.aggregated_stats['time_series']['risk'].append({
                'timestamp': timestamp,
                'value': risk_value
            })
    
    def _update_correlations(self) -> None:
        """Calcula correlações entre diferentes métricas."""
        correlations = {}
        
        # Correlação CVD WDO x DOL
        wdo_cvd = [item['value'] for item in self.aggregated_stats['time_series']['WDO_cvd']]
        dol_cvd = [item['value'] for item in self.aggregated_stats['time_series']['DOL_cvd']]
        
        if len(wdo_cvd) >= 100 and len(dol_cvd) >= 100:
            wdo_recent = np.array(wdo_cvd[-100:])
            dol_recent = np.array(dol_cvd[-100:])
            
            if np.std(wdo_recent) > 0 and np.std(dol_recent) > 0:
                correlation = np.corrcoef(wdo_recent, dol_recent)[0, 1]
                correlations['cvd_wdo_dol'] = correlation
            else:
                correlations['cvd_wdo_dol'] = 0
        
        # Correlação Spread x Risk
        spread_data = [item['value'] for item in self.aggregated_stats['time_series']['spread']]
        risk_data = [item['value'] for item in self.aggregated_stats['time_series']['risk']]
        
        if len(spread_data) >= 50 and len(risk_data) >= 50:
            spread_recent = np.array(spread_data[-50:])
            risk_recent = np.array(risk_data[-50:])
            
            if np.std(spread_recent) > 0 and np.std(risk_recent) > 0:
                correlation = np.corrcoef(spread_recent, risk_recent)[0, 1]
                correlations['spread_risk'] = correlation
        
        self.aggregated_stats['correlations'] = correlations
    
    def _update_signal_quality(self, services: Dict) -> None:
        """Atualiza métricas de qualidade de sinais."""
        quality = {}
        
        risk_data = services.get('risk')
        if risk_data:
            metrics = risk_data.get('metrics', {})
            
            quality['approval_rate'] = metrics.get('approval_rate', '0%')
            quality['consecutive_losses'] = metrics.get('consecutive_losses', 0)
            quality['active_breakers'] = len(risk_data.get('active_breakers', []))
        
        self.aggregated_stats['signal_quality'] = quality
    
    def _detect_regime_changes(self) -> None:
        """Detecta mudanças no regime de mercado."""
        if len(self.stats_history) < 60:  # Precisa de pelo menos 1 minuto
            return
        
        # Analisa últimos 5 minutos
        recent_stats = list(self.stats_history)[-300:]
        
        # Extrai métricas chave
        spreads = []
        volumes = []
        
        for stat in recent_stats:
            services = stat['stats'].get('services', {})
            
            # Spreads para volatilidade
            arb_data = services.get('arbitrage')
            if arb_data:
                spreads.append(arb_data.get('current', 0))
            
            # Volume agregado
            total_vol = 0
            for symbol in ['WDO', 'DOL']:
                tape_data = services.get(f'tape_{symbol}')
                if tape_data:
                    total_vol += tape_data.get('total_volume', 0)
            volumes.append(total_vol)
        
        # Calcula características do regime
        regime_features = {}
        
        if spreads:
            spread_volatility = np.std(spreads)
            regime_features['volatility'] = spread_volatility
            
            # Classifica volatilidade
            if spread_volatility < 0.5:
                volatility_regime = 'LOW'
            elif spread_volatility < 1.5:
                volatility_regime = 'NORMAL'
            else:
                volatility_regime = 'HIGH'
        else:
            volatility_regime = 'NORMAL'
        
        if volumes:
            avg_volume = np.mean(volumes)
            regime_features['avg_volume'] = avg_volume
            
            # Classifica liquidez
            if avg_volume < 1000:
                liquidity_regime = 'LOW'
            elif avg_volume < 5000:
                liquidity_regime = 'NORMAL'
            else:
                liquidity_regime = 'HIGH'
        else:
            liquidity_regime = 'NORMAL'
        
        # Determina regime geral
        if volatility_regime == 'HIGH' and liquidity_regime == 'HIGH':
            regime = 'VOLATILE_ACTIVE'
        elif volatility_regime == 'HIGH' and liquidity_regime == 'LOW':
            regime = 'VOLATILE_THIN'
        elif volatility_regime == 'LOW' and liquidity_regime == 'HIGH':
            regime = 'STABLE_ACTIVE'
        elif volatility_regime == 'LOW' and liquidity_regime == 'LOW':
            regime = 'QUIET'
        else:
            regime = 'NORMAL'
        
        # Atualiza se mudou
        if regime != self.aggregated_stats['regime']:
            old_regime = self.aggregated_stats['regime']
            self.aggregated_stats['regime'] = regime
            
            logger.info(f"Mudança de regime detectada: {old_regime} -> {regime}")
            
            self.event_bus.publish("REGIME_CHANGE", {
                'old_regime': old_regime,
                'new_regime': regime,
                'features': regime_features,
                'timestamp': datetime.now()
            })
    
    def _handle_signal(self, signal: Signal) -> None:
        """Processa sinal gerado para estatísticas."""
        if hasattr(signal, 'details') and isinstance(signal.details, dict):
            pattern = signal.details.get('original_pattern', 'UNKNOWN')
        else:
            pattern = 'UNKNOWN'
        self.aggregated_stats['pattern_frequencies'][pattern] += 1
    
    def _handle_tape_reading(self, data: Dict) -> None:
        pass
    
    def _handle_arbitrage(self, data: Dict) -> None:
        pass
    
    def get_market_context(self) -> Dict:
        """Retorna contexto de mercado consolidado."""
        context = {
            'regime': self.aggregated_stats['regime'],
            'profile': self.aggregated_stats['market_profile'],
            'flow': self.aggregated_stats['flow_metrics'],
            'quality': self.aggregated_stats['signal_quality'],
            'correlations': self.aggregated_stats['correlations'],
            'pattern_distribution': dict(self.aggregated_stats['pattern_frequencies'])
        }
        
        context['trends'] = self._calculate_trends()
        context['alerts'] = self._generate_alerts()
        
        return context
    
    def _calculate_trends(self) -> Dict:
        """Calcula tendências das principais métricas."""
        trends = {}
        
        for symbol in ['WDO', 'DOL']:
            cvd_series = list(self.aggregated_stats['time_series'][f'{symbol}_cvd'])
            if len(cvd_series) >= 20:
                recent_values = [item['value'] for item in cvd_series[-20:]]
                
                if np.std(recent_values) > 0:
                    x = np.arange(len(recent_values))
                    slope = np.polyfit(x, recent_values, 1)[0]
                    
                    if abs(slope) < 1:
                        trends[f'{symbol}_cvd'] = 'LATERAL'
                    elif slope > 0:
                        trends[f'{symbol}_cvd'] = 'ALTA'
                    else:
                        trends[f'{symbol}_cvd'] = 'BAIXA'
                else:
                    trends[f'{symbol}_cvd'] = 'LATERAL'
        
        spread_series = list(self.aggregated_stats['time_series']['spread'])
        if len(spread_series) >= 20:
            recent_spreads = [item['value'] for item in spread_series[-20:]]
            avg_spread = np.mean(recent_spreads)
            current_spread = recent_spreads[-1] if recent_spreads else 0
            
            if current_spread > avg_spread * 1.2:
                trends['spread'] = 'EXPANDING'
            elif current_spread < avg_spread * 0.8:
                trends['spread'] = 'CONTRACTING'
            else:
                trends['spread'] = 'STABLE'
        
        return trends
    
    def _generate_alerts(self) -> List[Dict]:
        """Gera alertas baseados nas estatísticas agregadas."""
        alerts = []
        
        flow = self.aggregated_stats['flow_metrics']
        if flow.get('pressure_alignment') == 'DIVERGENT' and abs(flow.get('cvd_divergence', 0)) > 500:
            alerts.append({
                'type': 'FLOW_DIVERGENCE', 'level': 'WARNING',
                'message': 'Divergência significativa de fluxo entre WDO e DOL'
            })
        
        correlations = self.aggregated_stats['correlations']
        if abs(correlations.get('cvd_wdo_dol', 1)) < 0.3:
            alerts.append({
                'type': 'CORRELATION_BREAK', 'level': 'INFO',
                'message': 'Correlação fraca entre CVD WDO/DOL detectada'
            })

        if self.aggregated_stats['regime'] in ['VOLATILE_ACTIVE', 'VOLATILE_THIN']:
            alerts.append({
                'type': 'VOLATILE_REGIME', 'level': 'WARNING',
                'message': f"Regime volátil detectado: {self.aggregated_stats['regime']}"
            })
        
        quality = self.aggregated_stats['signal_quality']
        if quality.get('consecutive_losses', 0) >= 3:
            alerts.append({
                'type': 'POOR_PERFORMANCE', 'level': 'ALERT',
                'message': f"Sequência de {quality['consecutive_losses']} perdas consecutivas"
            })
        
        return alerts