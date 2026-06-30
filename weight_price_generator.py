from __future__ import annotations

"""Gjenerim random Pesha/kg dhe Çmimi për rreshtat e listës."""
import random
from typing import Any


DEFAULT_RANDOM_COLUMNS = {
    "enabled": True,
    "pesha_min": 0.50,
    "pesha_max": 0.96,
    "pesha_common": [0.55, 0.60, 0.53, 0.58, 0.65, 0.68, 0.70, 0.74, 0.80],
    "cmimi_min": 15,
    "cmimi_max": 22,
}


def get_random_columns_config(settings: dict | None) -> dict:
    cfg = dict(DEFAULT_RANDOM_COLUMNS)
    if settings and isinstance(settings.get("random_columns"), dict):
        cfg.update(settings["random_columns"])
    cfg["pesha_min"] = float(cfg.get("pesha_min", 0.50))
    cfg["pesha_max"] = float(cfg.get("pesha_max", 0.96))
    cfg["cmimi_min"] = int(cfg.get("cmimi_min", 15))
    cfg["cmimi_max"] = int(cfg.get("cmimi_max", 22))
    common = cfg.get("pesha_common") or DEFAULT_RANDOM_COLUMNS["pesha_common"]
    cfg["pesha_common"] = [float(x) for x in common]
    cfg["enabled"] = bool(cfg.get("enabled", True))
    return cfg


def _effective_weight_bounds(
    count: int, target_total: float, min_w: float, max_w: float
) -> tuple[float, float, float]:
    """Kthen min/max efektiv dhe mesataren e nevojshme për totalin e caktuar."""
    if count <= 0:
        return min_w, max_w, 0.0
    avg_needed = target_total / count
    effective_min = min_w
    effective_max = max_w
    if avg_needed < min_w:
        effective_min = max(0.01, round(avg_needed * 0.55, 2))
    if avg_needed > max_w:
        effective_max = round(avg_needed * 1.45, 2)
    return effective_min, effective_max, avg_needed


def _validate_target_weight(
    count: int, target_total: float, min_w: float, max_w: float
) -> tuple[float, float]:
    if count <= 0:
        return min_w, max_w
    effective_min, effective_max, avg_needed = _effective_weight_bounds(
        count, target_total, min_w, max_w
    )
    min_sum = round(count * effective_min, 2)
    max_sum = round(count * effective_max, 2)
    if target_total < min_sum - 1.0:
        raise ValueError(
            f"Pesha totale {target_total} kg është shumë e vogël për {count} rreshta "
            f"(minimumi i arritshëm është ~{min_sum:.0f} kg)."
        )
    if target_total > max_sum + 1.0:
        raise ValueError(
            f"Pesha totale {target_total} kg është shumë e madhe për {count} rreshta "
            f"(maksimumi i arritshëm është ~{max_sum:.0f} kg)."
        )
    return effective_min, effective_max


def generate_weights(
    count: int,
    target_total: float,
    min_w: float,
    max_w: float,
    common: list[float] | None = None,
) -> list[float]:
    """Gjeneron pesha random që në total japin target_total (kg)."""
    if count <= 0:
        return []
    if count == 1:
        return [round(max(min_w, min(max_w, target_total)), 2)]

    effective_min, effective_max = _validate_target_weight(
        count, target_total, min_w, max_w
    )
    common = common or []

    min_c = int(round(effective_min * 100))
    max_c = int(round(effective_max * 100))
    target_c = int(round(target_total * 100))
    common_c = sorted(
        {
            int(round(c * 100))
            for c in common
            if min_c <= int(round(c * 100)) <= max_c
        }
    )

    cents: list[int] = []
    for _ in range(count):
        if common_c and random.random() < 0.78:
            cents.append(random.choice(common_c))
        else:
            cents.append(random.randint(min_c, max_c))

    total = sum(cents)
    if total <= 0:
        cents = [min_c] * count
        total = sum(cents)

    scaled = [max(min_c, min(max_c, int(round(c * target_c / total)))) for c in cents]
    diff = target_c - sum(scaled)
    order = list(range(count))
    random.shuffle(order)
    guard = 0
    while diff != 0 and guard < count * 5000:
        i = order[guard % count]
        if diff > 0 and scaled[i] < max_c:
            scaled[i] += 1
            diff -= 1
        elif diff < 0 and scaled[i] > min_c:
            scaled[i] -= 1
            diff += 1
        guard += 1

    if diff != 0:
        raise ValueError(
            f"Nuk u arrit pesha totale {target_total} kg me range {min_w}–{max_w}."
        )

    return [c / 100.0 for c in scaled]


def generate_prices(count: int, min_p: int, max_p: int) -> list[int]:
    if count <= 0:
        return []
    lo, hi = int(min_p), int(max_p)
    if lo > hi:
        lo, hi = hi, lo
    return [random.randint(lo, hi) for _ in range(count)]


def apply_random_pesha_cmimi(
    df,
    mapping: dict,
    settings: dict,
    row_indices: list[int],
    target_total_kg: float | None = None,
) -> dict[str, Any]:
    """Vendos Pesha/kg dhe Çmimi për rreshtat e listës (para mapimit të produkteve)."""
    cfg = get_random_columns_config(settings)
    meta: dict[str, Any] = {"applied": False, "rows": 0, "pesha_sum": 0.0}

    if not cfg["enabled"]:
        return meta

    if mapping.get("header_row") is None:
        return meta

    pesha_col = mapping.get("pesha_col")
    cmimi_col = mapping.get("cmimi_col")
    if pesha_col is None and cmimi_col is None:
        return meta

    if not row_indices:
        return meta

    n = len(row_indices)

    if pesha_col is not None and target_total_kg and target_total_kg > 0:
        weights = generate_weights(
            n,
            float(target_total_kg),
            cfg["pesha_min"],
            cfg["pesha_max"],
            cfg["pesha_common"],
        )
        for row_idx, weight in zip(row_indices, weights):
            df.iat[row_idx, pesha_col] = weight
        meta["pesha_sum"] = round(sum(weights), 2)
        meta["target_kg"] = float(target_total_kg)

    if cmimi_col is not None:
        prices = generate_prices(n, cfg["cmimi_min"], cfg["cmimi_max"])
        for row_idx, price in zip(row_indices, prices):
            df.iat[row_idx, cmimi_col] = price
        meta["cmimi_generated"] = True

    meta["applied"] = True
    meta["rows"] = n
    return meta
