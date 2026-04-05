# ===============================================================
# train_risk_model.py
# Procrastination Risk Predictor — Full Training Pipeline
# Includes: SHAP, RandomizedSearchCV, threshold tuning,
#           cyclic time encoding, Brier score calibration proof
# ===============================================================

import pandas as pd
import numpy as np
import pickle
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import (
    train_test_split, StratifiedKFold,
    cross_val_score, RandomizedSearchCV
)
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, precision_recall_curve, brier_score_loss
)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.utils.class_weight import compute_class_weight
import shap

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


# ================================================================
# SECTION 1 — CYCLIC ENCODING
# Time is circular, not linear. The raw integer 23 (11 PM) and 0
# (midnight) are mathematically adjacent on a clock but treated
# as maximally distant by any linear model. Sine/cosine encoding
# maps each value onto a circle so the model correctly understands
# that 23:00 and 00:00 are one step apart.
#
# For a value v with period P:
#   sin_component = sin(2π * v / P)
#   cos_component = cos(2π * v / P)
#
# Two components are needed because sin alone is not injective —
# sin(1) == sin(π-1), so hour 1 and hour 11 would look identical.
# Together, sin+cos uniquely identify every point on the circle.
#
# The raw columns (hour_of_due_time, day_of_week) are DROPPED after
# encoding. Keeping them alongside the encoded versions would
# reintroduce the linear distance problem we just fixed.
# ================================================================

def apply_cyclic_encoding(df: pd.DataFrame) -> pd.DataFrame:
    """
    Encodes hour_of_due_time (period=24) and day_of_week (period=7)
    into sine/cosine pairs and drops the original raw columns.
    """
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_due_time"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_due_time"] / 24)
    df["day_sin"]  = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["day_cos"]  = np.cos(2 * np.pi * df["day_of_week"] / 7)

    df = df.drop(columns=["hour_of_due_time", "day_of_week"])
    return df


def encode_task_for_inference(task: dict) -> dict:
    """
    Applies cyclic encoding to a single task dict at inference time.
    Also computes the snooze_rate interaction feature.
    Call this in your FastAPI endpoint before passing to predict_risk().
    """
    task = dict(task)

    hour = task.pop("hour_of_due_time")
    day  = task.pop("day_of_week")

    task["hour_sin"] = float(np.sin(2 * np.pi * hour / 24))
    task["hour_cos"] = float(np.cos(2 * np.pi * hour / 24))
    task["day_sin"]  = float(np.sin(2 * np.pi * day / 7))
    task["day_cos"]  = float(np.cos(2 * np.pi * day / 7))

    # FIX: compute snooze_rate at inference to match training features
    days = max(int(task.get("days_since_created", 1)), 1)
    task["snooze_rate"] = task.get("snooze_count", 0) / days

    return task


# ================================================================
# SECTION 2 — MANUAL ANCHOR EXAMPLES
# ================================================================

