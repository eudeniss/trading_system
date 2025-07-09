#core/analysis/patterns/book_dynamics_analyzer.py
"""
Analisador de dinâmica do book de ofertas - FASE 4.2.
Detecta manipulações e mudanças significativas no book.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque, defaultdict
import logging

from core.entities.book import OrderBook, BookLevel

logger = logging.getLogger(__name__)


class BookSnapshot:
    """Snapshot do book para comparação."""
    def __init__(self, book: OrderBook, timestamp: datetime):
        self.timestamp = timestamp
        self.bid_levels = {level.price: level.volume for level in book.bids}
        self.ask_levels = {level.price: level.volume for level in book.asks}
        self.best_bid = book.best_bid
        self.best_ask = book.best_ask
        self.total_bid_volume = sum(level.volume for level in book.bids)
        self.total_ask_volume = sum(level.volume for level in book.asks)


class BookDynamicsAnalyzer:
    """
    Analisa mudanças dinâmicas no book de ofertas.
    Detecta:
    - Pulling: Remoção súbita de liquidez
    - Stacking: Adição de liquidez em níveis específicos
    - Flashing: Ordens que aparecem e somem rapidamente
    - Imbalance shifts: Mudanças na proporção bid/ask
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Parâmetros configuráveis
        self.snapshot_history_size = self.config.get('snapshot_history', 20)
        self.pulling_threshold = self.config.get('pulling_threshold', 0.5)  # 50% de redução
        self.stacking_threshold = self.config.get('stacking_threshold', 2.0)  # 2x aumento
        self.flash_order_time = self.config.get('flash_order_seconds', 2)
        self.imbalance_shift_threshold = self.config.get('imbalance_shift', 0.3)  # 30% mudança
        
        # Histórico de snapshots por símbolo
        self.book_history: Dict[str, deque] = {}
        
        # Tracking de ordens flash
        self.flash_tracking: Dict[str, Dict] = {}
        
        # Estatísticas
        self.stats = {
            'pulling_detected': 0,
            'stacking_detected': 0,
            'flashing_detected': 0,
            'imbalance_shifts': 0
        }
        
        logger.info(
            f"BookDynamicsAnalyzer inicializado - "
            f"Pulling: {self.pulling_threshold}, "
            f"Stacking: {self.stacking_threshold}"
        )
    
    def analyze_book_update(self, symbol: str, current_book: OrderBook) -> List[Dict]:
        """
        Analisa atualização do book e detecta padrões dinâmicos.
        
        Returns:
            Lista de sinais detectados
        """
        if not current_book or not current_book.bids or not current_book.asks:
            return []
        
        # Inicializa histórico se necessário
        if symbol not in self.book_history:
            self.book_history[symbol] = deque(maxlen=self.snapshot_history_size)
            self.flash_tracking[symbol] = {}
        
        # Cria snapshot atual
        current_snapshot = BookSnapshot(current_book, datetime.now())
        
        # Se não há histórico, apenas salva
        if not self.book_history[symbol]:
            self.book_history[symbol].append(current_snapshot)
            return []
        
        # Analisa mudanças
        signals = []
        previous_snapshot = self.book_history[symbol][-1]
        
        # 1. Detecta Pulling (remoção de liquidez)
        pulling_signals = self._detect_pulling(symbol, previous_snapshot, current_snapshot)
        signals.extend(pulling_signals)
        
        # 2. Detecta Stacking (adição de liquidez)
        stacking_signals = self._detect_stacking(symbol, previous_snapshot, current_snapshot)
        signals.extend(stacking_signals)
        
        # 3. Detecta Flash Orders
        flash_signals = self._detect_flash_orders(symbol, current_snapshot)
        signals.extend(flash_signals)
        
        # 4. Detecta Imbalance Shifts
        imbalance_signals = self._detect_imbalance_shift(symbol, previous_snapshot, current_snapshot)
        signals.extend(imbalance_signals)
        
        # Salva snapshot
        self.book_history[symbol].append(current_snapshot)
        
        # Limpa flash tracking antigo
        self._cleanup_flash_tracking(symbol)
        
        return signals
    
    def _detect_pulling(self, symbol: str, prev: BookSnapshot, curr: BookSnapshot) -> List[Dict]:
        """Detecta remoção súbita de liquidez (pulling)."""
        signals = []
        
        # Analisa BID side
        for price, prev_volume in prev.bid_levels.items():
            curr_volume = curr.bid_levels.get(price, 0)
            
            if prev_volume > 100:  # Ignora níveis pequenos
                reduction_ratio = 1 - (curr_volume / prev_volume) if prev_volume > 0 else 1
                
                if reduction_ratio >= self.pulling_threshold:
                    self.stats['pulling_detected'] += 1
                    
                    signals.append({
                        'pattern': 'BOOK_PULLING',
                        'symbol': symbol,
                        'side': 'BID',
                        'price': price,
                        'previous_volume': prev_volume,
                        'current_volume': curr_volume,
                        'reduction_pct': reduction_ratio * 100,
                        'description': f"Liquidez removida no BID @ {price:.2f}",
                        'timestamp': curr.timestamp
                    })
        
        # Analisa ASK side
        for price, prev_volume in prev.ask_levels.items():
            curr_volume = curr.ask_levels.get(price, 0)
            
            if prev_volume > 100:
                reduction_ratio = 1 - (curr_volume / prev_volume) if prev_volume > 0 else 1
                
                if reduction_ratio >= self.pulling_threshold:
                    self.stats['pulling_detected'] += 1
                    
                    signals.append({
                        'pattern': 'BOOK_PULLING',
                        'symbol': symbol,
                        'side': 'ASK',
                        'price': price,
                        'previous_volume': prev_volume,
                        'current_volume': curr_volume,
                        'reduction_pct': reduction_ratio * 100,
                        'description': f"Liquidez removida no ASK @ {price:.2f}",
                        'timestamp': curr.timestamp
                    })
        
        return signals
    
    def _detect_stacking(self, symbol: str, prev: BookSnapshot, curr: BookSnapshot) -> List[Dict]:
        """Detecta adição súbita de liquidez (stacking)."""
        signals = []
        
        # Analisa BID side
        for price, curr_volume in curr.bid_levels.items():
            prev_volume = prev.bid_levels.get(price, 0)
            
            if curr_volume > 200 and prev_volume > 0:  # Volume significativo
                increase_ratio = curr_volume / prev_volume
                
                if increase_ratio >= self.stacking_threshold:
                    self.stats['stacking_detected'] += 1
                    
                    # Determina se é perto do topo
                    distance_from_best = (curr.best_bid - price) / curr.best_bid * 100
                    
                    signals.append({
                        'pattern': 'BOOK_STACKING',
                        'symbol': symbol,
                        'side': 'BID',
                        'price': price,
                        'previous_volume': prev_volume,
                        'current_volume': curr_volume,
                        'increase_ratio': increase_ratio,
                        'distance_from_best_pct': distance_from_best,
                        'description': f"Liquidez adicionada no BID @ {price:.2f} ({increase_ratio:.1f}x)",
                        'timestamp': curr.timestamp
                    })
        
        # Analisa ASK side
        for price, curr_volume in curr.ask_levels.items():
            prev_volume = prev.ask_levels.get(price, 0)
            
            if curr_volume > 200 and prev_volume > 0:
                increase_ratio = curr_volume / prev_volume
                
                if increase_ratio >= self.stacking_threshold:
                    self.stats['stacking_detected'] += 1
                    
                    distance_from_best = (price - curr.best_ask) / curr.best_ask * 100
                    
                    signals.append({
                        'pattern': 'BOOK_STACKING',
                        'symbol': symbol,
                        'side': 'ASK',
                        'price': price,
                        'previous_volume': prev_volume,
                        'current_volume': curr_volume,
                        'increase_ratio': increase_ratio,
                        'distance_from_best_pct': distance_from_best,
                        'description': f"Liquidez adicionada no ASK @ {price:.2f} ({increase_ratio:.1f}x)",
                        'timestamp': curr.timestamp
                    })
        
        return signals
    
    def _detect_flash_orders(self, symbol: str, curr: BookSnapshot) -> List[Dict]:
        """Detecta ordens que aparecem e desaparecem rapidamente."""
        signals = []
        flash_track = self.flash_tracking[symbol]
        
        # Verifica novas ordens grandes
        all_levels = []
        
        for price, volume in curr.bid_levels.items():
            if volume > 500:  # Ordem grande
                all_levels.append(('BID', price, volume))
        
        for price, volume in curr.ask_levels.items():
            if volume > 500:
                all_levels.append(('ASK', price, volume))
        
        # Rastreia novas ordens
        for side, price, volume in all_levels:
            key = f"{side}_{price}"
            
            if key not in flash_track:
                flash_track[key] = {
                    'first_seen': curr.timestamp,
                    'volume': volume,
                    'side': side,
                    'price': price
                }
        
        # Verifica ordens que sumiram
        current_keys = {f"{side}_{price}" for side, price, _ in all_levels}
        
        for key, order_info in list(flash_track.items()):
            if key not in current_keys:
                # Ordem sumiu, verifica tempo
                lifetime = (curr.timestamp - order_info['first_seen']).total_seconds()
                
                if lifetime <= self.flash_order_time:
                    self.stats['flashing_detected'] += 1
                    
                    signals.append({
                        'pattern': 'FLASH_ORDER',
                        'symbol': symbol,
                        'side': order_info['side'],
                        'price': order_info['price'],
                        'volume': order_info['volume'],
                        'lifetime_seconds': lifetime,
                        'description': (
                            f"Ordem flash detectada: {order_info['side']} "
                            f"{order_info['volume']} @ {order_info['price']:.2f} "
                            f"(durou {lifetime:.1f}s)"
                        ),
                        'timestamp': curr.timestamp
                    })
                
                del flash_track[key]
        
        return signals
    
    def _detect_imbalance_shift(self, symbol: str, prev: BookSnapshot, curr: BookSnapshot) -> List[Dict]:
        """Detecta mudanças significativas no balanço bid/ask."""
        signals = []
        
        # Calcula imbalances
        prev_imbalance = (prev.total_bid_volume - prev.total_ask_volume) / (
            prev.total_bid_volume + prev.total_ask_volume
        ) if (prev.total_bid_volume + prev.total_ask_volume) > 0 else 0
        
        curr_imbalance = (curr.total_bid_volume - curr.total_ask_volume) / (
            curr.total_bid_volume + curr.total_ask_volume
        ) if (curr.total_bid_volume + curr.total_ask_volume) > 0 else 0
        
        # Verifica mudança
        imbalance_change = abs(curr_imbalance - prev_imbalance)
        
        if imbalance_change >= self.imbalance_shift_threshold:
            self.stats['imbalance_shifts'] += 1
            
            # Determina direção
            if curr_imbalance > prev_imbalance:
                shift_direction = "BID_HEAVY"
                description = "Book ficou mais pesado no BID"
            else:
                shift_direction = "ASK_HEAVY"
                description = "Book ficou mais pesado no ASK"
            
            signals.append({
                'pattern': 'IMBALANCE_SHIFT',
                'symbol': symbol,
                'previous_imbalance': prev_imbalance,
                'current_imbalance': curr_imbalance,
                'change': imbalance_change,
                'direction': shift_direction,
                'bid_volume': curr.total_bid_volume,
                'ask_volume': curr.total_ask_volume,
                'description': description,
                'timestamp': curr.timestamp
            })
        
        return signals
    
    def _cleanup_flash_tracking(self, symbol: str):
        """Remove tracking de ordens antigas."""
        now = datetime.now()
        flash_track = self.flash_tracking[symbol]
        
        # Remove ordens rastreadas há mais de 1 minuto
        keys_to_remove = []
        for key, order_info in flash_track.items():
            if (now - order_info['first_seen']).total_seconds() > 60:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del flash_track[key]
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas de detecção."""
        total_detections = sum(self.stats.values())
        
        return {
            'total_detections': total_detections,
            'pulling_detected': self.stats['pulling_detected'],
            'stacking_detected': self.stats['stacking_detected'],
            'flashing_detected': self.stats['flashing_detected'],
            'imbalance_shifts': self.stats['imbalance_shifts'],
            'symbols_tracked': list(self.book_history.keys()),
            'flash_orders_tracking': sum(
                len(tracks) for tracks in self.flash_tracking.values()
            )
        }
    
    def reset_statistics(self):
        """Reseta estatísticas."""
        self.stats = {
            'pulling_detected': 0,
            'stacking_detected': 0,
            'flashing_detected': 0,
            'imbalance_shifts': 0
        }