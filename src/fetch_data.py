
"""
fetch_data.py
--------------
一鍵抓取「景氣/週期」回測所需的核心指標 + 常用補充指標，並輸出到 data/sample/。
預設使用 FRED + yfinance + 世界銀行 +（可選）台灣中央銀行(CBC) API。

使用前準備：
1) 安裝套件：
   pip install fredapi yfinance pandas pandas-datareader pandasdmx requests python-dateutil

2) 設定環境變數：
   - FRED_API_KEY=<你的FRED金鑰>  （https://fred.stlouisfed.org/docs/api/api_key.html）

執行：
   python src/fetch_data.py

輸出（核心，與 starter 專案對上）：
   data/sample/PMI.csv                # 欄: date, PMI                  -> 來源: FRED: NAPM（ISM製造業PMI）
   data/sample/INDPRO_yoy.csv         # 欄: date, INDPRO_yoy           -> 來源: FRED: INDPRO（年增率計算）
   data/sample/UNRATE_chg3m.csv       # 欄: date, UNRATE_chg3m         -> 來源: FRED: UNRATE（三個月變化）
   data/sample/TERM_10y_2y.csv        # 欄: date, TERM_10y_2y          -> 來源: FRED: DGS10 - DGS2
   data/sample/CreditSpread.csv       # 欄: date, CreditSpread         -> 來源: FRED: BAMLH0A0HYM2（HY OAS）
   data/sample/SP500.csv              # 欄: date, AdjClose             -> 來源: FRED: SP500（價位）

   （選配）ETF 價格：VT、IEF、GLD、IWM、TLT、DBC -> data/sample/<TICKER>.csv（欄: date, AdjClose）

附加：
   reports/data_sources.csv           # 指標對應來源與系列代碼一覽（你可以打開檢查/擴充）

注意：
- 本腳本會把高頻日資料轉成「月底月頻」以避免前視偏誤；並對宏觀指標採「上月→下月初生效」的自然滯後（你也可以在回測層控制）。
- 若你在台灣資料想接 CBC（M1B/M2等），請填入 CBC_ITEMS 內的代碼（預設示範 'EF21M01en' = Factors responsible for changes in M2, Monthly）。
"""

import os
import sys
import io
import json
import time
import math
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

# 可選: fredapi / yfinance
try:
    from fredapi import Fred
except Exception as e:
    Fred = None

try:
    import yfinance as yf
except Exception as e:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ========== 指標對應表（主項 + 系列代碼/來源） ==========
INDICATORS = [
    # 回測核心 ─ 與 starter 專案欄位/檔名一致
    {"name":"PMI",            "source":"FRED", "series_id":"MANEMP",          "notes":"ISM Manufacturing PMI (MANEMP, formerly NAPM)"},
    {"name":"INDPRO_yoy",     "source":"FRED", "series_id":"INDPRO",          "notes":"工業生產指數→年增率"},  # 計算
    {"name":"UNRATE_chg3m",   "source":"FRED", "series_id":"UNRATE",          "notes":"失業率→近三個月變化"},  # 計算
    {"name":"TERM_10y_2y",    "source":"FRED", "series_id":"DGS10-DGS2",      "notes":"10Y-2Y 期限利差（DGS10 - DGS2）"},  # 計算
    {"name":"CreditSpread",   "source":"FRED", "series_id":"BAMLH0A0HYM2",    "notes":"ICE BofA US High Yield OAS"},
    {"name":"SP500",          "source":"FRED", "series_id":"SP500",           "notes":"標普500（價位）"},

    # 附加（常用）：可自由擴充
    {"name":"CPI_US_yoy",     "source":"FRED", "series_id":"CPIAUCSL",        "notes":"美國CPI YoY（由月度CPI計算年增率）"},
    {"name":"FEDFUNDS",       "source":"FRED", "series_id":"FEDFUNDS",        "notes":"聯邦基金有效利率（EFFECTIVE）"},
    {"name":"M2SL_yoy",       "source":"FRED", "series_id":"M2SL",            "notes":"美國M2年增率（由M2SL計算）"},

    # 世界銀行（年頻，做視角輔助，不進回測核心）
    {"name":"WB_WLD_GDP_yoy","source":"WB",   "series_id":"NY.GDP.MKTP.KD.ZG","notes":"世界 GDP 成長率（WLD）"},
    {"name":"WB_WLD_CPI_yoy","source":"WB",   "series_id":"FP.CPI.TOTL.ZG",   "notes":"世界 CPI 年增率（WLD）"},
]

