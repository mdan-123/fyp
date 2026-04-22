import datetime
import uuid
import zoneinfo
from typing import List, Dict, Any, Optional

def safe_parse_dt(iso_str: str) -> Optional[datetime.datetime]:
    if not iso_str: return None
    try:
        s = str(iso_str).strip()
        # Scrub double offsets
        s = s.replace("+00:00Z", "+00:00")
        if s.endswith('Z'): s = s[:-1] + "+00:00"
        s = s.replace("+00:00+00:00", "+00:00")
        
        parsed = datetime.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except Exception as e:
        print(f"[Parse Error] Failed to parse {iso_str}: {e}")
        return None

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

        try:
            self.user_tz = zoneinfo.ZoneInfo(user_tz_string)
        except:
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

    def _get_day_boundaries(self, target_date: datetime.date):
        start_of_day = datetime.datetime.combine(target_date, datetime.time(8, 0), tzinfo=self.user_tz)
        end_of_day = datetime.datetime.combine(target_date, datetime.time(22, 0), tzinfo=self.user_tz)
        return start_of_day.astimezone(datetime.timezone.utc), end_of_day.astimezone(datetime.timezone.utc)

    def _is_overlapping(self, slot_start: datetime.datetime, slot_end: datetime.datetime) -> bool:
        for event in self.existing_events:
            if not event.get("is_locked", True):
                continue
            
            event_start = safe_parse_dt(event["start"])
            event_end = safe_parse_dt(event["end"])
            if not event_start or not event_end: continue
            
            travel_time = event.get("travel_time", 0)
            if travel_time > 0:
                event_start = event_start - datetime.timedelta(minutes=travel_time)

            if slot_start < event_end and slot_end > event_start:
                return True
        return False

    def _calculate_gaps(self, slot_start: datetime.datetime, slot_end: datetime.datetime):
        min_gap_before = float('inf')
        min_gap_after = float('inf')

        for event in self.existing_events:
            event_start = safe_parse_dt(event["start"])
            event_end = safe_parse_dt(event["end"])
            if not event_start or not event_end: continue
            
            travel_time = event.get("travel_time", 0)
            if travel_time > 0:
                event_start = event_start - datetime.timedelta(minutes=travel_time)

            if event_end <= slot_start:
                gap = int((slot_start - event_end).total_seconds() / 60)
                if gap < min_gap_before:
                    min_gap_before = gap
            
            if event_start >= slot_end:
                gap = int((event_start - slot_end).total_seconds() / 60)
                if gap < min_gap_after:
                    min_gap_after = gap

        return min_gap_before, min_gap_after

    def _fails_hard_constraints(self, slot_start: datetime.datetime, slot_end: datetime.datetime, event_category: str, gaps: tuple) -> bool:
        min_gap_before, min_gap_after = gaps
        
        # Check hour in local timezone
        slot_start_local = slot_start.astimezone(self.user_tz)
        slot_end_local = slot_end.astimezone(self.user_tz)
        slot_start_hour = slot_start_local.hour + (slot_start_local.minute / 60.0)
        slot_end_hour = slot_end_local.hour + (slot_end_local.minute / 60.0)

        for pref in self.preferences:
            if not pref.get("is_hard", False):
                continue
            
            pref_category = pref.get("category", "ALL")
            
            if pref["type"] == "WINDOW":
                if pref_category == "MEAL" and pref.get("is_routine") and "start" not in pref.get("params", {}):
                    allowed_start = 12.0
                    allowed_end = 15.0
                else:
                    allowed_start = pref.get("params", {}).get("start", 0)
                    allowed_end = pref.get("params", {}).get("end", 24)

                if pref_category == event_category or pref_category == "ALL":
                    if allowed_start > allowed_end:
                        if not (slot_start_hour >= allowed_start or slot_end_hour <= allowed_end):
                            return True
                    else:
                        if slot_start_hour < allowed_start or slot_end_hour > allowed_end:
                            return True 

                elif event_category != pref_category:
                    if slot_start_hour >= allowed_start and slot_end_hour <= allowed_end:
                        if pref.get("is_exclusive", False):
                            return True

            elif pref["type"] == "BUFFER" and pref_category in ("ALL", event_category):
                req_minutes = pref.get("params", {}).get("minutes", 0)
                if min_gap_before != float('inf') and min_gap_before < req_minutes:
                    return True
                if min_gap_after != float('inf') and min_gap_after < req_minutes:
                    return True
                    
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
            
            if is_hard and not relax_hard_constraints:
                continue

            weight = 1000 if (is_hard and relax_hard_constraints) else pref.get("weight", 5)

            if pref["type"] == "WINDOW":
                if pref_category == "MEAL" and pref.get("is_routine") and "start" not in pref.get("params", {}):
                    allowed_start = 12.0
                    allowed_end = 15.0
                else:
                    allowed_start = pref.get("params", {}).get("start", 0)
                    allowed_end = pref.get("params", {}).get("end", 24)
                
                if pref_category == event_category or pref_category == "ALL":
                    if allowed_start > allowed_end:
                        is_outside = not (slot_start_hour >= allowed_start or slot_end_hour <= allowed_end)
                    else:
                        is_outside = (slot_start_hour < allowed_start or slot_end_hour > allowed_end)
                        
                    if is_outside:
                        score -= (weight * 50) 
                        
                elif event_category != pref_category:
                    if slot_start_hour >= allowed_start and slot_end_hour <= allowed_end:
                        if pref.get("is_exclusive", False):
                            score -= (weight * 50)

            elif pref["type"] == "BUFFER" and pref_category in ("ALL", event_category):
                has_explicit_buffer_pref = True
                req_minutes = pref.get("params", {}).get("minutes", 15)
                if min_gap_before != float('inf') and min_gap_before < req_minutes:
                    score -= (weight * 10) 
                if min_gap_after != float('inf') and min_gap_after < req_minutes:
                    score -= (weight * 10)

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

    def _get_all_candidate_slots(self, target_date: datetime.date, duration_minutes: int, event_category: str, relax_hard_constraints: bool = False) -> List[TimeSlot]:
        """Returns every feasible, scored slot for a routine on a given day."""
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

    def _holistic_assign(self, routines_with_candidates: List[tuple]) -> Dict[str, Any]:
        """
        Globally optimal, non-conflicting assignment of routines to time slots.

        Instead of placing routines one at a time (greedy / first-come-first-served),
        this explores every combination of (routine → slot) assignments and selects
        the one that maximises total score, with placement count taking priority
        over score (i.e. always prefer placing more routines).

        Uses backtracking with branch-and-bound pruning.
        Practical for ≤ 6 routines with ≤ 20 candidates each.
        """
        if not routines_with_candidates:
            return {}

        n = len(routines_with_candidates)
        # Sort each routine's candidates best-first and cap at 20 to bound search space
        prepared = [
            (pref, sorted(cands, key=lambda s: s.score, reverse=True)[:20])
            for pref, cands in routines_with_candidates
        ]
        # Upper-bound per routine: best score achievable (used for pruning)
        best_possible = [max((s.score for s in c), default=0) for _, c in prepared]

        state: Dict[str, Any] = {"placed": -1, "score": float("-inf"), "assignment": {}}

        def backtrack(idx: int, assignment: Dict[str, TimeSlot], placed: int, score: int) -> None:
            if idx == n:
                if placed > state["placed"] or (placed == state["placed"] and score > state["score"]):
                    state.update(placed=placed, score=score, assignment=dict(assignment))
                return

            # Branch-and-bound: prune if we can't beat the current best
            remaining = n - idx
            if placed + remaining < state["placed"]:
                return
            if placed + remaining == state["placed"]:
                remaining_score = sum(best_possible[j] for j in range(idx, n))
                if score + remaining_score <= state["score"]:
                    return

            pref, candidates = prepared[idx]
            cat = pref.get("category", "ALL")

            for slot in candidates:
                # Skip slots that conflict with already-assigned routines
                if any(slot.start < a.end and slot.end > a.start for a in assignment.values()):
                    continue
                assignment[cat] = slot
                backtrack(idx + 1, assignment, placed + 1, score + slot.score)
                del assignment[cat]

            # Also explore skipping this routine so the solver can trade a lower-priority
            # routine for a globally better placement of higher-priority ones
            backtrack(idx + 1, assignment, placed, score)

        backtrack(0, {}, 0, 0)
        return state["assignment"]

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


