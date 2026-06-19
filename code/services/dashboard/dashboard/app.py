from __future__ import annotations

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from api_client import ApiClient
from utils import hourly_mean, parse_ts, to_time_df

st.set_page_config(page_title="Mobilité urbaine – Dashboard", layout="wide")

api = ApiClient()

st.title("Plateforme de mobilité urbaine (MVP)")
st.caption("Trafic, prédictions, environnement, corrélations et signalements citoyens.")

try:
    areas = api.get("/api/v1/areas").get("items", [])
except Exception as e:  # noqa: BLE001
    st.error(f"API injoignable: {e}")
    st.stop()

if not areas:
    st.error("Aucune zone disponible. Lancez l'ETL: `docker compose run --rm pipeline --mode sample --days 14`.")
    st.stop()

area_by_id = {a["id"]: a for a in areas}

# ---- Contrôles globaux ----
area_id = st.sidebar.selectbox(
    "Zone", options=list(area_by_id.keys()), format_func=lambda k: area_by_id[k]["name"]
)
history_hours = st.sidebar.slider("Historique (heures)", 6, 24 * 14, 72, step=6)
st.sidebar.caption("Astuce : exportez les données via les boutons « Exporter CSV ».")


def csv_button(df: pd.DataFrame, label: str, filename: str) -> None:
    if df is None or df.empty:
        return
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), filename, "text/csv")


def _fmt(value: object, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


tab_overview, tab_route, tab_env, tab_corr, tab_compare, tab_sim, tab_etl = st.tabs(
    ["Vue d'ensemble", "Itinéraire", "Environnement", "Corrélation", "Comparaison zones", "Simulation", "ETL"]
)

# ============================================================
# Onglet 1 — Vue d'ensemble
# ============================================================
with tab_overview:
    col1, col2, col3 = st.columns(3)

    try:
        latest = api.get("/api/v1/traffic/latest", params={"area_id": area_id})
    except Exception:  # noqa: BLE001
        latest = None

    with col1:
        st.subheader("État trafic")
        if latest:
            st.metric("Congestion (0–1)", f"{float(latest['congestion_index']):.2f}")
            st.caption(f"Dernière mesure: {latest['ts']}")
            if latest.get("speed_kph") is not None:
                st.metric("Vitesse (km/h)", f"{float(latest['speed_kph']):.0f}")
        else:
            st.info("Pas de donnée trafic (encore).")

    with col2:
        st.subheader("Recommandations")
        try:
            rec = api.get("/api/v1/recommendations", params={"area_id": area_id})
            for item in rec.get("items", []):
                st.write(f"- **{item['title']}** — {item['detail']}")
        except Exception as e:  # noqa: BLE001
            st.caption(f"Recommandations indisponibles: {e}")

    with col3:
        st.subheader("Signalement citoyen")
        with st.form("report"):
            category = st.selectbox(
                "Catégorie", ["accident", "chantier", "danger", "transport", "embouteillage", "autre"]
            )
            severity = st.slider("Sévérité (1–5)", 1, 5, 3)
            description = st.text_input("Description (optionnel)")
            submitted = st.form_submit_button("Envoyer")
            if submitted:
                try:
                    api.post(
                        "/api/v1/crowd_reports",
                        json={
                            "area_id": area_id,
                            "category": category,
                            "severity": severity,
                            "description": description,
                        },
                    )
                    st.success("Signalement envoyé.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Échec envoi: {e}")

    st.divider()
    st.subheader("Carte des zones")
    df_areas = pd.DataFrame(areas)
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_areas,
        get_position="[lon, lat]",
        get_radius=220,
        get_fill_color=[30, 144, 255, 160],
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=float(area_by_id[area_id]["lat"]),
        longitude=float(area_by_id[area_id]["lon"]),
        zoom=10,
    )
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{name} ({id})"}))

    st.subheader("Carte thermique de congestion")
    try:
        overview = api.get("/api/v1/traffic/overview").get("items", [])
    except Exception:  # noqa: BLE001
        overview = []
    heat_df = pd.DataFrame(overview)
    if not heat_df.empty and "congestion_index" in heat_df.columns:
        heat_df = heat_df.dropna(subset=["congestion_index"])
        heat_layer = pdk.Layer(
            "HeatmapLayer",
            data=heat_df,
            get_position="[lon, lat]",
            get_weight="congestion_index",
            radius_pixels=90,
            aggregation="MEAN",
        )
        st.pydeck_chart(pdk.Deck(layers=[heat_layer], initial_view_state=view_state))
        st.caption("Intensité = congestion la plus récente par zone (bleu = fluide → rouge = saturé).")
    else:
        st.caption("Pas de données de congestion pour la carte thermique.")

    st.subheader("Prédiction de congestion")
    colp1, colp2 = st.columns(2)
    horizon = colp1.slider("Horizon (minutes)", 30, 240, 120, step=30)
    step = colp2.select_slider("Pas (minutes)", options=[5, 10, 15], value=5)

    try:
        pred = api.get(
            "/api/v1/predictions",
            params={"area_id": area_id, "horizon_minutes": horizon, "step_minutes": step},
        )
        pred_df = pd.DataFrame(pred.get("items", []))
    except Exception as e:  # noqa: BLE001
        pred_df = pd.DataFrame()
        st.caption(f"Prédictions indisponibles: {e}")

    if not pred_df.empty:
        pred_df["ts"] = pred_df["ts"].apply(parse_ts)
        fig = px.line(pred_df, x="ts", y="congestion_index", title=f"Modèle: {pred.get('model')}")
        fig.update_yaxes(range=[0, 1])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas de prédictions (données insuffisantes).")

    st.subheader("Derniers signalements")
    reports = api.get("/api/v1/crowd_reports", params={"area_id": area_id, "limit": 50}).get("items", [])
    if reports:
        rep_df = pd.DataFrame(reports)
        st.dataframe(rep_df, use_container_width=True, hide_index=True)
        csv_button(rep_df, "Exporter CSV", f"signalements_{area_id}.csv")
    else:
        st.caption("Aucun signalement.")

