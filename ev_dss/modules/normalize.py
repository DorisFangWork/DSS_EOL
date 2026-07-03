"""normalize.py — 把异构原始读数统一映射到 0-1,1 表示"对二次利用更有利"。
这是护城河的第一道技术门槛:归一化的边界值(config里的min/max)就是领域know-how的载体。
"""
import pandas as pd


def _minmax(series: pd.Series, lo: float, hi: float, higher_is_better: bool) -> pd.Series:
    scaled = (series - lo) / (hi - lo)
    scaled = scaled.clip(0, 1)
    return scaled if higher_is_better else (1 - scaled)


def normalize(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    for field, rule in cfg["normalization"].items():
        if field in out.columns:
            out[f"{field}_norm"] = _minmax(
                out[field], rule["min"], rule["max"], rule["higher_is_better"]
            )
    return out
