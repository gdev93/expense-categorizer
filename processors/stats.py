import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import numpy as np
import pandas as pd
from api.config import ForecastConfig

# Improved logger formatting to exclude sensitive data
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

@dataclass
class ForecastInput:
    amount: float
    date: date



def mix_with_gaps(ama_input: List[ForecastInput], window_months: int = 12) -> float:
    """
    Predicts budget based on historical patterns with a focus on
    handling occasional vs regular spending.
    """
    if not ama_input:
        return 0.0

    # 1. Setup time window
    # We use 'now' to understand if we are currently in the last month of the series
    current_time = pd.Timestamp.now().normalize()
    start_date = (current_time - pd.DateOffset(months=window_months)).replace(day=1)

    # 2. Data Preparation
    df = pd.DataFrame([{'date': x.date, 'amount': x.amount} for x in ama_input])
    df['date'] = pd.to_datetime(df['date'])

    # Filter by window
    df = df[(df['date'] >= start_date) & (df['date'] <= current_time)]

    if df.empty:
        return 0.0

    # 3. Monthly Resampling with Fixed Range
    # We create a range that includes the current month
    full_range = pd.date_range(start=start_date, end=current_time, freq='ME')
    df_indexed = df.set_index('date').sort_index()
    monthly_series = df_indexed['amount'].resample('ME').sum().reindex(full_range, fill_value=0.0)

    s = pd.Series(monthly_series)
    active_spending = s[s > 0]

    if active_spending.empty:
        return 0.0

    # 4. Feature Extraction
    gap_ratio = (s == 0).sum() / len(s)
    cv = active_spending.std() / active_spending.mean() if len(active_spending) > 1 else 0

    # Check if there is activity in the current month
    current_month_key = s.index[-1]
    is_active_this_month = s[current_month_key] > 0

    # 5. Decision Logic

    # STRATEGY A: High Gaps (Occasional spending like Car Repairs)
    if gap_ratio > 0.3:
        if is_active_this_month:
            # If we see movement this month, trigger the 75th percentile budget
            return float(active_spending.quantile(0.75))
        else:
            # If the month is silent, assume no spending is needed
            return 0.0

    # STRATEGY B: Chaotic but Regular (e.g., Groceries)
    if cv > 0.4:
        return float(active_spending.tail(4).median())

    # STRATEGY C: Stable Recurring
    else:
        return float(s.ewm(span=3).mean().iloc[-1])

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


def compute_forecast(
        history: List[ForecastInput],
        seasonal_threshold: float = ForecastConfig.SEASONAL_THRESHOLD,
        cv_stable_threshold: float = ForecastConfig.CV_STABLE_THRESHOLD,
        er_period: int = ForecastConfig.KAMA_ER_PERIOD
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

    final_forecast = mix_with_gaps(history)
    logger.info(f"FINAL STRATEGY: AGNOS (No pattern detected).")
    return final_forecast