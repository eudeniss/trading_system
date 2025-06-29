# analyzers/statistics/pace_analyzer.py
from datetime import datetime, timedelta
from collections import deque
import numpy as np
from typing import Optional, Dict

class PaceAnalyzer:
    """Analisa o Pace of Tape (velocidade dos negócios)."""

    def __init__(self, baseline_samples=100, anomaly_stdev=2.5, window_seconds=10):
        self.trade_timestamps = deque(maxlen=10000)
        self.pace_history = deque(maxlen=baseline_samples)
        self.anomaly_stdev = anomaly_stdev
        self.window_seconds = window_seconds

    def update_and_check_anomaly(self) -> Optional[Dict]:
        """Adiciona um timestamp e verifica se há uma anomalia no pace."""
        self.trade_timestamps.append(datetime.now())
        
        now = datetime.now()
        window = timedelta(seconds=self.window_seconds)

        recent_trades_count = sum(1 for ts in reversed(self.trade_timestamps) if now - ts <= window)
        current_pace = recent_trades_count / self.window_seconds
        
        self.pace_history.append(current_pace)
        
        if len(self.pace_history) < 50:
            return None # Não há dados suficientes para uma baseline

        baseline = np.median(list(self.pace_history))
        std_dev = np.std(list(self.pace_history))
        
        if std_dev > 0 and current_pace > (baseline + self.anomaly_stdev * std_dev):
            return {
                "pace": current_pace,
                "baseline": baseline,
                "intensity": "HIGH"
            }
        
        return None