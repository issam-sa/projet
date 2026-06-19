from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def _easter_sunday(year: int) -> date:
    """Algorithme de Butcher (computus grégorien) -> dimanche de Pâques."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def french_holidays(year: int) -> set[date]:
    """Jours fériés légaux français (métropole) pour une année donnée."""
    easter = _easter_sunday(year)
    movable = {
        easter + timedelta(days=1),  # Lundi de Pâques
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Lundi de Pentecôte
    }
    fixed = {
        date(year, 1, 1),  # Jour de l'an
        date(year, 5, 1),  # Fête du travail
        date(year, 5, 8),  # Victoire 1945
        date(year, 7, 14),  # Fête nationale
        date(year, 8, 15),  # Assomption
        date(year, 11, 1),  # Toussaint
        date(year, 11, 11),  # Armistice
        date(year, 12, 25),  # Noël
    }
    return fixed | movable


def make_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Construit les features exogènes pour le modèle.

    Toutes ces features sont **connues à l'avance** (calendrier), donc valides
    aussi bien à l'entraînement qu'à la prévision de pas futurs.
    """
    hour = index.hour.values.astype(float)
    dow = index.dayofweek.values.astype(float)
    minute = index.minute.values.astype(float)

    is_weekend = (dow >= 5).astype(float)
    years = set(int(y) for y in np.unique(index.year.values))
    holidays: set[date] = set()
    for y in years:
        holidays |= french_holidays(y)
    is_holiday = np.array([1.0 if d.date() in holidays else 0.0 for d in index], dtype=float)
    # Pics d'heure de pointe (matin ~8h, soir ~18h)
    is_rush = (((hour >= 7) & (hour <= 9)) | ((hour >= 17) & (hour <= 19))).astype(float)

    return pd.DataFrame(
        {
            "hour": hour,
            "dow": dow,
            "minute": minute,
            "sin_hour": np.sin(2 * np.pi * hour / 24.0),
            "cos_hour": np.cos(2 * np.pi * hour / 24.0),
            "sin_dow": np.sin(2 * np.pi * dow / 7.0),
            "cos_dow": np.cos(2 * np.pi * dow / 7.0),
            "sin_min": np.sin(2 * np.pi * minute / 60.0),
            "cos_min": np.cos(2 * np.pi * minute / 60.0),
            "is_weekend": is_weekend,
            "is_holiday": is_holiday,
            "is_rush": is_rush,
        },
        index=index,
    )
