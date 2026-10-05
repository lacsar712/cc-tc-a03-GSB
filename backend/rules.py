"""扣漂与判定。

二衬龄期内洞温把测缝读数拧偏：drift = k × (当时洞温 − 基准洞温)，
扣漂后毫米 corrected = raw − drift。合格线仍看扣漂后值的绝对值 ±3.0 mm。
"""

LIMIT_MM = 3.0

# 温度系数允许范围（mm/℃），0.05 是常用值；0 或负数没有物理意义，0.20 封顶防抄错。
COEFF_MIN_EXCL = 0.0
COEFF_MAX = 0.20
# 洞温合理区间（℃），洞内实测超此值多半是探头坏了或抄错。
TEMP_MIN_C = -20.0
TEMP_MAX_C = 60.0

ROUND_DIGITS = 3


class CompensationError(ValueError):
    """报送材料不齐或越界，message 就是给测量员看的人话。"""


def validate_coeff(k: float) -> None:
    if not (COEFF_MIN_EXCL < k <= COEFF_MAX):
        raise CompensationError(
            f"温度系数 {k} 越界：只接受大于 0 且不超过 {COEFF_MAX} mm/℃ 的系数"
        )


def validate_temp(label: str, t: float) -> None:
    if not (TEMP_MIN_C <= t <= TEMP_MAX_C):
        raise CompensationError(
            f"{label} {t} ℃ 越界：只接受 {TEMP_MIN_C:g}～{TEMP_MAX_C:g} ℃ 之间的洞温"
        )


def compensate(raw_mm: float, k: float, baseline_temp_c: float, measured_temp_c: float):
    """返回 (漂移毫米, 扣漂后毫米)。洞温抬高时漂移为正，从原始读数里扣掉。"""
    drift = round(k * (measured_temp_c - baseline_temp_c), ROUND_DIGITS)
    corrected = round(raw_mm - drift, ROUND_DIGITS)
    return drift, corrected


def judge(delta_mm: float) -> tuple[str, str]:
    if abs(delta_mm) <= LIMIT_MM:
        return "合格", f"扣漂后 {delta_mm} mm 在 ±{LIMIT_MM} mm 以内"
    return "超限", f"扣漂后 {delta_mm} mm 超过 ±{LIMIT_MM} mm"
