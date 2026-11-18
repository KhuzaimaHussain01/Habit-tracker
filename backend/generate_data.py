from datetime import date, timedelta
from pathlib import Path
import numpy as np
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


def generate_habit_dataset(
    num_habits: int = 200,
    num_days: int = 90,
    random_seed: int = 42,
) -> pd.DataFrame:
    np.random.seed(random_seed)

    # We simulate (num_days + 1) days so that day 0..num_days-1 each have a "next day" label
    total_sim_days = num_days + 1
    start_date = date(2026, 1, 1)

    rows = []

    for habit_id in range(num_habits):
        # Base completion probability between 0.3 and 0.9
        base_prob = np.random.uniform(0.30, 0.90)

        checkins = np.zeros(total_sim_days, dtype=int)
        current_streak = 0

        # Simulate daily check-ins
        for d in range(total_sim_days):
            current_date = start_date + timedelta(days=d)
            dow = current_date.weekday()
            is_weekend = 1 if dow in (5, 6) else 0

            # Compute probability for day d
            prob = base_prob

            # Success is more likely after a streak
            if current_streak > 0:
                streak_bonus = min(current_streak * 0.02, 0.12)
                prob += streak_bonus

            # About 15% lower on weekends
            if is_weekend:
                prob -= 0.15

            # Lower after a miss yesterday
            if d > 0 and checkins[d - 1] == 0:
                prob -= 0.12

            # Random noise
            noise = np.random.normal(0, 0.04)
            prob += noise

            prob = np.clip(prob, 0.05, 0.95)
            done = 1 if np.random.rand() < prob else 0
            checkins[d] = done

            if done == 1:
                current_streak += 1
            else:
                current_streak = 0

        # Build daily feature rows for days 0 .. num_days - 1
        for t in range(num_days):
            # 1. streak_length ending at day t
            streak_len = 0
            for k in range(t, -1, -1):
                if checkins[k] == 1:
                    streak_len += 1
                else:
                    break

            # 2. completion_rate_7d
            window_7 = checkins[max(0, t - 6) : t + 1]
            completion_rate_7d = float(np.mean(window_7))

            # 3. completion_rate_30d
            window_30 = checkins[max(0, t - 29) : t + 1]
            completion_rate_30d = float(np.mean(window_30))

            # 4. days_since_last_miss
            if checkins[t] == 0:
                days_since_last_miss = 0
            else:
                last_miss_idx = None
                for k in range(t - 1, -1, -1):
                    if checkins[k] == 0:
                        last_miss_idx = k
                        break
                if last_miss_idx is not None:
                    days_since_last_miss = t - last_miss_idx
                else:
                    days_since_last_miss = t + 1

            # 5. day_of_week_tomorrow & 6. is_weekend_tomorrow
            tomorrow_date = start_date + timedelta(days=t + 1)
            day_of_week_tomorrow = tomorrow_date.weekday()
            is_weekend_tomorrow = 1 if day_of_week_tomorrow in (5, 6) else 0

            # 7. yesterday_done (checkin at day t - 1)
            yesterday_done = int(checkins[t - 1]) if t > 0 else 0

            # Label: whether the habit was completed the next day (day t + 1)
            completed_next_day = int(checkins[t + 1])

            rows.append({
                "habit_id": habit_id,
                "day_index": t,
                "streak_length": streak_len,
                "completion_rate_7d": round(completion_rate_7d, 4),
                "completion_rate_30d": round(completion_rate_30d, 4),
                "days_since_last_miss": days_since_last_miss,
                "day_of_week_tomorrow": day_of_week_tomorrow,
                "is_weekend_tomorrow": is_weekend_tomorrow,
                "yesterday_done": yesterday_done,
                "completed_next_day": completed_next_day,
            })

    df = pd.DataFrame(rows)
    return df


def main():
    root_dir = Path(__file__).resolve().parent.parent
    backend_dir = Path(__file__).resolve().parent

    # Save to data/habit_history.csv at project root
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "habit_history.csv"

    # Also keep a copy in backend/data for convenience
    backend_data_dir = backend_dir / "data"
    backend_data_dir.mkdir(parents=True, exist_ok=True)
    backend_out_path = backend_data_dir / "habit_history.csv"

    df = generate_habit_dataset(num_habits=200, num_days=90, random_seed=42)
    df.to_csv(out_path, index=False)
    df.to_csv(backend_out_path, index=False)

    print(f"Generated {len(df)} rows across {df['habit_id'].nunique()} habits.")
    print(f"Dataset saved to:\n  - {out_path}\n  - {backend_out_path}")
    print(f"Label distribution:\n{df['completed_next_day'].value_counts(normalize=True)}")


if __name__ == "__main__":
    main()