# ============================================================
# Onglet 2 — Itinéraire avec prédiction des perturbations
# ============================================================
with tab_route:
    st.subheader("Itinéraire avec prédiction des perturbations")
    st.caption(
        "Saisissez un point de départ et une arrivée. Le trajet est coloré selon la "
        "congestion **prédite** (vert = fluide, orange = dense, rouge = saturé) à l'heure de passage."
    )
    rc1, rc2, rc3 = st.columns([2, 2, 1])
    origin_addr = rc1.text_input("Départ", "Tour Eiffel, Paris")
    dest_addr = rc2.text_input("Arrivée", "Gare du Nord, Paris")
    depart_in = rc3.number_input("Départ dans (min)", min_value=0, max_value=240, value=0, step=15)

    if st.button("Calculer l'itinéraire", type="primary"):
        with st.spinner("Calcul de l'itinéraire et des perturbations…"):
            try:
                route = api.post(
                    "/api/v1/route",
                    json={
                        "origin": origin_addr,
                        "destination": dest_addr,
                        "depart_in_minutes": int(depart_in),
                    },
                )
                st.session_state["route_result"] = route
            except Exception as e:  # noqa: BLE001
                st.session_state["route_result"] = None
                st.error(f"Impossible de calculer l'itinéraire : {e}")

    route = st.session_state.get("route_result")
    if route and route.get("routes"):
        routes = route["routes"]
        o = route["origin"]
        d = route["destination"]

        # Tableau comparatif des itinéraires proposés
        st.markdown("**Itinéraires proposés** (triés par durée prévue, perturbations incluses) :")
        recap = pd.DataFrame(
            [
                {
                    "Itinéraire": r["label"] + (" ⚡" if r.get("fastest") else ""),
                    "Distance (km)": r["distance_km"],
                    "Durée normale (min)": r["duration_min"],
                    "Durée prévue (min)": r["duration_adjusted_min"],
                    "Retard (min)": r["delay_min"],
                }
                for r in routes
            ]
        )
        st.dataframe(recap, use_container_width=True, hide_index=True)

        if len(routes) == 1:
            st.caption(
                "OSRM n'a pas proposé d'alternative pour ce trajet. "
                "Essayez par ex. « Trocadéro, Paris » → « Bastille, Paris » pour comparer plusieurs routes."
            )

        # L'utilisateur choisit son itinéraire (le plus rapide est sélectionné par défaut)
        def _route_label(i: int) -> str:
            r = routes[i]
            tag = " ⚡ le plus rapide" if r.get("fastest") else ""
            return f"{r['label']} — {r['duration_adjusted_min']} min prévues, {r['distance_km']} km{tag}"

        choice = st.radio(
            "Choisissez votre itinéraire :",
            options=list(range(len(routes))),
            format_func=_route_label,
            index=0,
        )
        sel = routes[choice]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Distance", f"{sel['distance_km']} km")
        m2.metric("Durée normale", f"{sel['duration_min']} min")
        m3.metric("Durée prévue", f"{sel['duration_adjusted_min']} min")
        delay = sel["delay_min"]
        m4.metric("Retard estimé", f"+{delay} min", delta=f"{delay} min", delta_color="inverse")

        seg_df = pd.DataFrame(
            [
                {
                    "path": s["path"],
                    "color": s["color"],
                    "zone": s["zone_name"],
                    "congestion": s["congestion"] if s["congestion"] is not None else "—",
                }
                for s in sel.get("segments", [])
            ]
        )
        endpoints_df = pd.DataFrame(
            [
                {"lon": o["lon"], "lat": o["lat"], "label": "Départ", "color": [0, 100, 255]},
                {"lon": d["lon"], "lat": d["lat"], "label": "Arrivée", "color": [150, 0, 200]},
            ]
        )
        path_layer = pdk.Layer(
            "PathLayer", data=seg_df, get_path="path", get_color="color",
            width_min_pixels=6, pickable=True,
        )
        points_layer = pdk.Layer(
            "ScatterplotLayer", data=endpoints_df, get_position="[lon, lat]",
            get_radius=120, get_fill_color="color", pickable=True,
        )
        view = pdk.ViewState(
            latitude=(o["lat"] + d["lat"]) / 2, longitude=(o["lon"] + d["lon"]) / 2, zoom=12
        )
        st.pydeck_chart(
            pdk.Deck(
                layers=[path_layer, points_layer],
                initial_view_state=view,
                tooltip={"text": "{zone} — congestion {congestion}"},
            )
        )

        st.markdown("**Zones traversées et congestion prédite :**")
        zt = sel.get("zones_traversed", [])
        if zt:
            st.dataframe(pd.DataFrame(zt), use_container_width=True, hide_index=True)
        st.caption(f"Modèle de prédiction : {route.get('model', 'n/a')}")
    else:
        st.info("Saisissez deux adresses puis cliquez sur « Calculer l'itinéraire ».")


