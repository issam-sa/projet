from datetime import date

import pandas as pd

from app.features import french_holidays, make_features


def test_french_holidays_2025():
    h = french_holidays(2025)
    assert date(2025, 1, 1) in h  # Jour de l'an
    assert date(2025, 12, 25) in h  # Noël
    assert date(2025, 7, 14) in h  # Fête nationale
    assert date(2025, 4, 21) in h  # Lundi de Pâques (Pâques = 20 avr. 2025)
    assert date(2025, 5, 29) in h  # Ascension
    assert date(2025, 3, 17) not in h  # jour ordinaire


def test_make_features_columns_and_flags():
    idx = pd.date_range("2025-01-04 08:00", periods=4, freq="h", tz="UTC")  # samedi
    feats = make_features(idx)
    expected = {
        "hour", "dow", "minute", "sin_hour", "cos_hour", "sin_dow", "cos_dow",
        "sin_min", "cos_min", "is_weekend", "is_holiday", "is_rush",
    }
    assert expected.issubset(feats.columns)
    # 4 janvier 2025 = samedi -> week-end
    assert feats["is_weekend"].iloc[0] == 1.0
    # 08:00 -> heure de pointe
    assert feats["is_rush"].iloc[0] == 1.0