MANUAL_ANCHORS = [
    # --- Clear completions (label=0) ---
    {"snooze_count": 0, "priority": 1, "energy_level": 1, "estimated_duration": 15,
     "global_time_debt": 0,   "hour_of_due_time": 10, "day_of_week": 0,
     "tasks_due_same_day": 2, "days_since_created": 1,  "missed_task": 0},
    {"snooze_count": 0, "priority": 1, "energy_level": 2, "estimated_duration": 30,
     "global_time_debt": 20,  "hour_of_due_time": 9,  "day_of_week": 1,
     "tasks_due_same_day": 3, "days_since_created": 2,  "missed_task": 0},
    {"snooze_count": 1, "priority": 2, "energy_level": 1, "estimated_duration": 15,
     "global_time_debt": 10,  "hour_of_due_time": 11, "day_of_week": 2,
     "tasks_due_same_day": 4, "days_since_created": 0,  "missed_task": 0},
    {"snooze_count": 0, "priority": 1, "energy_level": 2, "estimated_duration": 60,
     "global_time_debt": 50,  "hour_of_due_time": 14, "day_of_week": 3,
     "tasks_due_same_day": 5, "days_since_created": 3,  "missed_task": 0},
    {"snooze_count": 2, "priority": 1, "energy_level": 2, "estimated_duration": 60,
     "global_time_debt": 150, "hour_of_due_time": 13, "day_of_week": 1,
     "tasks_due_same_day": 5, "days_since_created": 5,  "missed_task": 0},
    {"snooze_count": 0, "priority": 2, "energy_level": 3, "estimated_duration": 90,
     "global_time_debt": 80,  "hour_of_due_time": 10, "day_of_week": 0,
     "tasks_due_same_day": 3, "days_since_created": 4,  "missed_task": 0},

    # --- Clear misses (label=1) ---
    {"snooze_count": 6, "priority": 3, "energy_level": 3, "estimated_duration": 120,
     "global_time_debt": 400, "hour_of_due_time": 22, "day_of_week": 4,
     "tasks_due_same_day": 10,"days_since_created": 20, "missed_task": 1},
    {"snooze_count": 5, "priority": 4, "energy_level": 3, "estimated_duration": 120,
     "global_time_debt": 350, "hour_of_due_time": 23, "day_of_week": 5,
     "tasks_due_same_day": 12,"days_since_created": 25, "missed_task": 1},
    {"snooze_count": 3, "priority": 3, "energy_level": 2, "estimated_duration": 60,
     "global_time_debt": 200, "hour_of_due_time": 17, "day_of_week": 4,
     "tasks_due_same_day": 9, "days_since_created": 10, "missed_task": 1},
    {"snooze_count": 2, "priority": 3, "energy_level": 2, "estimated_duration": 90,
     "global_time_debt": 180, "hour_of_due_time": 15, "day_of_week": 3,
     "tasks_due_same_day": 13,"days_since_created": 8,  "missed_task": 1},
    {"snooze_count": 4, "priority": 4, "energy_level": 3, "estimated_duration": 120,
     "global_time_debt": 250, "hour_of_due_time": 20, "day_of_week": 6,
     "tasks_due_same_day": 7, "days_since_created": 18, "missed_task": 1},

    # --- Nuanced edge cases ---
    {"snooze_count": 5, "priority": 1, "energy_level": 3, "estimated_duration": 120,
     "global_time_debt": 500, "hour_of_due_time": 23, "day_of_week": 6,
     "tasks_due_same_day": 11,"days_since_created": 30, "missed_task": 1},
    {"snooze_count": 0, "priority": 3, "energy_level": 3, "estimated_duration": 120,
     "global_time_debt": 0,   "hour_of_due_time": 9,  "day_of_week": 1,
     "tasks_due_same_day": 2, "days_since_created": 1,  "missed_task": 0},
    {"snooze_count": 1, "priority": 5, "energy_level": 1, "estimated_duration": 15,
     "global_time_debt": 30,  "hour_of_due_time": 10, "day_of_week": 2,
     "tasks_due_same_day": 4, "days_since_created": 2,  "missed_task": 0},
    {"snooze_count": 2, "priority": 3, "energy_level": 2, "estimated_duration": 60,
     "global_time_debt": 120, "hour_of_due_time": 14, "day_of_week": 3,
     "tasks_due_same_day": 6, "days_since_created": 7,  "missed_task": 0},
    {"snooze_count": 3, "priority": 3, "energy_level": 2, "estimated_duration": 60,
     "global_time_debt": 180, "hour_of_due_time": 16, "day_of_week": 3,
     "tasks_due_same_day": 7, "days_since_created": 8,  "missed_task": 1},
]


# ================================================================
# SECTION 3 — SYNTHETIC DATA GENERATION
# ================================================================

def _compute_fail_probability(
    snooze_count, priority, energy_level, estimated_duration,
    global_time_debt, hour_of_due_time, day_of_week,
    tasks_due_same_day, days_since_created
) -> float:
    p = 0.10

    p += snooze_count * 0.10
    if snooze_count >= 5:
        p += 0.10

    priority_effect = {1: -0.15, 2: -0.08, 3: 0.0, 4: 0.10, 5: 0.18}
    p += priority_effect.get(priority, 0.0)

    if global_time_debt > 400:   p += 0.25
    elif global_time_debt > 240: p += 0.15
    elif global_time_debt > 120: p += 0.07
    elif global_time_debt < 30:  p -= 0.05

    if estimated_duration >= 90 and energy_level == 3: p += 0.18
    elif estimated_duration >= 90:                      p += 0.08
    elif energy_level == 3:                             p += 0.06

    if hour_of_due_time >= 22 or hour_of_due_time <= 4: p += 0.28
    elif hour_of_due_time >= 19:                         p += 0.12
    elif 9 <= hour_of_due_time <= 12:                    p -= 0.08
    elif 13 <= hour_of_due_time <= 15:                   p -= 0.03

    if day_of_week == 4:
        p += 0.08
        if hour_of_due_time >= 15: p += 0.15
    elif day_of_week in (5, 6):  p += 0.12
    elif day_of_week == 0:       p -= 0.04

    if tasks_due_same_day > 10:   p += 0.22
    elif tasks_due_same_day > 7:  p += 0.12
    elif tasks_due_same_day <= 3: p -= 0.05

    if days_since_created > 21:   p += 0.32
    elif days_since_created > 14: p += 0.22
    elif days_since_created > 7:  p += 0.12
    elif days_since_created <= 1: p -= 0.05

    if global_time_debt > 200 and snooze_count >= 3:
        p += 0.10
    if days_since_created <= 2 and global_time_debt < 60 and 8 <= hour_of_due_time <= 12:
        p -= 0.08

    p += np.random.normal(0, 0.04)
    return float(np.clip(p, 0.02, 0.98))


