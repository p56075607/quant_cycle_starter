# src/loader.py
import pandas as pd
from pathlib import Path

def load_single_csv(path: Path, value_col: str = None) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.set_index("date").sort_index()
    # 確保索引為 DatetimeIndex（移除時區資訊）
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    elif df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    if value_col is None:
        cols = [c for c in df.columns if c.lower() != "date"]
        if not cols:
            raise ValueError(f"No value column in {path}")
        value_col = cols[0]
    return df[value_col]

def load_macro(data_dir: Path) -> dict:
    # Load macro series as month-end Series.
    files = {
        "PMI": "PMI.csv",
        "INDPRO_yoy": "INDPRO_yoy.csv",
        "UNRATE_chg3m": "UNRATE_chg3m.csv",
        "TERM_10y_2y": "TERM_10y_2y.csv",
        "CreditSpread": "CreditSpread.csv",
        "SP500": "SP500.csv"
    }
    out = {}
    for k, fname in files.items():
        s = load_single_csv(data_dir / fname)
        s = s.resample("ME").last()
        out[k] = s
    return out

def load_prices(data_dir: Path, tickers: list, price_col: str = "AdjClose") -> pd.DataFrame:
    # Load ETF prices, resampled to month-end.
    frames = []
    for t in tickers:
        path = data_dir / f"{t}.csv"
        s = load_single_csv(path, value_col=price_col).resample("ME").last().rename(t)
        frames.append(s)
    df = pd.concat(frames, axis=1).dropna(how="all")
    return df