# 台灣 CBC API（選配）：項目代碼清單（可自行擴充/改為其他 M1B/M2等表）
CBC_ITEMS = [
    # 'EF21M01en',  # Factors responsible for changes in Monetary Aggregate M2, Monthly（英文代碼；結構需自行展開欄位）
]

ETF_TICKERS = ["VT", "IEF", "GLD", "IWM", "TLT", "DBC"]

# ========== 小工具 ==========
def month_end(s: pd.Series) -> pd.Series:
    """轉月底月頻；若原本就是月頻也會對齊月底"""
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    s = s.resample("ME").last()
    s.index.name = "date"
    return s

def pct_change_yoy(s: pd.Series) -> pd.Series:
    s = month_end(s)
    return (s / s.shift(12) - 1.0) * 100.0

def diff_3m(s: pd.Series) -> pd.Series:
    s = month_end(s)
    return s - s.shift(3)

def save_two_col_csv(path: str, name: str, series: pd.Series):
    df = series.to_frame(name)
    df.index.name = "date"
    df.reset_index().to_csv(path, index=False, encoding="utf-8")
    print(f"[OK] {path} -> {len(df)} rows")

def _fred_client() -> Optional["Fred"]:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        print("[WARN] FRED_API_KEY 未設定，fredapi 需要金鑰。請至 https://fred.stlouisfed.org/docs/api/api_key.html 申請並設為環境變數。")
        return None
    if Fred is None:
        print("[ERROR] 未安裝 fredapi，請先 pip install fredapi")
        return None
    return Fred(api_key=api_key)

def fetch_fred_series(series_id: str) -> pd.Series:
    fred = _fred_client()
    if fred is None:
        raise RuntimeError("FRED client 未就緒")
    return fred.get_series(series_id)

def fetch_world_bank_series(indicator: str, country: str="WLD") -> pd.Series:
    # World Bank API: https://api.worldbank.org/v2/country/WLD/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=20000
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    r = requests.get(url, params={"format":"json","per_page":20000}, timeout=30)
    r.raise_for_status()
    j = r.json()
    data = j[1]
    df = pd.DataFrame(data)[["date","value"]].dropna()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    s = df["value"].astype(float)
    s.index.name = "date"
    return s

def fetch_cbc_item(item_code: str) -> pd.DataFrame:
    """央行統計資料庫 API： https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=<ItemCode>"""
    url = "https://cpx.cbc.gov.tw/API/DataAPI/Get"
    r = requests.get(url, params={"FileName": item_code}, timeout=60)
    r.raise_for_status()
    j = r.json()
    raw_path = os.path.join(REPORTS_DIR, f"CBC_{item_code}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 CBC 原始 JSON -> {raw_path}")

    ds = j.get("DataSet", {})
    tables = ds.get("diffgr:diffgram", {}).get("NewDataSet", {})
    records = []
    if isinstance(tables, dict):
        for k, v in tables.items():
            if isinstance(v, list):
                for row in v:
                    if isinstance(row, dict):
                        t = row.get("TIME") or row.get("TIME_PERIOD") or row.get("Time") or row.get("time")
                        val = row.get("OBS_VALUE") or row.get("Value") or row.get("value")
                        if t is not None and val is not None:
                            records.append({"date": t, "value": val, "table": k})
    df = pd.DataFrame(records)
    if not df.empty:
        def _to_dt(x):
            x = str(x)
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    return pd.to_datetime(x, format=fmt)
                except:
                    pass
            return pd.to_datetime(x, errors="coerce")
        df["date"] = df["date"].map(_to_dt)
        df = df.dropna(subset=["date"]).sort_values("date")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

