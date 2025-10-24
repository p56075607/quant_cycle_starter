# src/regime.py
import pandas as pd
from .utils import zscore

def composite_score(macros: dict) -> pd.Series:
    """
    Compute composite economic score using z-scores of selected indicators.
    Score = z(PMI) + z(INDPRO_yoy) - z(UNRATE_chg3m) + z(TERM_10y_2y) - z(CreditSpread) + z(Equity_mom6)
    """
    pmi = macros["PMI"]
    ip = macros["INDPRO_yoy"]
    ue = macros["UNRATE_chg3m"]
    term = macros["TERM_10y_2y"]
    cs = macros["CreditSpread"]
    spx = macros["SP500"].resample("ME").last()
    eq_mom6 = spx.pct_change(6)

    score = (
        zscore(pmi) + zscore(ip) - zscore(ue) + zscore(term) - zscore(cs) + zscore(eq_mom6)
    )
    score = score.dropna()
    return score

def classify(score: pd.Series) -> pd.DataFrame:
    chg3m = score.diff(3)
    df = pd.concat([score, chg3m], axis=1).dropna()
    df.columns = ["score","d3"]

    def _lab(sc, dsc):
        if sc > 0 and dsc > 0:
            return "expansion"
        if sc > 0 and dsc <= 0:
            return "slowdown"
        if sc <= 0 and dsc > 0:
            return "recovery"
        return "recession"

    df["state"] = df.apply(lambda r: _lab(r["score"], r["d3"]), axis=1)
    return df[["state"]]