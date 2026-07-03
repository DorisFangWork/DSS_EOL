"""loader.py — 读取输入CSV,校验最小必要字段,处理缺失值。
这一层对应架构里的"输入适配器":它不生产状态数据,只负责接入和把关。
"""
import pandas as pd

REQUIRED_FIELDS = [
    "battery_id", "age_years", "soh_pct", "cycle_count",
    "avg_temp_c", "fault_count", "original_cost_usd", "book_value_usd",
]


def load_batteries(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    missing = [f for f in REQUIRED_FIELDS if f not in df.columns]
    if missing:
        raise ValueError(f"输入缺少必要字段: {missing}")

    numeric = [f for f in REQUIRED_FIELDS if f != "battery_id"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 简单缺失值处理:用中位数填补,并记录哪些行被填补(供置信度使用)
    df["_imputed"] = df[numeric].isna().any(axis=1)
    for col in numeric:
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    # 派生字段:残值率 = 账面价值 / 原始成本
    df["residual_ratio"] = (df["book_value_usd"] / df["original_cost_usd"]).clip(0, 1)

    return df
