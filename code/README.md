# Plateforme intelligente de mobilité urbaine (MVP)

MVP conforme au cahier des charges :
- Pipeline de données (ETL) avec couche **qualité** + historisation des exécutions
- Données réelles **OpenDataSoft** (trafic) + **Open-Meteo** (environnement) + mode `sample`
- Modèle prédictif trafic **hybride ARIMA + MLP** (features exogènes calendaires) + **évaluation** (MAE/RMSE/MAPE)
- API (Flask) durcie : validation, pagination, erreurs uniformes, logs JSON, rate limiting, CORS, **/metrics** Prometheus
- Dashboard interactif (Streamlit) : trafic, prédictions, **itinéraire A→B**, **carte thermique**, **simulation what-if**, **environnement**, **corrélations**, **comparaison de zones**, export CSV
- Crowdsourcing (signalements citoyens)
- Qualité logicielle : **tests pytest**, **ruff/black**, **pre-commit**, **CI GitHub Actions**

## Architecture
- `db/` : schéma PostgreSQL + PostGIS (+ table `etl_runs`)
- `services/pipeline/` : ETL (sources → qualité → chargement), modes `sample` / `open-meteo` / `ods`
- `services/api/` : API Flask (trafic, environnement, prédictions, évaluation, recommandations, signalements, ETL, métriques)
- `services/dashboard/` : Dashboard Streamlit multi-onglets

## Prérequis
- Docker Desktop (Windows) + Docker Compose

## Démarrage rapide (démo offline)
```bash
cp .env.example .env
docker compose up -d --build db api dashboard
docker compose build pipeline
docker compose run --rm pipeline --mode sample --days 14
```

Ouvrir :
- API : http://localhost:8000/health
- Métriques Prometheus : http://localhost:8000/metrics
- Dashboard : http://localhost:8501

## Sources de données

ETL environnement (Open-Meteo, sans clé) :
```bash
docker compose run --rm pipeline --mode open-meteo --hours 48
```

ETL trafic réel (OpenDataSoft) — renseigner `ODS_DATASET` dans `.env`
(ex. `comptages-routiers-permanents` sur `opendata.paris.fr`) :
```bash
docker compose run --rm pipeline --mode ods --max-records 5000
```
La série agrégée est rattachée à la zone `paris_ods`. Les noms de champs
(`ODS_FIELD_TS/FLOW/OCC`) sont paramétrables pour s'adapter à d'autres jeux.

## Endpoints API
- `GET /health`
- `GET /metrics` (Prometheus)
- `GET /api/v1/areas`
- `GET /api/v1/traffic/latest?area_id=paris_centre`
- `GET /api/v1/traffic/series?area_id=paris_centre&hours=72`
- `GET /api/v1/traffic/overview` (congestion la plus récente par zone — carte thermique)
- `GET /api/v1/simulation?reduction_pct=10` (simulation what-if gestionnaire)
- `GET /api/v1/environment/latest?area_id=paris_centre`
- `GET /api/v1/environment/series?area_id=paris_centre&hours=72`
- `GET /api/v1/predictions?area_id=paris_centre&horizon_minutes=120&step_minutes=5`
- `GET /api/v1/predictions/eval?area_id=paris_centre` (backtest MAE/RMSE/MAPE vs baseline naïve)
- `GET /api/v1/recommendations?area_id=paris_centre`
- `GET /api/v1/crowd_reports?area_id=paris_centre&limit=50&offset=0`
- `POST /api/v1/crowd_reports`
- `POST /api/v1/route` (itinéraire A→B avec prédiction des perturbations)
- `GET /api/v1/etl/runs?limit=50`

### Itinéraire avec prédiction des perturbations
Onglet **Itinéraire** du dashboard (ou `POST /api/v1/route`) : on saisit une adresse
de départ et d'arrivée. L'API calcule **plusieurs itinéraires alternatifs** (OSRM),
évalue pour chacun la **congestion prédite** (ARIMA+MLP) à l'heure de passage, puis les
**classe par durée prévue** (perturbations incluses). L'utilisateur **choisit son
itinéraire** ; le plus rapide est marqué ⚡. Chaque trajet est **coloré** selon la
congestion (vert/orange/rouge) et fournit distance, durée normale, **durée ajustée** et retard.
La réponse contient `routes` (liste triée) et `best_index`.

```bash
curl -X POST http://localhost:8000/api/v1/route \
  -H "Content-Type: application/json" \
  -d '{"origin":"Tour Eiffel, Paris","destination":"Gare du Nord, Paris","depart_in_minutes":0}'
```
> Nécessite un accès internet (géocodage Nominatim + routage OSRM). Serveurs de démo
> par défaut, paramétrables via `NOMINATIM_URL` / `OSRM_URL`. L'onglet est isolé :
> sans réseau, le reste du dashboard fonctionne normalement.

### Sécurité
- `CORS_ORIGINS` : origines autorisées (CSV).
- `API_KEY` : si défini, l'en-tête `X-API-Key` est exigé sur les écritures (POST).
- `RATE_LIMIT_DEFAULT` / `RATE_LIMIT_WRITE` : limites de débit.

## Qualité & tests (dev local)
```bash
pip install -r requirements-dev.txt
# Lint + format
ruff check .
ruff format --check .
# Tests (par service)
cd services/api && pip install -r requirements.txt && pytest
cd ../pipeline && pip install -r requirements.txt && pytest
cd ../dashboard && pip install -r requirements.txt && pytest
```
Hooks pre-commit :
```bash
pre-commit install
```
La CI GitHub Actions (`.github/workflows/ci.yml`) exécute lint + tests + audit des dépendances.

## Modélisation
- Hybride **ARIMA(2,0,2)** (tendance/saisonnalité) + **MLP** sur les résidus, avec
  features exogènes **calendaires** (heure, jour, week-end, jour férié FR, heure de pointe),
  valides aussi à l'inférence.
- Évaluation par **split temporel** : `GET /api/v1/predictions/eval?area_id=...`
  compare le modèle à une baseline **naïve saisonnière** (MAE / RMSE / MAPE).

## Dépannage Docker (Windows)
```bash
docker info
```
Si l'ETL affiche `exec: "--mode": executable file not found` :
```bash
docker compose build pipeline
docker compose run --rm pipeline --mode sample --days 14
```
