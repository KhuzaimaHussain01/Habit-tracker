import os
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import (
    calculate_streak,
    get_db_connection,
    get_last_7_days,
    init_db,
)
try:
    from model import predict_tomorrow_proba
except Exception:
    predict_tomorrow_proba = None  # Fallback if model dependencies missing

try:
    from train import retrain_with_real_checkins, train_model
except Exception:
    retrain_with_real_checkins = None
    train_model = None  # Fallback if training dependencies missing


def _find_static_dir() -> Optional[Path]:
    """Return the directory to serve static files.
    During local development we serve from the 'public' folder.
    On Vercel the static assets are served by Vercel itself, so we return None.
    """
    if os.getenv("VERCEL"):
        return None
    # Local development: prefer 'public' folder at project root
    public_dir = Path.cwd() / "public"
    if public_dir.is_dir():
        return public_dir
    # Fallback to legacy 'frontend' locations (kept for compatibility)
    candidates = [
        Path(__file__).resolve().parent / "frontend",
        Path(__file__).resolve().parent.parent / "frontend",
        Path.cwd() / "frontend",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Lazy model load — don't block startup; model.py handles fallback
    yield


app = FastAPI(
    title="Habit Tracker API",
    description="Backend API for Habit Tracker with Streak Predictor",
    version="1.0.0",
    lifespan=lifespan,
)

# Helper to locate static files in various possible locations
def _static_file_path(filename: str) -> Path:
    """Return the Path to a static file inside the public folder.
    Checks several locations to work both locally and in the Vercel runtime.
    """
    candidates = [
        Path(__file__).resolve().parent / "public" / filename,
        Path(__file__).resolve().parent.parent / "public" / filename,
        Path.cwd() / "public" / filename,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"Static file {filename} not found")

# Serve the main HTML page
@app.get("/", response_class=FileResponse)
def serve_index():
    return FileResponse(_static_file_path("index.html"), media_type="text/html")

# Serve CSS
@app.get("/style.css", response_class=FileResponse)
def serve_css():
    return FileResponse(_static_file_path("style.css"), media_type="text/css")

# Serve JS
@app.get("/app.js", response_class=FileResponse)
def serve_js():
    return FileResponse(_static_file_path("app.js"), media_type="application/javascript")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HabitCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Name of the habit")


class CheckinDay(BaseModel):
    date: str
    done: bool


class HabitResponse(BaseModel):
    id: int
    name: str
    created_at: str
    current_streak: int
    last_7_days: List[CheckinDay]
    predicted_probability: Optional[float] = None
    learning: bool = False


class CheckinToggleResponse(BaseModel):
    habit_id: int
    date: str
    done: bool
    current_streak: int
    last_7_days: List[CheckinDay]
    predicted_probability: Optional[float] = None
    learning: bool = False


@app.post("/habits", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
def create_habit(habit_in: HabitCreate):
    name = habit_in.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Habit name cannot be empty",
        )

    today = date.today()
    created_at = today.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO habits (name, created_at) VALUES (?, ?);",
        (name, created_at),
    )
    habit_id = cursor.lastrowid
    conn.commit()
    conn.close()

    empty_checkins: Dict[str, bool] = {}
    return HabitResponse(
        id=habit_id,
        name=name,
        created_at=created_at,
        current_streak=0,
        last_7_days=get_last_7_days(empty_checkins, today),
        predicted_probability=None,
        learning=True,
    )


@app.get("/habits", response_model=List[HabitResponse])
def get_habits():
    today = date.today()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, created_at FROM habits ORDER BY id ASC;")
    habits = cursor.fetchall()

    result = []
    for habit in habits:
        habit_id = habit["id"]
        cursor.execute(
            "SELECT date, done FROM checkins WHERE habit_id = ? ORDER BY date ASC;",
            (habit_id,),
        )
        checkin_rows = cursor.fetchall()
        checkin_map = {row["date"]: bool(row["done"]) for row in checkin_rows}

        streak = calculate_streak(checkin_map, today)
        last_7 = get_last_7_days(checkin_map, today)

        # If a habit has fewer than 3 days of history, set learning: true
        if len(checkin_rows) < 3:
            learning = True
            predicted_prob = None
        else:
            learning = False
            try:
                predicted_prob = round(predict_tomorrow_proba(checkin_map, today), 4)
            except Exception as e:
                print(f"Prediction error for habit {habit_id}: {e}")
                predicted_prob = None

        result.append(
            HabitResponse(
                id=habit_id,
                name=habit["name"],
                created_at=habit["created_at"],
                current_streak=streak,
                last_7_days=last_7,
                predicted_probability=predicted_prob,
                learning=learning,
            )
        )

    conn.close()
    return result


@app.delete("/habits/{habit_id}")
def delete_habit(habit_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM habits WHERE id = ?;", (habit_id,))
    habit = cursor.fetchone()
    if not habit:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Habit with id {habit_id} not found",
        )

    cursor.execute("DELETE FROM checkins WHERE habit_id = ?;", (habit_id,))
    cursor.execute("DELETE FROM habits WHERE id = ?;", (habit_id,))
    conn.commit()
    conn.close()

    return {"message": "Habit deleted successfully", "id": habit_id}


@app.post("/habits/{habit_id}/checkin", response_model=CheckinToggleResponse)
def toggle_checkin(habit_id: int):
    today = date.today()
    today_str = today.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM habits WHERE id = ?;", (habit_id,))
    habit = cursor.fetchone()
    if not habit:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Habit with id {habit_id} not found",
        )

    cursor.execute(
        "SELECT id, done FROM checkins WHERE habit_id = ? AND date = ?;",
        (habit_id, today_str),
    )
    existing_checkin = cursor.fetchone()

    if existing_checkin:
        new_done = 0 if existing_checkin["done"] else 1
        cursor.execute(
            "UPDATE checkins SET done = ? WHERE id = ?;",
            (new_done, existing_checkin["id"]),
        )
    else:
        new_done = 1
        cursor.execute(
            "INSERT INTO checkins (habit_id, date, done) VALUES (?, ?, ?);",
            (habit_id, today_str, new_done),
        )

    conn.commit()

    # Retrieve all check-ins to compute current streak & last 7 days
    cursor.execute(
        "SELECT date, done FROM checkins WHERE habit_id = ? ORDER BY date ASC;",
        (habit_id,),
    )
    all_checkins = cursor.fetchall()
    checkin_map = {row["date"]: bool(row["done"]) for row in all_checkins}

    current_streak = calculate_streak(checkin_map, today)
    last_7 = get_last_7_days(checkin_map, today)

    if len(all_checkins) < 3:
        learning = True
        predicted_prob = None
    else:
        learning = False
        try:
            predicted_prob = round(predict_tomorrow_proba(checkin_map, today), 4)
        except Exception:
            predicted_prob = None

    conn.close()

    return CheckinToggleResponse(
        habit_id=habit_id,
        date=today_str,
        done=bool(new_done),
        current_streak=current_streak,
        last_7_days=last_7,
        predicted_probability=predicted_prob,
        learning=learning,
    )


@app.post("/retrain")
def retrain():
    result = retrain_with_real_checkins()
    return {"message": "Model retrained successfully", **result}


# Serve frontend static files — only if the directory exists
STATIC_DIR = _find_static_dir()
if STATIC_DIR is not None:
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
else:
    print(f"[WARN] Static directory not found, skipping static file mount.")
