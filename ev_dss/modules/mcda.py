"""mcda.py — 决策引擎核心。对每个电池,针对每条处置路径用 TOPSIS 算贴近度。
逻辑:
  1. 每条路径有一个"理想画像"(profile,在四维上的期望强度)。
  2. 用电池的四维评分与每条路径画像做 TOPSIS,得到贴近度 (closeness)。
  3. 应用准入门槛 (gates):不达标的路径贴近度归零(硬约束)。
  4. 排序 → 首选/次选,并给出置信度与决策理由。
仅依赖 numpy/pandas,方便原型阶段调试;数据积累后可无痛替换为更复杂的 MCDA/优化。
"""
import numpy as np
import pandas as pd

from .scoring import DIMENSIONS


def _passes_gates(row: pd.Series, gates: dict) -> bool:
    for field, threshold in gates.items():
        if field in row and row[field] < threshold:
            return False
    return True


def _topsis_closeness(battery_vec: np.ndarray, profile_vec: np.ndarray) -> float:
    """单资产对单路径的简化 TOPSIS 贴近度。
    理想解 = 路径画像;负理想解 = 全 0(最差)。贴近度越高越匹配。
    """
    d_best = np.linalg.norm(battery_vec - profile_vec)
    d_worst = np.linalg.norm(battery_vec - np.zeros_like(profile_vec))
    if (d_best + d_worst) == 0:
        return 0.0
    return d_worst / (d_best + d_worst)


def recommend(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    dim_weights = np.array([cfg["dimension_weights"][d] for d in DIMENSIONS])
    dim_weights = dim_weights / dim_weights.sum()

    records = []
    for _, row in df.iterrows():
        battery_vec = np.array([row[f"{d}_score"] for d in DIMENSIONS]) * dim_weights

        path_scores = {}
        for pname, pdef in cfg["pathways"].items():
            profile_vec = np.array([pdef["profile"][d] for d in DIMENSIONS]) * dim_weights
            closeness = _topsis_closeness(battery_vec, profile_vec)
            if not _passes_gates(row, pdef.get("gates", {})):
                closeness = 0.0
            path_scores[pname] = closeness

        ranked = sorted(path_scores.items(), key=lambda x: x[1], reverse=True)
        top_name, top_score = ranked[0]
        second_name, second_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

        # 置信度:首选与次选的差距越大越有信心;数据被填补则打折
        margin = top_score - second_score
        confidence = min(1.0, margin * 2.5)
        if row.get("_imputed", False):
            confidence *= 0.7

        reason = _build_reason(row, top_name, cfg)

        records.append({
            "battery_id": row["battery_id"],
            "top_choice": cfg["pathways"][top_name]["label"],
            "top_key": top_name,
            "second_choice": cfg["pathways"][second_name]["label"] if second_name else "-",
            "top_score": round(top_score, 3),
            "confidence": round(confidence, 2),
            "reason": reason,
            "soh_pct": round(float(row.get("soh_pct", 0)), 1),
            "age_years": int(row.get("age_years", 0)),
            "fault_count": int(row.get("fault_count", 0)),
            "book_value_usd": round(float(row.get("book_value_usd", 0)), 0),
            **{f"{d}_score": round(row[f"{d}_score"], 3) for d in DIMENSIONS},
        })

    return pd.DataFrame(records)


def _build_reason(row: pd.Series, path: str, cfg: dict) -> str:
    scores = {d: row[f"{d}_score"] for d in DIMENSIONS}
    top_dim = max(scores, key=scores.get)
    low_dim = min(scores, key=scores.get)
    en = {"value": "Residual value", "risk": "Safety & compliance",
          "liquidity": "Market liquidity", "time_window": "Time window"}
    return (f"Driven by high {en[top_dim]} ({scores[top_dim]:.2f}); "
            f"weakest on {en[low_dim]} ({scores[low_dim]:.2f})")
