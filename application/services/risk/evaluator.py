#application/services/risk/evaluator.py
"""Avaliador de qualidade e risco de sinais."""
from typing import Dict, Tuple, List
from datetime import datetime
import logging

from core.entities.signal import Signal, SignalLevel, SignalSource
from .types import RiskLevel, SignalQuality, QualityEvaluation, ContextualRisk

logger = logging.getLogger(__name__)


class SignalEvaluator:
    """Avalia qualidade e risco de sinais."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.quality_threshold = config.get('signal_quality_threshold', 0.35)
        
        self.quality_weights = config.get('quality_weights', {
            'source_weight': 1.5,
            'level_weight': 0.8,
            'details_weight': 1.5,
            'pattern_weight': 1.2
        })
        
        # Estatísticas
        self.evaluated_count = 0
        self.approved_count = 0
        self.rejection_reasons = {}
        
        logger.info(f"SignalEvaluator inicializado - threshold: {self.quality_threshold}")
    
    def evaluate_quality(self, signal: Signal) -> QualityEvaluation:
        """Avalia qualidade de um sinal usando pesos configuráveis."""
        self.evaluated_count += 1
        
        score = 0.0
        max_score = 0.0
        criteria = []
        improvements = []
        
        weights = self.quality_weights
        
        # 1. Fonte do sinal
        source_weight = weights.get('source_weight', 1.5)
        max_score += source_weight
        
        if signal.source == SignalSource.CONFLUENCE:
            score += source_weight
            criteria.append(f"Confluência (+{source_weight})")
        elif signal.source == SignalSource.ARBITRAGE:
            score += source_weight * 0.8
            criteria.append(f"Arbitragem (+{source_weight * 0.8:.1f})")
        elif signal.source == SignalSource.TAPE_READING:
            score += source_weight * 0.6
            criteria.append(f"Tape Reading (+{source_weight * 0.6:.1f})")
        else:
            score += source_weight * 0.3
            improvements.append("Sinais de confluência têm maior confiabilidade")
        
        # 2. Nível de alerta
        level_weight = weights.get('level_weight', 0.8)
        max_score += level_weight
        
        if signal.level == SignalLevel.ALERT:
            score += level_weight
            criteria.append(f"Alert (+{level_weight})")
        elif signal.level == SignalLevel.WARNING:
            score += level_weight * 0.6
            criteria.append(f"Warning (+{level_weight * 0.6:.1f})")
        else:
            score += level_weight * 0.2
        
        # 3. Detalhes específicos
        details_weight = weights.get('details_weight', 1.5)
        max_score += details_weight
        
        profit = signal.details.get('profit', 0)
        if profit >= 50:
            score += details_weight * 0.6
            criteria.append(f"Lucro alto (+{details_weight * 0.6:.1f})")
        elif profit >= 20:
            score += details_weight * 0.4
            criteria.append(f"Lucro médio (+{details_weight * 0.4:.1f})")
        else:
            improvements.append("Busque oportunidades com maior potencial")
        
        # 4. Padrão específico
        pattern_weight = weights.get('pattern_weight', 1.2)
        max_score += pattern_weight
        
        pattern = signal.details.get('original_pattern', '')
        high_quality_patterns = [
            'ESCORA_DETECTADA', 'DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA', 
            'ICEBERG', 'MOMENTUM_EXTREMO'
        ]
        medium_quality_patterns = ['PRESSAO_COMPRA', 'PRESSAO_VENDA', 'VOLUME_SPIKE']
        
        if pattern in high_quality_patterns:
            score += pattern_weight
            criteria.append(f"Padrão forte: {pattern} (+{pattern_weight})")
        elif pattern in medium_quality_patterns:
            score += pattern_weight * 0.7
            criteria.append(f"Padrão médio: {pattern} (+{pattern_weight * 0.7:.1f})")
        
        # Score final
        normalized_score = score / max_score if max_score > 0 else 0
        
        # Rating
        if normalized_score >= 0.7:
            rating = SignalQuality.EXCELLENT
        elif normalized_score >= 0.5:
            rating = SignalQuality.GOOD
        elif normalized_score >= 0.35:
            rating = SignalQuality.FAIR
        else:
            rating = SignalQuality.POOR
        
        passed = normalized_score >= self.quality_threshold
        if passed:
            self.approved_count += 1
        else:
            pattern_key = pattern or 'UNKNOWN'
            self.rejection_reasons[pattern_key] = self.rejection_reasons.get(pattern_key, 0) + 1
        
        return {
            'score': normalized_score,
            'rating': rating,
            'criteria': criteria,
            'improvements': improvements,
            'passed': passed
        }
    
    def evaluate_contextual_risk(self, signal: Signal, context: Dict) -> ContextualRisk:
        """Avalia risco baseado no contexto atual."""
        risk_factors = []
        risk_score = 0
        
        # Risco atual do sistema
        current_risk = context.get('system_risk_level', RiskLevel.LOW)
        if current_risk == RiskLevel.CRITICAL:
            risk_score += 3
            risk_factors.append("Sistema em risco crítico")
        elif current_risk == RiskLevel.HIGH:
            risk_score += 2
            risk_factors.append("Sistema em risco alto")
        elif current_risk == RiskLevel.MEDIUM:
            risk_score += 1
            risk_factors.append("Sistema em risco médio")
        
        # Drawdown
        drawdown = context.get('current_drawdown', 0)
        if drawdown > 1.5:
            risk_score += 2
            risk_factors.append("Próximo do drawdown máximo")
        
        # Horário
        hour = datetime.now().hour
        if hour < 10 or hour > 16:
            risk_score += 1
            risk_factors.append("Horário de menor liquidez")
        
        # Volatilidade no sinal
        if 'cvd_roc' in signal.details and abs(signal.details['cvd_roc']) > 150:
            risk_score += 1
            risk_factors.append("Volatilidade extrema detectada")
        
        # Determina nível
        if risk_score >= 4:
            level = RiskLevel.CRITICAL
        elif risk_score >= 3:
            level = RiskLevel.HIGH
        elif risk_score >= 2:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        
        return {
            'level': level,
            'score': risk_score,
            'factors': risk_factors,
            'reason': '; '.join(risk_factors) if risk_factors else 'Risco normal'
        }
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do avaliador."""
        approval_rate = (self.approved_count / self.evaluated_count * 100) if self.evaluated_count > 0 else 0
        
        # Top 3 razões de rejeição
        top_rejections = sorted(
            self.rejection_reasons.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:3]
        
        return {
            'total_evaluated': self.evaluated_count,
            'total_approved': self.approved_count,
            'approval_rate': approval_rate,
            'top_rejection_patterns': [
                {'pattern': pattern, 'count': count} 
                for pattern, count in top_rejections
            ],
            'quality_threshold': self.quality_threshold
        }