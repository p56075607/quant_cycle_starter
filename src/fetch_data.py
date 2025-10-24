# src/fetch_data.py
# Comments in English for clarity; Traditional Chinese in docstrings.
import os
import io
import json
import argparse
from typing import Dict, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd
import requests

# Optional libs
try:
    from fredapi import Fred
except Exception:
    Fred = None

try:
    import yfinance as yf
except Exception:
    yf = None


# ------------------------
# Helpers (shared)
# ------------------------
def month_end(s: pd.Series) -> pd.Series:
    """Resample to month-end without forward-filling."""
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    s = s.resample("M").last()
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

def ensure_dirs(*paths: str):
    for p in paths:
        os.makedirs(p, exist_ok=True)


# ------------------------
# US data (FRED / ETF / World Bank)
# ------------------------
def _fred_client() -> Optional["Fred"]:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        print("[WARN] FRED_API_KEY not set. Get one at https://fred.stlouisfed.org/docs/api/api_key.html")
        return None
    if Fred is None:
        print("[ERROR] fredapi not installed. pip install fredapi")
        return None
    return Fred(api_key=api_key)

def fetch_fred_series(series_id: str) -> pd.Series:
    fred = _fred_client()
    if fred is None:
        raise RuntimeError("FRED client not ready")
    return fred.get_series(series_id)

def fetch_world_bank_series(indicator: str, country: str="WLD") -> pd.Series:
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

def fetch_etf_price(ticker: str) -> pd.Series:
    if yf is None:
        raise RuntimeError("yfinance not installed. pip install yfinance")
    data = yf.download(ticker, period="max", auto_adjust=True, progress=False)
    if "Close" not in data.columns:
        raise RuntimeError(f"yfinance has no Close for: {ticker}")
    s = data["Close"].rename("AdjClose")
    return month_end(s)


# ------------------------
# Taiwan data (DGBAS / CBC)
# ------------------------
def fetch_cbc_item(item_code: str) -> dict:
    """
    中央銀行統計資料庫 API
    GET https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=<ItemCode>
    回傳 JSON，表格結構依 item_code 而異。此函式回傳:
      {
        "raw": <original json>,
        "flat": <扁平化DataFrame，僅抓 TIME/TIME_PERIOD 與 OBS_VALUE 類欄位>
      }
    """
    url = "https://cpx.cbc.gov.tw/API/DataAPI/Get"
    r = requests.get(url, params={"FileName": item_code}, timeout=60)
    r.raise_for_status()
    j = r.json()

    # Flatten (best-effort)
    ds = j.get("DataSet", {})
    tables = ds.get("diffgr:diffgram", {}).get("NewDataSet", {})
    rows = []
    if isinstance(tables, dict):
        for k, v in tables.items():
            if isinstance(v, list):
                for row in v:
                    if isinstance(row, dict):
                        t = row.get("TIME") or row.get("TIME_PERIOD") or row.get("Time") or row.get("time")
                        val = row.get("OBS_VALUE") or row.get("Value") or row.get("value")
                        if t is not None and val is not None:
                            rows.append({"date": t, "value": val, "table": k})
    df = pd.DataFrame(rows)
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
    return {"raw": j, "flat": df}

def fetch_dgbas_sdmx(path_after_sdmx: str, start: Optional[str]=None, end: Optional[str]=None) -> dict:
    """
    主計總處 (DGBAS) SDMX 介面（API-JSON）
    典型語法：
      https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/<功能代碼>/<維度鍵>.M&startTime=YYYY-MM&endTime=YYYY-MM

    你要做的事：
      1) 確認功能代碼（例如 失業率/物價/工業生產 對應之表）
      2) 用網站提供的查詢工具拿到 <維度鍵> 字串
      3) 把 "<功能代碼>/<維度鍵>.M" 放到 path_after_sdmx 參數

    回傳:
      {
        "raw": <API JSON>,
        "flat": <扁平化DataFrame（TIME_PERIOD vs OBS_VALUE），需視表而調整>
      }
    """
    base = "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx"
    qs = f"sdmx/{path_after_sdmx}"
    if start:
        qs += f"&startTime={start}"
    if end:
        qs += f"&endTime={end}"
    url = f"{base}?{qs}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    j = r.json()

    # Flatten (generic TIME / OBS_VALUE)
    records = []
    # 結構會依表不同，以下為常見字段名稱
    ds = j.get("dataSet", j.get("DataSet", {}))
    # API-JSON 與 SDMX-JSON 在 DGBAS 兩種回法都有，先盡量兼容：
    # 嘗試針對 SDMX-JSON 結構 (series/observations)
    if "structure" in j and "dataSets" in j:
        try:
            series = j["dataSets"][0]["series"]
            dims = j["structure"]["dimensions"]["series"]
            time_list = j["structure"]["dimensions"]["observation"][0]["values"]
            for series_key, obs in series.items():
                # series_key like "0:1:0:..." -> decode labels if needed
                for time_idx, val in obs["observations"].items():
                    t = time_list[int(time_idx)]["id"]  # YYYY-MM
                    v = val[0]
                    records.append({"date": t, "value": v})
        except Exception:
            pass

    # 若上面抓不到，再試 API-JSON 的 NewDataSet 模式
    if not records:
        nds = j.get("diffgr:diffgram", {}).get("NewDataSet", {})
        if isinstance(nds, dict):
            for k, lst in nds.items():
                if isinstance(lst, list):
                    for row in lst:
                        t = row.get("TIME") or row.get("TIME_PERIOD") or row.get("Time")
                        v = row.get("OBS_VALUE") or row.get("Value")
                        if t is not None and v is not None:
                            records.append({"date": t, "value": v})

    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
    return {"raw": j, "flat": df}


