# application/services/tape_reading/analyzer_factory.py
"""Factory e gerenciamento de analyzers."""
from typing import Dict
import logging

from core.analysis.patterns.absorption import AbsorptionDetector
from core.analysis.patterns.iceberg import IcebergDetector
from core.analysis.patterns.momentum import MomentumAnalyzer
from core.analysis.patterns.pressure import PressureDetector
from core.analysis.patterns.volume_spike import VolumeSpikeDetector
from core.analysis.patterns.book_dynamics_analyzer import BookDynamicsAnalyzer
from core.analysis.patterns.institutional_footprint import InstitutionalFootprintDetector
from core.analysis.patterns.hidden_liquidity import HiddenLiquidityDetector
from core.analysis.patterns.multiframe_delta import MultiframeDeltaAnalyzer
from core.analysis.patterns.trap_detector import TrapDetector
from core.analysis.statistics.cvd import CvdCalculator
from core.analysis.statistics.pace import PaceAnalyzer

logger = logging.getLogger(__name__)


class AnalyzerFactory:
    """Factory para criar e gerenciar analyzers."""
    
    @staticmethod
    def create_analyzers(config: Dict) -> Dict:
        """Cria todos os analisadores com parâmetros do config."""
        return {
            # Analisadores básicos
            'cvd_calc': CvdCalculator(
                history_size=config.get('cvd_history_size', 1000)
            ),
            'pace_analyzer': PaceAnalyzer(
                baseline_samples=config.get('pace_baseline_samples', 100),
                anomaly_stdev=config.get('pace_anomaly_stdev', 2.0),
                window_seconds=config.get('pace_window_seconds', 10)
            ),
            'absorption_detector': AbsorptionDetector(
                concentration_threshold=config.get('concentration_threshold', 0.40),
                min_volume_threshold=config.get('absorption_threshold', 282)
            ),
            'iceberg_detector': IcebergDetector(
                repetitions=config.get('iceberg_repetitions', 4),
                min_volume=config.get('iceberg_min_volume', 59)
            ),
            'momentum_analyzer': MomentumAnalyzer(
                divergence_roc_threshold=config.get('divergence_threshold', 209),
                extreme_roc_threshold=config.get('extreme_threshold', 250)
            ),
            'pressure_detector': PressureDetector(
                threshold=config.get('pressure_threshold', 0.75),
                min_volume=config.get('pressure_min_volume', 100)
            ),
            'volume_spike_detector': VolumeSpikeDetector(
                spike_multiplier=config.get('spike_multiplier', 3.0),
                history_size=config.get('spike_history_size', 100)
            ),
            
            # FASE 4.2: Analisador de dinâmica do book
            'book_dynamics': BookDynamicsAnalyzer(config.get('book_dynamics', {})),
            
            # FASE 5: Detectores especializados
            'institutional': InstitutionalFootprintDetector(config.get('institutional', {})),
            'hidden_liquidity': HiddenLiquidityDetector(config.get('hidden_liquidity', {})),
            'multiframe_delta': MultiframeDeltaAnalyzer(config.get('multiframe', {})),
            'trap_detector': TrapDetector(config.get('trap_detection', {}))
        }