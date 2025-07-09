#core/analysis/statistics/volume_profile.py
"""Analisador de perfil de volume por nível de preço."""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from core.entities.trade import Trade, TradeSide
import numpy as np


class VolumeProfileAnalyzer:
    """Analisa e mantém o perfil de volume por nível de preço."""
    
    __slots__ = ['price_step', 'profiles']
    
    def __init__(self, price_step: float = 0.5):
        self.price_step = price_step
        self.profiles: Dict[str, Dict[float, Dict[str, int]]] = {}
    
    def update_profile(self, trades: List[Trade]) -> None:
        """Atualiza o perfil de volume com novos trades."""
        for trade in trades:
            symbol = trade.symbol
            if symbol not in self.profiles:
                self.profiles[symbol] = defaultdict(lambda: {
                    'buy': 0, 'sell': 0, 'total': 0, 'net': 0
                })
            
            # Arredonda o preço para o nível mais próximo
            price_level = round(trade.price / self.price_step) * self.price_step
            
            profile = self.profiles[symbol][price_level]
            
            if trade.side == TradeSide.BUY:
                profile['buy'] += trade.volume
            else:
                profile['sell'] += trade.volume
            
            profile['total'] += trade.volume
            profile['net'] = profile['buy'] - profile['sell']
    
    def get_profile(self, symbol: str, num_levels: int = 20) -> Dict[float, Dict[str, int]]:
        """Retorna os níveis mais significativos do perfil de volume."""
        if symbol not in self.profiles:
            return {}
        
        # Ordena por volume total e pega os top N
        sorted_levels = sorted(
            self.profiles[symbol].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )[:num_levels]
        
        return dict(sorted_levels)
    
    def find_poc(self, symbol: str) -> Optional[float]:
        """Encontra o Point of Control (nível com maior volume)."""
        if symbol not in self.profiles or not self.profiles[symbol]:
            return None
        
        poc_level = max(
            self.profiles[symbol].items(),
            key=lambda x: x[1]['total']
        )
        
        return poc_level[0]
    
    def find_support_resistance(self, symbol: str, current_price: float, 
                               range_pct: float = 0.02) -> Dict[str, List[float]]:
        """Identifica níveis de suporte e resistência baseados no volume."""
        if symbol not in self.profiles:
            return {'support': [], 'resistance': []}
        
        supports = []
        resistances = []
        
        price_range = current_price * range_pct
        
        for price_level, profile in self.profiles[symbol].items():
            if profile['total'] < 100:  # Ignora níveis com pouco volume
                continue
            
            # Suporte: níveis abaixo com volume líquido comprador
            if price_level < current_price and profile['net'] > 50:
                if abs(current_price - price_level) <= price_range:
                    supports.append(price_level)
            
            # Resistência: níveis acima com volume líquido vendedor
            elif price_level > current_price and profile['net'] < -50:
                if abs(price_level - current_price) <= price_range:
                    resistances.append(price_level)
        
        return {
            'support': sorted(supports, reverse=True)[:3],
            'resistance': sorted(resistances)[:3]
        }
    
    def get_value_area(self, symbol: str, percentage: float = 0.7) -> Optional[Dict[str, float]]:
        """Calcula a área de valor (70% do volume negociado)."""
        if symbol not in self.profiles or not self.profiles[symbol]:
            return None
        
        # Ordena níveis por preço
        sorted_levels = sorted(self.profiles[symbol].items())
        
        if not sorted_levels:
            return None
        
        # Calcula volume total
        total_volume = sum(level[1]['total'] for level in sorted_levels)
        target_volume = total_volume * percentage
        
        # Encontra POC
        poc_idx = max(range(len(sorted_levels)), 
                     key=lambda i: sorted_levels[i][1]['total'])
        
        # Expande a partir do POC até atingir o volume alvo
        low_idx, high_idx = poc_idx, poc_idx
        accumulated_volume = sorted_levels[poc_idx][1]['total']
        
        while accumulated_volume < target_volume:
            expand_low = low_idx > 0
            expand_high = high_idx < len(sorted_levels) - 1
            
            if not expand_low and not expand_high:
                break
            
            # Expande para o lado com maior volume
            low_vol = sorted_levels[low_idx - 1][1]['total'] if expand_low else 0
            high_vol = sorted_levels[high_idx + 1][1]['total'] if expand_high else 0
            
            if low_vol >= high_vol and expand_low:
                low_idx -= 1
                accumulated_volume += low_vol
            elif expand_high:
                high_idx += 1
                accumulated_volume += high_vol
        
        return {
            'vah': sorted_levels[high_idx][0],  # Value Area High
            'val': sorted_levels[low_idx][0],   # Value Area Low
            'poc': sorted_levels[poc_idx][0],   # Point of Control
            'volume_pct': accumulated_volume / total_volume
        }