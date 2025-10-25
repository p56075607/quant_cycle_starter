
# src/analyze_macro.py
from pathlib import Path
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Serif CJK JP"

# 將專案根目錄加入 sys.path，讓 import src.xxx 能正常運作
BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from src.loader import load_macro, load_prices
from src.regime import composite_score, classify

REPORTS = BASE / "reports"

REQUIRED_FILES = ["PMI.csv","INDPRO_yoy.csv","UNRATE_chg3m.csv","TERM_10y_2y.csv","CreditSpread.csv","SP500.csv"]

def pick_data_dir() -> Path:
    for c in [BASE/"data", BASE/"data"/"sample"]:
        if c.exists():
            hits = sum((c/f).exists() for f in REQUIRED_FILES)
            if hits >= 3:
                return c
    return BASE/"data"/"sample"

def pick_index_series(data_dir: Path) -> tuple[str, pd.Series]:
    candidates = [
        ("SP500","SP500.csv"),
        ("VT","VT.csv"),
        ("VTI","VTI.csv"),
        ("QQQ","QQQ.csv"),
        ("TAIEX","TAIEX.csv"),
        ("TW50","0050.TW.csv"),
    ]
    for name, fname in candidates:
        p = data_dir / fname
        if p.exists():
            df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
            col = "AdjClose" if "AdjClose" in df.columns else df.columns[-1]
            s = df[col].rename(name)
            return name, s
    for p in data_dir.glob("*.csv"):
        try:
            df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
            if "AdjClose" in df.columns:
                return p.stem, df["AdjClose"].rename(p.stem)
        except Exception:
            pass
    raise FileNotFoundError("No index price CSV found.")

