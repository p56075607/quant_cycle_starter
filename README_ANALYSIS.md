
# 宏觀週期分析（自動繪圖與位階判讀）

## 使用方式

把這個包放進你的 repo 後，從**專案根目錄**執行：

```bash
python src/analyze_macro.py
```

或者使用 Python 模組方式執行：

```bash
python -m src.analyze_macro
```

## 功能說明

執行後會：
- 自動偵測正式 `data/`（找不到才退到 `data/sample/`）
- 載入宏觀指標（PMI、INDPRO_yoy、UNRATE_chg3m、10y-2y、HY OAS、SP500）
- 計算景氣綜合分數與週期位階（使用你的 `src/regime.py`）
- 依你提供的 2020–2025 實戰脈絡畫上區段註記
- 匯出四張圖 + 一份 regime 摘要到 `reports/`

## 輸出檔案

- `macro_composite_shaded.png` - 景氣綜合分數與週期狀態
- `index_with_regime.png` - 指數價格與景氣週期
- `zscore_heatmap.png` - 主要宏觀指標標準化熱圖
- `returns_by_regime.png` / `returns_by_regime.csv` - 不同景氣狀態下的平均報酬
- `regime_snapshot.txt` - 當前景氣位階摘要

## 自訂說明

你可以在 `src/analyze_macro.py` 內的 `ANNOTATED_PERIODS` 修改每段日期/標籤。
