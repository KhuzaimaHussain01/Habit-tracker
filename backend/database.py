import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "habits.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (habit_id) REFERENCES habits (id) ON DELETE CASCADE,
            UNIQUE(habit_id, date)
        );
        """
    )

    # Check if first run (habits table is empty)
    cursor.execute("SELECT COUNT(*) as count FROM habits;")
    count = cursor.fetchone()["count"]

    if count == 0:
        seed_demo_data(cursor)

    conn.commit()
    conn.close()


def seed_demo_data(cursor: sqlite3.Cursor) -> None:
    today = date.today()
    demo_habits = [
        {
            "name": "Drink 2L Water",
            # Consistent with 4-day active streak ending today
            "pattern": [1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1],
        },
        {
            "name": "Morning Jog",
            # Consistent workout habit with rest days
            "pattern": [1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1],
        },
        {
            "name": "Read 20 Pages",
            # Consistent reader, checked in yesterday, not yet today
            "pattern": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        },
        {
            "name": "Meditate 10 Mins",
            # Intermittent habit with recent 2-day streak
            "pattern": [0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1],
        },
    ]

    for habit in demo_habits:
        created_at = (today - timedelta(days=14)).isoformat()
        cursor.execute(
            "INSERT INTO habits (name, created_at) VALUES (?, ?);",
            (habit["name"], created_at),
        )
        habit_id = cursor.lastrowid

        # Insert 14 days of check-ins (13 days ago to today)
        for offset in range(14):
            day = (today - timedelta(days=13 - offset)).isoformat()
            done = habit["pattern"][offset]
            cursor.execute(
                "INSERT INTO checkins (habit_id, date, done) VALUES (?, ?, ?);",
                (habit_id, day, done),
            )


def calculate_streak(checkin_map: Dict[str, bool], today: Optional[date] = None) -> int:
    """
    Calculates consecutive day streak ending today or yesterday.
    If today is done, streak counts back from today.
    If today is not yet done, streak counts back from yesterday (if done).
    If neither today nor yesterday was done, streak is 0.
    """
    if today is None:
        today = date.today()

    today_str = today.isoformat()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.isoformat()

    if checkin_map.get(today_str, False):
        current_date = today
    elif checkin_map.get(yesterday_str, False):
        current_date = yesterday
    else:
        return 0

    streak = 0
    while checkin_map.get(current_date.isoformat(), False):
        streak += 1
        current_date -= timedelta(days=1)

    return streak


def get_last_7_days(checkin_map: Dict[str, bool], today: Optional[date] = None) -> List[Dict[str, Any]]:
    if today is None:
        today = date.today()

    days = []
    for i in range(6, -1, -1):
        day_str = (today - timedelta(days=i)).isoformat()
        days.append({
            "date": day_str,
            "done": checkin_map.get(day_str, False),
        })
    return days
