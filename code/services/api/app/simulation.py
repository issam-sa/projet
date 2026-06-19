from __future__ import annotations

# Simulation "what-if" pour gestionnaires urbains.
#
# Modèle proxy documenté reliant une réduction du volume de trafic à la congestion :
#     congestion_simulée = congestion_actuelle × (1 - réduction)^β
# β (>0) règle la sensibilité : β=1 => effet linéaire, β<1 => effet atténué.
# Le temps de trajet est approximé par t ∝ 1/(1 - congestion) (forme type BPR).


def simulate_congestion(current: float, reduction_pct: float, beta: float = 0.8) -> float:
    factor = max(0.0, 1.0 - reduction_pct / 100.0) ** beta
    return max(0.0, min(1.0, current * factor))


def _travel_proxy(congestion: float) -> float:
    return 1.0 / max(0.05, 1.0 - congestion)


def simulate_zones(zones_latest: list[dict], reduction_pct: float, beta: float = 0.8) -> dict:
    items: list[dict] = []
    sum_before = sum_after = 0.0
    n = 0
    for z in zones_latest:
        c0 = z.get("congestion_index")
        if c0 is None:
            continue
        c0 = float(c0)
        c1 = simulate_congestion(c0, reduction_pct, beta)
        items.append(
            {
                "area_id": z.get("area_id"),
                "name": z.get("name"),
                "congestion_current": round(c0, 3),
                "congestion_simulated": round(c1, 3),
                "delta": round(c1 - c0, 3),
            }
        )
        sum_before += c0
        sum_after += c1
        n += 1

    avg_before = sum_before / n if n else 0.0
    avg_after = sum_after / n if n else 0.0
    tb, ta = _travel_proxy(avg_before), _travel_proxy(avg_after)
    time_gain = (tb - ta) / tb * 100.0 if tb > 0 else 0.0

    return {
        "reduction_pct": reduction_pct,
        "beta": beta,
        "zones": n,
        "avg_congestion_current": round(avg_before, 3),
        "avg_congestion_simulated": round(avg_after, 3),
        "avg_congestion_drop_pct": round((avg_before - avg_after) / avg_before * 100.0, 1) if avg_before > 0 else 0.0,
        "est_time_gain_pct": round(time_gain, 1),
        "items": items,
    }