def to_month_end(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    s = s.resample("ME").last()  # ME = Month End (替代已棄用的 'M')
    s.index.name = "date"
    return s

ANNOTATED_PERIODS = [
    ("2020-01-01","2020-03-31","2020Q1 高位轉衰退／系統性崩盤\n高位調節→低位重倉"),
    ("2020-04-01","2020-06-30","2020Q2 觸底復甦初期\n停止建倉、黃金配置"),
    ("2020-07-01","2020-12-31","2020Q3-4 庫存回補／擴張\n逢高調節、輪動大宗/金融"),
    ("2021-01-01","2021-03-31","2021Q1 繁榮頂／擴張尾聲\n出清權值、利率上行"),
    ("2021-04-01","2021-09-30","2021Q2-3 高位盤整／中期回檔\n科技布局、逢急跌加碼"),
    ("2021-10-01","2021-12-31","2021Q4 牛市延續／高基期修整\n極度貪婪、科技回檔加碼"),
    ("2022-01-01","2022-03-31","2022Q1 去估值年／熊市初期\n科技估值殺、烏俄衝擊"),
    ("2022-04-01","2022-06-30","2022Q2 主跌段／庫存下行\n加速布局科技、建倉長債"),
    ("2022-07-01","2022-09-30","2022Q3 末跌段／打底\n原油反向、逢破底續買"),
    ("2022-10-01","2022-12-31","2022Q4 慣性反彈／熊市尾聲\n逢高調節、長債續佈局"),
    ("2023-01-01","2023-03-31","2023Q1 熊市反彈／復甦初期\n保守持有、等待回調"),
    ("2023-04-01","2023-09-30","2023Q2-3 擴張／中期回調\nAI 推升估值，回調加碼"),
    ("2023-10-01","2023-12-31","2023Q4 擴張確認／高位震盪\n維持部位、提現金"),
    ("2024-01-01","2024-09-30","2024Q1-3 擴張／外部衝擊\n4月系統性拋售→抄底"),
    ("2024-10-01","2025-09-30","2024Q4-2025Q3 高位／繁榮預期\n拉高現金、降槓桿"),
]

def draw_quarterly_backgrounds(ax, xmin, xmax):
    """繪製季度背景色塊（Q1-Q4 使用不同顏色）"""
    # 定義每個季度的顏色（淡色系）
    quarter_colors = {
        1: '#E8F4F8',  # Q1 淺藍色
        2: '#E8F8E8',  # Q2 淺綠色
        3: '#FFF8E8',  # Q3 淺黃色
        4: '#F8E8F8',  # Q4 淺紫色
    }
    
    xmin = pd.to_datetime(xmin)
    xmax = pd.to_datetime(xmax)
    
    # 確定起始年份和結束年份
    start_year = xmin.year
    end_year = xmax.year
    
    for year in range(start_year, end_year + 1):
        for quarter in range(1, 5):
            # 計算季度起止日期
            q_start = pd.Timestamp(f'{year}-{(quarter-1)*3+1:02d}-01')
            if quarter < 4:
                q_end = pd.Timestamp(f'{year}-{quarter*3+1:02d}-01')
            else:
                q_end = pd.Timestamp(f'{year+1}-01-01')
            
            # 只繪製在可見範圍內的季度
            if q_end < xmin or q_start > xmax:
                continue
            
            # 調整邊界以符合可見範圍
            plot_start = max(q_start, xmin)
            plot_end = min(q_end, xmax)
            
            # 繪製季度背景
            ax.axvspan(plot_start, plot_end, 
                      facecolor=quarter_colors[quarter], 
                      alpha=0.3, 
                      zorder=0, 
                      edgecolor='none')
            
            # 在季度中間添加垂直分隔線（除了第一個季度的起始線）
            if q_start >= xmin:
                ax.axvline(q_start, color='gray', linestyle=':', 
                          linewidth=0.8, alpha=0.5, zorder=1)

def draw_regime_spans(ax, regime_df: pd.DataFrame):
    if regime_df.empty: return
    reg = regime_df["state"].dropna()
    if reg.empty: return
    start = None; last_state = None
    for dt, st in reg.items():
        if start is None:
            start = dt; last_state = st; continue
        if st != last_state:
            ax.axvspan(start, dt, alpha=0.08, zorder=2)
            start = dt; last_state = st
    ax.axvspan(start, reg.index[-1], alpha=0.08, zorder=2)

def draw_user_annotations(ax, xmin, xmax):
    """在圖表上標註週期區段，文字交替上下排列避免重疊"""
    ymin, ymax = ax.get_ylim()
    y_range = ymax - ymin
    # 三個高度位置交替使用，給文字更多空間
    positions = [
        ymax - 0.02 * y_range,  # 最上方
        ymax - 0.12 * y_range,  # 中上
        ymax - 0.22 * y_range   # 中間
    ]
    
    visible_periods = [(s, e, label) for s, e, label in ANNOTATED_PERIODS 
                       if pd.to_datetime(e) >= xmin and pd.to_datetime(s) <= xmax]
    
    for idx, (s, e, label) in enumerate(visible_periods):
        sdt = pd.to_datetime(s)
        edt = pd.to_datetime(e)
        mid = sdt + (edt - sdt) / 2
        
        # 背景色塊
        ax.axvspan(sdt, edt, alpha=0.08, color='lightblue', lw=0, zorder=2)
        
        # 簡化標籤：只取第一行（期間標註）
        short_label = label.split('\n')[0]
        
        # 交替使用三個高度位置
        y_pos = positions[idx % 3]
        
        # 文字置於區段中央（最上層）
        ax.text(mid, y_pos, short_label, 
                ha='center', va='top', 
                fontsize=7.5, 
                bbox=dict(boxstyle='round,pad=0.3', 
                         facecolor='white', 
                         alpha=0.85, 
                         edgecolor='gray',
                         linewidth=0.5),
                zorder=10)

def plot_composite(score: pd.Series, regime_df: pd.DataFrame, out_png: Path):
    fig = plt.figure(figsize=(18,7))  # 加寬加高圖表
    ax = fig.gca()
    
    # 先繪製季度背景（最底層）
    draw_quarterly_backgrounds(ax, score.index.min(), score.index.max())
    
    # 繪製主要內容
    line = ax.plot(score.index, score.values, label="綜合景氣分數", linewidth=1.8, color='#2E86AB', zorder=5)[0]
    ax.axhline(0, color='gray', linestyle='--', alpha=0.5, linewidth=1, zorder=3)
    draw_regime_spans(ax, regime_df)
    draw_user_annotations(ax, score.index.min(), score.index.max())
    
    ax.set_title("景氣綜合分數 × 週期狀態 × 實戰註記（2020–2025）｜背景色：Q1藍/Q2綠/Q3黃/Q4紫", fontsize=13, pad=20)
    ax.set_xlabel("日期", fontsize=11)
    ax.set_ylabel("綜合分數 (z-score)", fontsize=11)
    ax.legend([line], ["綜合景氣分數 (z-score)"], loc='lower left', fontsize=10)
    ax.grid(True, alpha=0.15, linestyle=':', linewidth=0.5, zorder=1)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches='tight')
    plt.close(fig)

