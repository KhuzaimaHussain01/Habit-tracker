# Habit Tracker with Streak Predictor

A minimal, full-stack habit tracking web application featuring machine learning-based streak prediction to help users maintain consistent daily routines.

---

## What the App Does

- **Habit Tracking**: Create habits, mark them as done for today, and track consecutive streaks.
- **Visual 7-Day History**: View a rolling row of daily dots for each habit (filled for completed days, empty for missed days).
- **Streak Predictor**: Predicts tomorrow's completion probability for each habit using machine learning.
- **Adaptive Chance Badges**:
  - 🟢 **Green** ($\ge 70\%$): High completion probability.
  - 🟡 **Amber** ($40\% - 69\%$): Moderate consistency.
  - 🔴 **Red** ($< 40\%$): Low completion likelihood.
  - ⚪ **Learning...**: Shown when a habit has fewer than 3 days of history.
- **On-Demand Retraining**: Retrain the model on the fly directly from the header **Retrain** button to incorporate your real check-in data.
- **Single Server**: The FastAPI backend serves both the REST API and the frontend static assets.

---

## Tech Stack

- **Backend**: Python 3, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), SQLite (`sqlite3` standard library module).
- **Machine Learning**: [scikit-learn](https://scikit-learn.org/) (`StandardScaler` + `LogisticRegression` pipeline), [pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/), [joblib](https://joblib.readthedocs.io/).
- **Frontend**: Vanilla HTML5, CSS3 (Light theme only, responsive single-column layout $\le 600\text{px}$), Vanilla JavaScript (no external frameworks).

---

## How the Model Works

The prediction pipeline models tomorrow's completion probability from 7 daily behavioral features:

1. `streak_length`: Consecutive days the habit has been completed ending today.
2. `completion_rate_7d`: Rolling completion percentage over the last 7 calendar days.
3. `completion_rate_30d`: Rolling completion percentage over the last 30 calendar days.
4. `days_since_last_miss`: Number of days elapsed since the most recent missed check-in.
5. `day_of_week_tomorrow`: Upcoming day of the week ($0$ = Monday, ..., $6$ = Sunday).
6. `is_weekend_tomorrow`: Binary flag ($1$ if tomorrow is Saturday or Sunday, else $0$).
7. `yesterday_done`: Binary flag indicating if the habit was completed yesterday.

**Target Label**: `completed_next_day` (binary indicator of completion on the next day).

> **Note on Personalization**: The baseline model is trained on a synthetic dataset (`data/habit_history.csv`) of 18,000 records across 200 simulated habits incorporating realistic behavioral dynamics (streak momentum, ~15% drop on weekends, penalties after missed days, and Gaussian noise). As real check-ins accumulate in your SQLite database, clicking the **Retrain** button (`POST /retrain`) merges your actual check-in patterns with the baseline dataset, making predictions progressively personalized.

---

## Model Evaluation Metrics (Test Set)

Trained with an 80/20 stratified train/test split using a `StandardScaler` + `LogisticRegression` pipeline:

| Metric | Score |
|---|---|
| **Accuracy** | **0.6669** (66.69%) |
| **Precision** | **0.6813** (68.13%) |
| **Recall** | **0.6565** (65.65%) |
| **ROC-AUC** | **0.7358** |

---

## Setup & Running Instructions

### 1. Create and Activate a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

*(On Windows, run `venv\Scripts\activate`)*

### 2. Install Requirements

```bash
pip install -r backend/requirements.txt
```

### 3. Generate Data & Train the Model

```bash
python backend/train.py
```

*(Note: If `backend/model.joblib` is missing, the backend will also train automatically on server startup).*

### 4. Run the Server

```bash
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

### 5. Open in Browser

Navigate to:
```
http://127.0.0.1:8000
```