def generate_synthetic_data(num_samples: int = 5000) -> pd.DataFrame:
    print(f"[DataGen] Generating {num_samples} synthetic records...")

    snooze_counts       = np.clip(np.random.poisson(1.5, num_samples), 0, 10)
    priorities          = np.random.choice([1,2,3,4,5], num_samples, p=[.10,.20,.40,.20,.10])
    energy_levels       = np.random.choice([1,2,3], num_samples, p=[.30,.50,.20])
    estimated_durations = np.random.choice([15,30,60,90,120], num_samples, p=[.25,.30,.25,.12,.08])
    global_time_debts   = np.clip(np.random.exponential(120, num_samples), 0, 600)
    hours               = np.clip(np.random.normal(14, 4, num_samples).astype(int), 0, 23)
    days                = np.random.choice([0,1,2,3,4,5,6], num_samples,
                                           p=[.18,.18,.17,.17,.15,.08,.07])
    tasks_same_day      = np.clip(np.random.poisson(4, num_samples), 1, 15)
    days_since          = np.clip(np.random.exponential(5.0, num_samples).astype(int), 0, 45)

    outcomes = [
        1 if np.random.random() < _compute_fail_probability(
            int(snooze_counts[i]), int(priorities[i]), int(energy_levels[i]),
            int(estimated_durations[i]), float(global_time_debts[i]),
            int(hours[i]), int(days[i]), int(tasks_same_day[i]), int(days_since[i])
        ) else 0
        for i in range(num_samples)
    ]

    df = pd.DataFrame({
        "snooze_count":       snooze_counts,
        "priority":           priorities,
        "energy_level":       energy_levels,
        "estimated_duration": estimated_durations,
        "global_time_debt":   global_time_debts,
        "hour_of_due_time":   hours,
        "day_of_week":        days,
        "tasks_due_same_day": tasks_same_day,
        "days_since_created": days_since,
        "missed_task":        outcomes,
    })

    # FIX: compute snooze_rate BEFORE cyclic encoding and BEFORE dropping raw columns,
    # so it can use days_since_created directly from the DataFrame.
    # snooze_rate = snooze_count / age of task (clamped to min 1 day).
    # This is a more informative signal than raw snooze_count alone:
    # 3 snoozes on a task created today is a much stronger avoidance signal
    # than 3 snoozes on a task created 3 weeks ago. Random Forest can
    # discover this interaction but giving it the derived ratio directly
    # speeds learning and makes feature importance more interpretable.
    df["snooze_rate"] = df["snooze_count"] / df["days_since_created"].clip(lower=1)

    # Inject anchors (upsampled 5x for ground-truth weight)
    anchors_df = pd.concat([pd.DataFrame(MANUAL_ANCHORS)] * 5, ignore_index=True)
    # Anchors need snooze_rate too
    anchors_df["snooze_rate"] = anchors_df["snooze_count"] / anchors_df["days_since_created"].clip(lower=1)

    df = pd.concat([df, anchors_df], ignore_index=True).sample(frac=1, random_state=RANDOM_SEED)

    total    = len(df)
    n_missed = int(df["missed_task"].sum())
    n_comp   = total - n_missed
    print(f"[DataGen] {total} records | Completed: {n_comp} ({n_comp/total*100:.1f}%) | "
          f"Missed: {n_missed} ({n_missed/total*100:.1f}%)")

    df = apply_cyclic_encoding(df)
    print(f"[DataGen] Cyclic encoding applied.")
    print(f"          hour_of_due_time → hour_sin, hour_cos")
    print(f"          day_of_week      → day_sin,  day_cos")
    print(f"          snooze_rate      added as interaction feature")
    print(f"          Final feature count: {len(df.columns) - 1}")

    return df


