# run_first_backtest.py
import pandas as pd
import yaml
from pathlib import Path
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Noto Serif CJK JP"

from src.loader import load_macro, load_prices
from src.regime import composite_score, classify
from src.backtest import backtest

BASE = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "PMI.csv",
    "INDPRO_yoy.csv",
    "UNRATE_chg3m.csv",
    "TERM_10y_2y.csv",
    "CreditSpread.csv",
    "SP500.csv",
]

def pick_data_dir():
    # Prefer official data/, fallback to data/sample/
    candidates = [BASE/"data", BASE/"data"/"sample"]
    for c in candidates:
        if c.exists():
            # check if has enough macro files
            hits = sum((c/f).exists() for f in REQUIRED_FILES)
            if hits >= 3:   # allow partial; composite_score can still work if some present
                return c
    # default fallback
    return BASE/"data"/"sample"

def main():
    cfg = yaml.safe_load((BASE/"config.yaml").read_text(encoding="utf-8"))
    DATA = pick_data_dir()
    print(f"[INFO] Using data directory: {DATA}")

    # 1) Load macro & prices
    macros = load_macro(DATA)
    prices = load_prices(DATA, tickers=list(set(cfg["core_universe"])), price_col=cfg.get("price_column","AdjClose"))

    # 2) Compute regime (lag to next month to avoid look-ahead)
    score = composite_score(macros)
    regime = classify(score)
    regime.index = regime.index + pd.offsets.MonthBegin(1)
    regime = regime.loc[prices.index.min(): prices.index.max()]

    # 3) Backtest
    res = backtest(
        prices=prices,
        regime_df=regime,
        weight_map=cfg["weights"],
        universe=list(set(cfg["core_universe"])),
        cost_bp=cfg.get("transaction_cost_bp", 0.0),
        leverage_cfg=cfg.get("leverage", None)
    )

    # 4) Save reports
    out_dir = BASE / "reports"
    out_dir.mkdir(exist_ok=True, parents=True)
    regime.to_csv(out_dir/"regime_timeline.csv", encoding="utf-8")
    pd.Series(res["summary"]).to_csv(out_dir/"perf_summary.csv", header=False)
    res["equity"].to_csv(out_dir/"equity_curve.csv")

    # 5) Plot equity curve (single chart)
    eq = res["equity"]
    dd = (eq/eq.cummax()) - 1.0

    fig = plt.figure(figsize=(10,5))
    ax = fig.gca()
    ax.plot(eq.index, eq.values, label="權益曲線")
    ax.fill_between(dd.index, eq.min(), eq.values, where=(dd<0), alpha=0.15, label="回撤區間")
    label_dir = "data" if "data/sample" not in str(DATA) else "sample"
    ax.set_title(f"景氣週期投資 — 權益曲線（資料來源：{label_dir}）")
    ax.set_ylabel("累積淨值（起始=1）")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir/"equity_curve.png", dpi=140)
    plt.close(fig)

    print("Done. Reports saved to:", out_dir)

if __name__ == "__main__":
    main()
