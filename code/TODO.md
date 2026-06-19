# TODO – Améliorations (post-MVP)

## 1) Données réelles (open data)
- Remplacer/compléter le mode `sample` par au moins 3 catégories de données **réelles** :
  - Trafic temps réel (OpenDataSoft / Data.gouv / sources locales)
  - Transports publics (GTFS + perturbations si dispo)
  - Environnement (Open-Meteo déjà OK; ajouter une source locale type Airparif si souhaité)
- Ajouter une couche “qualité des données” : déduplication, valeurs manquantes, contrôles de plage, logs.
- Versionner les jeux de données (metadata, date de collecte, licences, fréquence de mise à jour).

## 2) Pipeline & orchestration
- Planifier l’ETL (cron / Airflow / Prefect) et historiser les exécutions.
- Ajouter des tables “staging” + “curated” (bronze/silver/gold).
- Ajouter une stratégie de rétention (ex: 90 jours) + index/partitions si volumétrie augmente.

## 3) Modélisation trafic (hybride)
- Évaluer plusieurs variantes (SARIMAX/Prophet, LSTM/GRU) et comparer via métriques (MAE/RMSE/MAPE).
- Ajouter features exogènes (météo, jour férié, événements, signalements citoyens).
- Mettre en place un “train” périodique + stockage du modèle (artifact) + versioning.
- Ajouter un cache (Redis) ou cache DB pour éviter de refitter souvent.

## 4) Recommandations intelligentes
- Ajouter un score multi-critères (temps, fiabilité, CO₂ proxy, confort).
- Prendre en compte transports publics (GTFS) pour proposer alternatives intermodales.
- Ajouter explications (why) + niveaux de confiance sur les recommandations.

## 5) Dashboard (web)
- Ajouter vues environnement (AQI/PM2.5/NO2) + corrélations trafic ↔ pollution.
- Ajouter une “simulation” simple (ex: réduction volume -10% → impact congestion proxy).
- Ajouter filtres temporels, comparaison entre zones, export CSV.

## 6) API & sécurité
- Ajouter pagination, validation plus stricte, codes d’erreur uniformes.
- Ajouter authentification (API key / JWT) si besoin.
- Ajouter rate limiting + CORS paramétrable + logs structurés.

## 7) Observabilité / performance / Green IT
- Ajouter métriques (latence, taux d’erreur), Prometheus + Grafana.
- Ajouter traces/logs (OpenTelemetry).
- Mesurer consommation (CPU/RAM) et fixer objectifs (KPIs Green IT).

## 8) Tests & qualité
- Ajouter tests unitaires (ETL, API) + tests d’intégration (API+DB).
- Ajouter lint/format (ruff/black) + pré-commit.
- Ajouter CI GitHub Actions (build, tests, sécurité).

## 9) Livrables école
- Rédiger rapport technique (architecture, données, modèles, résultats, limites).
- Préparer vidéo (démo dashboard + endpoints + pipeline + perspectives).

