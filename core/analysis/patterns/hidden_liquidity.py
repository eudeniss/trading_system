#core/analysis/patterns/hidden_liquidity.py
"""
Detector de liquidez oculta - FASE 5.2.
Identifica níveis onde existe liquidez não visível no book.
"""
from typing import List, Optional, Dict, Tuple
from collections import defaultdict, deque
import numpy as np
from datetime import datetime, timedelta
import logging

from core.entities.trade import Trade, TradeSide
from core.entities.book import OrderBook

logger = logging.getLogger(__name__)


class HiddenLiquidityDetector:
    """
    Detecta liquidez oculta baseado em:
    - Execuções que excedem o volume visível
    - Regeneração rápida de liquidez em níveis
    - Padrões de "reload" automático
    - Dark pools e ordens reserva
    """
    
    def __init__(self, config: Dict = None):
        """
        Inicializa o detector com parâmetros configuráveis.
        
        Args:
            config: Configurações do detector
        """
        self.config = config or {}
        
        # Parâmetros
        self.min_excess_ratio = self.config.get('min_excess_ratio', 1.5)  # 150% do visível
        self.reload_time_seconds = self.config.get('reload_time', 2)
        self.level_tolerance = self.config.get('level_tolerance', 0.5)  # 1 tick
        self.min_hidden_volume = self.config.get('min_hidden_volume', 500)
        
        # Tracking de níveis
        self.level_history: Dict[str, Dict[float, deque]] = {
            'WDO': defaultdict(lambda: deque(maxlen=100)),
            'DOL': defaultdict(lambda: deque(maxlen=100))
        }
        
        # Cache de liquidez oculta detectada
        self.hidden_levels: Dict[str, Dict[float, Dict]] = {
            'WDO': {},
            'DOL': {}
        }
        
        # Estatísticas
        self.stats = {
            'excess_executions': 0,
            'reload_detected': 0,
            'hidden_levels_found': 0,
            'total_hidden_volume': 0
        }
        
        logger.info(
            f"HiddenLiquidityDetector inicializado - "
            f"Excess ratio: {self.min_excess_ratio}, "
            f"Reload time: {self.reload_time_seconds}s"
        )
    
    def detect(self, symbol: str, trades: List[Trade], book: Optional[OrderBook] = None) -> Optional[Dict]:
        """
        Detecta liquidez oculta analisando trades e book.
        
        Args:
            symbol: Símbolo do ativo
            trades: Lista de trades recentes
            book: Book atual (opcional)
            
        Returns:
            Dicionário com padrão detectado ou None
        """
        if not trades:
            return None
        
        detections = []
        
        # 1. Detecta execuções que excedem volume visível
        if book:
            excess_detection = self._detect_excess_execution(symbol, trades, book)
            if excess_detection:
                detections.append(excess_detection)
        
        # 2. Detecta reloads rápidos
        reload_detection = self._detect_reload_pattern(symbol, trades)
        if reload_detection:
            detections.append(reload_detection)
        
        # 3. Analisa níveis com liquidez persistente
        persistent_detection = self._detect_persistent_levels(symbol, trades)
        if persistent_detection:
            detections.append(persistent_detection)
        
        # Consolida detecções
        if detections:
            self.stats['hidden_levels_found'] += 1
            
            # Merge das detecções
            consolidated = self._consolidate_detections(detections)
            
            return {
                'pattern': 'HIDDEN_LIQUIDITY',
                'symbol': symbol,
                'confidence': consolidated['confidence'],
                'hidden_levels': consolidated['levels'],
                'estimated_hidden_volume': consolidated['total_hidden'],
                'detection_methods': consolidated['methods'],
                'characteristics': consolidated['characteristics']
            }
        
        return None
    
    def _detect_excess_execution(self, symbol: str, trades: List[Trade], book: OrderBook) -> Optional[Dict]:
        """Detecta quando execução excede volume visível no book."""
        if not trades:
            return None
        
        excess_levels = []
        
        # Agrupa trades por preço
        trades_by_price = defaultdict(list)
        for trade in trades[-20:]:  # Últimos 20 trades
            level = round(trade.price / self.level_tolerance) * self.level_tolerance
            trades_by_price[level].append(trade)
        
        # Verifica cada nível
        for price_level, level_trades in trades_by_price.items():
            total_executed = sum(t.volume for t in level_trades)
            
            # Busca volume visível no book
            visible_volume = 0
            
            # Verifica bids
            for bid in book.bids:
                if abs(bid.price - price_level) <= self.level_tolerance:
                    visible_volume += bid.volume
                    break
            
            # Verifica asks
            for ask in book.asks:
                if abs(ask.price - price_level) <= self.level_tolerance:
                    visible_volume += ask.volume
                    break
            
            # Detecta excesso
            if visible_volume > 0 and total_executed > visible_volume * self.min_excess_ratio:
                self.stats['excess_executions'] += 1
                
                excess_levels.append({
                    'price': price_level,
                    'executed_volume': total_executed,
                    'visible_volume': visible_volume,
                    'excess_ratio': total_executed / visible_volume,
                    'hidden_estimate': total_executed - visible_volume
                })
        
        if excess_levels:
            return {
                'method': 'EXCESS_EXECUTION',
                'levels': excess_levels,
                'confidence': min(0.9, max(e['excess_ratio'] for e in excess_levels) / 3)
            }
        
        return None
    
    def _detect_reload_pattern(self, symbol: str, trades: List[Trade]) -> Optional[Dict]:
        """Detecta padrões de reload rápido de liquidez."""
        reload_levels = []
        
        # Agrupa trades por nível e tempo
        level_time_map = defaultdict(list)
        
        for trade in trades:
            level = round(trade.price / self.level_tolerance) * self.level_tolerance
            level_time_map[level].append(trade.timestamp)
        
        # Analisa cada nível
        for price_level, timestamps in level_time_map.items():
            if len(timestamps) < 3:  # Precisa múltiplas execuções
                continue
            
            # Ordena timestamps
            timestamps.sort()
            
            # Busca reloads (múltiplas execuções com intervalos curtos)
            reload_count = 0
            for i in range(1, len(timestamps)):
                interval = (timestamps[i] - timestamps[i-1]).total_seconds()
                if interval <= self.reload_time_seconds:
                    reload_count += 1
            
            if reload_count >= 2:  # Pelo menos 2 reloads
                self.stats['reload_detected'] += 1
                
                # Estima volume oculto baseado na frequência
                estimated_hidden = self.min_hidden_volume * (1 + reload_count * 0.5)
                
                reload_levels.append({
                    'price': price_level,
                    'reload_count': reload_count,
                    'execution_count': len(timestamps),
                    'hidden_estimate': estimated_hidden
                })
                
                # Atualiza cache de níveis ocultos
                self.hidden_levels[symbol][price_level] = {
                    'last_seen': timestamps[-1],
                    'reload_count': reload_count,
                    'confidence': min(0.9, reload_count * 0.3)
                }
        
        if reload_levels:
            return {
                'method': 'RELOAD_PATTERN',
                'levels': reload_levels,
                'confidence': min(0.8, max(l['reload_count'] for l in reload_levels) * 0.2)
            }
        
        return None
    
    def _detect_persistent_levels(self, symbol: str, trades: List[Trade]) -> Optional[Dict]:
        """Detecta níveis com liquidez persistente ao longo do tempo."""
        persistent_levels = []
        
        # Atualiza histórico
        for trade in trades:
            level = round(trade.price / self.level_tolerance) * self.level_tolerance
            self.level_history[symbol][level].append({
                'timestamp': trade.timestamp,
                'volume': trade.volume,
                'side': trade.side
            })
        
        # Analisa persistência
        now = datetime.now()
        
        for price_level, history in self.level_history[symbol].items():
            if len(history) < 5:
                continue
            
            # Calcula métricas de persistência
            time_span = (history[-1]['timestamp'] - history[0]['timestamp']).total_seconds()
            
            if time_span < 60:  # Menos de 1 minuto
                continue
            
            # Volume total no nível
            total_volume = sum(h['volume'] for h in history)
            
            # Frequência de trades
            trade_frequency = len(history) / (time_span / 60)  # Trades por minuto
            
            # Detecta se é persistente
            if total_volume >= self.min_hidden_volume and trade_frequency > 0.5:
                self.stats['total_hidden_volume'] += total_volume
                
                persistent_levels.append({
                    'price': price_level,
                    'total_volume': total_volume,
                    'trade_count': len(history),
                    'time_span_minutes': time_span / 60,
                    'frequency': trade_frequency,
                    'hidden_estimate': total_volume * 0.7  # Estima 70% como oculto
                })
        
        if persistent_levels:
            return {
                'method': 'PERSISTENT_LEVELS',
                'levels': sorted(persistent_levels, key=lambda x: x['total_volume'], reverse=True)[:5],
                'confidence': 0.7
            }
        
        return None
    
    def _consolidate_detections(self, detections: List[Dict]) -> Dict:
        """Consolida múltiplas detecções em um resultado final."""
        all_levels = defaultdict(lambda: {
            'methods': [],
            'hidden_estimates': [],
            'confidence_scores': []
        })
        
        methods_used = []
        
        # Agrupa por nível de preço
        for detection in detections:
            methods_used.append(detection['method'])
            
            for level_info in detection['levels']:
                price = level_info['price']
                all_levels[price]['methods'].append(detection['method'])
                all_levels[price]['hidden_estimates'].append(level_info.get('hidden_estimate', 0))
                all_levels[price]['confidence_scores'].append(detection['confidence'])
        
        # Consolida níveis
        consolidated_levels = []
        total_hidden = 0
        
        for price, info in all_levels.items():
            # Média ponderada das estimativas
            avg_hidden = np.mean(info['hidden_estimates'])
            max_confidence = max(info['confidence_scores'])
            
            consolidated_levels.append({
                'price': price,
                'estimated_hidden_volume': avg_hidden,
                'detection_methods': info['methods'],
                'confidence': max_confidence
            })
            
            total_hidden += avg_hidden
        
        # Características gerais
        characteristics = []
        if 'EXCESS_EXECUTION' in methods_used:
            characteristics.append('Execuções excedem volume visível')
        if 'RELOAD_PATTERN' in methods_used:
            characteristics.append('Reposição automática de liquidez')
        if 'PERSISTENT_LEVELS' in methods_used:
            characteristics.append('Níveis com liquidez persistente')
        
        return {
            'levels': sorted(consolidated_levels, key=lambda x: x['estimated_hidden_volume'], reverse=True),
            'total_hidden': total_hidden,
            'methods': list(set(methods_used)),
            'characteristics': characteristics,
            'confidence': max(d['confidence'] for d in detections)
        }
    
    def get_hidden_levels(self, symbol: str, current_price: float, range_pct: float = 0.02) -> List[Dict]:
        """
        Retorna níveis com liquidez oculta próximos ao preço atual.
        
        Args:
            symbol: Símbolo do ativo
            current_price: Preço atual
            range_pct: Percentual de range (default 2%)
            
        Returns:
            Lista de níveis ocultos ordenados por proximidade
        """
        price_range = current_price * range_pct
        relevant_levels = []
        
        for price_level, info in self.hidden_levels[symbol].items():
            if abs(price_level - current_price) <= price_range:
                distance = abs(price_level - current_price)
                relevant_levels.append({
                    'price': price_level,
                    'distance': distance,
                    'distance_pct': (distance / current_price) * 100,
                    'confidence': info['confidence'],
                    'last_seen': info['last_seen'],
                    'side': 'BID' if price_level < current_price else 'ASK'
                })
        
        # Ordena por distância
        return sorted(relevant_levels, key=lambda x: x['distance'])
    
    def cleanup_old_levels(self, symbol: str, max_age_minutes: int = 30):
        """Remove níveis ocultos antigos."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=max_age_minutes)
        
        levels_to_remove = []
        
        for price_level, info in self.hidden_levels[symbol].items():
            if info['last_seen'] < cutoff:
                levels_to_remove.append(price_level)
        
        for level in levels_to_remove:
            del self.hidden_levels[symbol][level]
        
        if levels_to_remove:
            logger.info(f"Removidos {len(levels_to_remove)} níveis ocultos antigos de {symbol}")
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do detector."""
        total_levels = sum(len(levels) for levels in self.hidden_levels.values())
        
        return {
            'excess_executions': self.stats['excess_executions'],
            'reload_patterns': self.stats['reload_detected'],
            'hidden_levels_found': self.stats['hidden_levels_found'],
            'total_hidden_volume_estimate': self.stats['total_hidden_volume'],
            'active_hidden_levels': total_levels,
            'config': {
                'min_excess_ratio': self.min_excess_ratio,
                'reload_time_seconds': self.reload_time_seconds,
                'min_hidden_volume': self.min_hidden_volume
            }
        }