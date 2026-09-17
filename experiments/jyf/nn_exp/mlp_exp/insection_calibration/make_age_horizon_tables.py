#!/usr/bin/env python3
"""Render dense calibration results as readable age x horizon tables."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


SELECTED_AGES = (0, 5, 20, 60, 180, 600, 1800)
SELECTED_HORIZONS = (1, 5, 20, 60, 600, 1800)
METHODS = ("log_survival", "linear_survival", "right_step")


def fmt_pct(value):
    return f"{100.0 * value:.2f}%"


def fmt_signed_pct(value):
    return f"{100.0 * value:+.2f}%"


def markdown_matrix(title, ages, horizons, getter, formatter):
    lines = [f"## {title}", ""]
    lines.append("| Age \\ Horizon | " + " | ".join(f"{h:g}s" for h in horizons) + " |")
    lines.append("|---:|" + "---:|" * len(horizons))
    for age in ages:
        values = [formatter(getter(age, horizon)) for horizon in horizons]
        lines.append(f"| {age:g}s | " + " | ".join(values) + " |")
    lines.append("")
    return lines


def write_full_matrix(path, ages, horizons, getter):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["age_s"] + list(horizons))
        for age in ages:
            writer.writerow([age] + [getter(age, horizon) for horizon in horizons])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    with a.input.open(newline="") as f:
        rows = list(csv.DictReader(f))

    data = {}
    for row in rows:
        if row["weighting"] != "token":
            continue
        key = (row["method"], float(row["age_s"]), float(row["horizon_s"]))
        data[key] = {k: float(v) for k, v in row.items()
                     if k not in ("method", "weighting") and v != ""}

    ages = sorted(set(key[1] for key in data))
    horizons = sorted(set(key[2] for key in data))
    actual = lambda age, horizon: data[("log_survival", float(age), float(horizon))]["km_observed_risk"]
    at_risk = lambda age, horizon: data[("log_survival", float(age), float(horizon))]["n_at_risk"]
    events = lambda age, horizon: data[("log_survival", float(age), float(horizon))]["observed_events"]
    pred = lambda method, age, horizon: data[(method, float(age), float(horizon))]["mean_predicted_risk"]
    ece = lambda method, age, horizon: data[(method, float(age), float(horizon))]["km_ece10"]

    write_full_matrix(a.out_dir / "matrix_actual_km_risk.csv", ages, horizons, actual)
    write_full_matrix(a.out_dir / "matrix_log_predicted_risk.csv", ages, horizons,
                      lambda age, horizon: pred("log_survival", age, horizon))
    write_full_matrix(a.out_dir / "matrix_log_bias.csv", ages, horizons,
                      lambda age, horizon: pred("log_survival", age, horizon) - actual(age, horizon))
    for method in METHODS:
        write_full_matrix(a.out_dir / f"matrix_{method}_ece10.csv", ages, horizons,
                          lambda age, horizon, method=method: ece(method, age, horizon))

    lines = [
        "# Age × Horizon 条件风险校准表（token-weighted）",
        "",
        "每个单元格都对应固定 age 和 horizon，不再跨 age 平均。定义：",
        "",
        "`actual(a,h) = P(T <= a+h | T > a)`，通过 Kaplan–Meier 处理右删失。",
        "",
    ]
    lines += ["## 每个 Age 的 at-risk 节点数", "", "| Age | Nodes at risk |", "|---:|---:|"]
    for age in SELECTED_AGES:
        lines.append(f"| {age:g}s | {int(at_risk(age, SELECTED_HORIZONS[0])):,} |")
    lines.append("")
    lines += markdown_matrix(
        "窗口内实际 observed reuse 事件数", SELECTED_AGES, SELECTED_HORIZONS,
        events, lambda x: f"{int(x):,}")
    lines += markdown_matrix("实际 KM 风险", SELECTED_AGES, SELECTED_HORIZONS, actual, fmt_pct)
    lines += markdown_matrix(
        "Log-survival 预测风险", SELECTED_AGES, SELECTED_HORIZONS,
        lambda age, horizon: pred("log_survival", age, horizon), fmt_pct)
    lines += markdown_matrix(
        "Log-survival 偏差（预测 − 实际）", SELECTED_AGES, SELECTED_HORIZONS,
        lambda age, horizon: pred("log_survival", age, horizon) - actual(age, horizon), fmt_signed_pct)
    lines += markdown_matrix(
        "Log-survival ECE10", SELECTED_AGES, SELECTED_HORIZONS,
        lambda age, horizon: ece("log_survival", age, horizon), lambda x: f"{x:.4f}")
    lines += markdown_matrix(
        "Linear-survival ECE10", SELECTED_AGES, SELECTED_HORIZONS,
        lambda age, horizon: ece("linear_survival", age, horizon), lambda x: f"{x:.4f}")
    lines += markdown_matrix(
        "Right-step ECE10", SELECTED_AGES, SELECTED_HORIZONS,
        lambda age, horizon: ece("right_step", age, horizon), lambda x: f"{x:.4f}")
    lines += [
        "## 阅读方法",
        "",
        "例如 `age=20s, horizon=5s` 表示：已经等待 20 秒仍未返回的节点，在第 20～25 秒之间返回的条件概率。",
        "",
        "偏差为负表示模型低估返回概率，为正表示高估。ECE10 越低越好。",
        "",
        "正文展示代表性子矩阵；完整 22×17 数值在同目录的 `matrix_*.csv` 文件中。",
    ]
    (a.out_dir / "age_horizon_calibration_tables_zh.md").write_text("\n".join(lines) + "\n")
    print(a.out_dir / "age_horizon_calibration_tables_zh.md")


if __name__ == "__main__":
    main()
