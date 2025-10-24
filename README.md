# Quant Cycle Starter (from zero)

本專案提供「景氣/週期 投資 + 適度槓桿 + 長期持有」的 **最小可行樣板**，使用 Python 完成：
1. 載入宏觀與資產資料（目前內建**合成示例資料**，方便你先跑通流程）。
2. 計算景氣綜合分數與四象限狀態（復甦/擴張/放緩/衰退）。
3. 依狀態映射權重，月度再平衡，套用簡化的目標波動槓桿。
4. 產出績效摘要與資產曲線圖。

> ⚠️ 本樣板僅供教育與研究，不構成投資建議。請用你自己的真實資料替換 `data/sample/` 內檔案。

## 0. 安裝環境
```bash
conda env create -f environment.yml
conda activate quant-cycle
```

## 1. 快速執行
```bash
python run_first_backtest.py
```
輸出：
- `reports/regime_timeline.csv`：每月景氣狀態
- `reports/perf_summary.csv`：績效指標（CAGR/Sharpe/MDD/Calmar）
- `reports/equity_curve.png`：權益曲線（含回撤陰影）

## 2. 替換為真實資料
將你的**月度**資料（宏觀、ETF 價格）替換/覆蓋到 `data/` 目錄：
- 宏觀檔案（CSV, 月底對齊）：`PMI.csv`, `INDPRO_yoy.csv`, `UNRATE_chg3m.csv`, `TERM_10y_2y.csv`, `CreditSpread.csv`, `SP500.csv`
- 資產價格（CSV）：`VT.csv`, `IEF.csv`, `GLD.csv`, `IWM.csv`, `QUAL.csv`, `USMV.csv`, `MTUM.csv`, `TLT.csv`, `DBC.csv`（可只用子集）

每個 CSV 至少要有：
- `date` 欄（可被 `parse_dates`），
- 一個數值欄（如 `AdjClose` 或指標欄名）。

## 3. 調整策略
- 權重映射、再平衡、槓桿上限等參數，見 `config.yaml`。
- 欲增加指標：在 `src/regime.py` 擴充綜合分數計法。
- 欲改回測框架：替換 `src/backtest.py` 或串接 `vectorbt`/`bt` 等。

## 4. 重要注意
- 資料落後：回測時，**用下月初生效**的指標（檔案已內建處理）。
- 禁止未來資訊洩漏、請留意交易成本、稅務、滑價與流動性。
- 槓桿 ETF 存在路徑依賴與追蹤誤差，長持須特別測試。