# ------------------------
# Specs you can extend
# ------------------------
ETF_TICKERS = ["VT", "IEF", "GLD", "IWM", "TLT", "DBC"]

US_FRED_SERIES = {
    "PMI": "NAPM",
    "INDPRO": "INDPRO",
    "UNRATE": "UNRATE",
    "DGS10": "DGS10",
    "DGS2":  "DGS2",
    "CreditSpread": "BAMLH0A0HYM2",
    "SP500": "SP500",
    # optional extras
    "CPIAUCSL": "CPIAUCSL",
    "FEDFUNDS": "FEDFUNDS",
    "M2SL": "M2SL",
}

# ---- Taiwan presets ----
# 央行 CBC：兩個可直接跑的示例（其餘請自行把 item code 補入）
CBC_ITEM_CODES = [
    # 美元/台幣（美元兌新台幣）日資料（英文代碼；官方頁面找 "BP01D01en"）
    "BP01D01en",
    # M2 變動因素（示例，表結構較複雜，輸出 raw 與 basic flat）
    "EF21M01en",
]

# DGBAS：請把 <功能代碼>/<維度鍵>.M 放入下方，比如：
# - CPI（總指數、月頻、季調或未季調依你需求）
# - 失業率（總失業率、月頻）
# - 工業生產指數（總指數、月頻）
# 下面是「範例模板」：請把 YOUR_... 改成實際代碼；或先留空以略過。
DGBAS_SDMX_PATHS = [
    # "A010101/<dim_key>.M",   # CPI 總指數（示例代碼，請到 DGBAS 取得正確維度鍵）
    # "A040101020/<dim_key>.M",# 失業率（示例）
    # "D2101/<dim_key>.M",     # 工業生產指數（示例）
]


