"""Módulo de análise do sistema."""

# Patterns
from .patterns.absorption import AbsorptionDetector
from .patterns.iceberg import IcebergDetector
from .patterns.momentum import MomentumAnalyzer
from .patterns.pressure import PressureDetector
from .patterns.volume_spike import VolumeSpikeDetector

# Statistics
from .statistics.cvd import CvdCalculator
from .statistics.pace import PaceAnalyzer
from .statistics.volume_profile import VolumeProfileAnalyzer
from .statistics.aggregator import MarketStatsAggregator

# Filters
from .filters.defensive import DefensiveSignalFilter
from .filters.cooldown import PatternCooldown
from .filters.quality import SignalQualityFilter

# Regime
from .regime.detector import MarketRegimeDetector

__all__ = [
    # Patterns
    'AbsorptionDetector',
    'IcebergDetector',
    'MomentumAnalyzer',
    'PressureDetector',
    'VolumeSpikeDetector',
    
    # Statistics
    'CvdCalculator',
    'PaceAnalyzer',
    'VolumeProfileAnalyzer',
    'MarketStatsAggregator',
    
    # Filters
    'DefensiveSignalFilter',
    'PatternCooldown',
    'SignalQualityFilter',
    
    # Regime
    'MarketRegimeDetector'
]