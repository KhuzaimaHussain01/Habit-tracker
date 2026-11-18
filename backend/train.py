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

    # Locate dataset
    data_path = root_dir / "data" / "habit_history.csv"
    if not data_path.exists():
        data_path = backend_dir / "data" / "habit_history.csv"

    if not data_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {data_path}. Please run generate_data.py first."
        )

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

    # Save trained model to backend/model.joblib
    model_path = backend_dir / "model.joblib"
    joblib.dump(pipeline, model_path)
    print(f"Model saved to: {model_path}")

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "roc_auc": auc,
        "model_path": str(model_path),
    }


if __name__ == "__main__":
    train_model()
