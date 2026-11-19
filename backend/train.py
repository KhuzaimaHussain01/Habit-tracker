import os
from pathlib import Path
import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "streak_length",
    "completion_rate_7d",
    "completion_rate_30d",
    "days_since_last_miss",
    "day_of_week_tomorrow",
    "is_weekend_tomorrow",
    "yesterday_done",
]
LABEL_COLUMN = "completed_next_day"


def train_model():
    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent

    # Locate dataset with robust fallback for Vercel deployments
    candidates = [
        root_dir / "data" / "habit_history.csv",
        backend_dir / "data" / "habit_history.csv",
        Path.cwd() / "data" / "habit_history.csv",
        Path("/var/task") / "data" / "habit_history.csv",
    ]
    data_path = next((p for p in candidates if p.exists()), None)
    if data_path is None:
        raise FileNotFoundError("Dataset not found in any expected location. Please run generate_data.py first.")

    print(f"Loading dataset from: {data_path}")
    df = pd.read_csv(data_path)

    X = df[FEATURE_COLUMNS]
    y = df[LABEL_COLUMN]

    # Stratified 80/20 train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # Scikit-learn Pipeline with StandardScaler and LogisticRegression
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(random_state=42, max_iter=1000)),
    ])

    pipeline.fit(X_train, y_train)

    # Predictions
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    # Metrics
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)

    print("\n--- Model Evaluation Metrics (Test Set) ---")
    print(f"Accuracy:  {acc:.4f} ({acc*100:.2f}%)")
    print(f"Precision: {prec:.4f} ({prec*100:.2f}%)")
    print(f"Recall:    {rec:.4f} ({rec*100:.2f}%)")
    print(f"ROC-AUC:   {auc:.4f}")
    print("------------------------------------------\n")

    # Save trained model to backend/model.joblib (or /tmp on Vercel)
    model_path = Path("/tmp/model.joblib") if os.getenv("VERCEL") else backend_dir / "model.joblib"
    joblib.dump(pipeline, model_path)
    print(f"Model saved to: {model_path}")

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "roc_auc": auc,
        "model_path": str(model_path),
    }


def retrain_with_real_checkins():
    """
    Retrains the model on the base CSV dataset plus all real check-ins
    from the SQLite database converted to the same feature schema.
    """
    import sqlite3
    from datetime import datetime

    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent

    # Locate base CSV dataset with robust fallback for Vercel deployments
    candidates_base = [
        root_dir / "data" / "habit_history.csv",
        backend_dir / "data" / "habit_history.csv",
        Path.cwd() / "data" / "habit_history.csv",
        Path("/var/task") / "data" / "habit_history.csv",
    ]
    data_path = next((p for p in candidates_base if p.exists()), None)
    if data_path is None:
        raise FileNotFoundError("Base dataset not found in any expected location.")

    df_base = pd.read_csv(data_path)

    # Query real checkins from SQLite database
    db_path = Path("/tmp/habits.db") if os.getenv("VERCEL") else backend_dir / "habits.db"
    real_rows = []

    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM habits;")
        habit_ids = [row["id"] for row in cursor.fetchall()]

        for h_id in habit_ids:
            cursor.execute(
                "SELECT date, done FROM checkins WHERE habit_id = ? ORDER BY date ASC;",
                (h_id,),
            )
            checkins = cursor.fetchall()

            n = len(checkins)
            if n < 2:
                continue

            for t in range(n - 1):
                cur_date_str = checkins[t]["date"]
                next_date_str = checkins[t + 1]["date"]

                try:
                    cur_date = datetime.strptime(cur_date_str, "%Y-%m-%d").date()
                    next_date = datetime.strptime(next_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                # 1. streak_length ending at t
                streak_len = 0
                for k in range(t, -1, -1):
                    if checkins[k]["done"]:
                        streak_len += 1
                    else:
                        break

                # 2. completion_rate_7d
                window_7 = [checkins[k]["done"] for k in range(max(0, t - 6), t + 1)]
                cr_7d = round(sum(window_7) / len(window_7), 4)

                # 3. completion_rate_30d
                window_30 = [checkins[k]["done"] for k in range(max(0, t - 29), t + 1)]
                cr_30d = round(sum(window_30) / len(window_30), 4)

                # 4. days_since_last_miss
                if not checkins[t]["done"]:
                    days_since_last_miss = 0
                else:
                    miss_idx = None
                    for k in range(t - 1, -1, -1):
                        if not checkins[k]["done"]:
                            miss_idx = k
                            break
                    if miss_idx is not None:
                        days_since_last_miss = t - miss_idx
                    else:
                        days_since_last_miss = t + 1

                # 5. day_of_week_tomorrow & 6. is_weekend_tomorrow
                day_of_week_tomorrow = next_date.weekday()
                is_weekend_tomorrow = 1 if day_of_week_tomorrow in (5, 6) else 0

                # 7. yesterday_done
                yesterday_done = int(checkins[t - 1]["done"]) if t > 0 else 0

                # Label
                completed_next_day = int(checkins[t + 1]["done"])

                real_rows.append({
                    "streak_length": streak_len,
                    "completion_rate_7d": cr_7d,
                    "completion_rate_30d": cr_30d,
                    "days_since_last_miss": days_since_last_miss,
                    "day_of_week_tomorrow": day_of_week_tomorrow,
                    "is_weekend_tomorrow": is_weekend_tomorrow,
                    "yesterday_done": yesterday_done,
                    "completed_next_day": completed_next_day,
                })

        conn.close()

    if real_rows:
        df_real = pd.DataFrame(real_rows)
        df_combined = pd.concat([df_base[FEATURE_COLUMNS + [LABEL_COLUMN]], df_real], ignore_index=True)
        print(f"Retraining on {len(df_base)} base samples + {len(df_real)} real samples = {len(df_combined)} total.")
    else:
        df_combined = df_base[FEATURE_COLUMNS + [LABEL_COLUMN]]
        print(f"No additional real samples found. Retraining on {len(df_base)} base samples.")

    X = df_combined[FEATURE_COLUMNS]
    y = df_combined[LABEL_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(random_state=42, max_iter=1000)),
    ])
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred))
    rec = float(recall_score(y_test, y_pred))
    auc = float(roc_auc_score(y_test, y_proba))

    model_path = Path("/tmp/model.joblib") if os.getenv("VERCEL") else backend_dir / "model.joblib"
    joblib.dump(pipeline, model_path)
    print(f"Retrained model saved to: {model_path}")

    # Reset cache in model module if imported
    try:
        import model
        model._MODEL_CACHE = None
    except Exception:
        pass

    return {
        "base_samples": len(df_base),
        "real_samples": len(real_rows),
        "total_samples": len(df_combined),
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "roc_auc": auc,
    }


if __name__ == "__main__":
    train_model()