# ============================================================
# Onglet 3 — Environnement
# ============================================================
with tab_env:
    st.subheader("Qualité de l'air & météo")
    try:
        env_latest = api.get("/api/v1/environment/latest", params={"area_id": area_id})
    except Exception:  # noqa: BLE001
        env_latest = None

    if env_latest:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PM2.5 (µg/m³)", f"{_fmt(env_latest.get('pm2_5'))}")
        c2.metric("NO₂ (µg/m³)", f"{_fmt(env_latest.get('no2'))}")
        c3.metric("AQI (US)", f"{_fmt(env_latest.get('us_aqi'))}")
        c4.metric("Température (°C)", f"{_fmt(env_latest.get('temperature_c'))}")
    else:
        st.info("Pas de données environnementales. Lancez `--mode open-meteo` ou `--mode sample`.")

    env_items = api.get("/api/v1/environment/series", params={"area_id": area_id, "hours": history_hours}).get(
        "items", []
    )
    env_df = to_time_df(env_items)
    if not env_df.empty:
        pollutants = [c for c in ["pm2_5", "no2", "o3", "us_aqi"] if c in env_df.columns]
        if pollutants:
            long = env_df.melt(id_vars="ts", value_vars=pollutants, var_name="polluant", value_name="valeur")
            fig = px.line(long, x="ts", y="valeur", color="polluant", title="Polluants atmosphériques")
            st.plotly_chart(fig, use_container_width=True)
        if "temperature_c" in env_df.columns:
            fig_t = px.line(env_df, x="ts", y="temperature_c", title="Température (°C)")
            st.plotly_chart(fig_t, use_container_width=True)
        csv_button(env_df, "Exporter CSV", f"environnement_{area_id}.csv")
    else:
        st.info("Aucune série environnementale sur la période sélectionnée.")

# ============================================================
# Onglet 4 — Corrélation trafic ↔ pollution
# ============================================================
with tab_corr:
    st.subheader("Corrélation trafic ↔ pollution")
    st.caption("Trafic et environnement ré-échantillonnés à l'heure puis alignés sur l'horodatage.")

    traffic_items = api.get(
        "/api/v1/traffic/series", params={"area_id": area_id, "hours": history_hours}
    ).get("items", [])
    env_items = api.get(
        "/api/v1/environment/series", params={"area_id": area_id, "hours": history_hours}
    ).get("items", [])

    traffic_h = hourly_mean(to_time_df(traffic_items), ["congestion_index", "volume_veh_h"])
    env_h = hourly_mean(to_time_df(env_items), ["pm2_5", "no2", "o3", "us_aqi"])

    if traffic_h.empty or env_h.empty:
        st.info("Données insuffisantes pour la corrélation (besoin de trafic ET d'environnement sur la même zone).")
    else:
        merged = traffic_h.merge(env_h, on="ts", how="inner")
        if merged.empty:
            st.info("Aucune plage horaire commune entre trafic et environnement.")
        else:
            num_cols = [c for c in merged.columns if c != "ts"]
            corr = merged[num_cols].corr(numeric_only=True)
            st.write("Matrice de corrélation (Pearson) :")
            st.dataframe(corr.style.format("{:.2f}"), use_container_width=True)

            y_choices = [c for c in ["us_aqi", "pm2_5", "no2", "o3"] if c in merged.columns]
            if y_choices:
                y_col = st.selectbox("Polluant à corréler", y_choices)
                fig = px.scatter(
                    merged,
                    x="congestion_index",
                    y=y_col,
                    title=f"Congestion vs {y_col}",
                    opacity=0.6,
                )
                st.plotly_chart(fig, use_container_width=True)
                r = merged["congestion_index"].corr(merged[y_col])
                st.metric(f"Corrélation congestion ↔ {y_col}", f"{r:.2f}")
            csv_button(merged, "Exporter CSV (données alignées)", f"correlation_{area_id}.csv")

