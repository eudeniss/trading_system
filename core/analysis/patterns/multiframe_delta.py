#core/analysis/patterns/multiframe_delta.py
"""
Analisador de delta multi-timeframe - FASE 5.3.
Analisa divergências e confluências de fluxo em diferentes períodos.
"""
from typing import List, Optional, Dict, Tuple
from collections import deque
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
import logging

from core.entities.trade import Trade, TradeSide

logger = logging.getLogger(__name__)


class TimeFrame(str, Enum):
    """Timeframes disponíveis para análise."""
    MICRO = "MICRO"      # 1 minuto
    SHORT = "SHORT"      # 5 minutos
    MEDIUM = "MEDIUM"    # 15 minutos
    LONG = "LONG"        # 30 minutos


class MultiframeDeltaAnalyzer:
    """
    Analisa delta (diferença entre compra e venda) em múltiplos timeframes.
    
    Detecta:
    - Divergências entre timeframes
    - Confluência de fluxo
    - Mudanças de regime
    - Acumulação/Distribuição oculta
    """
    
    def __init__(self, config: Dict = None):
        """
        Inicializa o analisador com configurações.
        
        Args:
            config: Configurações do analisador
        """
        self.config = config or {}
        
        # Configuração de timeframes (em segundos)
        self.timeframe_config = {
            TimeFrame.MICRO: self.config.get('micro_seconds', 60),      # 1 min
            TimeFrame.SHORT: self.config.get('short_seconds', 300),     # 5 min
            TimeFrame.MEDIUM: self.config.get('medium_seconds', 900),   # 15 min
            TimeFrame.LONG: self.config.get('long_seconds', 1800)       # 30 min
        }
        
        # Thresholds
        self.divergence_threshold = self.config.get('divergence_threshold', 0.3)
        self.confluence_threshold = self.config.get('confluence_threshold', 0.7)
        self.regime_change_threshold = self.config.get('regime_change_threshold', 0.5)
        
        # Storage de trades por símbolo e timeframe
        self.trade_storage: Dict[str, Dict[TimeFrame, deque]] = {}
        
        # Cache de cálculos
        self.delta_cache: Dict[str, Dict[TimeFrame, Dict]] = {}
        
        # Histórico de regimes
        self.regime_history: Dict[str, deque] = {}
        
        # Estatísticas
        self.stats = {
            'divergences_detected': 0,
            'confluences_detected': 0,
            'regime_changes': 0,
            'hidden_accumulation': 0,
            'hidden_distribution': 0
        }
        
        logger.info(
            f"MultiframeDeltaAnalyzer inicializado - "
            f"Timeframes: {list(self.timeframe_config.keys())}"
        )
    
    def update(self, symbol: str, trades: List[Trade]) -> List[Dict]:
        """
        Atualiza análise com novos trades e retorna sinais detectados.
        
        Args:
            symbol: Símbolo do ativo
            trades: Lista de trades novos
            
        Returns:
            Lista de sinais detectados
        """
        if not trades:
            return []
        
        # Inicializa storage se necessário
        if symbol not in self.trade_storage:
            self._initialize_symbol_storage(symbol)
        
        # Adiciona trades ao storage
        self._update_trade_storage(symbol, trades)
        
        # Calcula deltas para cada timeframe
        current_deltas = self._calculate_all_deltas(symbol)
        
        # Detecta padrões
        signals = []
        
        # 1. Divergências entre timeframes
        divergence_signal = self._detect_divergence(symbol, current_deltas)
        if divergence_signal:
            signals.append(divergence_signal)
        
        # 2. Confluência de fluxo
        confluence_signal = self._detect_confluence(symbol, current_deltas)
        if confluence_signal:
            signals.append(confluence_signal)
        
        # 3. Mudança de regime
        regime_signal = self._detect_regime_change(symbol, current_deltas)
        if regime_signal:
            signals.append(regime_signal)
        
        # 4. Acumulação/Distribuição oculta
        hidden_signal = self._detect_hidden_flow(symbol, current_deltas)
        if hidden_signal:
            signals.append(hidden_signal)
        
        # Atualiza cache
        self.delta_cache[symbol] = current_deltas
        
        return signals
    
    def _initialize_symbol_storage(self, symbol: str):
        """Inicializa storage para um símbolo."""
        self.trade_storage[symbol] = {}
        self.delta_cache[symbol] = {}
        self.regime_history[symbol] = deque(maxlen=100)
        
        for tf in TimeFrame:
            # Tamanho do deque baseado no timeframe
            max_size = self.timeframe_config[tf] * 10  # Mantém 10x o período
            self.trade_storage[symbol][tf] = deque(maxlen=max_size)
            self.delta_cache[symbol][tf] = {'delta': 0, 'delta_pct': 0, 'total_volume': 0}
    
    def _update_trade_storage(self, symbol: str, trades: List[Trade]):
        """Adiciona trades ao storage de cada timeframe."""
        now = datetime.now()
        
        for trade in trades:
            # Adiciona a todos os timeframes
            for tf in TimeFrame:
                self.trade_storage[symbol][tf].append(trade)
    
    def _calculate_all_deltas(self, symbol: str) -> Dict[TimeFrame, Dict]:
        """Calcula delta para todos os timeframes."""
        now = datetime.now()
        deltas = {}
        
        for tf in TimeFrame:
            trades_deque = self.trade_storage[symbol][tf]
            if not trades_deque:
                deltas[tf] = {'delta': 0, 'delta_pct': 0, 'total_volume': 0, 'trade_count': 0}
                continue
            
            # Filtra trades dentro do período
            cutoff = now - timedelta(seconds=self.timeframe_config[tf])
            relevant_trades = [t for t in trades_deque if t.timestamp > cutoff]
            
            if not relevant_trades:
                deltas[tf] = {'delta': 0, 'delta_pct': 0, 'total_volume': 0, 'trade_count': 0}
                continue
            
            # Calcula métricas
            buy_volume = sum(t.volume for t in relevant_trades if t.side == TradeSide.BUY)
            sell_volume = sum(t.volume for t in relevant_trades if t.side == TradeSide.SELL)
            total_volume = buy_volume + sell_volume
            
            delta = buy_volume - sell_volume
            delta_pct = delta / total_volume if total_volume > 0 else 0
            
            # Calcula tendência (weighted price)
            if len(relevant_trades) >= 2:
                early_price = np.mean([t.price for t in relevant_trades[:5]])
                late_price = np.mean([t.price for t in relevant_trades[-5:]])
                price_trend = (late_price - early_price) / early_price
            else:
                price_trend = 0
            
            deltas[tf] = {
                'delta': delta,
                'delta_pct': delta_pct,
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'total_volume': total_volume,
                'trade_count': len(relevant_trades),
                'price_trend': price_trend
            }
        
        return deltas
    
    def _detect_divergence(self, symbol: str, deltas: Dict[TimeFrame, Dict]) -> Optional[Dict]:
        """Detecta divergências entre timeframes."""
        # Compara timeframes curto vs longo
        micro_delta = deltas[TimeFrame.MICRO]['delta_pct']
        short_delta = deltas[TimeFrame.SHORT]['delta_pct']
        medium_delta = deltas[TimeFrame.MEDIUM]['delta_pct']
        long_delta = deltas[TimeFrame.LONG]['delta_pct']
        
        # Verifica se há dados suficientes
        if deltas[TimeFrame.SHORT]['trade_count'] < 10 or deltas[TimeFrame.LONG]['trade_count'] < 20:
            return None
        
        # Detecta divergências significativas
        divergences = []
        
        # Micro vs Long
        if abs(micro_delta - long_delta) > self.divergence_threshold:
            if micro_delta > 0.2 and long_delta < -0.2:
                divergences.append({
                    'type': 'BULLISH_DIVERGENCE',
                    'description': 'Compra no curto prazo, venda no longo prazo',
                    'strength': abs(micro_delta - long_delta)
                })
            elif micro_delta < -0.2 and long_delta > 0.2:
                divergences.append({
                    'type': 'BEARISH_DIVERGENCE',
                    'description': 'Venda no curto prazo, compra no longo prazo',
                    'strength': abs(micro_delta - long_delta)
                })
        
        # Short vs Medium
        if abs(short_delta - medium_delta) > self.divergence_threshold * 0.8:
            if short_delta > 0.1 and medium_delta < -0.1:
                divergences.append({
                    'type': 'SHORT_TERM_REVERSAL',
                    'description': 'Possível reversão de curto prazo',
                    'strength': abs(short_delta - medium_delta)
                })
        
        if divergences:
            self.stats['divergences_detected'] += 1
            
            # Escolhe a divergência mais forte
            strongest = max(divergences, key=lambda x: x['strength'])
            
            return {
                'pattern': 'MULTIFRAME_DIVERGENCE',
                'symbol': symbol,
                'divergence_type': strongest['type'],
                'description': strongest['description'],
                'timeframes_analysis': {
                    'micro': {'delta_pct': micro_delta, 'volume': deltas[TimeFrame.MICRO]['total_volume']},
                    'short': {'delta_pct': short_delta, 'volume': deltas[TimeFrame.SHORT]['total_volume']},
                    'medium': {'delta_pct': medium_delta, 'volume': deltas[TimeFrame.MEDIUM]['total_volume']},
                    'long': {'delta_pct': long_delta, 'volume': deltas[TimeFrame.LONG]['total_volume']}
                },
                'confidence': min(0.9, strongest['strength'] / 0.5)
            }
        
        return None
    
    def _detect_confluence(self, symbol: str, deltas: Dict[TimeFrame, Dict]) -> Optional[Dict]:
        """Detecta confluência de fluxo em múltiplos timeframes."""
        # Extrai deltas percentuais
        delta_values = [d['delta_pct'] for d in deltas.values() if d['trade_count'] > 5]
        
        if len(delta_values) < 3:
            return None
        
        # Verifica se todos apontam na mesma direção
        all_positive = all(d > 0.1 for d in delta_values)
        all_negative = all(d < -0.1 for d in delta_values)
        
        if all_positive or all_negative:
            avg_delta = np.mean(delta_values)
            
            if abs(avg_delta) > self.confluence_threshold:
                self.stats['confluences_detected'] += 1
                
                direction = "COMPRA" if all_positive else "VENDA"
                
                return {
                    'pattern': 'MULTIFRAME_CONFLUENCE',
                    'symbol': symbol,
                    'direction': direction,
                    'strength': abs(avg_delta),
                    'description': f'Confluência forte de {direction} em todos os timeframes',
                    'timeframes_aligned': len(delta_values),
                    'average_delta': avg_delta,
                    'confidence': min(0.95, abs(avg_delta))
                }
        
        return None
    
    def _detect_regime_change(self, symbol: str, deltas: Dict[TimeFrame, Dict]) -> Optional[Dict]:
        """Detecta mudanças de regime baseado em análise multiframe."""
        # Calcula regime atual
        current_regime = self._calculate_regime(deltas)
        
        # Adiciona ao histórico
        self.regime_history[symbol].append({
            'timestamp': datetime.now(),
            'regime': current_regime,
            'deltas': deltas[TimeFrame.MEDIUM]['delta_pct']
        })
        
        if len(self.regime_history[symbol]) < 5:
            return None
        
        # Compara com regimes anteriores
        recent_regimes = [r['regime'] for r in list(self.regime_history[symbol])[-5:]]
        previous_regime = recent_regimes[-2] if len(recent_regimes) > 1 else None
        
        # Detecta mudança significativa
        if previous_regime and current_regime != previous_regime:
            # Verifica se a mudança é consistente
            regime_counts = {r: recent_regimes.count(r) for r in set(recent_regimes)}
            
            if regime_counts.get(current_regime, 0) >= 2:  # Novo regime apareceu 2+ vezes
                self.stats['regime_changes'] += 1
                
                return {
                    'pattern': 'REGIME_CHANGE',
                    'symbol': symbol,
                    'previous_regime': previous_regime,
                    'new_regime': current_regime,
                    'description': f'Mudança de regime: {previous_regime} → {current_regime}',
                    'consistency': regime_counts[current_regime] / len(recent_regimes),
                    'current_metrics': {
                        'short_delta': deltas[TimeFrame.SHORT]['delta_pct'],
                        'medium_delta': deltas[TimeFrame.MEDIUM]['delta_pct'],
                        'long_delta': deltas[TimeFrame.LONG]['delta_pct']
                    }
                }
        
        return None
    
    def _detect_hidden_flow(self, symbol: str, deltas: Dict[TimeFrame, Dict]) -> Optional[Dict]:
        """Detecta acumulação ou distribuição oculta."""
        # Analisa discrepância entre preço e fluxo
        medium_delta = deltas[TimeFrame.MEDIUM]
        long_delta = deltas[TimeFrame.LONG]
        
        if medium_delta['trade_count'] < 20 or long_delta['trade_count'] < 30:
            return None
        
        price_trend = long_delta['price_trend']
        flow_trend = long_delta['delta_pct']
        
        # Hidden Accumulation: Preço cai mas fluxo é comprador
        if price_trend < -0.001 and flow_trend > 0.3:
            self.stats['hidden_accumulation'] += 1
            
            return {
                'pattern': 'HIDDEN_ACCUMULATION',
                'symbol': symbol,
                'description': 'Acumulação oculta detectada - preço cai mas fluxo é comprador',
                'price_change': price_trend * 100,
                'net_flow': flow_trend,
                'supporting_timeframes': self._count_supporting_timeframes(deltas, 'BUY'),
                'confidence': min(0.85, flow_trend)
            }
        
        # Hidden Distribution: Preço sobe mas fluxo é vendedor
        elif price_trend > 0.001 and flow_trend < -0.3:
            self.stats['hidden_distribution'] += 1
            
            return {
                'pattern': 'HIDDEN_DISTRIBUTION',
                'symbol': symbol,
                'description': 'Distribuição oculta detectada - preço sobe mas fluxo é vendedor',
                'price_change': price_trend * 100,
                'net_flow': flow_trend,
                'supporting_timeframes': self._count_supporting_timeframes(deltas, 'SELL'),
                'confidence': min(0.85, abs(flow_trend))
            }
        
        return None
    
    def _calculate_regime(self, deltas: Dict[TimeFrame, Dict]) -> str:
        """Calcula o regime atual baseado nos deltas."""
        # Pondera por timeframe (mais peso para períodos longos)
        weights = {
            TimeFrame.MICRO: 0.1,
            TimeFrame.SHORT: 0.2,
            TimeFrame.MEDIUM: 0.3,
            TimeFrame.LONG: 0.4
        }
        
        weighted_delta = 0
        total_weight = 0
        
        for tf, weight in weights.items():
            if deltas[tf]['trade_count'] > 10:
                weighted_delta += deltas[tf]['delta_pct'] * weight
                total_weight += weight
        
        if total_weight > 0:
            weighted_delta /= total_weight
        
        # Determina regime
        if weighted_delta > 0.3:
            return "ACCUMULATION"
        elif weighted_delta < -0.3:
            return "DISTRIBUTION"
        elif abs(weighted_delta) < 0.1:
            return "BALANCED"
        else:
            return "TRANSITIONING"
    
    def _count_supporting_timeframes(self, deltas: Dict[TimeFrame, Dict], direction: str) -> int:
        """Conta quantos timeframes suportam uma direção."""
        count = 0
        threshold = 0.1 if direction == 'BUY' else -0.1
        
        for tf_delta in deltas.values():
            if tf_delta['trade_count'] > 5:
                if direction == 'BUY' and tf_delta['delta_pct'] > threshold:
                    count += 1
                elif direction == 'SELL' and tf_delta['delta_pct'] < threshold:
                    count += 1
        
        return count
    
    def get_current_analysis(self, symbol: str) -> Dict:
        """Retorna análise atual completa para um símbolo."""
        if symbol not in self.delta_cache:
            return {'status': 'NO_DATA'}
        
        current_deltas = self.delta_cache[symbol]
        regime = self._calculate_regime(current_deltas)
        
        return {
            'symbol': symbol,
            'current_regime': regime,
            'timeframes': {
                tf.value: {
                    'delta': delta['delta'],
                    'delta_pct': delta['delta_pct'],
                    'volume': delta['total_volume'],
                    'trades': delta['trade_count']
                }
                for tf, delta in current_deltas.items()
            },
            'last_update': datetime.now()
        }
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do analisador."""
        return {
            'divergences_detected': self.stats['divergences_detected'],
            'confluences_detected': self.stats['confluences_detected'],
            'regime_changes': self.stats['regime_changes'],
            'hidden_accumulation': self.stats['hidden_accumulation'],
            'hidden_distribution': self.stats['hidden_distribution'],
            'symbols_tracked': list(self.trade_storage.keys()),
            'config': {
                'timeframes': {tf.value: f"{seconds}s" for tf, seconds in self.timeframe_config.items()},
                'divergence_threshold': self.divergence_threshold,
                'confluence_threshold': self.confluence_threshold
            }
        }