class Optimiser(BaseScheduler):
    def inject_routines(self, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
        routine_events = []
        delta = end_date - start_date

        for i in range(delta.days + 1):
            current_date = start_date + datetime.timedelta(days=i)

            # Collect every routine that still needs to be placed on this day
            routines_to_place = []
            for pref in self.preferences:
                if not (pref.get("is_routine", False) and "duration" in pref):
                    continue
                category = pref.get("category", "ALL")
                already_exists = any(
                    e.get("category") == category
                    and e.get("provider") == "custom"
                    and e.get("start", "")[:10] == current_date.isoformat()
                    for e in self.existing_events
                )
                if not already_exists:
                    routines_to_place.append(pref)

            if not routines_to_place:
                continue

            # Generate ALL candidate slots for every routine up-front (before placing any).
            # This ensures the holistic solver sees unmodified free time for all routines.
            routines_with_candidates = []
            for pref in routines_to_place:
                category = pref.get("category", "ALL")
                duration = pref["duration"]
                candidates = self._get_all_candidate_slots(current_date, duration, category)
                if not candidates:
                    candidates = self._get_all_candidate_slots(current_date, duration, category, relax_hard_constraints=True)
                routines_with_candidates.append((pref, candidates))

            # Holistically find the globally optimal, non-conflicting assignment
            assignment = self._holistic_assign(routines_with_candidates)

            # Commit the chosen slots and register ghost events
            for category, slot in assignment.items():
                title = f"Routine: {category.replace('_', ' ').title()}"
                ghost_event = {
                    "id": f"ghost_{uuid.uuid4().hex[:8]}",
                    "title": title,
                    "start": slot.start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "end": slot.end.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "is_locked": True,
                    "provider": "custom",
                    "status": "synced",
                    "requires_review": False,
                    "has_drifted": False,
                    "category": category,
                    "is_ghost": True
                }
                self.existing_events.append(ghost_event)
                routine_events.append(ghost_event)

        return routine_events