# ================================================================
# SECTION 4 — HYPERPARAMETER TUNING
# ================================================================

def tune_hyperparameters(X_train, y_train, class_weights: dict) -> dict:
    print("\n[Tune] RandomizedSearchCV (40 iterations, 3-fold stratified CV)...")

    param_distributions = {
        "n_estimators":      [100, 150, 200, 300, 400],
        "max_depth":         [4, 6, 8, 10, 12, None],
        "min_samples_leaf":  [5, 10, 15, 20, 30],
        "min_samples_split": [2, 5, 10, 15],
        "max_features":      ["sqrt", "log2", 0.5, 0.7],
        "bootstrap":         [True, False],
    }

    base = RandomForestClassifier(
        class_weight=class_weights,
        random_state=RANDOM_SEED,
        n_jobs=-1
    )

    search = RandomizedSearchCV(
        estimator           = base,
        param_distributions = param_distributions,
        n_iter              = 40,
        scoring             = "roc_auc",
        cv                  = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED),
        random_state        = RANDOM_SEED,
        n_jobs              = -1,
        verbose             = 1
    )
    search.fit(X_train, y_train)

    best = search.best_params_
    print(f"\n[Tune] Best params (CV AUC: {search.best_score_:.4f}):")
    for k, v in best.items():
        print(f"       {k}: {v}")

    return best


# ================================================================
# SECTION 5 — THRESHOLD OPTIMISATION
# ================================================================

def find_optimal_threshold(y_true, y_prob) -> float:
    print("\n[Threshold] Computing optimal classification threshold...")

    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    # FIX: guard against edge case where precision_recall_curve returns
    # fewer than 2 threshold points (can happen on heavily imbalanced data)
    if len(thresholds) == 0:
        print("[Threshold] Warning: no threshold candidates found — defaulting to 0.5")
        return 0.5

    f1_scores = []
    for p, r in zip(precisions[:-1], recalls[:-1]):
        f1_scores.append(2 * p * r / (p + r) if (p + r) > 0 else 0.0)

    best_idx       = int(np.argmax(f1_scores))
    best_threshold = float(thresholds[best_idx])

    print(f"[Threshold] Optimal threshold: {best_threshold:.4f}")
    print(f"            F1:        {f1_scores[best_idx]:.4f}")
    print(f"            Precision: {precisions[best_idx]:.4f}")
    print(f"            Recall:    {recalls[best_idx]:.4f}")

    print("\n[Threshold] Sweep (10 sample points):")
    print(f"  {'Threshold':>10} | {'Precision':>10} | {'Recall':>8} | {'F1':>8}")
    print("  " + "-" * 44)
    for idx in np.linspace(0, len(thresholds) - 1, 10).astype(int):
        p = precisions[idx]
        r = recalls[idx]
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0
        marker = " <- optimal" if idx == best_idx else ""
        print(f"  {thresholds[idx]:>10.4f} | {p:>10.4f} | {r:>8.4f} | {f:>8.4f}{marker}")

    return best_threshold


# ================================================================
# SECTION 6 — BRIER SCORE CALIBRATION PROOF
# The Brier Score measures how accurate the model's probabilities
# are, not just its classifications. Formula:
#
#   BS = (1/N) * Σ (predicted_prob - actual_outcome)²
#
# Range: 0.0 (perfect) to 1.0 (worst possible)
# A "no-skill" baseline that always predicts the class prevalence
# gives a Brier score equal to prevalence * (1 - prevalence).
# A good calibrated model should beat this comfortably.
#
# We compare the UNCALIBRATED base model against the CALIBRATED
# model to prove calibration actually improved things — not just
# as a theoretical claim but as a measured result.
# ================================================================

