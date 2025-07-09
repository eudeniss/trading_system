#core/analysis/patterns/trap_detector.py
"""
Detector de armadilhas (traps) - FASE 5.4.
Identifica padrões de manipulação para prender traders.
"""
from typing import List, Optional, Dict, Tuple
from collections import deque, defaultdict
import numpy as np
from datetime import datetime, timedelta
import logging

from core.entities.trade import Trade, TradeSide
from core.entities.book import OrderBook

logger = logging.getLogger(__name__)


class TrapType:
    """Tipos de armadilhas detectáveis."""
    BULL_TRAP = "BULL_TRAP"           # Falso rompimento de alta
    BEAR_TRAP = "BEAR_TRAP"           # Falso rompimento de baixa
    LIQUIDITY_TRAP = "LIQUIDITY_TRAP" # Liquidez falsa para atrair
    STOP_HUNT = "STOP_HUNT"           # Caça aos stops
    SQUEEZE_TRAP = "SQUEEZE_TRAP"     # Squeeze forçado


class TrapDetector:
    """
    Detecta armadilhas de mercado baseado em:
    - Movimentos falsos (fake breakouts)
    - Caça aos stops
    - Liquidez enganosa
    - Squeezes artificiais
    """
    
    def __init__(self, config: Dict = None):
        """
        Inicializa o detector com configurações.
        
        Args:
            config: Configurações do detector
        """
        self.config = config or {}
        
        # Parâmetros
        self.breakout_threshold = self.config.get('breakout_threshold', 0.002)  # 0.2%
        self.reversal_threshold = self.config.get('reversal_threshold', 0.7)    # 70% retracement
        self.volume_spike_multiplier = self.config.get('volume_spike', 3.0)
        self.stop_hunt_range = self.config.get('stop_hunt_range', 0.003)       # 0.3%
        self.trap_time_window = self.config.get('trap_window_seconds', 300)    # 5 minutos
        
        # Storage de dados
        self.price_levels: Dict[str, deque] = {}
        self.breakout_tracking: Dict[str, List[Dict]] = {}
        self.stop_levels: Dict[str, Dict[float, int]] = {}
        
        # Estatísticas
        self.stats = defaultdict(int)
        
        logger.info(
            f"TrapDetector inicializado - "
            f"Breakout: {self.breakout_threshold}, "
            f"Reversal: {self.reversal_threshold}"
        )
    
    def detect(self, symbol: str, trades: List[Trade], book: Optional[OrderBook] = None) -> List[Dict]:
        """
        Detecta armadilhas nos dados de mercado.
        
        Args:
            symbol: Símbolo do ativo
            trades: Lista de trades recentes
            book: Book atual (opcional)
            
        Returns:
            Lista de armadilhas detectadas
        """
        if not trades or len(trades) < 20:
            return []
        
        # Inicializa storage se necessário
        if symbol not in self.price_levels:
            self._initialize_symbol_storage(symbol)
        
        # Atualiza dados
        self._update_price_levels(symbol, trades)
        self._identify_stop_levels(symbol, trades)
        
        detections = []
        
        # 1. Detecta Bull/Bear Traps
        breakout_traps = self._detect_breakout_traps(symbol, trades)
        detections.extend(breakout_traps)
        
        # 2. Detecta Stop Hunts
        stop_hunts = self._detect_stop_hunts(symbol, trades)
        detections.extend(stop_hunts)
        
        # 3. Detecta Liquidity Traps
        if book:
            liquidity_traps = self._detect_liquidity_traps(symbol, trades, book)
            detections.extend(liquidity_traps)
        
        # 4. Detecta Squeeze Traps
        squeeze_traps = self._detect_squeeze_traps(symbol, trades)
        detections.extend(squeeze_traps)
        
        return detections
    
    def _initialize_symbol_storage(self, symbol: str):
        """Inicializa storage para um símbolo."""
        self.price_levels[symbol] = deque(maxlen=500)
        self.breakout_tracking[symbol] = []
        self.stop_levels[symbol] = defaultdict(int)
    
    def _update_price_levels(self, symbol: str, trades: List[Trade]):
        """Atualiza níveis de preço importantes."""
        for trade in trades:
            self.price_levels[symbol].append({
                'price': trade.price,
                'volume': trade.volume,
                'timestamp': trade.timestamp,
                'side': trade.side
            })
    
    def _identify_stop_levels(self, symbol: str, trades: List[Trade]):
        """Identifica níveis prováveis de stops."""
        if len(trades) < 50:
            return
        
        prices = [t.price for t in trades[-50:]]
        
        # Encontra máximos e mínimos locais
        for i in range(2, len(prices) - 2):
            # Máximo local (possível stop de venda)
            if prices[i] > prices[i-1] and prices[i] > prices[i-2] and \
               prices[i] > prices[i+1] and prices[i] > prices[i+2]:
                stop_level = round(prices[i] * 1.001 / 0.5) * 0.5  # Arredonda para cima
                self.stop_levels[symbol][stop_level] += 1
            
            # Mínimo local (possível stop de compra)
            if prices[i] < prices[i-1] and prices[i] < prices[i-2] and \
               prices[i] < prices[i+1] and prices[i] < prices[i+2]:
                stop_level = round(prices[i] * 0.999 / 0.5) * 0.5  # Arredonda para baixo
                self.stop_levels[symbol][stop_level] += 1
    
    def _detect_breakout_traps(self, symbol: str, trades: List[Trade]) -> List[Dict]:
        """Detecta bull/bear traps (falsos rompimentos)."""
        traps = []
        
        if len(self.price_levels[symbol]) < 100:
            return traps
        
        # Calcula range recente
        recent_prices = [p['price'] for p in list(self.price_levels[symbol])[-100:]]
        price_high = max(recent_prices[-50:-10])  # Máxima dos últimos 50-10 trades
        price_low = min(recent_prices[-50:-10])   # Mínima dos últimos 50-10 trades
        current_price = trades[-1].price
        
        # Verifica breakouts recentes
        for i in range(len(trades) - 20, len(trades) - 5):
            if i < 0:
                continue
            
            trade = trades[i]
            
            # Bull trap: Rompe máxima e retorna
            if trade.price > price_high * (1 + self.breakout_threshold):
                # Verifica se voltou
                subsequent_prices = [t.price for t in trades[i:i+10] if i+10 <= len(trades)]
                if subsequent_prices:
                    min_after = min(subsequent_prices)
                    retracement = (trade.price - min_after) / (trade.price - price_high)
                    
                    if retracement > self.reversal_threshold:
                        self.stats['bull_traps'] += 1
                        
                        # Calcula volume do movimento
                        trap_volume = sum(t.volume for t in trades[i:i+10] if t.timestamp > trade.timestamp)
                        
                        traps.append({
                            'pattern': 'TRAP_DETECTED',
                            'trap_type': TrapType.BULL_TRAP,
                            'symbol': symbol,
                            'breakout_price': trade.price,
                            'resistance': price_high,
                            'current_price': current_price,
                            'retracement_pct': retracement * 100,
                            'trap_volume': trap_volume,
                            'description': f"Bull trap: Falso rompimento em {trade.price:.2f}, retorno para {min_after:.2f}",
                            'confidence': min(0.9, retracement)
                        })
            
            # Bear trap: Rompe mínima e retorna
            elif trade.price < price_low * (1 - self.breakout_threshold):
                subsequent_prices = [t.price for t in trades[i:i+10] if i+10 <= len(trades)]
                if subsequent_prices:
                    max_after = max(subsequent_prices)
                    retracement = (max_after - trade.price) / (price_low - trade.price)
                    
                    if retracement > self.reversal_threshold:
                        self.stats['bear_traps'] += 1
                        
                        trap_volume = sum(t.volume for t in trades[i:i+10] if t.timestamp > trade.timestamp)
                        
                        traps.append({
                            'pattern': 'TRAP_DETECTED',
                            'trap_type': TrapType.BEAR_TRAP,
                            'symbol': symbol,
                            'breakout_price': trade.price,
                            'support': price_low,
                            'current_price': current_price,
                            'retracement_pct': retracement * 100,
                            'trap_volume': trap_volume,
                            'description': f"Bear trap: Falso rompimento em {trade.price:.2f}, retorno para {max_after:.2f}",
                            'confidence': min(0.9, retracement)
                        })
        
        return traps
    
    def _detect_stop_hunts(self, symbol: str, trades: List[Trade]) -> List[Dict]:
        """Detecta movimentos de caça aos stops."""
        hunts = []
        
        # Identifica movimentos rápidos que tocam níveis de stop
        for stop_level, frequency in self.stop_levels[symbol].items():
            if frequency < 2:  # Precisa ser um nível relevante
                continue
            
            # Busca trades que atravessaram o nível
            hunt_trades = []
            for i, trade in enumerate(trades[-30:]):
                # Detecta se o preço passou pelo stop e voltou rapidamente
                if abs(trade.price - stop_level) <= self.stop_hunt_range * stop_level:
                    hunt_trades.append((i, trade))
            
            if len(hunt_trades) >= 2:
                # Verifica se foi um movimento rápido (spike)
                first_idx, first_trade = hunt_trades[0]
                last_idx, last_trade = hunt_trades[-1]
                
                if last_idx - first_idx <= 10:  # Movimento em 10 trades ou menos
                    # Calcula se o preço voltou
                    current_price = trades[-1].price
                    price_returned = abs(current_price - stop_level) > self.stop_hunt_range * stop_level
                    
                    if price_returned:
                        self.stats['stop_hunts'] += 1
                        
                        hunt_volume = sum(t.volume for idx, t in hunt_trades)
                        
                        hunts.append({
                            'pattern': 'TRAP_DETECTED',
                            'trap_type': TrapType.STOP_HUNT,
                            'symbol': symbol,
                            'stop_level': stop_level,
                            'hunt_volume': hunt_volume,
                            'trades_involved': len(hunt_trades),
                            'current_price': current_price,
                            'description': f"Stop hunt detectado em {stop_level:.2f} - {len(hunt_trades)} trades",
                            'confidence': min(0.8, frequency * 0.2)
                        })
        
        return hunts
    
    def _detect_liquidity_traps(self, symbol: str, trades: List[Trade], book: OrderBook) -> List[Dict]:
        """Detecta armadilhas de liquidez."""
        traps = []
        
        # Analisa desbalanceamento súbito do book
        total_bid_volume = sum(level.volume for level in book.bids[:5])
        total_ask_volume = sum(level.volume for level in book.asks[:5])
        
        if total_bid_volume == 0 or total_ask_volume == 0:
            return traps
        
        imbalance_ratio = max(total_bid_volume / total_ask_volume, 
                              total_ask_volume / total_bid_volume)
        
        # Se há grande desbalanceamento
        if imbalance_ratio > 3.0:
            # Verifica se houve movimento contrário ao desbalanceamento
            recent_trades = trades[-20:]
            buy_volume = sum(t.volume for t in recent_trades if t.side == TradeSide.BUY)
            sell_volume = sum(t.volume for t in recent_trades if t.side == TradeSide.SELL)
            
            # Liquidez trap: Book pesado de um lado mas fluxo vai pro outro
            if total_bid_volume > total_ask_volume * 2 and sell_volume > buy_volume * 1.5:
                self.stats['liquidity_traps'] += 1
                
                traps.append({
                    'pattern': 'TRAP_DETECTED',
                    'trap_type': TrapType.LIQUIDITY_TRAP,
                    'symbol': symbol,
                    'book_imbalance': 'BID_HEAVY',
                    'actual_flow': 'SELLING',
                    'bid_volume': total_bid_volume,
                    'ask_volume': total_ask_volume,
                    'flow_buy': buy_volume,
                    'flow_sell': sell_volume,
                    'description': "Liquidez trap: Book pesado no BID mas fluxo é vendedor",
                    'confidence': 0.75
                })
            
            elif total_ask_volume > total_bid_volume * 2 and buy_volume > sell_volume * 1.5:
                self.stats['liquidity_traps'] += 1
                
                traps.append({
                    'pattern': 'TRAP_DETECTED',
                    'trap_type': TrapType.LIQUIDITY_TRAP,
                    'symbol': symbol,
                    'book_imbalance': 'ASK_HEAVY',
                    'actual_flow': 'BUYING',
                    'bid_volume': total_bid_volume,
                    'ask_volume': total_ask_volume,
                    'flow_buy': buy_volume,
                    'flow_sell': sell_volume,
                    'description': "Liquidez trap: Book pesado no ASK mas fluxo é comprador",
                    'confidence': 0.75
                })
        
        return traps
    
    def _detect_squeeze_traps(self, symbol: str, trades: List[Trade]) -> List[Dict]:
        """Detecta squeeze traps (compressão artificial de preço)."""
        traps = []
        
        if len(trades) < 50:
            return traps
        
        # Analisa compressão de range
        prices_early = [t.price for t in trades[-50:-30]]
        prices_late = [t.price for t in trades[-20:]]
        
        range_early = max(prices_early) - min(prices_early)
        range_late = max(prices_late) - min(prices_late)
        
        # Detecta compressão
        if range_late < range_early * 0.3:  # Range diminuiu 70%+
            # Analisa volume durante a compressão
            volume_early = sum(t.volume for t in trades[-50:-30])
            volume_late = sum(t.volume for t in trades[-20:])
            
            # Squeeze trap: Compressão com volume anormal
            if volume_late > volume_early * self.volume_spike_multiplier:
                self.stats['squeeze_traps'] += 1
                
                # Determina direção provável do squeeze
                last_trades = trades[-5:]
                buy_pressure = sum(1 for t in last_trades if t.side == TradeSide.BUY)
                
                direction = "UP" if buy_pressure >= 3 else "DOWN"
                
                traps.append({
                    'pattern': 'TRAP_DETECTED',
                    'trap_type': TrapType.SQUEEZE_TRAP,
                    'symbol': symbol,
                    'range_compression': (1 - range_late / range_early) * 100,
                    'volume_increase': volume_late / volume_early,
                    'probable_direction': direction,
                    'current_range': range_late,
                    'description': f"Squeeze trap: Range comprimido {(1 - range_late/range_early)*100:.0f}% com volume {volume_late/volume_early:.1f}x",
                    'confidence': min(0.85, volume_late / volume_early / 3)
                })
        
        return traps
    
    def get_trap_risk_assessment(self, symbol: str) -> Dict:
        """Avalia risco atual de armadilhas."""
        if symbol not in self.price_levels:
            return {'risk_level': 'UNKNOWN', 'active_risks': []}
        
        active_risks = []
        risk_score = 0
        
        # Verifica condições de risco
        recent_prices = [p['price'] for p in list(self.price_levels[symbol])[-50:]]
        if recent_prices:
            current_price = recent_prices[-1]
            price_std = np.std(recent_prices)
            
            # Risco de breakout trap
            price_high = max(recent_prices[:-5])
            price_low = min(recent_prices[:-5])
            
            if current_price > price_high - price_std * 0.5:
                active_risks.append("Near resistance - Bull trap risk")
                risk_score += 1
            
            if current_price < price_low + price_std * 0.5:
                active_risks.append("Near support - Bear trap risk")
                risk_score += 1
            
            # Risco de stop hunt
            for stop_level, frequency in self.stop_levels[symbol].items():
                if frequency >= 3 and abs(current_price - stop_level) < price_std:
                    active_risks.append(f"Near stop cluster at {stop_level:.2f}")
                    risk_score += 1
                    break
        
        # Determina nível de risco
        if risk_score >= 3:
            risk_level = "HIGH"
        elif risk_score >= 2:
            risk_level = "MEDIUM"
        elif risk_score >= 1:
            risk_level = "LOW"
        else:
            risk_level = "MINIMAL"
        
        return {
            'risk_level': risk_level,
            'active_risks': active_risks,
            'risk_score': risk_score,
            'recommendation': self._get_risk_recommendation(risk_level)
        }
    
    def _get_risk_recommendation(self, risk_level: str) -> str:
        """Retorna recomendação baseada no nível de risco."""
        recommendations = {
            'HIGH': "⚠️ Alto risco de armadilhas - Evite novos trades ou use stops muito apertados",
            'MEDIUM': "⚡ Risco moderado - Opere com cautela e confirme sinais",
            'LOW': "📊 Risco baixo - Condições normais, mas mantenha vigilância",
            'MINIMAL': "✅ Risco mínimo - Condições favoráveis para operar"
        }
        return recommendations.get(risk_level, "Avalie as condições")
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do detector."""
        total_traps = sum(self.stats.values())
        
        return {
            'total_traps_detected': total_traps,
            'trap_breakdown': dict(self.stats),
            'symbols_monitored': list(self.price_levels.keys()),
            'stop_levels_identified': sum(len(levels) for levels in self.stop_levels.values()),
            'config': {
                'breakout_threshold': self.breakout_threshold,
                'reversal_threshold': self.reversal_threshold,
                'trap_window_seconds': self.trap_time_window
            }
        }