from __future__ import annotations

"""Gjenerim random Pesha/kg dhe Çmimi për rreshtat e listës."""
import random
from typing import Any

from database import normalize_business_name


DEFAULT_RANDOM_COLUMNS = {
    "enabled": True,
    "pesha_min": 0.50,
    "pesha_max": 0.96,
    "pesha_common": [0.55, 0.60, 0.53, 0.58, 0.65, 0.68, 0.70, 0.74, 0.80],
    "cmimi_min": 15,
    "cmimi_max": 22,
    "business_pesha_ranges": [],
}


def _optional_int(value) -> int | None:
    text = str(value if value is not None else "").strip().replace(",", ".")
    if text == "":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _normalize_business_ranges(raw) -> list[dict]:
    """Lista e ranges: [{business, pesha_min, pesha_max, cmimi_min?, cmimi_max?}, ...].

    Çmimi është opsional — nëse mungon, përdoret range-i default i çmimit.
    """
    if not isinstance(raw, list):
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("business") or item.get("name") or "").strip()
        if not name:
            continue
        key = normalize_business_name(name)
        if key in seen:
            continue
        try:
            lo = float(str(item.get("pesha_min", item.get("min", ""))).replace(",", "."))
            hi = float(str(item.get("pesha_max", item.get("max", ""))).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if lo <= 0 or hi <= 0:
            continue
        if lo > hi:
            lo, hi = hi, lo
        seen.add(key)
        entry = {
            "business": name,
            "pesha_min": round(lo, 2),
            "pesha_max": round(hi, 2),
            "cmimi_min": None,
            "cmimi_max": None,
        }
        cmimi_lo = _optional_int(item.get("cmimi_min"))
        cmimi_hi = _optional_int(item.get("cmimi_max"))
        if cmimi_lo is not None and cmimi_hi is not None:
            if cmimi_lo > cmimi_hi:
                cmimi_lo, cmimi_hi = cmimi_hi, cmimi_lo
            entry["cmimi_min"] = cmimi_lo
            entry["cmimi_max"] = cmimi_hi
        out.append(entry)
    return out


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
    cfg["business_pesha_ranges"] = _normalize_business_ranges(cfg.get("business_pesha_ranges"))
    return cfg


def business_pesha_lookup(cfg: dict) -> dict[str, tuple[float, float]]:
    """normalized business name → (pesha_min, pesha_max)."""
    lookup: dict[str, tuple[float, float]] = {}
    for item in cfg.get("business_pesha_ranges") or []:
        name = str(item.get("business") or "").strip()
        if not name:
            continue
        lookup[normalize_business_name(name)] = (
            float(item["pesha_min"]),
            float(item["pesha_max"]),
        )
    return lookup


def business_cmimi_lookup(cfg: dict) -> dict[str, tuple[int, int]]:
    """normalized business name → (cmimi_min, cmimi_max). Vetëm ku çmimi është caktuar."""
    lookup: dict[str, tuple[int, int]] = {}
    for item in cfg.get("business_pesha_ranges") or []:
        name = str(item.get("business") or "").strip()
        if not name:
            continue
        lo = item.get("cmimi_min")
        hi = item.get("cmimi_max")
        if lo is None or hi is None:
            continue
        lookup[normalize_business_name(name)] = (int(lo), int(hi))
    return lookup


def _row_business_key(df, row_idx: int, sh_col: int | None) -> str:
    if sh_col is None:
        return ""
    raw = df.iat[row_idx, sh_col]
    biz_name = "" if raw is None else str(raw).strip()
    return normalize_business_name(biz_name) if biz_name else ""


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


def _expand_row_bounds(
    mins: list[float],
    maxs: list[float],
    target_total: float,
    locked: list[bool] | None = None,
) -> tuple[list[float], list[float]]:
    """Zgjero bounds vetëm për rreshtat e hapur (range biznesi locked mbetet strikt)."""
    count = len(mins)
    if count == 0:
        return mins, maxs

    flags = locked if locked is not None else [False] * count
    unlocked = [i for i, is_locked in enumerate(flags) if not is_locked]
    if not unlocked:
        return mins, maxs

    locked_min_sum = sum(mins[i] for i, is_locked in enumerate(flags) if is_locked)
    locked_max_sum = sum(maxs[i] for i, is_locked in enumerate(flags) if is_locked)
    unlocked_count = len(unlocked)

    # Target që duhet ta mbajnë rreshtat e hapur, në dy skajet e mundshme të locked
    remain_low = target_total - locked_max_sum
    remain_high = target_total - locked_min_sum
    unlocked_min_sum = sum(mins[i] for i in unlocked)
    unlocked_max_sum = sum(maxs[i] for i in unlocked)

    if remain_high < unlocked_min_sum - 1e-9:
        avg_needed = remain_high / unlocked_count
        floor = max(0.01, round(avg_needed * 0.55, 2))
        for i in unlocked:
            if mins[i] > avg_needed:
                mins[i] = floor

    if remain_low > unlocked_max_sum + 1e-9:
        avg_needed = remain_low / unlocked_count
        ceiling = round(max(avg_needed * 1.45, avg_needed + 0.01), 2)
        for i in unlocked:
            if maxs[i] < avg_needed:
                maxs[i] = ceiling

    if target_total < sum(mins) - 1e-9:
        avg_needed = target_total / count
        floor = max(0.01, round(avg_needed * 0.55, 2))
        for i in unlocked:
            if mins[i] > avg_needed:
                mins[i] = floor

    if target_total > sum(maxs) + 1e-9:
        avg_needed = target_total / count
        ceiling = round(avg_needed * 1.45, 2)
        for i in unlocked:
            if maxs[i] < avg_needed:
                maxs[i] = ceiling

    for i in range(count):
        if mins[i] > maxs[i]:
            mins[i], maxs[i] = maxs[i], mins[i]

    return mins, maxs


def _pick_weight_in_range(lo: float, hi: float, common: list[float] | None = None) -> float:
    """Një peshë random brenda [lo, hi], me preferencë për vlerat e shpeshta."""
    lo_f, hi_f = float(lo), float(hi)
    if lo_f > hi_f:
        lo_f, hi_f = hi_f, lo_f
    lo_c = int(round(lo_f * 100))
    hi_c = int(round(hi_f * 100))
    if lo_c > hi_c:
        lo_c, hi_c = hi_c, lo_c
    row_common = sorted(
        {
            int(round(c * 100))
            for c in (common or [])
            if lo_c <= int(round(c * 100)) <= hi_c
        }
    )
    if row_common and random.random() < 0.78:
        return random.choice(row_common) / 100.0
    return random.randint(lo_c, hi_c) / 100.0


def _generate_weights_uniform(
    count: int,
    target_total: float,
    mins: list[float],
    maxs: list[float],
    common: list[float] | None = None,
) -> list[float]:
    """Shpërndan totalin brenda bounds të dhëna (të gjitha rreshtat e rregullueshme)."""
    if count <= 0:
        return []
    if count == 1:
        lo, hi = mins[0], maxs[0]
        return [round(max(lo, min(hi, target_total)), 2)]

    min_cents = [int(round(m * 100)) for m in mins]
    max_cents = [int(round(m * 100)) for m in maxs]
    for i in range(count):
        if min_cents[i] > max_cents[i]:
            min_cents[i], max_cents[i] = max_cents[i], min_cents[i]

    target_c = int(round(target_total * 100))
    min_sum = sum(min_cents)
    max_sum = sum(max_cents)
    if target_c < min_sum or target_c > max_sum:
        raise ValueError(
            f"Nuk u arrit pesha totale {target_total} kg me ranges e dhëna."
        )

    cents: list[int] = []
    for i in range(count):
        lo_c, hi_c = min_cents[i], max_cents[i]
        row_common = sorted(
            {
                int(round(c * 100))
                for c in (common or [])
                if lo_c <= int(round(c * 100)) <= hi_c
            }
        )
        if row_common and random.random() < 0.78:
            cents.append(random.choice(row_common))
        else:
            cents.append(random.randint(lo_c, hi_c))

    total = sum(cents)
    if total <= 0:
        cents = list(min_cents)
        total = sum(cents)

    scaled = [
        max(min_cents[i], min(max_cents[i], int(round(cents[i] * target_c / total))))
        for i in range(count)
    ]
    diff = target_c - sum(scaled)
    order = list(range(count))
    random.shuffle(order)
    guard = 0
    while diff != 0 and guard < count * 5000:
        i = order[guard % count]
        if diff > 0 and scaled[i] < max_cents[i]:
            scaled[i] += 1
            diff -= 1
        elif diff < 0 and scaled[i] > min_cents[i]:
            scaled[i] -= 1
            diff += 1
        guard += 1

    if diff != 0:
        raise ValueError(
            f"Nuk u arrit pesha totale {target_total} kg me ranges e dhëna."
        )
    return [c / 100.0 for c in scaled]


def generate_weights(
    count: int,
    target_total: float,
    min_w: float,
    max_w: float,
    common: list[float] | None = None,
    row_bounds: list[tuple[float, float]] | None = None,
    locked_bounds: list[bool] | None = None,
) -> list[float]:
    """Gjeneron pesha random që në total japin target_total (kg).

    row_bounds opsionale: (min, max) për çdo rresht.
    locked_bounds: True = range biznesi strikt — vendoset random brenda range-it
    PARA shpërndarjes së totalit te rreshtat e tjerë (nuk shtypet te max).
    """
    if count <= 0:
        return []

    common = common or []
    flags = locked_bounds if locked_bounds is not None else [False] * count
    if len(flags) != count:
        flags = [False] * count

    # Pa ranges biznesi → sjellja klasike
    if row_bounds is None or not any(flags):
        if count == 1:
            return [round(max(min_w, min(max_w, target_total)), 2)]
        effective_min, effective_max = _validate_target_weight(
            count, target_total, min_w, max_w
        )
        return _generate_weights_uniform(
            count,
            target_total,
            [effective_min] * count,
            [effective_max] * count,
            common,
        )

    if len(row_bounds) != count:
        raise ValueError("row_bounds duhet të ketë të njëjtin numër si rreshtat.")

    mins: list[float] = []
    maxs: list[float] = []
    for lo, hi in row_bounds:
        lo_f, hi_f = float(lo), float(hi)
        if lo_f > hi_f:
            lo_f, hi_f = hi_f, lo_f
        mins.append(max(0.01, lo_f))
        maxs.append(max(0.01, hi_f))

    locked_idx = [i for i, is_locked in enumerate(flags) if is_locked]
    unlocked_idx = [i for i, is_locked in enumerate(flags) if not is_locked]

    # 1) Bizneset e konfiguruara: random strikt brenda range-it (nuk preket më vonë)
    weights = [0.0] * count
    for i in locked_idx:
        weights[i] = _pick_weight_in_range(mins[i], maxs[i], common)

    locked_sum = round(sum(weights[i] for i in locked_idx), 2)

    if not unlocked_idx:
        # Vetëm ranges biznesi — provo të përputhësh totalin brenda bounds strikte
        return _generate_weights_uniform(count, target_total, mins, maxs, common)

    remaining = round(float(target_total) - locked_sum, 2)
    if remaining <= 0:
        raise ValueError(
            f"Pesha totale {target_total} kg është shumë e vogël: "
            f"bizneset e konfiguruara zënë tashmë ~{locked_sum} kg."
        )

    # 2) Rreshtat e tjerë mbushin mbetjen (me expand nëse duhet)
    u_mins = [mins[i] for i in unlocked_idx]
    u_maxs = [maxs[i] for i in unlocked_idx]
    # expand vetëm unlocked
    u_mins, u_maxs = _expand_row_bounds(
        u_mins, u_maxs, remaining, locked=[False] * len(unlocked_idx)
    )
    u_min_sum = round(sum(u_mins), 2)
    u_max_sum = round(sum(u_maxs), 2)
    if remaining < u_min_sum - 1.0:
        raise ValueError(
            f"Pesha totale {target_total} kg është shumë e vogël për {count} rreshta "
            f"(pas ranges së bizneseve mbeten ~{remaining} kg, minimumi ~{u_min_sum:.0f} kg)."
        )
    if remaining > u_max_sum + 1.0:
        raise ValueError(
            f"Pesha totale {target_total} kg është shumë e madhe për {count} rreshta "
            f"(pas ranges së bizneseve mbeten ~{remaining} kg, maksimumi ~{u_max_sum:.0f} kg)."
        )

    unlocked_weights = _generate_weights_uniform(
        len(unlocked_idx), remaining, u_mins, u_maxs, common
    )
    for i, w in zip(unlocked_idx, unlocked_weights):
        weights[i] = w

    return weights


def generate_prices(
    count: int,
    min_p: int,
    max_p: int,
    row_bounds: list[tuple[int, int]] | None = None,
) -> list[int]:
    if count <= 0:
        return []
    if row_bounds is not None:
        if len(row_bounds) != count:
            raise ValueError("row_bounds për çmim duhet të ketë të njëjtin numër si rreshtat.")
        prices: list[int] = []
        for lo, hi in row_bounds:
            a, b = int(lo), int(hi)
            if a > b:
                a, b = b, a
            prices.append(random.randint(a, b))
        return prices
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
    meta: dict[str, Any] = {
        "applied": False,
        "rows": 0,
        "pesha_sum": 0.0,
        "business_ranges_used": 0,
        "business_cmimi_used": 0,
    }

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
    sh_col = mapping.get("shitesi_col")
    pesha_lookup = business_pesha_lookup(cfg)
    cmimi_lookup = business_cmimi_lookup(cfg)

    if pesha_col is not None and target_total_kg and target_total_kg > 0:
        row_bounds = None
        locked_bounds = None
        used_custom = 0
        if pesha_lookup:
            row_bounds = []
            locked_bounds = []
            for row_idx in row_indices:
                key = _row_business_key(df, row_idx, sh_col)
                if key and key in pesha_lookup:
                    row_bounds.append(pesha_lookup[key])
                    locked_bounds.append(True)  # range biznesi: strikt, nuk zgjerohet
                    used_custom += 1
                else:
                    row_bounds.append((cfg["pesha_min"], cfg["pesha_max"]))
                    locked_bounds.append(False)
            # Nëse asnjë rresht nuk përputhet me bizneset e konfiguruara → siç ka qenë
            if used_custom == 0:
                row_bounds = None
                locked_bounds = None

        weights = generate_weights(
            n,
            float(target_total_kg),
            cfg["pesha_min"],
            cfg["pesha_max"],
            cfg["pesha_common"],
            row_bounds=row_bounds,
            locked_bounds=locked_bounds,
        )
        for row_idx, weight in zip(row_indices, weights):
            df.iat[row_idx, pesha_col] = weight
        meta["pesha_sum"] = round(sum(weights), 2)
        meta["target_kg"] = float(target_total_kg)
        meta["business_ranges_used"] = used_custom

    if cmimi_col is not None:
        price_bounds = None
        used_cmimi = 0
        if cmimi_lookup:
            price_bounds = []
            for row_idx in row_indices:
                key = _row_business_key(df, row_idx, sh_col)
                if key and key in cmimi_lookup:
                    price_bounds.append(cmimi_lookup[key])
                    used_cmimi += 1
                else:
                    price_bounds.append((cfg["cmimi_min"], cfg["cmimi_max"]))
            if used_cmimi == 0:
                price_bounds = None

        prices = generate_prices(
            n, cfg["cmimi_min"], cfg["cmimi_max"], row_bounds=price_bounds
        )
        for row_idx, price in zip(row_indices, prices):
            df.iat[row_idx, cmimi_col] = price
        meta["cmimi_generated"] = True
        meta["business_cmimi_used"] = used_cmimi

    meta["applied"] = True
    meta["rows"] = n
    return meta