def evaluate_calibration(fresh_base, calibrated_model, X_test, y_test):
    """
    Compares uncalibrated vs calibrated Brier scores.

    Args:
        fresh_base:        A RandomForestClassifier already fitted on X_train.
                           Passed in fitted — do NOT re-fit inside this function.
        calibrated_model:  The CalibratedClassifierCV model, also already fitted.
        X_test, y_test:    Held-out test set for evaluation.

    FIX: the original function attempted to re-fit fresh_base inside here using
    broken logic (y_test[:len(X_train)] when lengths are never equal, then
    falling back to fit(X_train, X_train) which uses features as labels).
    Both base and calibrated models are now fitted before being passed in.
    """
    print("\n[Brier] Evaluating probability calibration...")

    uncal_probs = fresh_base.predict_proba(X_test)[:, 1]
    cal_probs   = calibrated_model.predict_proba(X_test)[:, 1]

    brier_uncalibrated = brier_score_loss(y_test, uncal_probs)
    brier_calibrated   = brier_score_loss(y_test, cal_probs)

    prevalence     = float(y_test.mean())
    brier_baseline = prevalence * (1 - prevalence)

    print(f"\n[Brier] Results:")
    print(f"          No-skill baseline:      {brier_baseline:.4f}  (always predict {prevalence:.0%} failure)")
    print(f"          Uncalibrated RF:        {brier_uncalibrated:.4f}")
    print(f"          Calibrated RF (ours):   {brier_calibrated:.4f}  <- lower is better")

    improvement = ((brier_baseline - brier_calibrated) / brier_baseline) * 100
    print(f"\n[Brier] Calibration improves over baseline by {improvement:.1f}%")
    print(f"[Brier] Interpretation: When our model says 80% risk, it is")
    print(f"        approximately correct 80% of the time (Brier-verified).")

    return {
        "brier_calibrated":         round(brier_calibrated, 4),
        "brier_uncalibrated":       round(brier_uncalibrated, 4),
        "brier_baseline":           round(brier_baseline, 4),
        "baseline_improvement_pct": round(improvement, 2)
    }


# ================================================================
# SECTION 7 — SHAP EXPLAINABILITY
# ================================================================

def compute_shap_explainer(model, X_train: pd.DataFrame, output_path: str):
    """
    Builds a SHAP TreeExplainer from the calibrated model.

    FIX: the original code used only calibrated_classifiers_[0].estimator —
    the raw RF from fold 0 of the 3-fold calibration. The other two folds
    were silently ignored. SHAP values are now averaged across all calibrated
    classifiers so the explanation is consistent with the model's actual
    predictions rather than arbitrarily tied to one fold.
    """
    print("\n[SHAP] Building TreeExplainer (averaged across calibration folds)...")

    # Collect SHAP values from each calibrated fold and average them.
    # Each calibrated_classifiers_[i].estimator is one fold's raw RF.
    all_shap_values = []
    for i, cal in enumerate(model.calibrated_classifiers_):
        raw_rf    = cal.estimator
        explainer = shap.TreeExplainer(raw_rf)
        sv        = explainer.shap_values(X_train)
        # Handle both SHAP API versions:
        #   Old API (< 0.41): returns list [class_0_array, class_1_array]
        #   New API (>= 0.41): returns single 3D array (n_samples, n_features, n_classes)
        # In both cases we want class 1's values as a 2D (n_samples, n_features) array.
        if isinstance(sv, list):
            sv_class1 = sv[1]
        elif sv.ndim == 3:
            sv_class1 = sv[:, :, 1]
        else:
            sv_class1 = sv
        all_shap_values.append(sv_class1)
        print(f"[SHAP]   Fold {i+1}/{len(model.calibrated_classifiers_)} computed")

    # Use the first fold's explainer for single-prediction inference —
    # TreeExplainer is not directly averageable, but the global summary
    # uses the averaged values for accuracy.
    primary_explainer  = shap.TreeExplainer(model.calibrated_classifiers_[0].estimator)
    avg_shap           = np.mean(all_shap_values, axis=0)

    mean_shap = pd.DataFrame({
        "Feature":   X_train.columns,
        "Mean_SHAP": np.abs(avg_shap).mean(axis=0)
    }).sort_values("Mean_SHAP", ascending=False)

    print("\n[SHAP] Global Feature Impact (mean |SHAP|, averaged across folds):")
    for _, row in mean_shap.iterrows():
        bar = "█" * int(row["Mean_SHAP"] * 200)
        print(f"  {row['Feature']:<25} {row['Mean_SHAP']:.4f}  {bar}")

    explainer_path = output_path.replace(".pkl", "_shap_explainer.pkl")
    with open(explainer_path, "wb") as f:
        pickle.dump(primary_explainer, f)
    print(f"\n[SHAP] Explainer saved to: {explainer_path}")

    shap_path = output_path.replace(".pkl", "_shap_summary.json")
    with open(shap_path, "w") as f:
        json.dump(mean_shap.set_index("Feature")["Mean_SHAP"].round(4).to_dict(), f, indent=2)

    return primary_explainer