def plot_index_with_regime(price: pd.Series, regime_df: pd.DataFrame, out_png: Path):
    px = to_month_end(price)
    
    # 將 regime 索引也轉換為月末以便對齊
    regime_me = regime_df.copy()
    regime_me.index = regime_me.index + pd.offsets.MonthEnd(0)
    
    # 對齊索引
    idx = px.index.intersection(regime_me.index)
    if len(idx) == 0:
        print(f"[WARNING] No overlapping dates between price and regime data for plotting")
        return
    
    px = px.loc[idx]
    regime_me = regime_me.loc[idx]
    
    fig = plt.figure(figsize=(18,7))  # 加寬加高圖表
    ax = fig.gca()
    
    # 先繪製季度背景（最底層）
    draw_quarterly_backgrounds(ax, px.index.min(), px.index.max())
    
    # 繪製主要內容
    line = ax.plot(px.index, px.values, label=f"{px.name}（月末）", linewidth=1.8, color='#A23B72', zorder=5)[0]
    draw_regime_spans(ax, regime_me)
    draw_user_annotations(ax, px.index.min(), px.index.max())
    
    ax.set_title(f"{px.name} × 景氣週期 × 實戰註記（2020–2025）｜背景色：Q1藍/Q2綠/Q3黃/Q4紫", fontsize=13, pad=20)
    ax.set_xlabel("日期", fontsize=11)
    ax.set_ylabel("指數價格", fontsize=11)
    ax.legend([line], [f"{px.name}（月末）"], loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.15, linestyle=':', linewidth=0.5, zorder=1)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches='tight')
    plt.close(fig)

def plot_zscore_heatmap(macros: dict, out_png: Path, last_n_months: int = 60):
    series = {}
    for k in ["PMI","INDPRO_yoy","UNRATE_chg3m","TERM_10y_2y","CreditSpread"]:
        if k in macros and macros[k] is not None:
            s = macros[k].copy()
            s = to_month_end(s)
            if s.dropna().empty: continue
            z = (s - s.rolling(36).mean())/s.rolling(36).std()
            series[k] = z
    if not series: return
    Z = pd.concat(series, axis=1).dropna().tail(last_n_months)

    fig = plt.figure(figsize=(10,6))
    ax = fig.gca()
    im = ax.imshow(Z.values, aspect="auto", origin="lower")
    ax.set_yticks(range(len(Z.index)))
    ax.set_yticklabels([d.strftime("%Y-%m") for d in Z.index])
    ax.set_xticks(range(len(Z.columns)))
    ax.set_xticklabels(list(Z.columns), rotation=45, ha="right")
    ax.set_title("主要宏觀指標標準化熱圖（近年）")
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)

def plot_returns_by_regime(price: pd.Series, regime_df: pd.DataFrame, out_png: Path, out_csv: Path):
    px = to_month_end(price)
    ret = px.pct_change().dropna()
    
    # 將 regime 索引也轉換為月末以便對齊
    regime_me = regime_df.copy()
    regime_me.index = regime_me.index + pd.offsets.MonthEnd(0)
    
    reg = regime_me["state"].reindex(ret.index).dropna()
    aligned = pd.concat([ret, reg], axis=1).dropna()
    aligned.columns = ["ret","state"]
    avg = aligned.groupby("state")["ret"].mean().sort_index()
    avg.to_csv(out_csv, header=["avg_monthly_return"])

    fig = plt.figure(figsize=(8,5))
    ax = fig.gca()
    ax.bar(avg.index, avg.values)
    ax.set_title(f"{price.name}：不同景氣狀態的平均月報酬")
    ax.set_ylabel("平均月報酬率")
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)

def main():
    REPORTS.mkdir(exist_ok=True, parents=True)
    data_dir = pick_data_dir()
    print(f"[INFO] Using data directory: {data_dir}")

    macros = load_macro(data_dir)
    idx_name, idx_price = pick_index_series(data_dir)

    score = composite_score(macros)
    regime = classify(score)
    regime.index = regime.index + pd.offsets.MonthBegin(1)

    common_min = max(score.index.min(), idx_price.index.min())
    common_max = min(score.index.max(), idx_price.index.max())
    regime = regime.loc[common_min:common_max]
    score = score.loc[common_min:common_max]

    plot_composite(score, regime, REPORTS/"macro_composite_shaded.png")
    plot_index_with_regime(idx_price.rename(idx_name), regime, REPORTS/"index_with_regime.png")
    plot_zscore_heatmap(macros, REPORTS/"zscore_heatmap.png")
    plot_returns_by_regime(idx_price.rename(idx_name), regime, REPORTS/"returns_by_regime.png", REPORTS/"returns_by_regime.csv")

    latest_state = regime["state"].dropna().iloc[-1] if not regime.empty else "N/A"
    with open(REPORTS/"regime_snapshot.txt","w",encoding="utf-8") as f:
        f.write(f"資料區間：{common_min.date()} ~ {common_max.date()}\n")
        f.write(f"指數：{idx_name}\n")
        f.write(f"最新景氣位階（composite_score）：{latest_state}\n")

    print("[DONE] 圖表與表格已輸出到 reports/:\n - macro_composite_shaded.png\n - index_with_regime.png\n - zscore_heatmap.png\n - returns_by_regime.png, returns_by_regime.csv\n - regime_snapshot.txt")

if __name__ == "__main__":
    main()
