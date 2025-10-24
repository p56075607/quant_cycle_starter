# src/backtest.py
import pandas as pd
import numpy as np
from .utils import annualize_vol, performance_summary

def map_weights(regime_df: pd.DataFrame, weight_map: dict, universe: list) -> pd.DataFrame:
    # Map regime state to weight vector (sum to 1). Missing assets get 0.
    frames = []
    for dt, row in regime_df.iterrows():
        state = row["state"]
        w = {k:0.0 for k in universe}
        w.update(weight_map.get(state, {}))
        s = pd.Series(w, name=dt)
        s = s / s.sum() if s.sum() > 0 else s
        frames.append(s)
    W = pd.DataFrame(frames).sort_index()
    return W

def monthly_returns_from_prices(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.resample("ME").last().pct_change().dropna(how="all")

def apply_transaction_costs(weights: pd.DataFrame, cost_bp: float = 0.0) -> pd.Series:
    # Return monthly cost series (negative) as turnover * cost per month.
    if weights.empty or cost_bp <= 0:
        return pd.Series(0.0, index=weights.index)
    turnover = weights.diff().abs().sum(axis=1).fillna(0)  # L1 turnover
    cost = - turnover * (cost_bp / 10000.0)
    return cost

def leverage_series(port_ret: pd.Series, target_vol: float, lookback_months: int, L_min: float, L_max: float) -> pd.Series:
    L = pd.Series(index=port_ret.index, dtype=float)
    for i, dt in enumerate(port_ret.index):
        # realized vol from past lookback_months (exclude current month)
        if i == 0:
            L.iloc[i] = 1.0
            continue
        lb_start = max(0, i - lookback_months)
        hist = port_ret.iloc[lb_start:i]
        vol = annualize_vol(hist) if len(hist) > 1 else np.nan
        if not np.isfinite(vol) or vol < 1e-6:
            L.iloc[i] = 1.0
        else:
            raw = target_vol / vol
            L.iloc[i] = min(max(L_min, raw), L_max)
    L = L.fillna(1.0)
    return L

def backtest(prices: pd.DataFrame, regime_df: pd.DataFrame, weight_map: dict, universe: list,
             cost_bp: float = 0.0, leverage_cfg: dict | None = None) -> dict:
    # 1) monthly rets
    rets = monthly_returns_from_prices(prices)
    idx = rets.index.intersection(regime_df.index)
    rets = rets.loc[idx]
    reg = regime_df.loc[idx]

    # 2) weights per regime (rebalance monthly)
    W = map_weights(reg, weight_map, universe).loc[idx]
    W = W.reindex(columns=rets.columns, fill_value=0.0)

    # 3) portfolio returns before leverage & costs
    port_ret = (W * rets).sum(axis=1)

    # 4) leverage wrapper
    L = pd.Series(1.0, index=port_ret.index)
    if leverage_cfg and leverage_cfg.get("use", False):
        L = leverage_series(
            port_ret,
            target_vol=leverage_cfg.get("target_vol", 0.12),
            lookback_months=leverage_cfg.get("lookback_months", 12),
            L_min=leverage_cfg.get("L_min", 0.8),
            L_max=leverage_cfg.get("L_max", 1.5),
        )
    port_ret_L = port_ret * L

    # 5) transaction costs (based on weight changes)
    cost = apply_transaction_costs(W, cost_bp=cost_bp)

    # 6) equity curve
    eq = (1 + (port_ret_L + cost)).cumprod()

    # Summary
    summ = performance_summary(eq)

    return {"weights": W, "rets": port_ret, "L": L, "rets_levered": port_ret_L, "cost": cost, "equity": eq, "summary": summ}