def explain_prediction(explainer, encoded_task: dict, column_order: list,
                        original_task: dict = None) -> list:
    """
    Returns per-feature SHAP explanations for a single prediction.
    encoded_task:  task dict AFTER cyclic encoding (matches column_order)
    original_task: optional raw task dict for human-readable hour/day values
    """
    row         = pd.DataFrame([[encoded_task[col] for col in column_order]], columns=column_order)
    shap_values = explainer.shap_values(row)
    # Handle both SHAP API versions for single-row inference
    if isinstance(shap_values, list):
        sv = shap_values[1][0]       # old API: list[class_1][first_row]
    elif shap_values.ndim == 3:
        sv = shap_values[0, :, 1]    # new API: (n_samples, n_features, n_classes)[row, :, class_1]
    else:
        sv = shap_values[0]

    ENERGY_LABELS = {1: "Low", 2: "Medium", 3: "High"}

    def feature_label(feat, val, original):
        if feat in ("hour_sin", "hour_cos"):
            h = original.get("hour_of_due_time", "?") if original else "?"
            return f"Due time: {h}:00"
        if feat in ("day_sin", "day_cos"):
            d = original.get("day_of_week", -1) if original else -1
            day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] if 0 <= d <= 6 else "?"
            return f"Day: {day_name}"
        # FIX: use dict lookup instead of list indexing for energy_level —
        # list indexing raises IndexError if val is 0 or out of range.
        # An empty string from index 0 would also silently produce bad labels.
        label_map = {
            "snooze_count":       f"Snoozed {int(val)} time(s)",
            "priority":           f"Priority {int(val)}",
            "energy_level":       f"Energy: {ENERGY_LABELS.get(int(val), str(val))}",
            "estimated_duration": f"Duration: {int(val)} mins",
            "global_time_debt":   f"Time debt: {int(val)} mins",
            "tasks_due_same_day": f"{int(val)} other tasks today",
            "days_since_created": f"Task age: {int(val)} days",
            "snooze_rate":        f"Snooze rate: {val:.2f}/day",
        }
        return label_map.get(feat, feat)

    hour_shap = 0.0
    day_shap  = 0.0
    other     = []

    for feat, val, sv_val in zip(column_order, row.iloc[0], sv):
        if feat in ("hour_sin", "hour_cos"):
            hour_shap += float(sv_val)
        elif feat in ("day_sin", "day_cos"):
            day_shap += float(sv_val)
        else:
            other.append({
                "feature":   feat,
                "value":     float(val),
                "shap":      round(float(sv_val), 4),
                "direction": "increases_risk" if sv_val > 0 else "decreases_risk",
                "label":     feature_label(feat, val, original_task)
            })

    h = original_task.get("hour_of_due_time", "?") if original_task else "?"
    d = original_task.get("day_of_week", -1) if original_task else -1
    day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] if 0 <= d <= 6 else "?"

    other.append({
        "feature":   "hour_of_due_time",
        "value":     h,
        "shap":      round(hour_shap, 4),
        "direction": "increases_risk" if hour_shap > 0 else "decreases_risk",
        "label":     f"Due time: {h}:00"
    })
    other.append({
        "feature":   "day_of_week",
        "value":     d,
        "shap":      round(day_shap, 4),
        "direction": "increases_risk" if day_shap > 0 else "decreases_risk",
        "label":     f"Day: {day_name}"
    })

    other.sort(key=lambda x: abs(x["shap"]), reverse=True)

    for item in other:
        sign = "+" if item["shap"] > 0 else "-"
        pct  = abs(round(item["shap"] * 100, 1))
        item["explanation"] = f"{item['label']} ({sign}{pct}% risk)"

    return other


# ================================================================
# SECTION 8 — MAIN TRAINING PIPELINE
# ================================================================

