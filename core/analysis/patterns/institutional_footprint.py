#core/analysis/patterns/institutional_footprint.py
"""
Detector de pegada institucional - FASE 5.1.
Identifica padrões característicos de operadores institucionais.
"""
from typing import List, Optional, Dict
from collections import Counter, defaultdict
import numpy as np
from datetime import datetime, timedelta
import logging

from core.entities.trade import Trade, TradeSide

logger = logging.getLogger(__name__)


class InstitutionalFootprintDetector:
    """
    Detecta presença institucional baseado em padrões de execução.
    
    Características institucionais:
    - Ordens fracionadas em tamanhos específicos (iceberg)
    - Execuções rítmicas e consistentes
    - Volumes grandes mas disfarçados
    - Padrões de acumulação/distribuição
    - Timing específico (VWAP, TWAP)
    """
    
    def __init__(self, config: Dict = None):
        """
        Inicializa o detector com parâmetros configuráveis.
        
        Args:
            config: Configurações do detector
        """
        self.config = config or {}
        
        # Parâmetros de detecção
        self.min_trades = self.config.get('min_trades', 50)
        self.iceberg_size_tolerance = self.config.get('iceberg_tolerance', 0.1)  # 10%
        self.rhythm_threshold = self.config.get('rhythm_threshold', 0.7)
        self.institutional_volume_pct = self.config.get('institutional_volume_pct', 0.3)
        self.time_window_seconds = self.config.get('time_window', 300)  # 5 minutos
        
        # Tamanhos típicos de iceberg
        self.common_iceberg_sizes = self.config.get('iceberg_sizes', [
            10, 20, 25, 50, 100, 200, 250, 500, 1000
        ])
        
        # Estatísticas
        self.detection_count = 0
        self.pattern_stats = defaultdict(int)
        
        logger.info(
            f"InstitutionalFootprintDetector inicializado - "
            f"Min trades: {self.min_trades}, "
            f"Iceberg sizes: {self.common_iceberg_sizes[:5]}..."
        )
    
    def detect(self, trades: List[Trade]) -> Optional[Dict]:
        """
        Detecta pegada institucional nos trades.
        
        Args:
            trades: Lista de trades recentes
            
        Returns:
            Dicionário com padrão detectado ou None
        """
        if len(trades) < self.min_trades:
            return None
        
        # Análises
        size_analysis = self._analyze_trade_sizes(trades)
        timing_analysis = self._analyze_timing_patterns(trades)
        volume_analysis = self._analyze_volume_distribution(trades)
        execution_analysis = self._analyze_execution_pattern(trades)
        
        # Score final
        institutional_score = self._calculate_institutional_score(
            size_analysis, timing_analysis, volume_analysis, execution_analysis
        )
        
        if institutional_score >= 0.6:  # 60% de confiança
            self.detection_count += 1
            
            # Determina tipo de operação institucional
            operation_type = self._determine_operation_type(trades, execution_analysis)
            
            return {
                'pattern': 'INSTITUTIONAL_FOOTPRINT',
                'confidence': institutional_score,
                'operation_type': operation_type,
                'characteristics': {
                    'size_pattern': size_analysis['pattern'],
                    'timing_pattern': timing_analysis['pattern'],
                    'volume_concentration': volume_analysis['institutional_pct'],
                    'execution_style': execution_analysis['style']
                },
                'details': {
                    'trade_count': len(trades),
                    'total_volume': sum(t.volume for t in trades),
                    'dominant_sizes': size_analysis['dominant_sizes'],
                    'rhythm_score': timing_analysis['rhythm_score'],
                    'avg_interval': timing_analysis['avg_interval']
                }
            }
        
        return None
    
    def _analyze_trade_sizes(self, trades: List[Trade]) -> Dict:
        """Analisa distribuição de tamanhos de trades."""
        sizes = [t.volume for t in trades]
        size_counter = Counter(sizes)
        
        # Detecta tamanhos repetitivos (iceberg)
        dominant_sizes = []
        iceberg_trades = 0
        
        for size, count in size_counter.most_common(10):
            # Verifica se é um tamanho comum de iceberg
            is_iceberg = any(
                abs(size - iceberg_size) / iceberg_size <= self.iceberg_size_tolerance
                for iceberg_size in self.common_iceberg_sizes
            )
            
            if is_iceberg and count >= 3:  # Pelo menos 3 repetições
                dominant_sizes.append((size, count))
                iceberg_trades += count
        
        # Determina padrão
        if iceberg_trades / len(trades) > 0.3:
            pattern = 'ICEBERG_HEAVY'
        elif len(set(sizes)) / len(sizes) < 0.3:  # Pouca variação
            pattern = 'REPETITIVE'
        else:
            pattern = 'MIXED'
        
        self.pattern_stats[f'size_pattern_{pattern}'] += 1
        
        return {
            'pattern': pattern,
            'dominant_sizes': dominant_sizes[:3],
            'iceberg_ratio': iceberg_trades / len(trades),
            'size_diversity': len(set(sizes)) / len(sizes)
        }
    
    def _analyze_timing_patterns(self, trades: List[Trade]) -> Dict:
        """Analisa padrões temporais de execução."""
        if len(trades) < 2:
            return {'pattern': 'INSUFFICIENT', 'rhythm_score': 0, 'avg_interval': 0}
        
        # Calcula intervalos entre trades
        intervals = []
        for i in range(1, len(trades)):
            interval = (trades[i].timestamp - trades[i-1].timestamp).total_seconds()
            if interval < 60:  # Ignora intervalos muito longos
                intervals.append(interval)
        
        if not intervals:
            return {'pattern': 'SPARSE', 'rhythm_score': 0, 'avg_interval': 0}
        
        # Analisa regularidade (ritmo)
        avg_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        cv = std_interval / avg_interval if avg_interval > 0 else float('inf')
        
        # Score de ritmo (menor CV = mais rítmico)
        rhythm_score = max(0, 1 - cv) if cv < 2 else 0
        
        # Determina padrão
        if rhythm_score > self.rhythm_threshold:
            if avg_interval < 2:
                pattern = 'HIGH_FREQUENCY_ALGO'
            elif avg_interval < 10:
                pattern = 'REGULAR_EXECUTION'
            else:
                pattern = 'PATIENT_ACCUMULATION'
        else:
            pattern = 'IRREGULAR'
        
        self.pattern_stats[f'timing_pattern_{pattern}'] += 1
        
        return {
            'pattern': pattern,
            'rhythm_score': rhythm_score,
            'avg_interval': avg_interval,
            'interval_cv': cv
        }
    
    def _analyze_volume_distribution(self, trades: List[Trade]) -> Dict:
        """Analisa distribuição de volume entre trades."""
        volumes = [t.volume for t in trades]
        total_volume = sum(volumes)
        
        if total_volume == 0:
            return {'pattern': 'NO_VOLUME', 'institutional_pct': 0}
        
        # Ordena volumes
        sorted_volumes = sorted(volumes, reverse=True)
        
        # Calcula concentração (quantos trades representam X% do volume)
        cumsum = 0
        trades_for_50pct = 0
        for i, vol in enumerate(sorted_volumes):
            cumsum += vol
            if cumsum >= total_volume * 0.5:
                trades_for_50pct = i + 1
                break
        
        concentration_ratio = trades_for_50pct / len(trades)
        
        # Estima volume institucional (trades grandes mas não extremos)
        institutional_volume = 0
        retail_volume = 0
        
        for vol in volumes:
            if 50 <= vol <= 1000:  # Range institucional típico
                institutional_volume += vol
            elif vol < 50:  # Provavelmente retail
                retail_volume += vol
        
        institutional_pct = institutional_volume / total_volume
        
        return {
            'pattern': 'CONCENTRATED' if concentration_ratio < 0.2 else 'DISTRIBUTED',
            'institutional_pct': institutional_pct,
            'retail_pct': retail_volume / total_volume,
            'concentration_ratio': concentration_ratio
        }
    
    def _analyze_execution_pattern(self, trades: List[Trade]) -> Dict:
        """Analisa padrão de execução (agressão, direção, etc)."""
        buy_trades = [t for t in trades if t.side == TradeSide.BUY]
        sell_trades = [t for t in trades if t.side == TradeSide.SELL]
        
        buy_volume = sum(t.volume for t in buy_trades)
        sell_volume = sum(t.volume for t in sell_trades)
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return {'style': 'UNKNOWN', 'aggression': 0, 'direction_bias': 0}
        
        # Calcula viés direcional
        direction_bias = (buy_volume - sell_volume) / total_volume
        
        # Analisa agressividade (trades grandes em sequência)
        aggression_score = 0
        for i in range(1, min(len(trades), 10)):
            if trades[i].volume > 100 and trades[i].side == trades[i-1].side:
                aggression_score += 1
        
        aggression_score = aggression_score / 9 if len(trades) >= 10 else 0
        
        # Determina estilo
        if abs(direction_bias) > 0.7:
            if direction_bias > 0:
                style = 'AGGRESSIVE_BUYING'
            else:
                style = 'AGGRESSIVE_SELLING'
        elif abs(direction_bias) < 0.2:
            style = 'BALANCED_EXECUTION'
        else:
            style = 'DIRECTIONAL_BIAS'
        
        self.pattern_stats[f'execution_style_{style}'] += 1
        
        return {
            'style': style,
            'aggression': aggression_score,
            'direction_bias': direction_bias,
            'buy_ratio': len(buy_trades) / len(trades)
        }
    
    def _calculate_institutional_score(self, size_analysis: Dict, timing_analysis: Dict,
                                     volume_analysis: Dict, execution_analysis: Dict) -> float:
        """Calcula score final de presença institucional."""
        score = 0.0
        weights = 0.0
        
        # Size patterns (peso 2.0)
        if size_analysis['pattern'] in ['ICEBERG_HEAVY', 'REPETITIVE']:
            score += 2.0 * size_analysis['iceberg_ratio']
            weights += 2.0
        else:
            weights += 2.0
        
        # Timing patterns (peso 1.5)
        if timing_analysis['pattern'] in ['REGULAR_EXECUTION', 'PATIENT_ACCUMULATION']:
            score += 1.5 * timing_analysis['rhythm_score']
            weights += 1.5
        elif timing_analysis['pattern'] == 'HIGH_FREQUENCY_ALGO':
            score += 1.5 * 0.8  # Também é institucional
            weights += 1.5
        else:
            weights += 1.5
        
        # Volume distribution (peso 1.0)
        score += 1.0 * volume_analysis['institutional_pct']
        weights += 1.0
        
        # Execution style (peso 0.5)
        if execution_analysis['style'] in ['BALANCED_EXECUTION', 'DIRECTIONAL_BIAS']:
            score += 0.5 * 0.7
            weights += 0.5
        else:
            weights += 0.5
        
        return score / weights if weights > 0 else 0
    
    def _determine_operation_type(self, trades: List[Trade], execution_analysis: Dict) -> str:
        """Determina o tipo de operação institucional."""
        direction_bias = execution_analysis['direction_bias']
        
        # Analisa tendência de preço
        if len(trades) >= 10:
            early_price = np.mean([t.price for t in trades[:5]])
            late_price = np.mean([t.price for t in trades[-5:]])
            price_trend = (late_price - early_price) / early_price
        else:
            price_trend = 0
        
        # Determina tipo baseado em direção e tendência
        if direction_bias > 0.3:
            if price_trend > 0.001:
                return "ACCUMULATION_AGGRESSIVE"
            else:
                return "ACCUMULATION_PATIENT"
        elif direction_bias < -0.3:
            if price_trend < -0.001:
                return "DISTRIBUTION_AGGRESSIVE"
            else:
                return "DISTRIBUTION_PATIENT"
        else:
            if abs(price_trend) < 0.0005:
                return "POSITION_MAINTENANCE"
            else:
                return "MARKET_MAKING"
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do detector."""
        return {
            'total_detections': self.detection_count,
            'pattern_distribution': dict(self.pattern_stats),
            'config': {
                'min_trades': self.min_trades,
                'rhythm_threshold': self.rhythm_threshold,
                'iceberg_sizes': len(self.common_iceberg_sizes)
            }
        }