# ============================================================
# Onglet 5 — Comparaison de zones
# ============================================================
with tab_compare:
    st.subheader("Comparaison de la congestion entre zones")
    selected = st.multiselect(
        "Zones à comparer",
        options=list(area_by_id.keys()),
        default=list(area_by_id.keys())[: min(3, len(area_by_id))],
        format_func=lambda k: area_by_id[k]["name"],
    )
    frames = []
    for aid in selected:
        items = api.get("/api/v1/traffic/series", params={"area_id": aid, "hours": history_hours}).get(
            "items", []
        )
        d = to_time_df(items)
        if not d.empty and "congestion_index" in d.columns:
            d = d[["ts", "congestion_index"]].copy()
            d["zone"] = area_by_id[aid]["name"]
            frames.append(d)

    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        fig = px.line(all_df, x="ts", y="congestion_index", color="zone", title="Congestion comparée")
        fig.update_yaxes(range=[0, 1])
        st.plotly_chart(fig, use_container_width=True)

        st.write("Congestion moyenne sur la période :")
        summary = (
            all_df.groupby("zone")["congestion_index"].mean().reset_index().sort_values("congestion_index", ascending=False)
        )
        st.dataframe(summary.style.format({"congestion_index": "{:.2f}"}), use_container_width=True, hide_index=True)
        csv_button(all_df, "Exporter CSV", "comparaison_zones.csv")
    else:
        st.info("Sélectionnez au moins une zone disposant de données trafic.")

# ============================================================
# Onglet 6 — Simulation what-if (gestionnaire)
# ============================================================
with tab_sim:
    st.subheader("Simulation what-if — pilotage gestionnaire")
    st.caption(
        "Estimez l'impact d'une réduction du volume de trafic sur la congestion. "
        "Modèle proxy documenté : congestion × (1 − réduction)^β."
    )
    reduction = st.slider("Réduction du volume de trafic (%)", 0, 50, 10, step=5)
    try:
        sim = api.get("/api/v1/simulation", params={"reduction_pct": reduction})
    except Exception as e:  # noqa: BLE001
        sim = None
        st.error(f"Simulation indisponible : {e}")

    if sim and sim.get("items"):
        s1, s2, s3 = st.columns(3)
        s1.metric("Congestion moyenne actuelle", f"{sim['avg_congestion_current']:.2f}")
        s2.metric(
            "Congestion moyenne simulée",
            f"{sim['avg_congestion_simulated']:.2f}",
            delta=f"-{sim['avg_congestion_drop_pct']}%",
            delta_color="inverse",
        )
        s3.metric("Gain de temps estimé", f"{sim['est_time_gain_pct']} %")

        sim_df = pd.DataFrame(sim["items"])
        long = sim_df.melt(
            id_vars=["name"],
            value_vars=["congestion_current", "congestion_simulated"],
            var_name="scénario",
            value_name="congestion",
        )
        long["scénario"] = long["scénario"].map(
            {"congestion_current": "Actuel", "congestion_simulated": f"Simulé (-{reduction}%)"}
        )
        fig = px.bar(
            long, x="name", y="congestion", color="scénario", barmode="group",
            title=f"Impact d'une réduction de {reduction}% du volume",
        )
        fig.update_yaxes(range=[0, 1])
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(sim_df, use_container_width=True, hide_index=True)
        csv_button(sim_df, "Exporter CSV", f"simulation_{reduction}pct.csv")
    elif sim:
        st.info("Pas de données de trafic pour simuler. Lancez l'ETL.")


# ============================================================
# Onglet 7 — Historique ETL
# ============================================================
with tab_etl:
    st.subheader("Historique des exécutions ETL")
    try:
        runs = api.get("/api/v1/etl/runs", params={"limit": 50}).get("items", [])
    except Exception as e:  # noqa: BLE001
        runs = []
        st.caption(f"Indisponible: {e}")
    if runs:
        runs_df = pd.DataFrame(runs)
        st.dataframe(runs_df, use_container_width=True, hide_index=True)
        csv_button(runs_df, "Exporter CSV", "etl_runs.csv")
    else:
        st.info("Aucune exécution ETL enregistrée pour l'instant.")
