#core/analysis/statistics/pace.py
"""Analisador de ritmo (pace) de negociação."""
from datetime import datetime, timedelta
from collections import deque
import numpy as np
from typing import Optional, Dict


class PaceAnalyzer:
    """Analisa o Pace of Tape com parâmetros v3.1."""

    __slots__ = ['trade_timestamps', 'pace_history', 'anomaly_stdev', 'window_seconds']

    def __init__(self, baseline_samples: int = 100, anomaly_stdev: float = 2.0, window_seconds: int = 10):
        self.trade_timestamps = deque(maxlen=10000)
        self.pace_history = deque(maxlen=baseline_samples)
        self.anomaly_stdev = anomaly_stdev  # Agora é stdev, não multiplier
        self.window_seconds = window_seconds

    def update_and_check_anomaly(self) -> Optional[Dict]:
        """Adiciona timestamp e verifica anomalia."""
        self.trade_timestamps.append(datetime.now())
        
        now = datetime.now()
        window = timedelta(seconds=self.window_seconds)

        recent_trades_count = sum(1 for ts in reversed(self.trade_timestamps) if now - ts <= window)
        current_pace = recent_trades_count / self.window_seconds
        
        self.pace_history.append(current_pace)
        
        if len(self.pace_history) < 50:
            return None

        baseline = np.median(list(self.pace_history))
        std_dev = np.std(list(self.pace_history))
        
        # Usa anomaly_stdev do config
        if std_dev > 0 and current_pace > (baseline + self.anomaly_stdev * std_dev):
            return {
                "pace": current_pace,
                "baseline": baseline,
                "intensity": "HIGH",
                "deviation": (current_pace - baseline) / std_dev if std_dev > 0 else 0
            }
        
        return None