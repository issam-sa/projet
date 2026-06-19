from __future__ import annotations

from datetime import datetime, timezone

from app.models import get_latest_traffic, list_crowd_reports
from app.predictors import forecast

# Facteur proxy reliant la baisse de congestion évitée à un gain d'empreinte
# relatif. Ce n'est PAS une mesure d'émissions réelle (faute de facteurs
# d'émission par véhicule) mais un indicateur relatif documenté :
#   gain_proxy = (congestion_actuelle - congestion_creux) * CO2_PROXY_FACTOR
CO2_PROXY_FACTOR = 100.0
PEAK_THRESHOLD = 0.7  # au-dessus : congestion considérée comme forte


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def recommend(area_id: str) -> dict:
    latest = get_latest_traffic(area_id)
    if not latest:
        return {"area_id": area_id, "generated_at": _now(), "items": [], "confidence": "low"}

    fc = forecast(area_id, horizon_minutes=120, step_minutes=5)
    points = fc.points
    if not points:
        return {"area_id": area_id, "generated_at": _now(), "items": [], "confidence": "low"}

    best = min(points, key=lambda p: p["congestion_index"])
    worst = max(points, key=lambda p: p["congestion_index"])
    current_ci = float(latest["congestion_index"])

    items: list[dict] = []

    # 1) Recommandation de timing si un pic est prévu.
    if float(worst["congestion_index"]) >= PEAK_THRESHOLD:
        items.append(
            {
                "type": "timing",
                "title": "Décaler le départ",
                "detail": (
                    f"Pic de congestion prévu (~{float(worst['congestion_index']):.2f}). "
                    f"Fenêtre la plus favorable vers {best['ts']} (~{float(best['congestion_index']):.2f})."
                ),
                "why": "La prévision indique une congestion nettement plus faible en dehors du pic.",
            }
        )

    # 2) Recommandation écologique (proxy documenté).
    eco_gain = max(0.0, (current_ci - float(best["congestion_index"])) * CO2_PROXY_FACTOR)
    items.append(
        {
            "type": "eco",
            "title": "Recommandation écologique",
            "detail": (
                f"En évitant le pic, gain d'empreinte relatif estimé ≈ {eco_gain:.0f} (proxy, "
                f"facteur={CO2_PROXY_FACTOR:.0f})."
            ),
            "why": "Moins de congestion ⇒ moins d'arrêts/redémarrages ⇒ proxy d'émissions plus faible.",
        }
    )

    # 3) Vigilance basée sur les signalements citoyens récents (crowdsourcing).
    reports = list_crowd_reports(area_id=area_id, limit=20)
    open_high = [r for r in reports if r.get("status") == "open" and int(r.get("severity", 0)) >= 4]
    if open_high:
        cats = sorted({r.get("category", "autre") for r in open_high})
        items.append(
            {
                "type": "safety",
                "title": "Vigilance signalements",
                "detail": f"{len(open_high)} signalement(s) sévère(s) en cours : {', '.join(cats)}.",
                "why": "Des incidents citoyens non résolus peuvent dégrader les conditions réelles.",
            }
        )

    # Confiance : proportionnelle à l'amplitude prévue (signal exploitable).
    spread = float(worst["congestion_index"]) - float(best["congestion_index"])
    confidence = "high" if spread >= 0.25 else "medium" if spread >= 0.1 else "low"

    return {
        "area_id": area_id,
        "generated_at": _now(),
        "model": fc.model_name,
        "confidence": confidence,
        "items": items,
    }
