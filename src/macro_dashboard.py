# src/macro_dashboard.py
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Serif CJK JP"

BASE = Path(__file__).resolve().parent.parent
DATA_CANDIDATES = [BASE/'data', BASE/'data'/'sample']
REPORTS = BASE/'reports'
REPORTS.mkdir(exist_ok=True, parents=True)

def pick_data_dir():
    for d in DATA_CANDIDATES:
        if d.exists():
            hits = sum((d/f).exists() for f in [
                'PMI.csv','INDPRO_yoy.csv','UNRATE_chg3m.csv',
                'TERM_10y_2y.csv','CreditSpread.csv','SP500.csv'
            ])
            if hits >= 3:
                return d
    return DATA_CANDIDATES[-1]

DATA = pick_data_dir()
print(f'[INFO] Using data dir: {DATA}')

def read_series(filename, col):
    p = DATA/filename
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=['date']).set_index('date').sort_index()
    return df[col].dropna()

PMI = read_series('PMI.csv','PMI')
INDPRO_yoy = read_series('INDPRO_yoy.csv','INDPRO_yoy')
UNRATE_chg3m = read_series('UNRATE_chg3m.csv','UNRATE_chg3m')
TERM = read_series('TERM_10y_2y.csv','TERM_10y_2y')
Credit = read_series('CreditSpread.csv','CreditSpread')
SPX = read_series('SP500.csv','AdjClose')

def zscore(s, win=36):
    return (s - s.rolling(win).mean()) / s.rolling(win).std()

eq_mom6 = SPX.pct_change(6) if len(SPX)>0 else pd.Series(dtype=float)
score = pd.concat([
    zscore(PMI),
    zscore(INDPRO_yoy),
    -zscore(UNRATE_chg3m),
    zscore(TERM),
    -zscore(Credit),
    zscore(eq_mom6)
], axis=1)
score.columns = ['PMI','INDPRO_yoy','-dUNRATE_3m','+TermSpread','-HY_OAS','+EQ_mom6']
score['Composite'] = score.mean(axis=1, skipna=True)
score = score.dropna(how='all')

chg3m = score['Composite'].diff(3)
def classify(sc, dsc):
    if pd.isna(sc) or pd.isna(dsc): return np.nan
    if sc>0 and dsc>0: return '擴張'
    if sc>0 and dsc<=0: return '放緩'
    if sc<=0 and dsc>0: return '復甦'
    return '衰退'
regime = pd.DataFrame({
    'score': score['Composite'],
    'd3': chg3m,
    'state': [classify(a,b) for a,b in zip(score['Composite'], chg3m)]
}).dropna()

def save_plot(fig, name):
    out = REPORTS/name
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out

def plot_line(s, title, ylab, hline=None, name='chart.png'):
    fig = plt.figure(figsize=(9,4))
    ax = fig.gca()
    ax.plot(s.index, s.values)
    if hline is not None:
        ax.axhline(hline, linestyle='--')
    ax.set_title(title)
    ax.set_ylabel(ylab)
    return save_plot(fig, name)

files = []
if len(PMI): files.append(plot_line(PMI, 'ISM 製造業 PMI（>50 擴張）', 'PMI', 50, 'pmi.png'))
if len(INDPRO_yoy): files.append(plot_line(INDPRO_yoy, '工業生產 年增率（YoY）', '%', 0, 'indpro_yoy.png'))
if len(UNRATE_chg3m): files.append(plot_line(UNRATE_chg3m, '失業率 3個月變化（上升為景氣轉弱訊號）', 'ppt', 0, 'unrate_chg3m.png'))
if len(TERM): files.append(plot_line(TERM, '殖利率期限利差（10Y-2Y）', '百分點', 0, 'term_spread.png'))
if len(Credit): files.append(plot_line(Credit, '高收益債 OAS（信用利差，越高越緊張）', '%', None, 'hy_oas.png'))

if len(SPX):
    fig = plt.figure(figsize=(9,4))
    ax = fig.gca()
    ax.plot(SPX.index, SPX.values)
    ax.set_title('S&P 500 指數（月收）')
    ax.set_ylabel('Index')
    files.append(save_plot(fig, 'spx.png'))

if len(score):
    fig = plt.figure(figsize=(9,4))
    ax = fig.gca()
    ax.plot(score.index, score['Composite'].values)
    ax.axhline(0, linestyle='--')
    ax.set_title('景氣綜合分數（z-score 平均）')
    ax.set_ylabel('z')
    files.append(save_plot(fig, 'composite.png'))

def latest(s): 
    return (s.index[-1], float(s.iloc[-1])) if len(s)>0 else (None, None)
def fmt_dt(dt): 
    return dt.strftime('%Y-%m') if isinstance(dt, pd.Timestamp) else 'n/a'

lines = ['# 宏觀儀表板（依你目前資料）', '']
for name, s, meta in [
    ('PMI', PMI, '(>50 擴張)'),
    ('工業生產 YoY', INDPRO_yoy, ''),
    ('失業率 Δ3m', UNRATE_chg3m, '(正值=轉弱)'),
    ('10Y-2Y 利差', TERM, ''),
    ('HY OAS', Credit, '(越高越緊張)'),
    ('S&P 500', SPX, ''),
]:
    dt, val = latest(s)
    if val is not None:
        lines.append(f'- {name} 最新（{fmt_dt(dt)}）：{val:.2f} {meta}')

if len(regime):
    recent = regime.iloc[-24:]['state'].value_counts().to_dict()
    lines.append('')
    lines.append(f'- 近24個月景氣狀態分布：{recent}')

(REPORTS/'macro_readout.md').write_text('\n'.join(lines), encoding='utf-8')
print('[DONE] Charts written to:', REPORTS)
print('Files:', [p.name for p in REPORTS.iterdir()])
