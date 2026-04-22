import datetime
import uuid
import zoneinfo
from typing import List, Dict, Any, Optional

class TimeSlot:
    def __init__(self, start_time: datetime.datetime, end_time: datetime.datetime, score: int = 0):
        self.start = start_time
        self.end = end_time
        self.duration_minutes = int((end_time - start_time).total_seconds() / 60)
        self.score = score

class BaseScheduler:
    def __init__(self, existing_events: List[Dict[str, Any]], preferences: List[Dict[str, Any]], user_tz_string: str = "UTC"):
        self.existing_events = list(existing_events) 
        self.preferences = list(preferences)
        self.interval_minutes = 15 
        
        # --- THE FIX: DYNAMIC TIMEZONE INJECTION ---
        try:
            self.user_tz = zoneinfo.ZoneInfo(user_tz_string)
        except zoneinfo.ZoneInfoNotFoundError:
            print(f"⚠️ Invalid timezone '{user_tz_string}', falling back to UTC.")
            self.user_tz = zoneinfo.ZoneInfo("UTC")

        has_meal_window = any(p.get("category") == "MEAL" and p.get("type") == "WINDOW" for p in self.preferences)
        if not has_meal_window:
            self.preferences.append({
                "category": "MEAL",
                "type": "WINDOW",
                "params": {"start": 12.0, "end": 15.0},
                "is_hard": False,
                "weight": 8
            })

    def _parse_dt(self, iso_str: str) -> Optional[datetime.datetime]:
        if not iso_str: return None
        try:
            s = str(iso_str).strip()
            if s.endswith('Z'): s = s[:-1] + "+00:00"
            s = s.replace("+00:00+00:00", "+00:00")
            
            parsed = datetime.datetime.fromisoformat(s)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed
        except Exception as e:
            print(f"[Parse Error] Failed to parse {iso_str}: {e}")
            return None

    def _get_day_boundaries(self, target_date: datetime.date):
        start_of_day_local = datetime.datetime.combine(target_date, datetime.time(8, 0), tzinfo=self.user_tz)
        end_of_day_local = datetime.datetime.combine(target_date, datetime.time(22, 0), tzinfo=self.user_tz)
        
        # --- THE FIX: Block Time-Travel Booking ---
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = now_utc.astimezone(self.user_tz)
        
        # If the target date is in the past, return a zero-minute window so the engine skips it entirely
        if target_date < now_local.date():
            return end_of_day_local.astimezone(datetime.timezone.utc), end_of_day_local.astimezone(datetime.timezone.utc)
            
        # If the target date is today, push the start line forward to the current time
        if target_date == now_local.date() and now_local > start_of_day_local:
            # Round the current time up to the next 15-minute mark for neat calendar blocks
            discard = datetime.timedelta(minutes=now_local.minute % 15,
                                         seconds=now_local.second,
                                         microseconds=now_local.microsecond)
            now_local -= discard
            if discard > datetime.timedelta(0):
                now_local += datetime.timedelta(minutes=15)
            
            start_of_day_local = max(start_of_day_local, now_local)
            
        return start_of_day_local.astimezone(datetime.timezone.utc), end_of_day_local.astimezone(datetime.timezone.utc)

    def _is_overlapping(self, slot_start: datetime.datetime, slot_end: datetime.datetime) -> bool:
        for event in self.existing_events:
            if not event.get("is_locked", True): continue
            
            event_start = self._parse_dt(event.get("start"))
            event_end = self._parse_dt(event.get("end"))
            if not event_start or not event_end: continue
            
            travel_time = event.get("travel_time", 0)
            if travel_time > 0: event_start = event_start - datetime.timedelta(minutes=travel_time)

            if slot_start < event_end and slot_end > event_start:
                return True
        return False

    def _calculate_gaps(self, slot_start: datetime.datetime, slot_end: datetime.datetime):
        min_gap_before = float('inf')
        min_gap_after = float('inf')

        for event in self.existing_events:
            event_start = self._parse_dt(event.get("start"))
            event_end = self._parse_dt(event.get("end"))
            if not event_start or not event_end: continue
            
            travel_time = event.get("travel_time", 0)
            if travel_time > 0: event_start = event_start - datetime.timedelta(minutes=travel_time)

            if event_end <= slot_start:
                gap = int((slot_start - event_end).total_seconds() / 60)
                if gap < min_gap_before: min_gap_before = gap
            
            if event_start >= slot_end:
                gap = int((event_start - slot_end).total_seconds() / 60)
                if gap < min_gap_after: min_gap_after = gap

        return min_gap_before, min_gap_after

    def _fails_hard_constraints(self, slot_start: datetime.datetime, slot_end: datetime.datetime, event_category: str, gaps: tuple) -> bool:
        min_gap_before, min_gap_after = gaps
        slot_start_local = slot_start.astimezone(self.user_tz)
        slot_end_local = slot_end.astimezone(self.user_tz)
        slot_start_hour = slot_start_local.hour + (slot_start_local.minute / 60.0)
        slot_end_hour = slot_end_local.hour + (slot_end_local.minute / 60.0)

        for pref in self.preferences:
            if not pref.get("is_hard", False): continue
            pref_category = pref.get("category", "ALL")
            
            if pref["type"] == "WINDOW":
                if pref_category == "MEAL" and pref.get("is_routine") and "start" not in pref.get("params", {}):
                    allowed_start, allowed_end = 12.0, 15.0
                else:
                    allowed_start = pref.get("params", {}).get("start", 0)
                    allowed_end = pref.get("params", {}).get("end", 24)

                if pref_category == event_category or pref_category == "ALL":
                    if allowed_start > allowed_end:
                        if not (slot_start_hour >= allowed_start or slot_end_hour <= allowed_end): return True
                    else:
                        if slot_start_hour < allowed_start or slot_end_hour > allowed_end: return True 

                elif event_category != pref_category:
                    if slot_start_hour >= allowed_start and slot_end_hour <= allowed_end:
                        if pref.get("is_exclusive", False): return True

            elif pref["type"] == "BUFFER" and pref_category in ("ALL", event_category):
                req_minutes = pref.get("params", {}).get("minutes", 0)
                if min_gap_before != float('inf') and min_gap_before < req_minutes: return True
                if min_gap_after != float('inf') and min_gap_after < req_minutes: return True
                    
        return False

    def _score_soft_constraints(self, slot_start: datetime.datetime, slot_end: datetime.datetime, event_category: str, gaps: tuple, relax_hard_constraints: bool, original_start_dt: Optional[datetime.datetime]) -> int:
        score = 100 
        min_gap_before, min_gap_after = gaps
        has_explicit_buffer_pref = False
        slot_start_local = slot_start.astimezone(self.user_tz)
        slot_end_local = slot_end.astimezone(self.user_tz)
        slot_start_hour = slot_start_local.hour + (slot_start_local.minute / 60.0)
        slot_end_hour = slot_end_local.hour + (slot_end_local.minute / 60.0)

        if original_start_dt:
            orig_local = original_start_dt.astimezone(self.user_tz)
            orig_hour = orig_local.hour + (orig_local.minute / 60.0)
            hour_diff = abs(slot_start_hour - orig_hour)
            score -= int(hour_diff * 0.5) 
        
        for pref in self.preferences:
            pref_category = pref.get("category", "ALL")
            is_hard = pref.get("is_hard", False)
            if is_hard and not relax_hard_constraints: continue
            weight = 1000 if (is_hard and relax_hard_constraints) else pref.get("weight", 5)

            if pref["type"] == "WINDOW":
                if pref_category == "MEAL" and pref.get("is_routine") and "start" not in pref.get("params", {}):
                    allowed_start, allowed_end = 12.0, 15.0
                else:
                    allowed_start = pref.get("params", {}).get("start", 0)
                    allowed_end = pref.get("params", {}).get("end", 24)
                
                if pref_category == event_category or pref_category == "ALL":
                    is_outside = not (slot_start_hour >= allowed_start or slot_end_hour <= allowed_end) if allowed_start > allowed_end else (slot_start_hour < allowed_start or slot_end_hour > allowed_end)
                    if is_outside: score -= (weight * 50) 
                elif event_category != pref_category:
                    if slot_start_hour >= allowed_start and slot_end_hour <= allowed_end:
                        if pref.get("is_exclusive", False): score -= (weight * 50)

            elif pref["type"] == "BUFFER" and pref_category in ("ALL", event_category):
                has_explicit_buffer_pref = True
                req_minutes = pref.get("params", {}).get("minutes", 15)
                if min_gap_before != float('inf') and min_gap_before < req_minutes: score -= (weight * 10) 
                if min_gap_after != float('inf') and min_gap_after < req_minutes: score -= (weight * 10)

        if not has_explicit_buffer_pref:
            if min_gap_before != float('inf'):
                if min_gap_before == 0: score -= 20 
                elif min_gap_before < 5: score -= 30 
                else: score += 20 
            if min_gap_after != float('inf'):
                if min_gap_after == 0: score -= 20 
                elif min_gap_after < 5: score -= 30 
                else: score += 20 

        return score

    def _search_slots(self, target_date: datetime.date, duration_minutes: int, event_category: str, relax_hard_constraints: bool, original_start_dt: Optional[datetime.datetime]) -> Optional[TimeSlot]:
        start_of_day, end_of_day = self._get_day_boundaries(target_date)
        current_time = start_of_day
        best_slot = None
        highest_score = -99999

        while current_time + datetime.timedelta(minutes=duration_minutes) <= end_of_day:
            slot_end = current_time + datetime.timedelta(minutes=duration_minutes)
            if self._is_overlapping(current_time, slot_end):
                current_time += datetime.timedelta(minutes=self.interval_minutes)
                continue

            gaps = self._calculate_gaps(current_time, slot_end)
            if not relax_hard_constraints and self._fails_hard_constraints(current_time, slot_end, event_category, gaps):
                current_time += datetime.timedelta(minutes=self.interval_minutes)
                continue

            slot_score = self._score_soft_constraints(current_time, slot_end, event_category, gaps, relax_hard_constraints, original_start_dt)
            if slot_score > highest_score:
                highest_score = slot_score
                best_slot = TimeSlot(current_time, slot_end, slot_score)

            current_time += datetime.timedelta(minutes=self.interval_minutes)

        return best_slot

    def find_best_slot(self, target_date: datetime.date, duration_minutes: int, event_category: str = "MEETING", original_start_dt: Optional[datetime.datetime] = None) -> Optional[TimeSlot]:
        best_slot = self._search_slots(target_date, duration_minutes, event_category, relax_hard_constraints=False, original_start_dt=original_start_dt)
        if not best_slot:
            best_slot = self._search_slots(target_date, duration_minutes, event_category, relax_hard_constraints=True, original_start_dt=original_start_dt)
        return best_slot

    def _get_all_candidate_slots(self, target_date: datetime.date, duration_minutes: int, event_category: str, relax_hard_constraints: bool = False) -> List[TimeSlot]:
        """Returns every feasible, scored slot for a given day."""
        start_of_day, end_of_day = self._get_day_boundaries(target_date)
        current_time = start_of_day
        candidates = []

        while current_time + datetime.timedelta(minutes=duration_minutes) <= end_of_day:
            slot_end = current_time + datetime.timedelta(minutes=duration_minutes)
            if not self._is_overlapping(current_time, slot_end):
                gaps = self._calculate_gaps(current_time, slot_end)
                if relax_hard_constraints or not self._fails_hard_constraints(current_time, slot_end, event_category, gaps):
                    score = self._score_soft_constraints(current_time, slot_end, event_category, gaps, relax_hard_constraints, None)
                    candidates.append(TimeSlot(current_time, slot_end, score))
            current_time += datetime.timedelta(minutes=self.interval_minutes)

        return candidates

    def _get_all_candidates_across_days(self, start_date: datetime.date, end_date: datetime.date, duration_minutes: int, event_category: str, due_dt: Optional[datetime.datetime], scheduled_dates: List[datetime.date], relax_hard_constraints: bool = False) -> List[TimeSlot]:
        """Returns all candidate slots across a date range, with spacing penalties applied."""
        all_candidates = []
        max_days = min((end_date - start_date).days + 1, 60)

        for i in range(max_days):
            current_date = start_date + datetime.timedelta(days=i)
            for slot in self._get_all_candidate_slots(current_date, duration_minutes, event_category, relax_hard_constraints):
                if due_dt and slot.end > due_dt:
                    continue
                spacing_penalty = 0
                for prev_date in scheduled_dates:
                    diff_days = abs((current_date - prev_date).days)
                    if diff_days == 0: spacing_penalty += 3000
                    elif diff_days == 1: spacing_penalty += 800
                    elif diff_days == 2: spacing_penalty += 300
                    elif diff_days == 3: spacing_penalty += 100
                slot.score -= spacing_penalty
                all_candidates.append(slot)

        return all_candidates

    def _holistic_assign(self, items_with_candidates: List[tuple]) -> Dict:
        """
        Globally optimal, non-conflicting assignment of items to time slots.

        Instead of placing items one at a time (greedy / first-come-first-served),
        this explores every valid combination of (item → slot) assignments and picks
        the one that maximises total score, with placement count taking priority.

        Uses backtracking with branch-and-bound pruning.
        Practical for ≤ 8 items with ≤ 20 candidates each.

        items_with_candidates: List of (key, List[TimeSlot]) — key can be any hashable.
        Returns: dict mapping key -> TimeSlot for the optimal assignment.
        """
        if not items_with_candidates:
            return {}

        n = len(items_with_candidates)
        prepared = [
            (key, sorted(cands, key=lambda s: s.score, reverse=True)[:20])
            for key, cands in items_with_candidates
        ]
        best_possible = [max((s.score for s in c), default=0) for _, c in prepared]

        state: Dict = {"placed": -1, "score": float("-inf"), "assignment": {}}

        def backtrack(idx: int, assignment: Dict, placed: int, score: int) -> None:
            if idx == n:
                if placed > state["placed"] or (placed == state["placed"] and score > state["score"]):
                    state.update(placed=placed, score=score, assignment=dict(assignment))
                return

            remaining = n - idx
            if placed + remaining < state["placed"]:
                return
            if placed + remaining == state["placed"]:
                if score + sum(best_possible[j] for j in range(idx, n)) <= state["score"]:
                    return

            key, candidates = prepared[idx]
            for slot in candidates:
                if any(slot.start < a.end and slot.end > a.start for a in assignment.values()):
                    continue
                assignment[key] = slot
                backtrack(idx + 1, assignment, placed + 1, score + slot.score)
                del assignment[key]

            # Allow skipping so the solver can trade one item for a better global fit
            backtrack(idx + 1, assignment, placed, score)

        backtrack(0, {}, 0, 0)
        return state["assignment"]