# ------------------------
# Main pipeline
# ------------------------
def run(output_dir: str, with_us: bool=True, with_tw: bool=False, tw_only: bool=False):
    data_dir = os.path.join(output_dir)
    reports_dir = os.path.join("reports")
    ensure_dirs(data_dir, reports_dir)

    # ---------- US ----------
    if with_us and not tw_only:
        fred_data: Dict[str, pd.Series] = {}
        fred = _fred_client()
        if fred is None:
            print("[US] Skip FRED (no key or no fredapi).")
        else:
            for key, sid in US_FRED_SERIES.items():
                try:
                    s = fetch_fred_series(sid)
                    fred_data[key] = s
                    print(f"[FRED] {key} <- {sid}: {len(s)} obs")
                except Exception as e:
                    print(f"[WARN] FRED fetch fail {key} ({sid}): {e}")

        # Derived outputs (align to starter schema)
        if "PMI" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "PMI.csv"), "PMI", month_end(fred_data["PMI"]))
        if "INDPRO" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "INDPRO_yoy.csv"), "INDPRO_yoy", pct_change_yoy(fred_data["INDPRO"]))
        if "UNRATE" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "UNRATE_chg3m.csv"), "UNRATE_chg3m", diff_3m(fred_data["UNRATE"]))
        if "DGS10" in fred_data and "DGS2" in fred_data:
            ts = month_end(fred_data["DGS10"]) - month_end(fred_data["DGS2"])
            ts.name = "TERM_10y_2y"
            save_two_col_csv(os.path.join(data_dir, "TERM_10y_2y.csv"), "TERM_10y_2y", ts)
        if "CreditSpread" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "CreditSpread.csv"), "CreditSpread", month_end(fred_data["CreditSpread"]))
        if "SP500" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "SP500.csv"), "AdjClose", month_end(fred_data["SP500"]))

        # Extras
        if "CPIAUCSL" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "CPI_US_yoy.csv"), "CPI_US_yoy", pct_change_yoy(fred_data["CPIAUCSL"]))
        if "FEDFUNDS" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "FEDFUNDS.csv"), "FEDFUNDS", month_end(fred_data["FEDFUNDS"]))
        if "M2SL" in fred_data:
            save_two_col_csv(os.path.join(data_dir, "M2SL_yoy.csv"), "M2SL_yoy", pct_change_yoy(fred_data["M2SL"]))

        # ETFs (optional)
        if yf is not None:
            for t in ETF_TICKERS:
                try:
                    s = fetch_etf_price(t)
                    save_two_col_csv(os.path.join(data_dir, f"{t}.csv"), "AdjClose", s)
                except Exception as e:
                    print(f"[WARN] ETF {t} failed: {e}")

        # World Bank world view (annual, reference only)
        try:
            w_gdp = fetch_world_bank_series("NY.GDP.MKTP.KD.ZG", "WLD").rename("GDP_yoy")
            w_cpi = fetch_world_bank_series("FP.CPI.TOTL.ZG", "WLD").rename("CPI_yoy")
            df_w = pd.concat([w_gdp, w_cpi], axis=1).dropna(how="all")
            df_w.index.name = "date"
            df_w.reset_index().to_csv(os.path.join(reports_dir, "worldbank_WLD.csv"), index=False, encoding="utf-8")
            print(f"[OK] reports/worldbank_WLD.csv -> {len(df_w)} rows")
        except Exception as e:
            print(f"[WARN] World Bank fetch fail: {e}")

    # ---------- Taiwan ----------
    if with_tw or tw_only:
        # CBC examples
        for item in CBC_ITEM_CODES:
            try:
                res = fetch_cbc_item(item)
                # 1) Save raw JSON
                raw_path = os.path.join(reports_dir, f"CBC_{item}.json")
                with open(raw_path, "w", encoding="utf-8") as f:
                    json.dump(res["raw"], f, ensure_ascii=False, indent=2)
                # 2) Save basic flat
                df = res["flat"]
                if not df.empty:
                    out = os.path.join(reports_dir, f"CBC_{item}.csv")
                    df.to_csv(out, index=False, encoding="utf-8")
                    print(f"[OK] {out} -> {len(df)} rows")
                # 3) Special mapping examples
                if item == "BP01D01en":
                    # USD/TWD daily -> month-end close
                    if not df.empty:
                        s = df.set_index("date")["value"].astype(float)
                        s = month_end(s).rename("USD_TWD")
                        save_two_col_csv(os.path.join(data_dir, "USD_TWD.csv"), "USD_TWD", s)
                # EF21M01en is factor table of M2 changes (kept in reports)
            except Exception as e:
                print(f"[WARN] CBC {item} failed: {e}")

        # DGBAS SDMX paths (fill your own)
        for sdmx_path in DGBAS_SDMX_PATHS:
            try:
                res = fetch_dgbas_sdmx(sdmx_path)
                raw_path = os.path.join(reports_dir, f"DGBAS_{sdmx_path.replace('/','_')}.json")
                with open(raw_path, "w", encoding="utf-8") as f:
                    json.dump(res["raw"], f, ensure_ascii=False, indent=2)
                df = res["flat"]
                if not df.empty:
                    # Heuristic: try to save as two-col (rename as needed)
                    name = sdmx_path.split("/")[0]
                    # You can change name mapping below to your desired CSV name/column
                    col_name = name
                    s = df.set_index("date")["value"]
                    save_two_col_csv(os.path.join(data_dir, f"{name}.csv"), col_name, s)
            except Exception as e:
                print(f"[WARN] DGBAS {sdmx_path} failed: {e}")


# ------------------------
# CLI
# ------------------------
def main():
    p = argparse.ArgumentParser(description="Fetch macro indicators for US/TW; output CSVs ready for backtest.")
    p.add_argument("--output-dir", default="data", help="Where to write CSVs (default: data)")
    p.add_argument("--with-tw", action="store_true", help="Also fetch Taiwan data (CBC/DGBAS)")
    p.add_argument("--tw-only", action="store_true", help="Fetch only Taiwan data (skip US)")
    args = p.parse_args()

    run(output_dir=args.output_dir, with_us=not args.tw_only, with_tw=args.with_tw, tw_only=args.tw_only)

if __name__ == "__main__":
    main()
