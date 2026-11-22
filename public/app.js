const API_BASE = "";

const summaryEl = document.getElementById("summary");
const habitsListEl = document.getElementById("habits-list");
const addHabitForm = document.getElementById("add-habit-form");
const habitInput = document.getElementById("habit-input");
const retrainBtn = document.getElementById("retrain-btn");

async function fetchHabits() {
  try {
    const res = await fetch(`${API_BASE}/habits`);
    if (!res.ok) throw new Error("Failed to fetch habits");
    return await res.json();
  } catch (err) {
    console.error("Error fetching habits:", err);
    summaryEl.textContent = "Error loading habits. Please try again.";
    return [];
  }
}

function updateSummary(habits) {
  const total = habits.length;
  if (total === 0) {
    summaryEl.textContent = "0 of 0 done today • Best streak: 0 days";
    return;
  }

  let doneTodayCount = 0;
  let bestStreak = 0;

  habits.forEach((habit) => {
    if (habit.current_streak > bestStreak) {
      bestStreak = habit.current_streak;
    }
    const days = habit.last_7_days || [];
    const todayCheckin = days.length > 0 ? days[days.length - 1] : null;
    if (todayCheckin && todayCheckin.done) {
      doneTodayCount++;
    }
  });

  const streakUnit = bestStreak === 1 ? "day" : "days";
  summaryEl.textContent = `${doneTodayCount} of ${total} done today • Best streak: ${bestStreak} ${streakUnit}`;
}

function renderHabits(habits) {
  habitsListEl.innerHTML = "";

  if (habits.length === 0) {
    habitsListEl.innerHTML = '<div class="empty-state">No habits yet. Add one above!</div>';
    return;
  }

  habits.forEach((habit) => {
    const card = document.createElement("div");
    card.className = "habit-card";

    const days = habit.last_7_days || [];
    const todayCheckin = days.length > 0 ? days[days.length - 1] : null;
    const isDoneToday = todayCheckin ? todayCheckin.done : false;

    // Left section: Done button + Habit Details (name & dots)
    const leftDiv = document.createElement("div");
    leftDiv.className = "habit-left";

    const doneBtn = document.createElement("button");
    doneBtn.className = `done-btn ${isDoneToday ? "is-done" : ""}`;
    doneBtn.textContent = isDoneToday ? "Done" : "Done";
    doneBtn.setAttribute("aria-label", `Mark ${habit.name} as done`);
    doneBtn.addEventListener("click", () => handleToggleCheckin(habit.id));

    const detailsDiv = document.createElement("div");
    detailsDiv.className = "habit-details";

    const nameEl = document.createElement("div");
    nameEl.className = "habit-name";
    nameEl.textContent = habit.name;

    const dotsRow = document.createElement("div");
    dotsRow.className = "dots-row";
    days.forEach((day) => {
      const dot = document.createElement("span");
      dot.className = `dot ${day.done ? "done" : "missed"}`;
      dot.title = `${day.date}: ${day.done ? "Done" : "Missed"}`;
      dotsRow.appendChild(dot);
    });

    detailsDiv.appendChild(nameEl);
    detailsDiv.appendChild(dotsRow);

    leftDiv.appendChild(doneBtn);
    leftDiv.appendChild(detailsDiv);

    // Right section: Tomorrow's chance badge + Current Streak + Delete button
    const rightDiv = document.createElement("div");
    rightDiv.className = "habit-right";

    // Tomorrow's chance badge
    const badgeEl = document.createElement("span");
    badgeEl.className = "chance-badge";

    if (habit.learning) {
      badgeEl.classList.add("badge-learning");
      badgeEl.textContent = "Learning...";
      badgeEl.title = "Fewer than 3 days of history";
    } else if (habit.predicted_probability !== null && habit.predicted_probability !== undefined) {
      const pct = Math.round(habit.predicted_probability * 100);
      if (pct >= 70) {
        badgeEl.classList.add("badge-green");
      } else if (pct >= 40) {
        badgeEl.classList.add("badge-amber");
      } else {
        badgeEl.classList.add("badge-red");
      }
      badgeEl.textContent = `${pct}% tomorrow`;
      badgeEl.title = `Tomorrow's chance: ${pct}%`;
    } else {
      badgeEl.classList.add("badge-learning");
      badgeEl.textContent = "Learning...";
    }

    const streakEl = document.createElement("span");
    streakEl.className = "streak-text";
    const streakDays = habit.current_streak;
    streakEl.textContent = `${streakDays} ${streakDays === 1 ? "day" : "days"}`;

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-btn";
    deleteBtn.innerHTML = "&times;";
    deleteBtn.title = "Delete habit";
    deleteBtn.setAttribute("aria-label", `Delete habit ${habit.name}`);
    deleteBtn.addEventListener("click", () => handleDeleteHabit(habit.id));

    rightDiv.appendChild(badgeEl);
    rightDiv.appendChild(streakEl);
    rightDiv.appendChild(deleteBtn);

    card.appendChild(leftDiv);
    card.appendChild(rightDiv);

    habitsListEl.appendChild(card);
  });
}

async function loadHabits() {
  const habits = await fetchHabits();
  updateSummary(habits);
  renderHabits(habits);
}

async function handleAddHabit(e) {
  e.preventDefault();
  const name = habitInput.value.trim();
  if (!name) return;

  try {
    const res = await fetch(`${API_BASE}/habits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error("Failed to create habit");
    habitInput.value = "";
    await loadHabits();
  } catch (err) {
    console.error("Error creating habit:", err);
  }
}

async function handleToggleCheckin(habitId) {
  try {
    const res = await fetch(`${API_BASE}/habits/${habitId}/checkin`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to toggle checkin");
    await loadHabits();
  } catch (err) {
    console.error("Error toggling checkin:", err);
  }
}

async function handleDeleteHabit(habitId) {
  try {
    const res = await fetch(`${API_BASE}/habits/${habitId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete habit");
    await loadHabits();
  } catch (err) {
    console.error("Error deleting habit:", err);
  }
}

async function handleRetrain() {
  if (!retrainBtn) return;
  retrainBtn.disabled = true;
  const originalText = retrainBtn.textContent;
  retrainBtn.textContent = "Retraining...";

  try {
    const res = await fetch(`${API_BASE}/retrain`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to retrain model");
    await loadHabits();
    retrainBtn.textContent = "Retrained!";
    setTimeout(() => {
      retrainBtn.disabled = false;
      retrainBtn.textContent = originalText;
    }, 1500);
  } catch (err) {
    console.error("Error retraining:", err);
    retrainBtn.textContent = "Error";
    setTimeout(() => {
      retrainBtn.disabled = false;
      retrainBtn.textContent = originalText;
    }, 1500);
  }
}

addHabitForm.addEventListener("submit", handleAddHabit);
if (retrainBtn) {
  retrainBtn.addEventListener("click", handleRetrain);
}
document.addEventListener("DOMContentLoaded", loadHabits);
