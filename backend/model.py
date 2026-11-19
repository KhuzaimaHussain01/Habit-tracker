import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import joblib
import pandas as pd

FEATURE_COLUMNS = [
    "streak_length",
    "completion_rate_7d",
    "completion_rate_30d",
    "days_since_last_miss",
    "day_of_week_tomorrow",
    "is_weekend_tomorrow",
    "yesterday_done",
]

_MODEL_CACHE = None

# Default probability returned when the model is unavailable
DEFAULT_PROBABILITY = 0.5


def get_model_path() -> Path:
    if os.getenv("VERCEL"):
        return Path("/tmp/model.joblib")
    return Path(__file__).resolve().parent / "model.joblib"


def load_model():
    """
    Lazily loads the model. If model.joblib is missing, attempts to train
    from data/habit_history.csv. Returns None if training also fails.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        model_path = get_model_path()
        if not model_path.exists():
            try:
                from train import train_model
                print("model.joblib missing, training model automatically...")
                train_model()
            except Exception as e:
                print(f"[WARN] Could not train model: {e}. Using default probability.")
                return None
        try:
            _MODEL_CACHE = joblib.load(model_path)
        except Exception as e:
            print(f"[WARN] Could not load model: {e}. Using default probability.")
            return None
    return _MODEL_CACHE


def build_features_from_history(
    checkin_map: Dict[str, bool],
    today: Optional[date] = None,
) -> pd.DataFrame:
    """
    Builds the exact feature row matching the training data from a habit's
    real check-in history to predict completion probability for tomorrow.
    """
    if today is None:
        today = date.today()

    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)

    today_str = today.isoformat()
    yesterday_str = yesterday.isoformat()

    today_done = bool(checkin_map.get(today_str, False))
    yesterday_done = 1 if bool(checkin_map.get(yesterday_str, False)) else 0

    # 1. streak_length ending at today
    if today_done:
        current_date = today
        streak_length = 0
        while bool(checkin_map.get(current_date.isoformat(), False)):
            streak_length += 1
            current_date -= timedelta(days=1)
    else:
        streak_length = 0

    # 2. completion_rate_7d (last 7 days ending today)
    completed_7d = sum(
        1 for i in range(7)
        if bool(checkin_map.get((today - timedelta(days=i)).isoformat(), False))
    )
    completion_rate_7d = round(completed_7d / 7.0, 4)

    # 3. completion_rate_30d (last 30 days ending today)
    completed_30d = sum(
        1 for i in range(30)
        if bool(checkin_map.get((today - timedelta(days=i)).isoformat(), False))
    )
    completion_rate_30d = round(completed_30d / 30.0, 4)

    # 4. days_since_last_miss
    if not today_done:
        days_since_last_miss = 0
    else:
        days_since_last_miss = 0
        for i in range(1, 365):
            d_str = (today - timedelta(days=i)).isoformat()
            if not bool(checkin_map.get(d_str, False)):
                days_since_last_miss = i
                break
        else:
            days_since_last_miss = 365

    # 5. day_of_week_tomorrow (0 = Monday, ..., 6 = Sunday)
    day_of_week_tomorrow = tomorrow.weekday()

    # 6. is_weekend_tomorrow (Saturday or Sunday)
    is_weekend_tomorrow = 1 if day_of_week_tomorrow in (5, 6) else 0

    feature_data = {
        "streak_length": [streak_length],
        "completion_rate_7d": [completion_rate_7d],
        "completion_rate_30d": [completion_rate_30d],
        "days_since_last_miss": [days_since_last_miss],
        "day_of_week_tomorrow": [day_of_week_tomorrow],
        "is_weekend_tomorrow": [is_weekend_tomorrow],
        "yesterday_done": [yesterday_done],
    }

    return pd.DataFrame(feature_data, columns=FEATURE_COLUMNS)


def predict_tomorrow_proba(
    checkin_history: Union[Dict[str, bool], List[Dict[str, Any]]],
    today: Optional[date] = None,
) -> float:
    """
    Given a habit's check-in history, extracts features and returns the
    model's predicted probability of completion tomorrow. Falls back to
    DEFAULT_PROBABILITY if the model is unavailable.
    """
    if isinstance(checkin_history, list):
        checkin_map = {item["date"]: bool(item["done"]) for item in checkin_history}
    else:
        checkin_map = {k: bool(v) for k, v in checkin_history.items()}

    model = load_model()
    if model is None:
        return DEFAULT_PROBABILITY

    features_df = build_features_from_history(checkin_map, today=today)

    # predict_proba returns [[P(miss), P(done)]]
    probabilities = model.predict_proba(features_df)
    prob_completed_tomorrow = float(probabilities[0][1])

    return prob_completed_tomorrow


def predict_for_habit_id(habit_id: int, today: Optional[date] = None) -> float:
    """
    Convenience function that queries the SQLite database for a habit's check-ins
    and predicts tomorrow's completion probability.
    """
    import sqlite3
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT date, done FROM checkins WHERE habit_id = ? ORDER BY date ASC;",
        (habit_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    checkin_map = {row["date"]: bool(row["done"]) for row in rows}
    return predict_tomorrow_proba(checkin_map, today=today)
