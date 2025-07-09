#core/analysis/filters/quality.py
"""Filtro de qualidade para sinais de tape reading."""
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class SignalQualityFilter:
    """Filtro de qualidade para sinais de tape reading."""
    
    __slots__ = ['min_quality_score', 'filtered_count', 'passed_count']
    
    def __init__(self, min_quality_score: float = 0.7):
        self.min_quality_score = min_quality_score
        self.filtered_count = 0
        self.passed_count = 0
    
    def evaluate_signal_quality(self, pattern_data: Dict) -> Dict:
        """Avalia qualidade do sinal de 0 a 1."""
        score = 0.0
        max_score = 0.0
        criteria = []
        
        pattern = pattern_data.get('pattern')
        
        # 1. Pressão: quanto mais extrema, melhor (peso 2.0)
        if pattern in ['PRESSAO_COMPRA', 'PRESSAO_VENDA']:
            max_score += 2.0
            ratio = pattern_data.get('ratio', 0)
            if ratio > 0.9:
                score += 2.0
                criteria.append("Pressão muito forte (+2.0)")
            elif ratio > 0.85:
                score += 1.5
                criteria.append("Pressão forte (+1.5)")
            else:
                score += 0.5
                criteria.append("Pressão moderada (+0.5)")
                
        # 2. Momentum: quanto mais extremo, melhor (peso 2.5)
        elif pattern == 'MOMENTUM_EXTREMO':
            max_score += 2.5
            cvd_roc = abs(pattern_data.get('cvd_roc', 0))
            if cvd_roc > 500:
                score += 2.5
                criteria.append("Momentum extremíssimo (+2.5)")
            elif cvd_roc > 300:
                score += 2.0
                criteria.append("Momentum muito forte (+2.0)")
            elif cvd_roc > 200:
                score += 1.5
                criteria.append("Momentum forte (+1.5)")
            else:
                score += 0.8
                criteria.append("Momentum moderado (+0.8)")
                
        # 3. Escora: volume e concentração (peso 3.0)
        elif pattern == 'ESCORA_DETECTADA':
            max_score += 3.0
            volume = pattern_data.get('volume', 0)
            concentration = pattern_data.get('concentration', 0)
            
            # Volume score
            if volume > 5000:
                score += 1.5
                criteria.append("Volume muito alto (+1.5)")
            elif volume > 2000:
                score += 1.0
                criteria.append("Volume alto (+1.0)")
            else:
                score += 0.5
                criteria.append("Volume moderado (+0.5)")
            
            # Concentração score
            if concentration > 0.6:
                score += 1.5
                criteria.append("Concentração muito alta (+1.5)")
            elif concentration > 0.5:
                score += 1.0
                criteria.append("Concentração alta (+1.0)")
            else:
                score += 0.5
                criteria.append("Concentração moderada (+0.5)")
        
        # 4. Divergências (peso 2.5)
        elif pattern in ['DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA']:
            max_score += 2.5
            cvd_roc = abs(pattern_data.get('cvd_roc', 0))
            if cvd_roc > 150:
                score += 2.5
                criteria.append("Divergência forte (+2.5)")
            elif cvd_roc > 100:
                score += 2.0
                criteria.append("Divergência moderada (+2.0)")
            else:
                score += 1.0
                criteria.append("Divergência fraca (+1.0)")
        
        # 5. Iceberg (peso 2.0)
        elif pattern == 'ICEBERG':
            max_score += 2.0
            repetitions = pattern_data.get('repetitions', 0)
            if repetitions > 5:
                score += 2.0
                criteria.append("Iceberg confirmado (+2.0)")
            elif repetitions > 3:
                score += 1.5
                criteria.append("Iceberg provável (+1.5)")
            else:
                score += 0.8
                criteria.append("Iceberg possível (+0.8)")
        
        # 6. Volume Spike (peso 1.5)
        elif pattern == 'VOLUME_SPIKE':
            max_score += 1.5
            multiplier = pattern_data.get('multiplier', 0)
            if multiplier > 10:
                score += 1.5
                criteria.append("Spike extremo (+1.5)")
            elif multiplier > 5:
                score += 1.0
                criteria.append("Spike forte (+1.0)")
            else:
                score += 0.5
                criteria.append("Spike moderado (+0.5)")
        
        # 7. Pace Anomaly (peso 1.0)
        elif pattern == 'PACE_ANOMALY':
            max_score += 1.0
            pace = pattern_data.get('pace', 0)
            baseline = pattern_data.get('baseline', 1)
            ratio = pace / baseline if baseline > 0 else 0
            
            if ratio > 5:
                score += 1.0
                criteria.append("Pace anormal extremo (+1.0)")
            elif ratio > 3:
                score += 0.7
                criteria.append("Pace anormal forte (+0.7)")
            else:
                score += 0.3
                criteria.append("Pace anormal moderado (+0.3)")
        
        # Padrão desconhecido
        else:
            max_score += 1.0
            score += 0.3
            criteria.append("Padrão não classificado (+0.3)")
        
        # Calcula score normalizado
        normalized_score = score / max_score if max_score > 0 else 0
        
        # Estatísticas
        if normalized_score >= self.min_quality_score:
            self.passed_count += 1
        else:
            self.filtered_count += 1
        
        return {
            'score': normalized_score,
            'passed': normalized_score >= self.min_quality_score,
            'criteria': criteria,
            'raw_score': score,
            'max_score': max_score
        }
    
    def should_emit_signal(self, pattern_data: Dict) -> bool:
        """Verifica se o sinal deve ser emitido baseado na qualidade."""
        quality = self.evaluate_signal_quality(pattern_data)
        
        if not quality['passed']:
            logger.debug(
                f"Sinal {pattern_data.get('pattern')} filtrado por qualidade: "
                f"{quality['score']:.2f} < {self.min_quality_score}"
            )
        
        return quality['passed']
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do filtro."""
        total = self.passed_count + self.filtered_count
        return {
            'total_evaluated': total,
            'passed': self.passed_count,
            'filtered': self.filtered_count,
            'pass_rate': (self.passed_count / total * 100) if total > 0 else 0
        }