class TaskScheduler(BaseScheduler):
    def __init__(self, existing_events: List[Dict[str, Any]], preferences: List[Dict[str, Any]], user_tz_string: str = "UTC"):
        # --- THE FIX: PASS DYNAMIC TIMEZONE UP ---
        super().__init__(existing_events, preferences, user_tz_string=user_tz_string)
        self.interval_minutes = 5

    def _is_overlapping(self, slot_start: datetime.datetime, slot_end: datetime.datetime) -> bool:
        for event in self.existing_events:
            event_start = self._parse_dt(event.get("start"))
            event_end = self._parse_dt(event.get("end"))
            if not event_start or not event_end: continue

            travel_time = event.get("travel_time", 0)
            if travel_time > 0:
                event_start = event_start - datetime.timedelta(minutes=travel_time)

            if slot_start < event_end and slot_end > event_start:
                return True
        return False

    def _map_task_to_category(self, task: Dict[str, Any]) -> str:
        tags = [t.upper() for t in task.get("tags", [])]
        energy = task.get("energy_level", "medium").lower()
        if "DEEP WORK" in tags or "STUDY" in tags or energy == "high":
            return "DEEP_WORK"
        elif "MEETING" in tags or "CALL" in tags:
            return "MEETING"
        elif "ADMIN" in tags or energy == "low":
            return "SHALLOW_WORK"
        return "SHALLOW_WORK"

    def _find_best_slot_across_days(self, start_date: datetime.date, end_date: datetime.date, duration: int, category: str, due_dt: Optional[datetime.datetime], scheduled_dates: List[datetime.date]) -> Optional[TimeSlot]:
        overall_best = None
        delta = end_date - start_date
        max_days = min(delta.days + 1, 60)
        
        for i in range(max_days):
            current_date = start_date + datetime.timedelta(days=i)
            slot = self.find_best_slot(current_date, duration, category)
            
            if slot:
                if due_dt and slot.end > due_dt:
                    continue
                
                spacing_penalty = 0
                for prev_date in scheduled_dates:
                    diff_days = abs((current_date - prev_date).days)
                    if diff_days == 0: spacing_penalty += 3000
                    elif diff_days == 1: spacing_penalty += 800  
                    elif diff_days == 2: spacing_penalty += 300  
                    elif diff_days == 3: spacing_penalty += 100
                        
                slot.score -= spacing_penalty
                
                if not overall_best or slot.score > overall_best.score:
                    overall_best = slot
                    
        return overall_best

    def schedule_tasks(self, start_date: datetime.date, fallback_end_date: datetime.date, pending_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scheduled_task_events = []
        valid_tasks = [t for t in pending_tasks if t.get("estimated_duration")]
        valid_tasks.sort(key=lambda t: (t.get("priority", 3), t.get("due_date") or "9999-12-31T23:59:59Z"))

        # Build per-task state so we can track progress across holistic rounds
        task_states = []
        for task in valid_tasks:
            energy = task.get("energy_level", "medium").lower()
            if energy == "high":
                min_chunk, max_chunk = 45, 90
            elif energy == "low":
                min_chunk, max_chunk = 15, 60
            else:
                min_chunk, max_chunk = 30, 120
            min_chunk = min(min_chunk, task["estimated_duration"])

            due_date_str = task.get("due_date")
            if due_date_str:
                due_dt = self._parse_dt(due_date_str)
                task_end_date = due_dt.date() if due_dt else fallback_end_date
            else:
                due_dt = None
                task_end_date = fallback_end_date

            task_states.append({
                "task": task,
                "remaining": task["estimated_duration"],
                "scheduled_dates": [],
                "chunk_count": 0,
                "min_chunk": min_chunk,
                "max_chunk": max_chunk,
                "category": self._map_task_to_category(task),
                "due_dt": due_dt,
                "task_end_date": task_end_date,
            })

        # Round-based holistic scheduling: each round assigns one chunk per task simultaneously.
        # All candidates are generated before any slot is committed, so every task sees the
        # same unmodified free time and the solver finds the globally optimal non-conflicting set.
        MAX_ROUNDS = 20
        for _ in range(MAX_ROUNDS):
            items_with_candidates = []   # (idx, candidates)
            attempt_durations: Dict[int, int] = {}

            for idx, state in enumerate(task_states):
                if state["remaining"] <= 0:
                    continue
                if state["task_end_date"] < start_date:
                    state["remaining"] = 0
                    continue

                # Determine chunk size, shrinking until we find candidates
                attempt_duration = min(state["remaining"], state["max_chunk"])
                candidates: List[TimeSlot] = []
                while attempt_duration >= state["min_chunk"]:
                    candidates = self._get_all_candidates_across_days(
                        start_date, state["task_end_date"], attempt_duration,
                        state["category"], state["due_dt"], state["scheduled_dates"]
                    )
                    if candidates:
                        break
                    next_attempt = max(15, round((attempt_duration // 2) / 15) * 15)
                    if next_attempt < state["min_chunk"]:
                        break
                    attempt_duration = next_attempt

                if candidates:
                    items_with_candidates.append((idx, candidates))
                    attempt_durations[idx] = attempt_duration

            if not items_with_candidates:
                break

            # Holistically find the globally optimal non-conflicting assignment
            assignment = self._holistic_assign(items_with_candidates)
            if not assignment:
                break

            # Commit placed chunks and update state
            for idx, slot in assignment.items():
                state = task_states[idx]
                task = state["task"]
                state["chunk_count"] += 1
                attempt_duration = attempt_durations[idx]

                is_multi = state["remaining"] < task["estimated_duration"] or state["chunk_count"] > 1
                title = f"{task.get('title')} (Part {state['chunk_count']})" if is_multi else task.get("title")

                ghost_event = {
                    "id": f"evt_task_{uuid.uuid4().hex[:8]}",
                    "title": title,
                    "start": slot.start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "end": slot.end.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "is_locked": True,
                    "provider": "tasks",
                    "status": "synced",
                    "requires_review": False,
                    "has_drifted": False,
                    "category": state["category"],
                    "is_ghost": True,
                    "linked_task_id": task.get("id")
                }
                self.existing_events.append(ghost_event)
                scheduled_task_events.append(ghost_event)
                state["remaining"] -= attempt_duration
                state["scheduled_dates"].append(slot.start.date())

        return scheduled_task_events
    
class DebtRescheduler(BaseScheduler):
    def schedule_debt(self, start_date: datetime.date, end_date: datetime.date, debt_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print(f"\n[DebtRescheduler] 🧠 Booting up. Attempting to fill gaps with {len(debt_items)} reclaimed items...")
        ghost_events = []

        max_days = min((end_date - start_date).days + 1, 14)
        window_end = start_date + datetime.timedelta(days=max_days - 1)

        debt_items.sort(key=lambda x: x.get("priority", 3))

        # Generate ALL candidates for every debt item up-front (before placing any).
        # This ensures the holistic solver sees unmodified free time for all items.
        items_with_meta = []
        for item in debt_items:
            duration = item.get("duration", 60)
            category = "DEEP_WORK" if item.get("priority", 3) <= 2 else "SHALLOW_WORK"
            if item.get("original_type") == "event":
                category = "MEETING"

            candidates = self._get_all_candidates_across_days(start_date, window_end, duration, category, None, [])
            if not candidates:
                candidates = self._get_all_candidates_across_days(start_date, window_end, duration, category, None, [], relax_hard_constraints=True)

            print(f"[DebtRescheduler] 🎯 '{item.get('title')}' ({duration} mins | {category}) — {len(candidates)} candidate slots")
            items_with_meta.append((item, category, candidates))

        # Holistically find the globally optimal non-conflicting assignment
        solver_input = [(idx, cands) for idx, (_, _, cands) in enumerate(items_with_meta)]
        assignment = self._holistic_assign(solver_input)

        # Commit placed items
        for idx, slot in assignment.items():
            item, category, _ = items_with_meta[idx]
            local_start = slot.start.astimezone(self.user_tz)
            print(f"[DebtRescheduler]   ✅ Placed '{item.get('title')}' on {local_start.date()} at {local_start.strftime('%H:%M')} (Score: {slot.score})")

            ghost_event = {
                "id": f"ghost_debt_{uuid.uuid4().hex[:8]}",
                "title": item.get("title"),
                "start": slot.start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "end": slot.end.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "is_locked": True,
                "provider": "tasks" if item.get("original_type") == "task" else "custom",
                "status": "synced",
                "requires_review": False,
                "has_drifted": False,
                "category": category,
                "is_ghost": True,
                "linked_task_id": item.get("id") if item.get("original_type") == "task" else None,
                "linked_event_id": item.get("id") if item.get("original_type") == "event" else None,
                "debt_duration": item.get("duration", 60)
            }
            self.existing_events.append(ghost_event)
            ghost_events.append(ghost_event)

        # Report unplaced items
        placed = set(assignment.keys())
        for idx, (item, _, _) in enumerate(items_with_meta):
            if idx not in placed:
                print(f"[DebtRescheduler]   ❌ FAILED to find any non-overlapping {item.get('duration', 60)}m slot for '{item.get('title')}' within {max_days} days.")

        print(f"[DebtRescheduler] 🏁 Finished. Successfully slotted {len(ghost_events)} catch-up blocks.")
        return ghost_events