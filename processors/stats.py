import logging
from datetime import date
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from api.config import ForecastConfig

# Improved logger formatting to exclude sensitive data
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

@dataclass
class ForecastInput:
    amount: float
    date: date


def calculate_ama_from_history(
        ama_input: List[ForecastInput],
        fast_n: int = ForecastConfig.KAMA_FAST_N,
        slow_n: int = ForecastConfig.KAMA_SLOW_N,
        er_period: int = ForecastConfig.KAMA_ER_PERIOD
) -> float:
    """
    Calculates the Kaufman's Adaptive Moving Average (KAMA).
    All internal calculations remain unchanged to preserve accuracy.
    """
    if not ama_input:
        return 0.0
    if len(ama_input) == 1:
        return round(ama_input[0].amount, 2)

    # Sort to process chronologically: from oldest to newest
    amounts: List[float] = [float(x.amount) for x in sorted(ama_input, key=lambda x: x.date)]

    current_ama: float = amounts[0]
    fast_sc: float = 2 / (fast_n + 1)
    slow_sc: float = 2 / (slow_n + 1)

    for i in range(1, len(amounts)):
        if i >= er_period:
            change: float = abs(amounts[i] - amounts[i - er_period])
            volatility: float = sum(
                abs(amounts[j] - amounts[j - 1])
                for j in range(i - er_period + 1, i + 1)
            )
            er: float = change / volatility if volatility != 0 else 0
            sc: float = (er * (fast_sc - slow_sc) + slow_sc) ** 2
            current_ama = current_ama + sc * (amounts[i] - current_ama)
        else:
            alpha_warmup: float = ForecastConfig.KAMA_WARMUP_ALPHA
            current_ama = (amounts[i] * alpha_warmup) + (current_ama * (1 - alpha_warmup))

    return round(current_ama, 2)


def is_stable_expense(amounts: np.ndarray, threshold: float) -> bool:
    mean_val = np.mean(amounts)
    if mean_val == 0:
        logger.info("Stability Check: Data series is zero/empty. Treating as stable.")
        return True

    cv = np.std(amounts) / mean_val
    is_stable = cv < threshold

    # Log only the Coefficient of Variation (relative metric), not the amounts
    logger.info(f"Stability Check: CV={cv:.4f} (Threshold={threshold}). Stable={is_stable}")
    return is_stable


def get_seasonal_forecast(amounts: np.ndarray, threshold: float) -> Optional[float]:
    if len(amounts) < ForecastConfig.SEASONALITY_MIN_DATA_POINTS:
        logger.info(f"Seasonality Check: Insufficient data points ({len(amounts)} units). Skipping.")
        return None

    import pandas as pd
    series = pd.Series(amounts)
    correlation = series.autocorr(lag=ForecastConfig.SEASONALITY_LAG_MONTHS)

    if correlation > threshold:
        last_year_val = amounts[-ForecastConfig.SEASONALITY_LAG_MONTHS]
        growth_factor = 1 + (correlation * ForecastConfig.SEASONALITY_GROWTH_ALPHA)
        forecast = round(float(last_year_val * growth_factor), 2)
        # Log correlation strength instead of values
        logger.info(f"Seasonality Check: High Correlation ({correlation:.4f}). Forecast generated via YoY.")
        return forecast

    logger.info(f"Seasonality Check: Correlation ({correlation:.4f}) below threshold. Not seasonal.")
    return None


def apply_momentum_correction(current_kama: float, history: List[ForecastInput], er_period: int) -> float:
    if len(history) < ForecastConfig.MOMENTUM_HISTORY_WINDOW:
        logger.info("Momentum: Insufficient history for trend analysis.")
        return current_kama

    past_kama = calculate_ama_from_history(history[:-(ForecastConfig.MOMENTUM_HISTORY_WINDOW - 1)], er_period=er_period)

    if past_kama <= 0:
        return current_kama

    momentum_factor = current_kama / past_kama
    capped_factor = max(ForecastConfig.MOMENTUM_MIN_FACTOR, min(ForecastConfig.MOMENTUM_MAX_FACTOR, momentum_factor))

    # Log the factor (relative change), which doesn't reveal the absolute amount
    logger.info(f"Momentum: Trend Factor={momentum_factor:.4f} (Capped to={capped_factor:.4f}).")
    return round(current_kama * capped_factor, 2)


def compute_forecast(
        history: List[ForecastInput],
        seasonal_threshold: float = ForecastConfig.SEASONAL_THRESHOLD,
        cv_stable_threshold: float = ForecastConfig.CV_STABLE_THRESHOLD,
        er_period: int = ForecastConfig.ER_PERIOD_BASE
) -> float:
    """
    Orchestrates the forecasting workflow without exposing sensitive financial data in logs.
    """
    if not history:
        logger.warning("Compute Forecast: Input history is empty.")
        return 0.0

    sorted_history = sorted(history, key=lambda x: x.date)
    amounts = np.array([float(x.amount) for x in sorted_history])

    # 1. Stability Check
    if is_stable_expense(amounts, cv_stable_threshold):
        logger.info("FINAL STRATEGY: FIXED (Expense is stable).")
        return round(float(amounts[-1]), 2)

    # 2. Seasonality Check
    seasonal_val = get_seasonal_forecast(amounts, seasonal_threshold)
    if seasonal_val is not None:
        logger.info("FINAL STRATEGY: SEASONAL (Recurring pattern detected).")
        return seasonal_val

    # 3. KAMA Engine
    current_er_period = max(1, min(er_period, len(amounts) - 1))
    current_kama = calculate_ama_from_history(history, er_period=current_er_period)
    logger.info(f"Adaptive Engine: Base KAMA calculated using ER period {current_er_period}.")

    # 4. Momentum Correction
    final_forecast = apply_momentum_correction(current_kama, history, current_er_period)
    logger.info("FINAL STRATEGY: IRREGULAR (KAMA + Momentum correction applied).")

    return final_forecast