"""收敛判定与二衬龄期洞温漂移补偿：先扣漂，再按 ±3.0 mm 出结论。"""
LIMIT_MM = 3.0

# 补偿系数允许区间（mm/℃），越界一律退回
COEF_MIN = 0.001
COEF_MAX = 0.5
# 洞温允许区间（℃），基准洞温同此区间
TEMP_MIN = -20.0
TEMP_MAX = 60.0


def judge(compensated_mm: float) -> tuple[str, str]:
    """对扣漂后的毫米值下结论。"""
    if abs(compensated_mm) <= LIMIT_MM:
        return "合格", f"扣漂后 {compensated_mm} mm 在 ±{LIMIT_MM} mm 以内"
    return "超限", f"扣漂后 {compensated_mm} mm 超过 ±{LIMIT_MM} mm"


def compensate(
    raw_mm: float, temp_c: float, baseline_c: float, coefficient: float
) -> tuple[float, float]:
    """漂移量 = 系数 × (当时洞温 - 基准洞温)；扣漂后 = 原始值 - 漂移量。

    系数 0.05、洞温抬高 20℃ 时漂移 1.0 mm，扣漂后值与原始值差约 1 mm。
    """
    drift = coefficient * (temp_c - baseline_c)
    return round(drift, 3), round(raw_mm - drift, 3)


def coefficient_ok(value: float) -> bool:
    return COEF_MIN <= value <= COEF_MAX


def temp_ok(value: float) -> bool:
    return TEMP_MIN <= value <= TEMP_MAX
