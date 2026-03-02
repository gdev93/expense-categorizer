import os

class ForecastConfig:
    """Configuration utility for forecasting parameters."""
    
    # General forecasting thresholds
    FORECAST_THRESHOLD_DAYS: int = int(os.getenv('FORECAST_THRESHOLD_DAYS', 15))
    HISTORY_MONTHS: int = int(os.getenv('FORECAST_HISTORY_MONTHS', 9))
    
    # Statistical thresholds for forecasting strategies
    SEASONAL_THRESHOLD: float = float(os.getenv('FORECAST_SEASONAL_THRESHOLD', 0.6))
    CV_STABLE_THRESHOLD: float = float(os.getenv('FORECAST_CV_STABLE_THRESHOLD', 0.1))
    ER_PERIOD_BASE: int = int(os.getenv('FORECAST_ER_PERIOD_BASE', 4))
    
    # Seasonality check parameters
    SEASONALITY_MIN_DATA_POINTS: int = int(os.getenv('FORECAST_SEASONALITY_MIN_DATA_POINTS', 24))
    SEASONALITY_LAG_MONTHS: int = int(os.getenv('FORECAST_SEASONALITY_LAG_MONTHS', 12))
    SEASONALITY_GROWTH_ALPHA: float = float(os.getenv('FORECAST_SEASONALITY_GROWTH_ALPHA', 0.1))
    
    # Momentum correction factors
    MOMENTUM_MIN_FACTOR: float = float(os.getenv('FORECAST_MOMENTUM_MIN_FACTOR', 0.85))
    MOMENTUM_MAX_FACTOR: float = float(os.getenv('FORECAST_MOMENTUM_MAX_FACTOR', 1.15))
    MOMENTUM_HISTORY_WINDOW: int = int(os.getenv('FORECAST_MOMENTUM_HISTORY_WINDOW', 4))
    
    # Kaufman's Adaptive Moving Average (KAMA) parameters
    KAMA_FAST_N: int = int(os.getenv('FORECAST_KAMA_FAST_N', 2))
    KAMA_SLOW_N: int = int(os.getenv('FORECAST_KAMA_SLOW_N', 30))
    KAMA_ER_PERIOD: int = int(os.getenv('FORECAST_KAMA_ER_PERIOD', 10))
    KAMA_WARMUP_ALPHA: float = float(os.getenv('FORECAST_KAMA_WARMUP_ALPHA', 0.2))

    @classmethod
    def get_history_days(cls) -> int:
        """Returns the history period in days."""
        return cls.HISTORY_MONTHS * 30
