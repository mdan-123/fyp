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
    def __init__(self, existing_events: List[Dict[str, Any]], preferences: List[Dict[str, Any]], user_tz_string: str = "UTC", skip_weekends: bool = False, routines_on_weekends: bool = False, scheduling_start_hour: int = 8, scheduling_end_hour: int = 22):
        self.existing_events = list(existing_events) 
        self.preferences = list(preferences)
        self.interval_minutes = 15
        self.skip_weekends = skip_weekends
        self.routines_on_weekends = routines_on_weekends
        self.scheduling_start_hour = max(0, min(23, scheduling_start_hour))
        self.scheduling_end_hour = max(self.scheduling_start_hour + 1, min(24, scheduling_end_hour))
        
        # Validate and store the user's local timezone
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
        # Weekend days return a zero-length window so the engine skips them
        if self.skip_weekends and target_date.weekday() >= 5:
            d = datetime.datetime.combine(target_date, datetime.time(self.scheduling_start_hour % 24, 0), tzinfo=self.user_tz).astimezone(datetime.timezone.utc)
            return d, d

        start_of_day_local = datetime.datetime.combine(target_date, datetime.time(self.scheduling_start_hour % 24, 0), tzinfo=self.user_tz)

        # Handle midnight end (hour 24 = start of next day)
        if self.scheduling_end_hour == 24:
            end_of_day_local = datetime.datetime.combine(target_date + datetime.timedelta(days=1), datetime.time(0, 0), tzinfo=self.user_tz)
        else:
            end_of_day_local = datetime.datetime.combine(target_date, datetime.time(self.scheduling_end_hour, 0), tzinfo=self.user_tz)

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = now_utc.astimezone(self.user_tz)

        # Past dates return a zero-length window so they are skipped entirely
        if target_date < now_local.date():
            return end_of_day_local.astimezone(datetime.timezone.utc), end_of_day_local.astimezone(datetime.timezone.utc)

        # For today, advance the start to now (rounded up to nearest 15 min)
        if target_date == now_local.date() and now_local > start_of_day_local:
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



