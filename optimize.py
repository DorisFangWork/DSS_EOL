"""optimize.py — 可选增强模块(架构第4层的第二档)。
MCDA 回答"单个电池该走哪条路径";本模块回答"一批电池在产能/预算约束下如何整体分配"。
这是一个带约束的指派问题:最大化总贴近度,同时满足各路径的产能上限。
依赖 PuLP(纯 Python LP 求解器)。原型阶段可先不启用。
"""
import pulp
import pandas as pd
import numpy as np

from .scoring import DIMENSIONS


def optimize_allocation(df: pd.DataFrame, cfg: dict, capacity: dict) -> pd.DataFrame:
    """capacity: {路径名: 该路径最多能处理多少个电池}"""
    dim_weights = np.array([cfg["dimension_weights"][d] for d in DIMENSIONS])
    dim_weights = dim_weights / dim_weights.sum()
    paths = list(cfg["pathways"].keys())
    batteries = df["battery_id"].tolist()

    # 预计算每个 (电池,路径) 的贴近度作为收益
    benefit = {}
    for _, row in df.iterrows():
        bvec = np.array([row[f"{d}_score"] for d in DIMENSIONS]) * dim_weights
        for p in paths:
            pvec = np.array([cfg["pathways"][p]["profile"][d] for d in DIMENSIONS]) * dim_weights
            d_best = np.linalg.norm(bvec - pvec)
            d_worst = np.linalg.norm(bvec)
            benefit[(row["battery_id"], p)] = d_worst / (d_best + d_worst) if (d_best + d_worst) else 0

    prob = pulp.LpProblem("battery_allocation", pulp.LpMaximize)
    x = {(b, p): pulp.LpVariable(f"x_{b}_{p}", cat="Binary") for b in batteries for p in paths}

    # 目标:最大化总贴近度
    prob += pulp.lpSum(benefit[(b, p)] * x[(b, p)] for b in batteries for p in paths)

    # 约束1:每个电池恰好分配一条路径
    for b in batteries:
        prob += pulp.lpSum(x[(b, p)] for p in paths) == 1

    # 约束2:各路径产能上限
    for p in paths:
        if p in capacity:
            prob += pulp.lpSum(x[(b, p)] for b in batteries) <= capacity[p]

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    rows = []
    for b in batteries:
        for p in paths:
            if pulp.value(x[(b, p)]) == 1:
                rows.append({
                    "battery_id": b,
                    "allocated_path": cfg["pathways"][p]["label"],
                    "benefit": round(benefit[(b, p)], 3),
                })
    return pd.DataFrame(rows)