def fetch_etf_price(ticker: str) -> pd.Series:
    if yf is None:
        raise RuntimeError("尚未安裝 yfinance，請先 pip install yfinance")
    # 使用 Ticker 物件來下載，避免 download 函數問題
    ticker_obj = yf.Ticker(ticker)
    data = ticker_obj.history(period="max", auto_adjust=True)
    if data.empty or "Close" not in data.columns:
        raise RuntimeError(f"yfinance 無法取得 {ticker} 的資料")
    s = data["Close"].rename("AdjClose")
    return month_end(s)

def main():
    # 1) FRED 核心
    fred_needed = {
        "PMI": "MANEMP",
        "INDPRO": "INDPRO",
        "UNRATE": "UNRATE",
        "DGS10": "DGS10",
        "DGS2": "DGS2",
        "CreditSpread": "BAMLH0A0HYM2",
        "SP500": "SP500",
        # 附加
        "CPIAUCSL": "CPIAUCSL",
        "FEDFUNDS": "FEDFUNDS",
        "M2SL": "M2SL",
    }

    fred_data: Dict[str, pd.Series] = {}
    if _fred_client() is None:
        print("[FRED] 跳過（沒有金鑰或未安裝 fredapi）")
    else:
        for key, sid in fred_needed.items():
            try:
                s = fetch_fred_series(sid)
                fred_data[key] = s
                print(f"[FRED] {key} <- {sid}: {len(s)} obs")
            except Exception as e:
                print(f"[WARN] FRED 抓取失敗 {key} ({sid}): {e}")

    # PMI
    pmi = pd.Series(dtype=float, name="PMI")
    if "PMI" in fred_data:
        pmi = month_end(fred_data["PMI"]).rename("PMI")
    else:
        try:
            pmi = month_end(fetch_fred_series("MANEMP")).rename("PMI")
        except Exception:
            pass
    if not pmi.empty:
        save_two_col_csv(os.path.join(DATA_DIR, "PMI.csv"), "PMI", pmi)

    # INDPRO_yoy
    if "INDPRO" in fred_data:
        indpro_yoy = pct_change_yoy(fred_data["INDPRO"]).rename("INDPRO_yoy")
        save_two_col_csv(os.path.join(DATA_DIR, "INDPRO_yoy.csv"), "INDPRO_yoy", indpro_yoy)

    # UNRATE_chg3m
    if "UNRATE" in fred_data:
        unrate_chg3m = diff_3m(fred_data["UNRATE"]).rename("UNRATE_chg3m")
        save_two_col_csv(os.path.join(DATA_DIR, "UNRATE_chg3m.csv"), "UNRATE_chg3m", unrate_chg3m)

    # TERM_10y_2y
    if "DGS10" in fred_data and "DGS2" in fred_data:
        ts = month_end(fred_data["DGS10"]) - month_end(fred_data["DGS2"])
        ts.name = "TERM_10y_2y"
        save_two_col_csv(os.path.join(DATA_DIR, "TERM_10y_2y.csv"), "TERM_10y_2y", ts)

    # CreditSpread
    if "CreditSpread" in fred_data:
        cs = month_end(fred_data["CreditSpread"]).rename("CreditSpread")
        save_two_col_csv(os.path.join(DATA_DIR, "CreditSpread.csv"), "CreditSpread", cs)

    # SP500 價格（欄位要叫 AdjClose 以接 Starter）
    if "SP500" in fred_data:
        spx = month_end(fred_data["SP500"]).rename("AdjClose")
        save_two_col_csv(os.path.join(DATA_DIR, "SP500.csv"), "AdjClose", spx)

    # 3) 附加常用衍生
    if "CPIAUCSL" in fred_data:
        cpi_yoy = pct_change_yoy(fred_data["CPIAUCSL"]).rename("CPI_US_yoy")
        save_two_col_csv(os.path.join(DATA_DIR, "CPI_US_yoy.csv"), "CPI_US_yoy", cpi_yoy)
    if "FEDFUNDS" in fred_data:
        ffr = month_end(fred_data["FEDFUNDS"]).rename("FEDFUNDS")
        save_two_col_csv(os.path.join(DATA_DIR, "FEDFUNDS.csv"), "FEDFUNDS", ffr)
    if "M2SL" in fred_data:
        m2_yoy = pct_change_yoy(fred_data["M2SL"]).rename("M2SL_yoy")
        save_two_col_csv(os.path.join(DATA_DIR, "M2SL_yoy.csv"), "M2SL_yoy", m2_yoy)

    # 4) 世界銀行（年頻：世界視角），輸出到 reports/
    try:
        w_gdp = fetch_world_bank_series("NY.GDP.MKTP.KD.ZG", "WLD").rename("GDP_yoy")
        w_cpi = fetch_world_bank_series("FP.CPI.TOTL.ZG", "WLD").rename("CPI_yoy")
        df_w = pd.concat([w_gdp, w_cpi], axis=1).dropna(how="all")
        df_w.index.name = "date"
        df_w.reset_index().to_csv(os.path.join(REPORTS_DIR, "worldbank_WLD.csv"), index=False, encoding="utf-8")
        print(f"[OK] reports/worldbank_WLD.csv -> {len(df_w)} rows")
    except Exception as e:
        print(f"[WARN] 世界銀行抓取失敗: {e}")

    # 5) （選配）台灣央行 CBC：若填了 CBC_ITEMS 就抓，輸出到 reports/
    for item in CBC_ITEMS:
        try:
            df = fetch_cbc_item(item)
            if not df.empty:
                out = os.path.join(REPORTS_DIR, f"CBC_{item}.csv")
                df.to_csv(out, index=False, encoding="utf-8")
                print(f"[OK] {out} -> {len(df)} rows")
        except Exception as e:
            print(f"[WARN] CBC 抓取失敗 {item}: {e}")

    # 6) ETF 價格（選配，接回測資產）
    if yf is not None:
        for t in ETF_TICKERS:
            try:
                s = fetch_etf_price(t)
                save_two_col_csv(os.path.join(DATA_DIR, f"{t}.csv"), "AdjClose", s)
            except Exception as e:
                print(f"[WARN] ETF {t} 下載失敗：{e}")

    # 7) 輸出來源對照表
    rows = []
    for it in INDICATORS:
        rows.append({
            "name": it["name"],
            "source": it["source"],
            "series_id": it["series_id"],
            "notes": it.get("notes", ""),
            "output_csv": {
                "PMI":"PMI.csv",
                "INDPRO_yoy":"INDPRO_yoy.csv",
                "UNRATE_chg3m":"UNRATE_chg3m.csv",
                "TERM_10y_2y":"TERM_10y_2y.csv",
                "CreditSpread":"CreditSpread.csv",
                "SP500":"SP500.csv",
                "CPI_US_yoy":"CPI_US_yoy.csv",
                "FEDFUNDS":"FEDFUNDS.csv",
                "M2SL_yoy":"M2SL_yoy.csv",
                "WB_WLD_GDP_yoy":"worldbank_WLD.csv",
                "WB_WLD_CPI_yoy":"worldbank_WLD.csv",
            }.get(it["name"], "")
        })
    pd.DataFrame(rows).to_csv(os.path.join(REPORTS_DIR, "data_sources.csv"), index=False, encoding="utf-8")
    print(f"[DONE] 指標抓取完成！檔案已輸出到 {DATA_DIR} 與 {REPORTS_DIR}")
    print("如需更多台灣指標（CPI、失業率、工業生產等），請參考：") 
    print(" - 主計總處 DGBAS API（需先確認資料表代碼與維度）：https://nstatdb.dgbas.gov.tw/dgbasall/download/API說明文件.pdf")
    print(" - 央行 CBC API（ItemCode 例如 EF21M01en 等）：https://cpx.cbc.gov.tw/Data/ExportToEnAPIInfo")

if __name__ == "__main__":
    main()
