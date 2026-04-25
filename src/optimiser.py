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
    def __init__(self, existing_events: List[Dict[str, Any]], preferences: List[Dict[str, Any]], user_tz_string: str = "UTC", skip_weekends: bool = False, routines_on_weekends: bool = False, scheduling_start_hour: int = 8, scheduling_end_hour: int = 22):
        self.existing_events = list(existing_events) 
        self.preferences = list(preferences)
        self.interval_minutes = 15
        self.skip_weekends = skip_weekends
        self.routines_on_weekends = routines_on_weekends
        self.scheduling_start_hour = max(0, min(23, scheduling_start_hour))
        self.scheduling_end_hour = max(self.scheduling_start_hour + 1, min(24, scheduling_end_hour))

        try:
            self.user_tz = zoneinfo.ZoneInfo(user_tz_string)
        except Exception:
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
        if self.skip_weekends and target_date.weekday() >= 5:
            d = datetime.datetime.combine(target_date, datetime.time(self.scheduling_start_hour % 24, 0), tzinfo=self.user_tz).astimezone(datetime.timezone.utc)
            return d, d
        start_of_day = datetime.datetime.combine(target_date, datetime.time(self.scheduling_start_hour % 24, 0), tzinfo=self.user_tz)
        end_hour = self.scheduling_end_hour % 24
        if self.scheduling_end_hour == 24:
            end_of_day = datetime.datetime.combine(target_date + datetime.timedelta(days=1), datetime.time(0, 0), tzinfo=self.user_tz)
        else:
            end_of_day = datetime.datetime.combine(target_date, datetime.time(end_hour, 0), tzinfo=self.user_tz)
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

        print(f"\n{'='*60}")
        print(f"[inject_routines] {start_date} → {end_date} | {len(self.existing_events)} existing events")
        for ev in self.existing_events:
            ev_start = safe_parse_dt(ev.get("start", ""))
            ev_start_local = ev_start.astimezone(self.user_tz).strftime('%Y-%m-%d %H:%M') if ev_start else "?"
            ev_end = safe_parse_dt(ev.get("end", ""))
            ev_end_local = ev_end.astimezone(self.user_tz).strftime('%H:%M') if ev_end else "?"
            locked = "locked" if ev.get("is_locked") else "unlocked"
            print(f"  Event: {ev.get('title', 'Untitled')!r} [{ev.get('category','?')}] {ev_start_local}–{ev_end_local} ({locked})")
        print(f"{'='*60}\n")

        # ── Phase 1: Collect one best candidate per (day, routine) without committing ──
        all_candidates = []  # (score, day_offset, pref_idx, slot, pref, current_date)

        for i in range(delta.days + 1):
            current_date = start_date + datetime.timedelta(days=i)

            if not self.routines_on_weekends and current_date.weekday() >= 5:
                continue

            for pref_idx, pref in enumerate(self.preferences):
                if not (pref.get("is_routine", False) and "duration" in pref):
                    continue

                category = pref.get("category", "ALL")

                routine_already_exists = False
                for existing_event in self.existing_events:
                    if existing_event.get("category") == category and existing_event.get("provider") == "custom":
                        evt_date_str = existing_event.get("start", "")[:10]
                        if evt_date_str == current_date.isoformat():
                            routine_already_exists = True
                            break

                if routine_already_exists:
                    continue

                best_slot = self.find_best_slot(current_date, pref["duration"], category)
                if best_slot:
                    slot_start_local = best_slot.start.astimezone(self.user_tz)
                    slot_end_local = best_slot.end.astimezone(self.user_tz)
                    print(f"[Candidate] {current_date} | {category} ({pref['duration']}min) → {slot_start_local.strftime('%H:%M')}–{slot_end_local.strftime('%H:%M')} | score={best_slot.score}")
                    all_candidates.append((best_slot.score, i, pref_idx, best_slot, pref, current_date))

        # ── Phase 2: Sort globally by score (highest first) ──
        all_candidates.sort(key=lambda x: x[0], reverse=True)

        # ── Phase 3: Assign in score order, re-verifying each slot ──
        assigned: set = set()  # (day_offset, pref_idx)

        for score, day_idx, pref_idx, slot, pref, current_date in all_candidates:
            key = (day_idx, pref_idx)
            if key in assigned:
                continue

            category = pref.get("category", "ALL")

            # Re-verify: a higher-scoring prior commit may have claimed this slot
            if self._is_overlapping(slot.start, slot.end):
                print(f"[Re-search] {current_date} | {category} slot conflicted, searching again...")
                # Try a fresh search against the now-updated calendar
                slot = self.find_best_slot(current_date, pref["duration"], category)
                if not slot or self._is_overlapping(slot.start, slot.end):
                    print(f"[Skip] {current_date} | {category} — no valid slot found after re-search")
                    continue

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
                "is_ghost": True,
            }

            slot_start_local = slot.start.astimezone(self.user_tz)
            slot_end_local = slot.end.astimezone(self.user_tz)
            print(f"[Assigned] {current_date} | {category} → {slot_start_local.strftime('%H:%M')}–{slot_end_local.strftime('%H:%M')} | score={slot.score}")
            self.existing_events.append(ghost_event)
            routine_events.append(ghost_event)
            assigned.add(key)

        return routine_events