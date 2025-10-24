# fetch_data.py 使用說明（快速）

## 1) 安裝依賴（建議在原環境中補裝）：
pip install -r requirements_fetch.txt

## 2) 設定環境變數（FRED 需要 API Key）：
# macOS/Linux
export FRED_API_KEY=fe115f91d11284b243402cae0e3b365e

# Windows (PowerShell)
setx FRED_API_KEY fe115f91d11284b243402cae0e3b365e

金鑰申請：https://fred.stlouisfed.org/docs/api/api_key.html

## 3) 執行
python src/fetch_data.py

## 4) 產出位置
data/sample/*.csv   與  reports/*.csv

產出對 starter 的核心檔：
- PMI.csv（欄: PMI）
- INDPRO_yoy.csv（欄: INDPRO_yoy）
- UNRATE_chg3m.csv（欄: UNRATE_chg3m）
- TERM_10y_2y.csv（欄: TERM_10y_2y）
- CreditSpread.csv（欄: CreditSpread）
- SP500.csv（欄: AdjClose）
