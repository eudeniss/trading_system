# application/services/tape_reading/pattern_confirmation.py
"""Sistema de confirmação de padrões."""
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import uuid
import logging

from core.entities.signal import Signal
from core.contracts.cache import ITradeCache
from core.contracts.messaging import ISystemEventBus
from core.analysis.filters.defensive import DefensiveSignalFilter
from core.analysis.filters.cooldown import PatternCooldown
from core.formatters.signal_formatter import SignalFormatter

from .types import PendingPattern

logger = logging.getLogger(__name__)


class PatternConfirmationSystem:
    """Sistema de confirmação de padrões (FASE 4.1)."""
    
    def __init__(self, event_bus: ISystemEventBus, cache: ITradeCache, 
                 analyzers: Dict, config: Dict, defensive_filter: DefensiveSignalFilter,
                 pattern_cooldown: PatternCooldown, formatter: SignalFormatter):
        self.event_bus = event_bus
        self.cache = cache
        self.analyzers = analyzers
        self.config = config
        self.defensive_filter = defensive_filter
        self.pattern_cooldown = pattern_cooldown
        self.formatter = formatter
        
        self.pending_patterns: Dict[str, PendingPattern] = {}
        self.current_books = {}
        
        # Estatísticas
        self.stats = {
            'signals_emitted': 0,
            'manipulation_detected': 0
        }
    
    def requires_confirmation(self, pattern: str) -> bool:
        """Verifica se padrão requer confirmação."""
        if not self.config['enabled']:
            return False
        
        return pattern in self.config['patterns']
    
    def add_pending_pattern(self, pattern: str, symbol: str, data: Dict):
        """Adiciona padrão para confirmação posterior."""
        # Limita quantidade de pendentes
        if len(self.pending_patterns) >= self.config['max_pending']:
            # Remove o mais antigo
            oldest = min(self.pending_patterns.items(), key=lambda x: x[1].created_at)
            del self.pending_patterns[oldest[0]]
            logger.debug(f"Removido padrão pendente mais antigo: {oldest[1].pattern}")
        
        # Configura confirmação
        pattern_config = self.config['patterns'].get(
            pattern, 
            {'timeout': self.config['default_timeout']}
        )
        
        timeout = pattern_config.get('timeout', self.config['default_timeout'])
        
        # Cria critérios específicos
        criteria = self._build_confirmation_criteria(pattern, data, pattern_config)
        
        # Cria o padrão pendente
        pending = PendingPattern(
            id=str(uuid.uuid4()),
            pattern=pattern,
            symbol=symbol,
            data=data,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=timeout),
            confirmation_criteria=criteria
        )
        
        self.pending_patterns[pending.id] = pending
        
        logger.debug(
            f"Padrão pendente: {pattern} em {symbol}, "
            f"expira em {timeout}s, critérios: {list(criteria.keys())}"
        )
    
    def check_pending_patterns(self):
        """Verifica padrões pendentes."""
        now = datetime.now()
        to_remove = []
        confirmed_patterns = []
        
        for pattern_id, pending in self.pending_patterns.items():
            # Verifica expiração
            if now > pending.expires_at:
                to_remove.append(pattern_id)
                logger.debug(f"Padrão {pending.pattern} expirado sem confirmação")
                continue
            
            # Verifica confirmação
            is_confirmed, updated_criteria = self._check_pattern_confirmation(pending)
            
            # Atualiza critérios
            pending.confirmation_criteria = updated_criteria
            pending.attempts += 1
            pending.last_check = now
            
            if is_confirmed:
                confirmed_patterns.append(pending)
                to_remove.append(pattern_id)
                logger.info(f"✅ {pending.pattern} CONFIRMADO após {pending.attempts} verificações")
        
        # Remove padrões processados
        for pattern_id in to_remove:
            del self.pending_patterns[pattern_id]
        
        # Emite sinais confirmados
        for pending in confirmed_patterns:
            self._emit_confirmed_pattern(pending)
    
    def _build_confirmation_criteria(self, pattern: str, data: Dict, config: Dict) -> Dict:
        """Constrói critérios de confirmação específicos."""
        criteria = {}
        
        if pattern == 'ESCORA_DETECTADA':
            criteria.update({
                'min_tests': config.get('min_tests', 2),
                'test_threshold': config.get('test_threshold', 0.7),
                'level': data.get('level', 0),
                'original_volume': data.get('volume', 0),
                'test_count': 0,
                'test_volumes': []
            })
            
        elif pattern in ['DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA']:
            criteria.update({
                'confirmation_bars': config.get('confirmation_bars', 3),
                'price_confirmation': config.get('price_confirmation', True),
                'original_price': data.get('price', 0),
                'original_cvd_roc': data.get('cvd_roc', 0),
                'bars_checked': 0,
                'price_direction': data.get('price_direction'),
                'flow_direction': data.get('flow_direction')
            })
            
        elif pattern == 'MOMENTUM_EXTREMO':
            criteria.update({
                'requires_continuation': config.get('requires_continuation', True),
                'min_continuation_cvd': config.get('min_continuation_cvd', 50),
                'original_cvd_roc': data.get('cvd_roc', 0),
                'original_direction': data.get('direction')
            })
            
        elif pattern == 'INSTITUTIONAL_FOOTPRINT':
            criteria.update({
                'min_persistence': config.get('min_persistence', 30),
                'volume_threshold': config.get('volume_threshold', 0.3),
                'original_confidence': data.get('confidence', 0),
                'operation_type': data.get('operation_type'),
                'persistence_checks': 0
            })
            
        elif pattern == 'HIDDEN_LIQUIDITY':
            criteria.update({
                'reload_confirmations': config.get('reload_confirmations', 2),
                'min_hidden_volume': config.get('min_hidden_volume', 500),
                'original_levels': data.get('hidden_levels', []),
                'confirmed_reloads': 0
            })
        
        return criteria
    
    def _check_pattern_confirmation(self, pending: PendingPattern) -> Tuple[bool, Dict]:
        """Lógica específica de confirmação por padrão."""
        pattern = pending.pattern
        symbol = pending.symbol
        criteria = pending.confirmation_criteria.copy()
        
        if pattern == 'ESCORA_DETECTADA':
            return self._check_absorption_confirmation(symbol, criteria)
        elif pattern in ['DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA']:
            return self._check_divergence_confirmation(symbol, pattern, criteria)
        elif pattern == 'MOMENTUM_EXTREMO':
            return self._check_momentum_confirmation(symbol, criteria)
        elif pattern == 'INSTITUTIONAL_FOOTPRINT':
            return self._check_institutional_confirmation(symbol, criteria)
        elif pattern == 'HIDDEN_LIQUIDITY':
            return self._check_hidden_liquidity_confirmation(symbol, criteria)
        
        return False, criteria
    
    def _check_absorption_confirmation(self, symbol: str, criteria: Dict) -> Tuple[bool, Dict]:
        """Confirma se escora/absorção foi testada."""
        level = criteria['level']
        original_volume = criteria['original_volume']
        min_tests = criteria['min_tests']
        test_threshold = criteria['test_threshold']
        
        # Busca trades recentes
        recent_trades = self.cache.get_recent_trades(symbol, 100)
        
        # Conta testes do nível
        for trade in recent_trades[-20:]:
            if abs(trade.price - level) <= 0.5:
                criteria['test_volumes'].append(trade.volume)
                
                # Teste significativo?
                if trade.volume >= original_volume * test_threshold:
                    criteria['test_count'] += 1
        
        is_confirmed = criteria['test_count'] >= min_tests
        return is_confirmed, criteria
    
    def _check_divergence_confirmation(self, symbol: str, pattern: str, criteria: Dict) -> Tuple[bool, Dict]:
        """Confirma divergência com movimento de preço."""
        confirmation_bars = criteria['confirmation_bars']
        price_confirmation = criteria['price_confirmation']
        original_price = criteria['original_price']
        
        recent_trades = self.cache.get_recent_trades(symbol, 50)
        if len(recent_trades) < 10:
            return False, criteria
        
        criteria['bars_checked'] += 1
        
        current_price = recent_trades[-1].price
        
        if price_confirmation:
            if pattern == 'DIVERGENCIA_ALTA':
                price_confirmed = current_price >= original_price * 0.999
            else:  # DIVERGENCIA_BAIXA
                price_confirmed = current_price <= original_price * 1.001
            
            if not price_confirmed:
                return False, criteria
        
        is_confirmed = criteria['bars_checked'] >= confirmation_bars
        return is_confirmed, criteria
    
    def _check_momentum_confirmation(self, symbol: str, criteria: Dict) -> Tuple[bool, Dict]:
        """Confirma se momentum continua na mesma direção."""
        requires_continuation = criteria['requires_continuation']
        min_continuation_cvd = criteria['min_continuation_cvd']
        original_direction = criteria['original_direction']
        
        if not requires_continuation:
            return True, criteria
        
        recent_trades = self.cache.get_recent_trades(symbol, 50)
        cvd = self.analyzers[symbol]['cvd_calc'].calculate_cvd_for_trades(recent_trades)
        
        if original_direction == 'COMPRA':
            is_confirmed = cvd >= min_continuation_cvd
        else:  # VENDA
            is_confirmed = cvd <= -min_continuation_cvd
        
        return is_confirmed, criteria
    
    def _check_institutional_confirmation(self, symbol: str, criteria: Dict) -> Tuple[bool, Dict]:
        """Confirma persistência de atividade institucional."""
        min_persistence = criteria['min_persistence']
        volume_threshold = criteria['volume_threshold']
        
        criteria['persistence_checks'] += 1
        
        # Verifica se ainda há volume institucional
        recent_trades = self.cache.get_recent_trades(symbol, 100)
        if not recent_trades:
            return False, criteria
        
        total_volume = sum(t.volume for t in recent_trades)
        institutional_volume = sum(
            t.volume for t in recent_trades 
            if 50 <= t.volume <= 1000  # Range institucional
        )
        
        inst_ratio = institutional_volume / total_volume if total_volume > 0 else 0
        
        # Confirmado se mantém ratio e passou tempo mínimo
        is_confirmed = (
            inst_ratio >= volume_threshold and
            criteria['persistence_checks'] * 10 >= min_persistence  # Assumindo check a cada 10s
        )
        
        return is_confirmed, criteria
    
    def _check_hidden_liquidity_confirmation(self, symbol: str, criteria: Dict) -> Tuple[bool, Dict]:
        """Confirma se liquidez oculta continua presente."""
        reload_confirmations = criteria['reload_confirmations']
        min_hidden_volume = criteria['min_hidden_volume']
        original_levels = criteria['original_levels']
        
        if not original_levels:
            return False, criteria
        
        # Verifica se níveis continuam ativos
        current_hidden = self.analyzers[symbol]['hidden_liquidity'].get_hidden_levels(
            symbol, 
            original_levels[0]['price'],
            range_pct=0.005
        )
        
        if current_hidden:
            criteria['confirmed_reloads'] += 1
        
        is_confirmed = criteria['confirmed_reloads'] >= reload_confirmations
        return is_confirmed, criteria
    
    def _emit_confirmed_pattern(self, pending: PendingPattern):
        """Emite sinal para padrão confirmado."""
        # Atualiza dados
        signal_data = pending.data.copy()
        signal_data['confirmed'] = True
        signal_data['confirmation_attempts'] = pending.attempts
        signal_data['confirmation_time'] = (datetime.now() - pending.created_at).seconds
        signal_data['pattern'] = f"{pending.pattern}_CONFIRMED"
        
        # Verifica cooldown
        if not self.pattern_cooldown.can_emit_pattern(pending.pattern, pending.symbol):
            return
        
        # Formata
        signal = self.formatter.format(signal_data, pending.symbol)
        
        # Cria novo signal com mensagem confirmada
        confirmed_signal = Signal(
            source=signal.source,
            level=signal.level,
            message=f"✅ [CONFIRMADO] {signal.message}",
            timestamp=signal.timestamp,
            details=signal.details
        )
        
        # Filtro defensivo
        book = self.current_books.get(pending.symbol)
        recent_trades = self.cache.get_recent_trades(pending.symbol, 50)
        
        is_safe, risk_info = self.defensive_filter.is_signal_safe(
            confirmed_signal,
            book,
            recent_trades
        )
        
        if is_safe:
            self.event_bus.publish("SIGNAL_GENERATED", confirmed_signal)
            self.stats['signals_emitted'] += 1
            logger.info(f"📢 Sinal confirmado: {confirmed_signal.message}")
        else:
            self.stats['manipulation_detected'] += 1
            self.event_bus.publish('MANIPULATION_DETECTED', {
                'signal': confirmed_signal,
                'risk_info': risk_info, 
                'symbol': pending.symbol
            })
    
    def update_book(self, symbol: str, book):
        """Atualiza book atual para uso na confirmação."""
        self.current_books[symbol] = book
    
    def get_pending_count(self, symbol: str) -> int:
        """Retorna quantidade de padrões pendentes para um símbolo."""
        return sum(1 for p in self.pending_patterns.values() if p.symbol == symbol)
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do sistema de confirmação."""
        return {
            'pending_patterns': len(self.pending_patterns),
            'pending_by_pattern': {},
            'signals_emitted': self.stats['signals_emitted'],
            'manipulation_detected': self.stats['manipulation_detected']
        }