#core/analysis/filters/defensive.py
"""Filtro defensivo para detecção de manipulação."""
from typing import Dict, Tuple, Optional, List
from core.entities.signal import Signal
from core.entities.book import OrderBook
from core.entities.trade import Trade
import logging

logger = logging.getLogger(__name__)


class DefensiveSignalFilter:
    """Filtra sinais baseado nas configurações de manipulation_detection."""
    
    __slots__ = ['config', 'manipulation_patterns']
    
    def __init__(self, config: Dict = None):  # <<< TORNAR OPCIONAL
        self.config = config or {}  # <<< SE NÃO VIER CONFIG, USA DICT VAZIO
        self.manipulation_patterns = {}

        # Usar get() com defaults para evitar KeyError
        if self.config.get('layering', {}).get('enabled', True):
            self.manipulation_patterns['LAYERING'] = self._check_layering
            
        if self.config.get('spoofing', {}).get('enabled', True):
            self.manipulation_patterns['SPOOFING'] = self._check_spoofing
    
    def is_signal_safe(self, signal: Signal, book: Optional[OrderBook] = None, 
                      recent_trades: Optional[List[Trade]] = None) -> Tuple[bool, Dict]:
        """Verifica se um sinal é seguro baseado no que vemos no BOOK."""
        risk_info = {
            'safe': True,
            'risks': [],
            'confidence': 1.0,
            'action_required': None,
            'details': []
        }
        
        # Só verifica se temos book
        if book and self.config.get('actions', {}).get('block_signals', True):
            # LAYERING - se habilitado
            if 'LAYERING' in self.manipulation_patterns:
                layering_result = self._check_layering(book)
                if layering_result['detected']:
                    risk_info['risks'].append('LAYERING')
                    risk_info['confidence'] *= (1 - self.config.get('confidence', {}).get('layering_penalty', 0.4))
                    risk_info['details'].append(layering_result)
            
            # SPOOFING - se habilitado
            if 'SPOOFING' in self.manipulation_patterns:
                spoofing_result = self._check_spoofing(book)
                if spoofing_result['detected']:
                    risk_info['risks'].append('SPOOFING')
                    risk_info['confidence'] *= (1 - self.config.get('confidence', {}).get('spoofing_penalty', 0.3))
                    risk_info['details'].append(spoofing_result)
        
        risk_info['safe'] = len(risk_info['risks']) == 0
        
        # Define ação recomendada
        if not risk_info['safe']:
            risk_info['action_required'] = self._determine_action(risk_info)
            if self.config.get('actions', {}).get('log_details', True):
                logger.warning(f"Manipulação VISÍVEL no book: {risk_info['risks']}")
        
        return risk_info['safe'], risk_info
    
    def _check_layering(self, book: OrderBook) -> Dict:
        """Detecta LAYERING baseado no config."""
        layering_config = self.config.get('layering', {})
        
        result = {
            'detected': False,
            'type': 'LAYERING',
            'side': None,
            'description': None
        }
        
        MIN_LEVELS = layering_config.get('min_levels', 4)
        MIN_VOLUME = layering_config.get('min_volume_per_level', 50)
        MAX_DEVIATION = layering_config.get('uniformity_threshold', 0.10)
        
        # Verifica BIDS
        if len(book.bids) >= MIN_LEVELS:
            bid_volumes = [level.volume for level in book.bids[:6]]
            
            if all(vol >= MIN_VOLUME for vol in bid_volumes[:MIN_LEVELS]):
                avg_vol = sum(bid_volumes[:MIN_LEVELS]) / MIN_LEVELS
                
                all_similar = all(
                    abs(vol - avg_vol) / avg_vol <= MAX_DEVIATION 
                    for vol in bid_volumes[:MIN_LEVELS]
                )
                
                if all_similar:
                    result['detected'] = True
                    result['side'] = 'BID'
                    result['description'] = (
                        f"BOOK SUSPEITO (Compra): {MIN_LEVELS}+ ordens "
                        f"IDÊNTICAS de ~{int(avg_vol)} contratos"
                    )
                    return result
        
        # Verifica ASKS
        if len(book.asks) >= MIN_LEVELS:
            ask_volumes = [level.volume for level in book.asks[:6]]
            
            if all(vol >= MIN_VOLUME for vol in ask_volumes[:MIN_LEVELS]):
                avg_vol = sum(ask_volumes[:MIN_LEVELS]) / MIN_LEVELS
                
                all_similar = all(
                    abs(vol - avg_vol) / avg_vol <= MAX_DEVIATION 
                    for vol in ask_volumes[:MIN_LEVELS]
                )
                
                if all_similar:
                    result['detected'] = True
                    result['side'] = 'ASK'
                    result['description'] = (
                        f"BOOK SUSPEITO (Venda): {MIN_LEVELS}+ ordens "
                        f"IDÊNTICAS de ~{int(avg_vol)} contratos"
                    )
                    return result
        
        return result
    
    def _check_spoofing(self, book: OrderBook) -> Dict:
        """Detecta SPOOFING baseado no config."""
        spoofing_config = self.config.get('spoofing', {})
        
        result = {
            'detected': False,
            'type': 'SPOOFING',
            'side': None,
            'description': None
        }
        
        if not book.bids or not book.asks:
            return result
        
        LEVELS_TO_CHECK = spoofing_config.get('levels_to_check', 5)
        SPOOFING_THRESHOLD = spoofing_config.get('imbalance_ratio', 5.0)
        
        bid_volume = sum(level.volume for level in book.bids[:LEVELS_TO_CHECK])
        ask_volume = sum(level.volume for level in book.asks[:LEVELS_TO_CHECK])
        
        if bid_volume == 0 or ask_volume == 0:
            return result
        
        if bid_volume > ask_volume:
            ratio = bid_volume / ask_volume
            heavier_side = 'BID'
        else:
            ratio = ask_volume / bid_volume
            heavier_side = 'ASK'
        
        if ratio >= SPOOFING_THRESHOLD:
            result['detected'] = True
            result['side'] = heavier_side
            
            if heavier_side == 'BID':
                result['description'] = (
                    f"BOOK ANORMAL: Compra {ratio:.1f}x maior que Venda - "
                    f"possíveis ordens FALSAS"
                )
            else:
                result['description'] = (
                    f"BOOK ANORMAL: Venda {ratio:.1f}x maior que Compra - "
                    f"possíveis ordens FALSAS"
                )
        
        return result
    
    def _determine_action(self, risk_info: Dict) -> str:
        """Determina ação baseada no que VEMOS no book."""
        risks = risk_info.get('risks', [])
        details = risk_info.get('details', [])
        
        if 'LAYERING' in risks:
            for detail in details:
                if detail.get('type') == 'LAYERING':
                    if detail.get('side') == 'BID':
                        return "⚠️ CUIDADO ao COMPRAR! Book com ordens suspeitas na compra"
                    elif detail.get('side') == 'ASK':
                        return "⚠️ CUIDADO ao VENDER! Book com ordens suspeitas na venda"
        
        if 'SPOOFING' in risks:
            for detail in details:
                if detail.get('type') == 'SPOOFING':
                    if detail.get('side') == 'BID':
                        return "⚠️ BOOK PESADO na COMPRA! Possível manipulação"
                    elif detail.get('side') == 'ASK':
                        return "⚠️ BOOK PESADO na VENDA! Possível manipulação"
        
        return "⚠️ BOOK ANORMAL! Opere com extrema cautela"