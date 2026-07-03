"""scoring.py — 把归一化字段聚合成四个决策维度:价值/风险/流动性/时间窗口。
每个维度是若干 *_norm 字段的加权和,权重来自 config。透明、可解释、可调。
"""
import pandas as pd

DIMENSIONS = ["value", "risk", "liquidity", "time_window"]


def score_dimensions(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    for dim in DIMENSIONS:
        weights = cfg["scoring"][dim]
        col = pd.Series(0.0, index=out.index)
        wsum = 0.0
        for field, w in weights.items():
            norm_col = f"{field}_norm"
            if norm_col in out.columns:
                col = col + out[norm_col] * w
                wsum += w
        out[f"{dim}_score"] = col / wsum if wsum else col
    return out
