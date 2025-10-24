# run_first_backtest.py
import pandas as pd
import yaml
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib as mpl

# 設定支援繁體中文的字體（Windows 系統內建）
mpl.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
mpl.rcParams['axes.unicode_minus'] = False  # 解決負號顯示問題

from src.loader import load_macro, load_prices
from src.regime import composite_score, classify
from src.backtest import backtest

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "sample"

def main():
    cfg = yaml.safe_load((BASE/"config.yaml").read_text(encoding="utf-8"))
    macros = load_macro(DATA)
    prices = load_prices(DATA, tickers=list(set(cfg["core_universe"])), price_col=cfg.get("price_column","AdjClose"))

    score = composite_score(macros)
    regime = classify(score)
    regime.index = regime.index + pd.offsets.MonthBegin(1)  # next month effect
    regime = regime.loc[prices.index.min(): prices.index.max()]

    res = backtest(
        prices=prices,
        regime_df=regime,
        weight_map=cfg["weights"],
        universe=list(set(cfg["core_universe"])),
        cost_bp=cfg.get("transaction_cost_bp", 0.0),
        leverage_cfg=cfg.get("leverage", None)
    )

    out_dir = BASE / "reports"
    out_dir.mkdir(exist_ok=True, parents=True)
    regime.to_csv(out_dir/"regime_timeline.csv", encoding="utf-8")
    pd.Series(res["summary"]).to_csv(out_dir/"perf_summary.csv", header=False)
    res["equity"].to_csv(out_dir/"equity_curve.csv")

    # Plot equity curve (single chart, no seaborn, no styles)
    eq = res["equity"]
    dd = (eq/eq.cummax()) - 1.0

    fig = plt.figure(figsize=(10,5))
    ax = fig.gca()
    ax.plot(eq.index, eq.values, label="權益曲線")
    # Shade drawdown periods by using min value baseline
    ax.fill_between(dd.index, eq.min(), eq.values, where=(dd<0), alpha=0.15, label="回撤區間")
    ax.set_title("景氣週期投資（示例資料）— 權益曲線")
    ax.set_ylabel("累積淨值（起始=1）")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir/"equity_curve.png", dpi=140)

    print("Done. Reports saved to:", out_dir)

if __name__ == "__main__":
    main()