class TaskScheduler(BaseScheduler):
    def __init__(self, existing_events: List[Dict[str, Any]], preferences: List[Dict[str, Any]], user_tz_string: str = "UTC", skip_weekends: bool = False, scheduling_start_hour: int = 8, scheduling_end_hour: int = 22):
        super().__init__(existing_events, preferences, user_tz_string=user_tz_string, skip_weekends=skip_weekends, scheduling_start_hour=scheduling_start_hour, scheduling_end_hour=scheduling_end_hour)
        # Finer 5-minute scan interval for task placement vs 15 min for calendar events
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
        # Maps task tags/energy to a preference category used by the constraint scorer
        tags = [t.upper() for t in task.get("tags", [])]
        energy = task.get("energy_level", "medium").lower()
        if "DEEP WORK" in tags or "STUDY" in tags or energy == "high":
            return "DEEP_WORK"
        elif "MEETING" in tags or "CALL" in tags:
            return "MEETING"
        elif "ADMIN" in tags or energy == "low":
            return "SHALLOW_WORK"
        return "SHALLOW_WORK"

    def _determine_chunks(self, task: Dict[str, Any]) -> List[int]:
        """Split a task's total duration into manageable chunks based on energy level."""
        total = task["estimated_duration"]
        energy = task.get("energy_level", "medium").lower()

        # High-energy tasks use shorter, focused blocks; low-energy tasks allow longer stretches
        if energy == "high":
            min_chunk, max_chunk = 45, 90
        elif energy == "low":
            min_chunk, max_chunk = 15, 60
        else:
            min_chunk, max_chunk = 30, 120

        min_chunk = min(min_chunk, total)
        chunks: List[int] = []
        remaining = total
        while remaining > 0:
            chunk = min(remaining, max_chunk)
            # If the leftover is too small for its own block, merge it into the last chunk
            if chunk < min_chunk:
                if chunks:
                    chunks[-1] += chunk
                else:
                    chunks.append(chunk)
                break
            chunks.append(chunk)
            remaining -= chunk
        return chunks

    def _collect_top_k_slots(self, start_date: datetime.date, end_date: datetime.date,
                              duration: int, category: str, due_dt: Optional[datetime.datetime],
                              k: int = 10) -> List[TimeSlot]:
        """Return the top-k scoring candidate slots across the date range.
        Purely a read operation — does not commit anything to the calendar."""
        seen: set = set()
        collected: List[TimeSlot] = []
        max_days = min((end_date - start_date).days + 1, 60)
        for relax in (False, True):
            if len(collected) >= k:
                break
            for i in range(max_days):
                current_date = start_date + datetime.timedelta(days=i)
                start_of_day, end_of_day = self._get_day_boundaries(current_date)
                t = start_of_day
                while t + datetime.timedelta(minutes=duration) <= end_of_day:
                    slot_end = t + datetime.timedelta(minutes=duration)
                    slot_key = (t, slot_end)
                    if slot_key not in seen and not self._is_overlapping(t, slot_end):
                        if due_dt is None or slot_end <= due_dt:
                            gaps = self._calculate_gaps(t, slot_end)
                            hard_fail = self._fails_hard_constraints(t, slot_end, category, gaps)
                            if not hard_fail or relax:
                                score = self._score_soft_constraints(
                                    t, slot_end, category, gaps, relax, None
                                )
                                collected.append(TimeSlot(t, slot_end, score))
                                seen.add(slot_key)
                    t += datetime.timedelta(minutes=self.interval_minutes)
        collected.sort(key=lambda s: s.score, reverse=True)
        return collected[:k]

    def schedule_tasks(self, start_date: datetime.date, fallback_end_date: datetime.date,
                       pending_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scheduled_task_events: List[Dict[str, Any]] = []
        valid_tasks = [t for t in pending_tasks if t.get("estimated_duration")]

        # Earlier due date first; ties broken by priority (1 = most urgent)
        valid_tasks.sort(key=lambda t: (
            t.get("due_date") or "9999-12-31T23:59:59Z",
            t.get("priority", 3)
        ))

        print("\n" + "="*60)
        print(f"[TaskScheduler] INCOMING TASKS ({len(pending_tasks)} total, {len(valid_tasks)} with duration)")
        print(f"[TaskScheduler]    Scheduling window: {start_date} -> {fallback_end_date}")
        print("="*60)
        skipped_no_duration = [t for t in pending_tasks if not t.get("estimated_duration")]
        if skipped_no_duration:
            print(f"[TaskScheduler] WARNING: SKIPPED (no estimated_duration): {[t.get('title') for t in skipped_no_duration]}")
        for t in valid_tasks:
            print(f"[TaskScheduler]   * '{t.get('title')}' | duration={t.get('estimated_duration')}min | due={t.get('due_date','NO DUE DATE')} | priority={t.get('priority',3)} | energy={t.get('energy_level','medium')}")
        print(f"[TaskScheduler] Scheduling order: earlier due date first, then higher priority (lower number)")

        # Tasks are scheduled sequentially so each chunk sees the calendar updated by previous placements
        for task in valid_tasks:
            due_date_str = task.get("due_date")
            due_dt = self._parse_dt(due_date_str) if due_date_str else None
            task_end_date = due_dt.date() if due_dt else fallback_end_date

            if task_end_date < start_date:
                print(f"\n[TaskScheduler] SKIPPED '{task.get('title')}' -- due {task_end_date} is before start {start_date}")
                continue

            chunks = self._determine_chunks(task)
            category = self._map_task_to_category(task)
            total_days = max(1, (task_end_date - start_date).days)
            # Spread chunks across the window; min_spacing prevents two chunks landing on the same day
            min_spacing = max(1, total_days // len(chunks))
            total_chunk_min = sum(chunks)

            print(f"\n[TaskScheduler] -- Task '{task.get('title')}' | {task.get('estimated_duration')}min | {len(chunks)} chunks={chunks} (sum={total_chunk_min}min) | window {start_date}->{task_end_date} ({total_days}d) | min_spacing={min_spacing}d --")

            days_used_by_task: set = set()
            last_date: Optional[datetime.date] = None
            parts_placed = 0
            total_scheduled_min = 0

            for chunk_idx, chunk_dur in enumerate(chunks):
                placed = False

                # Pass 1: enforce even spacing. Pass 2: relax spacing, but never double-book a day
                for relax_spacing in (False, True):
                    if placed:
                        break
                    if relax_spacing:
                        print(f"[TaskScheduler]     Chunk[{chunk_idx}] ({chunk_dur}min): no slot with >={min_spacing}d spacing, relaxing spacing...")

                    for i in range(total_days + 1):
                        candidate_date = start_date + datetime.timedelta(days=i)
                        if candidate_date > task_end_date:
                            break
                        # Never schedule two chunks of the same task on the same day
                        if candidate_date in days_used_by_task:
                            continue
                        # Enforce minimum spacing between chunks of this task
                        if not relax_spacing and last_date is not None:
                            if (candidate_date - last_date).days < min_spacing:
                                continue

                        slot = self.find_best_slot(candidate_date, chunk_dur, category)
                        if slot:
                            days_used_by_task.add(candidate_date)
                            last_date = candidate_date
                            parts_placed += 1
                            total_scheduled_min += chunk_dur
                            is_multipart = len(chunks) > 1
                            title = (
                                f"{task.get('title')} (Part {parts_placed})"
                                if is_multipart else task.get('title')
                            )
                            local_start = slot.start.astimezone(self.user_tz)
                            local_end = slot.end.astimezone(self.user_tz)
                            print(f"[TaskScheduler]     OK Chunk[{chunk_idx}] '{title}' | {local_start.strftime('%Y-%m-%d %H:%M')} -> {local_end.strftime('%H:%M')} ({chunk_dur}min) | score={slot.score}")

                            # Ghost event holds the slot in the in-memory calendar so later chunks
                            # and tasks don't collide with it
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
                                "category": category,
                                "is_ghost": True,
                                "linked_task_id": task.get("id"),
                            }
                            self.existing_events.append(ghost_event)
                            scheduled_task_events.append(ghost_event)
                            placed = True
                            break

                if not placed:
                    print(f"[TaskScheduler]     FAILED Chunk[{chunk_idx}] ({chunk_dur}min): no free slot found in {total_days}-day window")

            needed = sum(chunks)
            status = "FULLY SCHEDULED" if total_scheduled_min >= needed else f"PARTIAL ({total_scheduled_min}/{needed}min)"
            print(f"[TaskScheduler]   -> '{task.get('title')}': {parts_placed}/{len(chunks)} chunks placed, {total_scheduled_min}/{needed}min | {status}")

        print(f"\n[TaskScheduler] Done. {len(scheduled_task_events)} ghost events created.")
        print("="*60 + "\n")
        return scheduled_task_events
    
class DebtRescheduler(BaseScheduler):
    def _is_overlapping(self, slot_start: datetime.datetime, slot_end: datetime.datetime) -> bool:
        """Blocks on every calendar entry (locked or not) — debt slots must fit in genuinely free gaps."""
        for event in self.existing_events:
            event_start = self._parse_dt(event.get("start"))
            event_end = self._parse_dt(event.get("end"))
            if not event_start or not event_end:
                continue
            travel_time = event.get("travel_time", 0)
            if travel_time > 0:
                event_start = event_start - datetime.timedelta(minutes=travel_time)
            if slot_start < event_end and slot_end > event_start:
                return True
        return False

    def schedule_debt(self, start_date: datetime.date, end_date: datetime.date, debt_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print(f"\n[DebtRescheduler] 🧠 Booting up. Attempting to fill gaps with {len(debt_items)} reclaimed items...")
        print(f"[DebtRescheduler]    Rescheduling window: {start_date} -> {end_date}")
        print(f"[DebtRescheduler]    Existing calendar events passed in: {len(self.existing_events)}")
        for ev in self.existing_events:
            ev_start = ev.get("start", "?")
            ev_end = ev.get("end", "?")
            ev_title = ev.get("title", "Untitled")
            ev_type = "ghost" if ev.get("is_ghost") else ("locked" if ev.get("is_locked") else "unlocked")
            print(f"[DebtRescheduler]      • [{ev_type}] '{ev_title}' | {ev_start} -> {ev_end}")

        tasks_in  = [d for d in debt_items if d.get("original_type") == "task"]
        events_in = [d for d in debt_items if d.get("original_type") == "event"]
        other_in  = [d for d in debt_items if d.get("original_type") not in ("task", "event")]
        print(f"[DebtRescheduler]    Debt breakdown: {len(tasks_in)} task(s), {len(events_in)} event(s), {len(other_in)} other")
        for item in debt_items:
            print(f"[DebtRescheduler]      → [{item.get('original_type','?')}] '{item.get('title','Untitled')}' | duration={item.get('duration','?')}min | priority={item.get('priority',3)}")
        print()
        ghost_events = []

        # Cap the search window at 14 days to avoid unbounded scans
        delta = end_date - start_date
        max_days = min(delta.days + 1, 14)

        # Higher-priority items get placed first
        debt_items.sort(key=lambda x: x.get("priority", 3))

        for item in debt_items:
            duration = item.get("duration", 60)
            category = "DEEP_WORK" if item.get("priority", 3) <= 2 else "SHALLOW_WORK"
            if item.get("original_type") == "event": 
                category = "MEETING"

            print(f"[DebtRescheduler] 🎯 Finding earliest gap for: '{item.get('title')}' ({duration} mins | {category})")
            
            best_slot_found = None
            best_negative_slot = None

            for i in range(max_days):
                current_date = start_date + datetime.timedelta(days=i)
                slot = self.find_best_slot(current_date, duration, category)

                if slot:
                    if slot.score >= 0:
                        # Good slot found — stop searching
                        best_slot_found = slot
                        break
                    else:
                        # Keep the least-bad negative slot as a fallback
                        if not best_negative_slot or slot.score > best_negative_slot.score:
                            best_negative_slot = slot

            if not best_slot_found and best_negative_slot:
                print(f"[DebtRescheduler]   ⚠️ Perfect gap not found. Using best available fallback.")
                best_slot_found = best_negative_slot

            if best_slot_found:
                local_start = best_slot_found.start.astimezone(self.user_tz)
                print(f"[DebtRescheduler]   ✅ Placed on {local_start.date()} at {local_start.strftime('%H:%M')} (Score: {best_slot_found.score})")
                
                start_str = best_slot_found.start.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                end_str = best_slot_found.end.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

                ghost_event = {
                    "id": f"ghost_debt_{uuid.uuid4().hex[:8]}",
                    "title": item.get('title'),
                    "start": start_str,
                    "end": end_str,
                    "is_locked": True,
                    "provider": "tasks" if item.get("original_type") == "task" else "custom",
                    "status": "synced",
                    "requires_review": False,
                    "has_drifted": False,
                    "category": category,
                    "is_ghost": True,
                    "linked_task_id": item.get("id") if item.get("original_type") == "task" else None,
                    "linked_event_id": item.get("id") if item.get("original_type") == "event" else None,
                    "debt_duration": duration  # stored so the frontend can display catch-up context
                }
                
                self.existing_events.append(ghost_event)
                ghost_events.append(ghost_event)
            else:
                print(f"[DebtRescheduler]   ❌ FAILED to find any non-overlapping {duration}m slot within {max_days} days.")

        print(f"[DebtRescheduler] 🏁 Finished. Successfully slotted {len(ghost_events)} catch-up blocks.")
        return ghost_events