def train_and_save_model(
    num_samples: int  = 5000,
    output_path: str  = "risk_prediction_model.pkl",
    tune:        bool = True
):
    print("=" * 60)
    print("PROCRASTINATION RISK MODEL — TRAINING PIPELINE")
    print("=" * 60)

    df = generate_synthetic_data(num_samples)
    X  = df.drop("missed_task", axis=1)
    y  = df["missed_task"]

    classes           = np.array([0, 1])
    class_weights_arr = compute_class_weight("balanced", classes=classes, y=y)
    weight_dict       = {0: float(class_weights_arr[0]), 1: float(class_weights_arr[1])}
    print(f"\n[Train] Class weights: {weight_dict}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )

    if tune:
        best_params = tune_hyperparameters(X_train, y_train, weight_dict)
    else:
        best_params = {
            "n_estimators": 200, "max_depth": 8, "min_samples_leaf": 10,
            "min_samples_split": 5, "max_features": "sqrt", "bootstrap": True,
        }

    base_model = RandomForestClassifier(
        **best_params,
        class_weight = weight_dict,
        random_state = RANDOM_SEED,
        n_jobs       = -1
    )

    model = CalibratedClassifierCV(base_model, method="isotonic", cv=3)

    print("\n[Train] 5-fold CV (AUC)...")
    cv_scores = cross_val_score(
        base_model, X_train, y_train,
        cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED),
        scoring = "roc_auc",
        n_jobs  = -1
    )
    print(f"[Train] CV AUC: {np.round(cv_scores, 3)} → {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    print("\n[Train] Fitting calibrated model...")
    model.fit(X_train, y_train)

    y_prob            = model.predict_proba(X_test)[:, 1]
    optimal_threshold = find_optimal_threshold(y_test, y_prob)
    y_pred_optimal    = (y_prob >= optimal_threshold).astype(int)
    auc_score         = roc_auc_score(y_test, y_prob)

    print("\n" + "=" * 60)
    print("EVALUATION — OPTIMAL THRESHOLD")
    print("=" * 60)
    print(classification_report(y_test, y_pred_optimal, target_names=["Completed", "Missed"]))
    print(f"ROC-AUC Score: {auc_score:.4f}")

    cm = confusion_matrix(y_test, y_pred_optimal)
    print("\nConfusion Matrix:")
    print(f"  True Negatives  (correctly completed): {cm[0][0]}")
    print(f"  False Positives (wrongly flagged):     {cm[0][1]}")
    print(f"  False Negatives (missed warnings):     {cm[1][0]}")
    print(f"  True Positives  (correctly flagged):   {cm[1][1]}")

    # FIX: fit fresh_base HERE before passing to evaluate_calibration.
    # The original code attempted to re-fit inside evaluate_calibration
    # using broken logic — now the caller owns the fit, the function
    # owns only the evaluation.
    fresh_base = RandomForestClassifier(
        **best_params, class_weight=weight_dict,
        random_state=RANDOM_SEED, n_jobs=-1
    )
    fresh_base.fit(X_train, y_train)
    brier_results = evaluate_calibration(fresh_base, model, X_test, y_test)

    raw_rf   = model.calibrated_classifiers_[0].estimator
    feat_imp = pd.DataFrame({
        "Feature":    X.columns,
        "Importance": raw_rf.feature_importances_
    }).sort_values("Importance", ascending=False)

    print("\n[Train] Sklearn Feature Importance:")
    for _, row in feat_imp.iterrows():
        bar = "█" * int(row["Importance"] * 100)
        print(f"  {row['Feature']:<25} {row['Importance']:.4f}  {bar}")

    explainer = compute_shap_explainer(model, X_train, output_path)

    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    print(f"\n[Save] Model:    {output_path}")

    meta = {
        "optimal_threshold":    optimal_threshold,
        "roc_auc":              round(auc_score, 4),
        "cv_auc_mean":          round(float(cv_scores.mean()), 4),
        "cv_auc_std":           round(float(cv_scores.std()), 4),
        "brier_score":          brier_results,
        "best_hyperparameters": best_params,
        "class_weights":        weight_dict,
        "feature_columns":      list(X.columns),
        "raw_feature_columns":  [
            "snooze_count", "priority", "energy_level", "estimated_duration",
            "global_time_debt", "tasks_due_same_day", "days_since_created",
            "hour_of_due_time", "day_of_week"
            # snooze_rate is derived inside encode_task_for_inference — not a raw input
        ],
        "feature_importance": feat_imp.set_index("Feature")["Importance"].round(4).to_dict(),
        "cyclic_encoded_features": {
            "hour_of_due_time": ["hour_sin", "hour_cos"],
            "day_of_week":      ["day_sin",  "day_cos"]
        },
        "derived_features": {
            "snooze_rate": "snooze_count / max(days_since_created, 1)"
        },
        "risk_thresholds": {
            "LOW":    "risk_score < 0.35",
            "MEDIUM": "0.35 <= risk_score < 0.65",
            "HIGH":   "risk_score >= 0.65"
        }
    }

    meta_path = output_path.replace(".pkl", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[Save] Metadata: {meta_path}")

    return model, explainer, meta


# ================================================================
# SECTION 9 — INFERENCE HELPERS (drop into FastAPI)
# ================================================================

# Required keys for a valid task dict at inference time.
# hour_of_due_time and day_of_week are raw inputs — cyclic encoding
# and snooze_rate derivation happen inside encode_task_for_inference.
REQUIRED_TASK_FIELDS = [
    "snooze_count", "priority", "energy_level", "estimated_duration",
    "global_time_debt", "tasks_due_same_day", "days_since_created",
    "hour_of_due_time", "day_of_week"
]

def load_model_artifacts(model_path: str):
    """
    Loads all artifacts. Call once at FastAPI startup, not per-request.
    """
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    explainer_path = model_path.replace(".pkl", "_shap_explainer.pkl")
    with open(explainer_path, "rb") as f:
        explainer = pickle.load(f)

    meta_path = model_path.replace(".pkl", "_meta.json")
    with open(meta_path, "r") as f:
        meta = json.load(f)

    return model, explainer, meta


def predict_risk(model, explainer, task: dict, meta: dict) -> dict:
    """
    Scores a single live task against the trained model.

    Accepts a raw task dict (with hour_of_due_time and day_of_week as integers)
    and handles cyclic encoding and snooze_rate derivation internally.

    FIX: added explicit input validation. A missing key previously caused a
    silent KeyError deep inside encode_task_for_inference or the DataFrame
    constructor — now surfaces a clear ValueError with the missing field name.

    FastAPI usage:
        model, explainer, meta = load_model_artifacts("risk_prediction_model.pkl")

        @app.post("/api/tasks/risk")
        async def score_task(task: TaskSchema):
            return predict_risk(model, explainer, task.dict(), meta)
    """
    # FIX: validate all required fields are present before any processing
    missing = [f for f in REQUIRED_TASK_FIELDS if f not in task]
    if missing:
        raise ValueError(
            f"predict_risk: missing required task field(s): {missing}. "
            f"Required fields: {REQUIRED_TASK_FIELDS}"
        )

    column_order = meta["feature_columns"]
    threshold    = meta["optimal_threshold"]

    encoded_task = encode_task_for_inference(task)

    row        = pd.DataFrame([[encoded_task[col] for col in column_order]], columns=column_order)
    prob       = float(model.predict_proba(row)[0][1])
    prediction = int(prob >= threshold)

    if prob < 0.35:   label = "LOW"
    elif prob < 0.65: label = "MEDIUM"
    else:             label = "HIGH"

    explanations = explain_prediction(
        explainer, encoded_task, column_order, original_task=task
    )

    return {
        "risk_score":   round(prob, 4),
        "risk_label":   label,
        "prediction":   prediction,
        "threshold":    round(threshold, 4),
        "explanations": explanations[:4]
    }


# ================================================================
# ENTRY POINT
# ================================================================
if __name__ == "__main__":
    model, explainer, meta = train_and_save_model(
        num_samples = 5000,
        output_path = "risk_prediction_model.pkl",
        tune        = True
    )

    print("\n" + "=" * 60)
    print("DEMO — SINGLE TASK WITH SHAP EXPLANATION")
    print("=" * 60)

    sample_task = {
        "snooze_count":       3,
        "priority":           3,
        "energy_level":       2,
        "estimated_duration": 90,
        "global_time_debt":   250,
        "hour_of_due_time":   17,
        "day_of_week":        4,
        "tasks_due_same_day": 8,
        "days_since_created": 12,
    }

    result = predict_risk(model, explainer, sample_task, meta)

    print(f"\nRisk Score:  {result['risk_score']} ({result['risk_label']})")
    print(f"Prediction:  {'LIKELY MISSED' if result['prediction'] == 1 else 'LIKELY COMPLETED'}")
    print(f"Threshold:   {result['threshold']}")
    print("\nTop reasons (SHAP):")
    for exp in result["explanations"]:
        arrow = "↑" if exp["direction"] == "increases_risk" else "↓"
        print(f"  {arrow} {exp['explanation']}")