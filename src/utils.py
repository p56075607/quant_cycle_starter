# src/utils.py
import pandas as pd
import numpy as np

def to_month_end(s: pd.Series) -> pd.Series:
    # Align a Series to month-end by resampling and taking last valid observation.
    if isinstance(s.index, pd.DatetimeIndex):
        return s.resample("ME").last()
    raise ValueError("Index must be DatetimeIndex.")

def zscore(s: pd.Series, win: int = 36) -> pd.Series:
    m = s.rolling(win).mean()
    sd = s.rolling(win).std()
    return (s - m) / sd

def annualize_vol(monthly_ret: pd.Series) -> float:
    # Monthly returns standard deviation * sqrt(12)
    return float(monthly_ret.std(ddof=0) * np.sqrt(12))

def drawdown_series(curve: pd.Series) -> pd.Series:
    # Compute drawdown series given an equity curve.
    peak = curve.cummax()
    dd = (curve / peak) - 1.0
    return dd

def performance_summary(curve: pd.Series) -> dict:
    ret = curve.pct_change().dropna()
    if ret.empty:
        return {"CAGR": 0.0, "Vol": 0.0, "Sharpe": 0.0, "MDD": 0.0, "Calmar": 0.0}
    # CAGR
    n_years = (curve.index[-1] - curve.index[0]).days / 365.25
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1/n_years) - 1 if n_years > 0 else 0.0
    vol = annualize_vol(ret)
    sharpe = (ret.mean()*12) / vol if vol > 1e-9 else 0.0
    dd = drawdown_series(curve)
    mdd = dd.min()
    calmar = (ret.mean()*12) / abs(mdd) if mdd < 0 else 0.0
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MDD": mdd, "Calmar": calmar}