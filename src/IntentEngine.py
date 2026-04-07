# ===============================================================
# database_handlers.py
# Execution layer — only CREATE_EVENT is fully implemented.
# All other intents are placeholders for incremental development.
# ===============================================================

import uuid
import datetime as dt
from datetime import timezone
import zoneinfo
import dateparser
import json
import re
from google.cloud import firestore
from google import genai
from google.genai import types
from custom_exceptions import AmbiguityError, SlotConflictError

from categorise import categorise_event

class IntentExecutionEngine:
    def __init__(self, db_client: firestore.Client, nlu_engine=None, gemini_api_key: str = None):
        self.db = db_client
        self.nlu_engine = nlu_engine
        self.gemini_api_key = gemini_api_key

        if self.gemini_api_key:
            self.genai_client = genai.Client(api_key=self.gemini_api_key)
        else:
            self.genai_client = None

    def _find_next_available_slot(self, user_id: str, start_iso: str, end_iso: str,
                                exclude_doc_id: str = None) -> tuple[str, str]:
        start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt   = dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        duration = end_dt - start_dt

        for _ in range(24):   
            s_iso = start_dt.isoformat().replace("+00:00", "Z")
            e_iso = (start_dt + duration).isoformat().replace("+00:00", "Z")
            if self._is_slot_available(user_id, s_iso, e_iso, exclude_doc_id):
                return s_iso, e_iso
            start_dt += dt.timedelta(minutes=30)

        return start_iso, end_iso   

    def _is_slot_available(self, user_id: str, start_iso: str, end_iso: str, exclude_doc_id: str = None) -> bool:
        events_ref = self.db.collection("users").document(user_id).collection("raw_events")
        candidates = events_ref.where("end", ">", start_iso).stream()
        for doc in candidates:
            if exclude_doc_id and doc.id == exclude_doc_id:
                continue
            data = doc.to_dict()
            if data.get("start", "") < end_iso:   
                return False
        return True

    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"


    def _get_user_tz_str(self, user_id: str) -> str:
        """Helper to fetch the user's dynamic timezone from Firestore."""
        try:
            doc = self.db.collection("users").document(user_id).get()
            if doc.exists:
                tz = doc.to_dict().get("timezone", "UTC")
                zoneinfo.ZoneInfo(tz) # Validate it
                return tz
        except Exception:
            pass
        return "UTC"

    def _format_time(self, iso_string: str, user_timezone: str = "UTC") -> str:
        """Formats ISO timestamps into readable strings in the local timezone."""
        if not iso_string:
            return "the requested time"
        try:
            clean_iso = iso_string.replace("Z", "+00:00")
            parsed_dt = dt.datetime.fromisoformat(clean_iso)
            local_dt = parsed_dt.astimezone(zoneinfo.ZoneInfo(user_timezone))
            return local_dt.strftime("%A at %-I:%M %p")  
        except Exception:
            return "the requested time"



    def _resolve_with_aliases(self, title_query: str, aliases: dict) -> list[str]:
        """
        Returns a list of candidate strings to try for title resolution.
        Always includes the original query. If an alias maps to a different
        string, that expansion is also included so the resolver tries both.
        """
        candidates = [title_query]
        q_lower = title_query.lower()

        # Direct alias lookup — "fyp" → "final year project"
        if q_lower in aliases:
            candidates.append(aliases[q_lower])

        # Reverse lookup — if the stored title contains an alias value,
        # the user might have typed the short form anywhere in the query
        for alias, full_form in aliases.items():
            if alias in q_lower and full_form not in candidates:
                expanded = re.sub(
                    rf'\b{re.escape(alias)}\b',
                    full_form,
                    title_query,
                    flags=re.IGNORECASE
                )
                if expanded != title_query:
                    candidates.append(expanded)

        return candidates
    
    # ------------------------------------------------------------------ #
    #  RESOLUTION HELPER                                                   #
    #  Replaces _check_ambiguity — works with full event/task dicts so    #
    #  the AmbiguityError carries enough metadata for the frontend to     #
    #  display date, time, and location alongside the title.              #
    # ------------------------------------------------------------------ #
    def _resolve_or_raise(self, matches: list, query: str, entity_key: str):
        """
        Takes a list of matched item dictionaries.
        - 0 matches → returns None
        - 1 match   → returns the full item dict
        - 2+ matches → raises AmbiguityError with enriched candidate dicts
        """
        if not matches:
            return None

        # Deduplicate based on document ID to ensure we don't present the exact same document twice
        unique_matches = {m.get("_doc_id"): m for m in matches if m.get("_doc_id")}
        deduped = list(unique_matches.values())
        
        if not deduped:
            return None

        if len(deduped) == 1:
            return deduped[0]

        # Multiple matches — enrich each candidate with display metadata
        # so the frontend can show date/time/location, not just the title.
        enriched = []
        for item in deduped:
            enriched.append({
                "id":          item.get("_doc_id", ""),
                "title":       item.get("title", ""),
                "start":       item.get("start", ""),
                "end":         item.get("end", ""),
                "location":    item.get("location", ""),
                "description": item.get("description", ""),
                "due_date":    item.get("due_date", ""),   # tasks
                "status":      item.get("status", ""),
            })

        raise AmbiguityError(
            message    = f"I found multiple items matching '{query}'. Which one did you mean?",
            candidates = enriched,
            query      = query,
            entity_key = entity_key,
        )


    def _fetch_event_by_id(self, user_id: str, doc_id: str) -> dict | None:
        """
        Fetches a single event directly by Firestore document ID.
        Used after ambiguity resolution so we never trigger title search again.
        """
        try:
            doc = (
                self.db.collection("users")
                    .document(user_id)
                    .collection("raw_events")
                    .document(doc_id)
                    .get()
            )
            if doc.exists:
                data             = doc.to_dict()
                data["_doc_id"]  = doc.id
                return data
        except Exception as e:
            print(f"[FetchById] Failed for {doc_id}: {e}")
        return None


    def _fetch_task_by_id(self, user_id: str, doc_id: str) -> dict | None:
        """Same as above but for tasks."""
        try:
            doc = (
                self.db.collection("users")
                    .document(user_id)
                    .collection("raw_tasks")
                    .document(doc_id)
                    .get()
            )
            if doc.exists:
                data             = doc.to_dict()
                data["_doc_id"]  = doc.id
                return data
        except Exception as e:
            print(f"[FetchById] Failed for {doc_id}: {e}")
        return None



    # ------------------------------------------------------------------ #
    #  AMBIGUITY CHECKER & RESOLUTION                                    #
    # ------------------------------------------------------------------ #
    def _check_ambiguity(self, matches: list, title_query: str, entity_key: str = "events"):
        if len(matches) > 1:
            raise AmbiguityError(
                message    = f"I found multiple items matching '{title_query}'. Which one did you mean?",
                candidates = matches,
                query      = title_query,
                entity_key = entity_key,
            )
        return matches[0] if matches else None

    def _get_wordnet_synonyms(self, word: str) -> set:
        try:
            from nltk.corpus import wordnet
            synonyms = set()
            for syn in wordnet.synsets(word):
                for lemma in syn.lemmas():
                    synonyms.add(lemma.name().replace("_", " ").lower())
            synonyms.discard(word.lower())
            return synonyms
        except Exception:
            return set()

    def _fuzzy_match_title(self, title_query: str, candidates: list, threshold: int = 80):
        try:
            from rapidfuzz import process, fuzz
            results = process.extract(
                title_query, candidates,
                scorer=fuzz.partial_ratio,
                score_cutoff=threshold
            )
            if not results:
                return []
            max_score = results[0][1]
            return [res[0] for res in results if res[1] == max_score]
        except ImportError:
            return []

    def _wordnet_match_title(self, title_query: str, candidates: list):
        query_words = title_query.lower().split()
        all_synonyms = set(query_words)
        for word in query_words:
            all_synonyms.update(self._get_wordnet_synonyms(word))
        return [cand for cand in candidates if any(syn in cand.lower() for syn in all_synonyms)]

    def _embedding_match_title(self, title_query: str, candidates: list, threshold: float = 0.75):
        if not self.nlu_engine:
            return []
        try:
            import torch
            import torch.nn.functional as F
            tokenizer = self.nlu_engine.tokenizer
            model     = self.nlu_engine.intent_model
            device    = next(model.parameters()).device

            def get_cls(text):
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=64).to(device)
                with torch.no_grad():
                    outputs = model(**inputs, output_hidden_states=True)
                return outputs.hidden_states[-1][:, 0, :]

            query_emb = get_cls(title_query)
            scored_candidates = []
            for candidate in candidates:
                score = F.cosine_similarity(query_emb, get_cls(candidate)).item()
                if score >= threshold:
                    scored_candidates.append((candidate, score))
            if not scored_candidates:
                return []
            max_score = max(score for _, score in scored_candidates)
            return [cand for cand, score in scored_candidates if score >= max_score - 0.01]
        except Exception as e:
            print(f"[EmbeddingMatcher] Failed: {e}")
            return []

    def _resolve_title_with_gemini(self, title_query: str, candidates: list):
        if not self.genai_client or not candidates:
            return []
        prompt = f"""
        A user referred to a calendar event as: "{title_query}"
        Their upcoming event titles: {json.dumps(candidates)}
        Which titles are they most likely referring to?
        Rules:
        - Return ONLY valid JSON: {{"matched_titles": ["..."]}}
        - If multiple events are equally likely, return them all in the array.
        - If nothing is a confident match, return an empty array: {{"matched_titles": []}}
        - Never guess. A wrong match is worse than no match.
        """
        try:
            response = self.genai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text).get("matched_titles", [])
        except Exception as e:
            print(f"[TitleResolver] Gemini fallback failed: {e}")
            return []




    def _find_event_by_title(self, user_id: str, title_query: str, aliases: dict = None):
        if not title_query:
            return None
        
        direct_match = self._fetch_event_by_id(user_id, title_query)
        if direct_match:
            print(f"[TitleResolver] Direct ID match (Ambiguity Bypass): {title_query}")
            return direct_match

        aliases          = aliases or {}
        query_candidates = self._resolve_with_aliases(title_query, aliases)

        events_ref = self.db.collection("users").document(user_id).collection("raw_events")
        now_iso    = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        all_events = []
        for doc in events_ref.where("end", ">=", now_iso).stream():
            event_data             = doc.to_dict()
            event_data["_doc_id"]  = doc.id
            all_events.append(event_data)

        all_titles = [e.get("title", "") for e in all_events if e.get("title")]

        for query in query_candidates:
            if query != title_query:
                print(f"[TitleResolver] Trying alias expansion: '{query}'")

            # Stage 1 — Substring
            # THE FIX: Directly extract the event dictionary instead of just the string
            stage1 = [e for e in all_events if query.lower() in e.get("title", "").lower()]
            resolved = self._resolve_or_raise(stage1, query, "events")
            if resolved:
                return resolved

            # Stage 2 — Fuzzy
            fuzzy_titles = self._fuzzy_match_title(query, all_titles)
            fuzzy_events = [e for e in all_events if e.get("title", "") in fuzzy_titles]
            resolved = self._resolve_or_raise(fuzzy_events, query, "events")
            if resolved:
                print(f"[TitleResolver] Fuzzy: '{query}' → '{resolved.get('title')}'")
                return resolved

            # Stage 3 — WordNet
            wordnet_titles = self._wordnet_match_title(query, all_titles)
            wordnet_events = [e for e in all_events if e.get("title", "") in wordnet_titles]
            resolved = self._resolve_or_raise(wordnet_events, query, "events")
            if resolved:
                print(f"[TitleResolver] WordNet: '{query}' → '{resolved.get('title')}'")
                return resolved

            # Stage 4 — Embedding
            embedding_titles = self._embedding_match_title(query, all_titles)
            embedding_events = [e for e in all_events if e.get("title", "") in embedding_titles]
            resolved = self._resolve_or_raise(embedding_events, query, "events")
            if resolved:
                print(f"[TitleResolver] Embedding: '{query}' → '{resolved.get('title')}'")
                return resolved

        # Stage 5 — Gemini (once, with original query)
        print(f"[TitleResolver] All local stages missed '{title_query}'. Trying Gemini.")
        gemini_titles = self._resolve_title_with_gemini(title_query, all_titles)
        gemini_events = [e for e in all_events if e.get("title", "") in gemini_titles]
        resolved = self._resolve_or_raise(gemini_events, title_query, "events")
        if resolved:
            print(f"[TitleResolver] Gemini: '{title_query}' → '{resolved.get('title')}'")
            return resolved

        return None


    def _find_task_by_title(self, user_id: str, title_query: str, aliases: dict = None):
        if not title_query:
            return None
        direct_match = self._fetch_task_by_id(user_id, title_query)
        if direct_match:
            print(f"[TaskResolver] Direct ID match (Ambiguity Bypass): {title_query}")
            return direct_match
        aliases          = aliases or {}
        query_candidates = self._resolve_with_aliases(title_query, aliases)
        tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
        all_tasks = []
        for status in ["pending", "scheduled", "in_progress"]:
            for doc in tasks_ref.where("status", "==", status).stream():
                task_data             = doc.to_dict()
                task_data["_doc_id"]  = doc.id
                all_tasks.append(task_data)

        all_titles = [t.get("title", "") for t in all_tasks if t.get("title")]

        for query in query_candidates:
            if query != title_query:
                print(f"[TaskResolver] Trying alias expansion: '{query}'")

            stage1 = [t for t in all_tasks if query.lower() in t.get("title", "").lower()]
            resolved = self._resolve_or_raise(stage1, query, "tasks")
            if resolved:
                return resolved

            fuzzy_titles = self._fuzzy_match_title(query, all_titles)
            fuzzy_tasks = [t for t in all_tasks if t.get("title", "") in fuzzy_titles]
            resolved = self._resolve_or_raise(fuzzy_tasks, query, "tasks")
            if resolved:
                print(f"[TaskResolver] Fuzzy: '{query}' → '{resolved.get('title')}'")
                return resolved

            wordnet_titles = self._wordnet_match_title(query, all_titles)
            wordnet_tasks = [t for t in all_tasks if t.get("title", "") in wordnet_titles]
            resolved = self._resolve_or_raise(wordnet_tasks, query, "tasks")
            if resolved:
                print(f"[TaskResolver] WordNet: '{query}' → '{resolved.get('title')}'")
                return resolved

            embedding_titles = self._embedding_match_title(query, all_titles)
            embedding_tasks = [t for t in all_tasks if t.get("title", "") in embedding_titles]
            resolved = self._resolve_or_raise(embedding_tasks, query, "tasks")
            if resolved:
                print(f"[TaskResolver] Embedding: '{query}' → '{resolved.get('title')}'")
                return resolved

        print(f"[TaskResolver] All local stages missed '{title_query}'. Trying Gemini.")
        gemini_titles = self._resolve_title_with_gemini(title_query, all_titles)
        gemini_tasks = [t for t in all_tasks if t.get("title", "") in gemini_titles]
        resolved = self._resolve_or_raise(gemini_tasks, title_query, "tasks")
        if resolved:
            print(f"[TaskResolver] Gemini: '{title_query}' → '{resolved.get('title')}'")
            return resolved

        return None
    
    def _parse_duration_minutes(self, duration_str: str) -> int:
        duration_str = duration_str.lower()
        if "hour" in duration_str or "hr" in duration_str:
            nums = re.findall(r'\d+', duration_str)
            if nums: return int(nums[0]) * 60
            elif "half" in duration_str: return 30
        elif "min" in duration_str:
            nums = re.findall(r'\d+', duration_str)
            if nums: return int(nums[0])
        return 60

    # ------------------------------------------------------------------ #
    #  INTENT EXECUTORS                                                  #
    # ------------------------------------------------------------------ #

    def handle_create_event(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [CreateEvent] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        print(f"  user_id: {user_id}")
        user_tz_str = self._get_user_tz_str(user_id)

        try:
            events_list = entities.get("events", [])
            title = events_list[0] if events_list else "Untitled Event"
            print(f"  title: {title}")

            start_iso = entities.get("start_timestamp")
            end_iso = entities.get("end_timestamp")
            print(f"  start_iso: {start_iso}")
            print(f"  end_iso: {end_iso}")

            if not start_iso:
                raise ValueError(f"I couldn't determine when to schedule '{title}'. Could you specify a date or time?")

            if not end_iso:
                start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                end_dt = start_dt + dt.timedelta(hours=1)
                end_iso = end_dt.isoformat().replace("+00:00", "Z")
                print(f"  defaulted end_iso to: {end_iso}")

            print("  Checking slot availability...")
            if not self._is_slot_available(user_id, start_iso, end_iso):
                suggested_start, suggested_end = self._find_next_available_slot(user_id, start_iso, end_iso)
                raise SlotConflictError(
                    message         = f"The time slot from {self._format_time(start_iso, user_tz_str)} to {self._format_time(end_iso, user_tz_str)} is already booked.",
                    requested_start = start_iso,
                    requested_end   = end_iso,
                    suggested_start = suggested_start,
                    suggested_end   = suggested_end,
                    title           = title,
                )
            print("  Slot available.")

            doc_id = self._generate_id("custom")
            print(f"  doc_id: {doc_id}")

            events_ref = self.db.collection("users").document(user_id).collection("raw_events")
            print(f"  Firestore collection path: users/{user_id}/raw_events")

            category = categorise_event(title)
            print(f"  category: {category}")

            locations_list = entities.get("locations", [])
            location = locations_list[0] if locations_list else ""
            print(f"  location: {location}")

            # --- TELEMETRY INITIALIZATION ---
            perishable_categories = ["Health & Fitness", "Routine", "Meals", "Personal Care"]
            is_perishable = category in perishable_categories

            event_data = {
                "id": doc_id,
                "user_id": user_id,
                "title": title,
                "start": start_iso,
                "end": end_iso,
                "location": location,
                "meeting_link": "",
                "is_locked": False, 
                "description": "",
                "recurrence": "none",
                "recurrence_days": [],
                "travel_time": 0,
                "travel_origin": "",
                "travel_mode": "driving",
                "provider": "custom",
                "calendar_id": "default", 
                "email": user_id,
                "attachments": [],
                "category": category,
                "sync_status": "synced",
                "requires_review": False,
                "has_drifted": False,
                "original_start": start_iso,
                "original_end": end_iso,
                "sync_action_required": "push_to_provider",
                "created_at": dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "completion_status": "pending",
                "snooze_count": 0,
                "completed_at": None,
                "debt_applied": False,
                "is_perishable": is_perishable
            }

            print("  Writing to Firestore...")
            try:
                events_ref.document(doc_id).set(event_data)
                written = events_ref.document(doc_id).get().to_dict()
                print(f"  ✅ Document written: {written}")
            except Exception as e:
                print(f"  ❌ Firestore write error: {e}")
                raise

            friendly_time = self._format_time(start_iso, user_tz_str)
            print(f"  friendly_time: {friendly_time}")

            print("\n>>> [CreateEvent] SUCCESS, returning result <<<\n")
            return {
                "status": "success",
                "message": f"I have scheduled '{title}' for {friendly_time}.",
                "data": {"eventId": doc_id}
            }

        except Exception as e:
            print(f"❌ [CreateEvent] Unhandled exception: {e}")
            raise


    def handle_update_event(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [UpdateEvent] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)

        try:
            from google.cloud import firestore 
            
            # ── 1. Extract target date/time ────────────────────────────────────
            event_titles     = [t for t in entities.get("events", []) if t]
            dates_list       = entities.get("dates", [])
            times_list       = entities.get("times", [])
            durations_list   = entities.get("durations", [])

            new_date_str     = dates_list[-1] if dates_list else None
            new_time_str     = times_list[-1] if times_list else None
            new_duration_str = durations_list[0] if durations_list else None

            if not event_titles:
                raise ValueError("No event titles were found to update.")

            if not new_date_str and not new_time_str:
                raise ValueError(
                    "I couldn't determine a target date or time. "
                    "Could you specify where you want to move the events?"
                )

            events_ref = self.db.collection("users").document(user_id).collection("raw_events")

            # ── 2. Timezone-aware dateparser helper ────────────────────────────
            def parse_dt(expression: str) -> dt.datetime | None:
                now_local = dt.datetime.now(user_tz)
                return dateparser.parse(
                    expression,
                    settings={
                        "TIMEZONE":                user_tz_str,
                        "TO_TIMEZONE":             "UTC",
                        "RETURN_AS_TIMEZONE_AWARE": True,
                        "DATE_ORDER":              "DMY",
                        "RELATIVE_BASE":           now_local,
                        "PREFER_DATES_FROM":       "future",
                    }
                )
            # ── 3. Build source-day snapshot ───────────────────────────────────
            source_ts = entities.get("source_timestamp")
            if not source_ts:
                source_date_str = entities.get("source_date")
                if source_date_str:
                    resolved = parse_dt(source_date_str)
                    if resolved:
                        source_ts = resolved.isoformat().replace("+00:00", "Z")
            day_snapshot = []
            if source_ts:
                window_start_dt = dt.datetime.fromisoformat(source_ts.replace("Z", "+00:00"))
                window_end_dt   = window_start_dt + dt.timedelta(hours=24)
                window_start    = window_start_dt.isoformat().replace("+00:00", "Z")
                window_end      = window_end_dt.isoformat().replace("+00:00", "Z")
                print(f"  Day window (UTC): {window_start} → {window_end}")
                docs = events_ref.where("start", ">=", window_start).stream()
                for d in docs:
                    data        = d.to_dict()
                    event_start = data.get("start", "")
                    # THE FIX: Only include the event if it's within the window AND its status is 'pending'
                    # We check for 'pending' explicitly to ignore 'completed' and 'missed'
                    status = data.get("completion_status", "pending")
                    
                    if event_start < window_end and status == "pending":
                        day_snapshot.append(data | {"_doc_id": d.id})
                print(f"  Day snapshot (Filtered): {len(day_snapshot)} pending event(s) found.")
            # ── 4. Resolve each title to a Firestore document ─────────────────
            processed_ids  = set()
            resolved_pairs = []

            for title in event_titles:
                print(f"\n  Resolving title: '{title}'")
                matched = None

                direct_match = self._fetch_event_by_id(user_id, title)
                if direct_match:
                    matched = direct_match
                    if matched["_doc_id"] not in processed_ids:
                        processed_ids.add(matched["_doc_id"])
                        print(f"  ✓ Direct ID match: '{matched.get('title')}'")
                        resolved_pairs.append((matched, matched.get("title")))
                    continue #

                if day_snapshot:
                    candidates = [
                        e for e in day_snapshot
                        if e.get("title", "").lower() == title.lower()
                        and e["_doc_id"] not in processed_ids
                    ]
                    if candidates:
                        matched = candidates[0]
                        processed_ids.add(matched["_doc_id"])
                        print(f"  ✓ Snapshot match: '{matched.get('title')}' (ID: {matched['_doc_id']})")
                    else:
                        print(f"  ✗ No unused snapshot match for '{title}'")

                if not matched and not day_snapshot:
                    matched = self._find_event_by_title(user_id, title)
                    if matched:
                        if matched["_doc_id"] not in processed_ids:
                            processed_ids.add(matched["_doc_id"])
                            print(f"  ✓ Resolver match: '{matched.get('title')}' (ID: {matched['_doc_id']})")
                        else:
                            matched = None

                if matched:
                    resolved_pairs.append((matched, title))
                else:
                    print(f"  ✗ Could not resolve '{title}' — skipping.")

            if not resolved_pairs:
                raise ValueError(
                    f"I couldn't find any of the specified events to update. "
                    f"Titles searched: {', '.join(event_titles)}"
                )

            # ── 5. TWO-PASS: compute all slots BEFORE writing ──────────────────
            all_batch_ids = {pair[0]["_doc_id"] for pair in resolved_pairs}
            in_memory_allocations = []
            MAX_SANE_DURATION = dt.timedelta(hours=23)

            def is_slot_free(start_iso: str, end_iso: str, exclude_ids: set = None) -> bool:
                candidates = events_ref.where("end", ">", start_iso).stream()
                for doc in candidates:
                    if exclude_ids and doc.id in exclude_ids:
                        continue
                    data        = doc.to_dict()
                    event_start = data.get("start", "")
                    event_end   = data.get("end",   "")
                    if event_start < end_iso:
                        print(f"    [SlotCheck] BLOCKED by Firestore: '{data.get('title')}' ({event_start} → {event_end})")
                        return False

                for alloc_start, alloc_end in in_memory_allocations:
                    if alloc_start < end_iso and alloc_end > start_iso:
                        print(f"    [SlotCheck] BLOCKED by in-memory: {alloc_start} → {alloc_end}")
                        return False

                return True

            def find_free_slot(start_iso: str, end_iso: str, exclude_ids: set = None) -> tuple[str, str]:
                start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                end_dt   = dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                duration = end_dt - start_dt

                for _ in range(24):
                    s = start_dt.isoformat().replace("+00:00", "Z")
                    e = (start_dt + duration).isoformat().replace("+00:00", "Z")
                    if is_slot_free(s, e, exclude_ids):
                        return s, e
                    start_dt += dt.timedelta(minutes=30)

                print(f"    [SlotCheck] Search exhausted — using preferred slot as fallback")
                return start_iso, end_iso

            # ── PASS 1: plan all moves & Calculate Telemetry Hooks ─────────────
            planned_updates = []

            for target_event, original_title in resolved_pairs:
                doc_id     = target_event["_doc_id"]
                orig_start = target_event.get("start", "")
                orig_end   = target_event.get("end",   "")

                print(f"\n  Planning move for '{target_event.get('title')}'")

                def safe_parse_iso(iso_str: str) -> dt.datetime | None:
                    if not iso_str: return None
                    try:
                        cleaned = iso_str.replace(".000Z", "Z").replace("Z", "+00:00")
                        return dt.datetime.fromisoformat(cleaned)
                    except Exception as e:
                        print(f"    [ParseISO] Failed on '{iso_str}': {e}")
                        return None

                orig_start_dt = safe_parse_iso(orig_start)
                orig_end_dt   = safe_parse_iso(orig_end)
                new_start_dt  = None

                if new_date_str and new_time_str:
                    new_start_dt = parse_dt(f"{new_date_str} at {new_time_str}")
                elif new_date_str and orig_start_dt:
                    orig_local   = orig_start_dt.astimezone(user_tz)
                    new_start_dt = parse_dt(f"{new_date_str} at {orig_local.strftime('%H:%M')}")
                elif new_time_str and orig_start_dt:
                    orig_local   = orig_start_dt.astimezone(user_tz)
                    new_start_dt = parse_dt(f"{orig_local.strftime('%d/%m/%Y')} at {new_time_str}")
                else:
                    raw_ts = entities.get("start_timestamp")
                    if raw_ts: new_start_dt = safe_parse_iso(raw_ts)

                if not new_start_dt:
                    planned_updates.append((
                        doc_id, None, None, target_event.get("title"),
                        f"Couldn't determine new time for '{target_event.get('title')}'", 
                        None, None, None, 0 
                    ))
                    continue

                if new_duration_str:
                    duration_mins = self._parse_duration_minutes(new_duration_str)
                    new_end_dt    = new_start_dt + dt.timedelta(minutes=duration_mins)
                elif orig_start_dt and orig_end_dt:
                    orig_start_local = orig_start_dt.astimezone(user_tz)
                    orig_end_local   = orig_end_dt.astimezone(user_tz)
                    local_duration   = orig_end_local - orig_start_local

                    if local_duration <= dt.timedelta(0) or local_duration > MAX_SANE_DURATION:
                        local_duration = dt.timedelta(hours=1)
                    new_end_dt = new_start_dt + local_duration
                else:
                    new_end_dt = new_start_dt + dt.timedelta(hours=1)

                preferred_start = new_start_dt.isoformat().replace("+00:00", "Z")
                preferred_end   = new_end_dt.isoformat().replace("+00:00", "Z")

                if is_slot_free(preferred_start, preferred_end, exclude_ids=all_batch_ids):
                    final_start = preferred_start
                    final_end   = preferred_end
                    msg = f"'{target_event.get('title')}' moved to {self._format_time(final_start, user_tz_str)}."
                else:
                    final_start, final_end = find_free_slot(preferred_start, preferred_end, exclude_ids=all_batch_ids)
                    msg = f"'{target_event.get('title')}' moved to {self._format_time(final_start, user_tz_str)} (original slot busy)."

                in_memory_allocations.append((final_start, final_end))

                # --- TELEMETRY HOOKS INJECTION ---
                snooze_increment = 0
                if orig_start_dt and new_start_dt and new_start_dt > orig_start_dt:
                    snooze_increment = 1
                
                comp_status = target_event.get("completion_status", "pending")
                snooze_count = target_event.get("snooze_count", 0) + snooze_increment
                debt_applied = target_event.get("debt_applied", False)
                is_perish = target_event.get("is_perishable", False)
                debt_refund = 0

                # Check for Debt Relief
                if comp_status == "missed" and snooze_increment > 0:
                    comp_status = "pending" # Resurrect the event
                    
                    if debt_applied and not is_perish and orig_start_dt and orig_end_dt:
                        dur_mins = int((orig_end_dt - orig_start_dt).total_seconds() / 60)
                        if dur_mins > 0:
                            debt_refund = dur_mins # Queue the refund
                            
                    debt_applied = False # Reset the lock

                planned_updates.append((
                    doc_id, final_start, final_end, target_event.get("title"), msg,
                    snooze_count, comp_status, debt_applied, debt_refund
                ))

            # ── PASS 2: write all updates and execute Refunds ──────────────────
            results  = []
            messages = []

            for doc_id, final_start, final_end, title, msg, snz, cmp_st, dbt_app, dbt_ref in planned_updates:
                messages.append(msg)

                if final_start is None:
                    continue

                events_ref.document(doc_id).update({
                    "start":                final_start,
                    "end":                  final_end,
                    "proposed_start":       final_start,
                    "proposed_end":         final_end,
                    "has_drifted":          False,
                    "sync_action_required": "push_to_provider",
                    # Apply Telemetry Updates
                    "snooze_count":         snz,
                    "completion_status":    cmp_st,
                    "debt_applied":         dbt_app,
                })

                # Execute Atomic Debt Refund if applicable
                if dbt_ref > 0:
                    try:
                        self.db.collection("users").document(user_id).update({
                            "total_time_debt": firestore.Increment(-dbt_ref)
                        })
                        print(f"  💰 Refunded {dbt_ref} minutes of Time Debt for '{title}'")
                    except Exception as e:
                        print(f"  ⚠ Failed to refund time debt: {e}")

                results.append({
                    "eventId":  doc_id,
                    "title":    title,
                    "newStart": final_start,
                    "newEnd":   final_end,
                })
                print(f"  ✅ Written '{title}': {final_start} → {final_end}")

            # ── 6. Build response ──────────────────────────────────────────────
            if not results:
                raise ValueError("No events were updated. " + " ".join(messages))

            summary = (
                f"I have moved {len(results)} event(s) to "
                f"{new_date_str or new_time_str or 'the new time'}."
                if len(results) > 1
                else messages[0] if messages else "Update successful."
            )

            print(f"\n>>> [UpdateEvent] COMPLETE — {len(results)} event(s) updated <<<\n")
            return {
                "status":  "success",
                "message": summary,
                "data":    {"updated": results},
            }

        except Exception as e:
            print(f"❌ [UpdateEvent] Unhandled exception: {e}")
            raise
    

    def handle_delete_event(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [DeleteEvent] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")

        try:
            event_titles = [t for t in entities.get("events", []) if t]
            if not event_titles:
                raise ValueError("No event title found to delete.")

            results = []
            messages = []
            events_ref = self.db.collection("users").document(user_id).collection("raw_events")

            target_ts = entities.get("start_timestamp")
            
            day_snapshot = []
            if target_ts:
                target_iso_prefix = target_ts.split('T')[0]
                print(f"  Targeting day for deletion: {target_iso_prefix}")
                docs = events_ref.where("start", ">=", target_iso_prefix).stream()
                for d in docs:
                    data = d.to_dict()
                    if data.get("start", "").startswith(target_iso_prefix):
                        day_snapshot.append(data | {"_doc_id": d.id})

            processed_ids = set()

            for title in event_titles:
                print(f"\n--- Processing deletion for: '{title}' ---")
                
                target_events = []

                direct_match = self._fetch_event_by_id(user_id, title)
                if direct_match:
                    target_events = [direct_match]
                    processed_ids.add(direct_match["_doc_id"])
                    print(f"  ✓ Direct ID match: '{direct_match.get('title')}'")
                
                if day_snapshot:
                    matches = [e for e in day_snapshot if e.get("title", "").lower() == title.lower() and e["_doc_id"] not in processed_ids]
                    if matches:
                        target_events = [matches[0]]
                        processed_ids.add(matches[0]["_doc_id"])
                        print(f"  ✓ Snapshot match: '{matches[0].get('title')}'")
                
                if not target_events:
                    print("  No snapshot match found, checking calendar...")
                    single_match = self._find_event_by_title(user_id, title)
                    if single_match:
                        target_events = [single_match]

                if not target_events:
                    messages.append(f"Could not find an event matching '{title}'.")
                    continue

                for target_event in target_events:
                    doc_id = target_event["_doc_id"]
                    events_ref.document(doc_id).delete()
                    results.append({"eventId": doc_id, "title": title})
                    print(f"  ✅ Deleted: {title} (ID: {doc_id})")

            if len(results) > 1:
                final_msg = f"I have deleted {len(results)} items."
            elif len(results) == 1:
                final_msg = f"I have deleted '{results[0]['title']}'."
            else:
                final_msg = " ".join(list(dict.fromkeys(messages))) if messages else "No items deleted."

            return {
                "status": "success",
                "message": final_msg,
                "data": {"deleted": results}
            }

        except Exception as e:
            print(f" [DeleteEvent] Error during execution: {e}")
            raise


    def handle_query_event(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [QueryEvent] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)

        try:
            event_titles = [t for t in entities.get("events", []) if t]
            dates_list   = entities.get("dates", [])
            events_ref   = self.db.collection("users").document(user_id).collection("raw_events")
            now_utc      = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            found_events = []
            query_context_msg = ""

            # ── Ambiguity bypass — user already picked a specific doc ──────
            selected_doc_id = entities.get("selected_doc_id")
            if selected_doc_id:
                print(f"  selected_doc_id={selected_doc_id} — fetching directly")
                event = self._fetch_event_by_id(user_id, selected_doc_id)
                if event:
                    found_events = [event]
                # Fall through to response formatting below

            elif dates_list:
                target_date_str = dates_list[-1]
                now_local       = dt.datetime.now(user_tz)
                parsed_date     = dateparser.parse(
                    target_date_str,
                    settings={
                        "TIMEZONE": user_tz_str, "RETURN_AS_TIMEZONE_AWARE": True,
                        "RELATIVE_BASE": now_local, "PREFER_DATES_FROM": "future"
                    }
                )
                if parsed_date:
                    local_midnight = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    window_start   = local_midnight.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    window_end     = (local_midnight + dt.timedelta(hours=24)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    query_context_msg = f"on {local_midnight.strftime('%A, %b %d')}"
                    print(f"  Targeting Day Window: {window_start} → {window_end}")

                    docs       = events_ref.where("start", ">=", window_start).stream()
                    day_events = []
                    for d in docs:
                        data = d.to_dict()
                        if data.get("start", "") < window_end:
                            day_events.append(data | {"_doc_id": d.id})

                    if event_titles:
                        for title in event_titles:
                            matches = [e for e in day_events if e.get("title", "").lower() == title.lower()]
                            found_events.extend(matches)
                    else:
                        found_events.extend(day_events)

            elif event_titles:
                print("  No date provided, looking for next occurrence of specific titles...")
                for title in event_titles:
                    match = self._find_event_by_title(user_id, title)
                    if match:
                        found_events.append(match)

            else:
                print("  General query detected. Fetching next 5 upcoming events...")
                query_context_msg = "coming up next"
                docs = events_ref.where("end", ">", now_utc).limit(5).stream()
                for d in docs:
                    found_events.append(d.to_dict() | {"_doc_id": d.id})

            if not found_events:
                msg = (
                    f"You don't have any events scheduled {query_context_msg}."
                    if query_context_msg
                    else "I couldn't find any matching events on your calendar."
                )
                return {"status": "success", "message": msg, "data": {"events": []}}

            unique_events = {e["_doc_id"]: e for e in found_events}.values()
            sorted_events = sorted(unique_events, key=lambda x: x.get("start", ""))

            if len(sorted_events) == 1:
                e             = list(sorted_events)[0]
                friendly_time = self._format_time(e.get("start"), user_tz_str)
                msg           = f"'{e.get('title')}' is scheduled for {friendly_time}."
            else:
                msg_parts = [f"You have {len(sorted_events)} events {query_context_msg}:"]
                for e in sorted_events:
                    start_local = dt.datetime.fromisoformat(
                        e.get("start").replace("Z", "+00:00")
                    ).astimezone(user_tz)
                    time_str = (
                        start_local.strftime("%-I:%M %p")
                        if dates_list
                        else start_local.strftime("%A at %-I:%M %p")
                    )
                    msg_parts.append(f"- {e.get('title')} at {time_str}")
                msg = "\n".join(msg_parts)

            print(f"  ✅ Successfully retrieved {len(sorted_events)} events.")
            return {
                "status":  "success",
                "message": msg,
                "data":    {"events": list(sorted_events)}
            }

        except Exception as e:
            print(f"❌ [QueryEvent] Error: {e}")
            raise



    def handle_find_free_time(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [FindFreeTime] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)

        try:
            dates_list = entities.get("dates", [])
            # Use the adapter logic to catch source_date if the LLM misclassified it
            source_date = entities.get("source_date")
            if source_date and not dates_list:
                dates_list.append(source_date)

            durations_list = entities.get("durations", [])
            
            # 1. Determine requested duration (default 60 mins)
            req_duration_mins = 60
            if durations_list:
                req_duration_mins = self._parse_duration_minutes(durations_list[0])
            
            now_local = dt.datetime.now(user_tz)
            
            # 2. Define the Search Window boundaries
            if dates_list:
                # Target a specific day: 09:00 to 18:00 (Working Hours)
                target_date_str = dates_list[-1]
                parsed_day = dateparser.parse(target_date_str, settings={
                    "TIMEZONE": user_tz_str, "RETURN_AS_TIMEZONE_AWARE": True,
                    "RELATIVE_BASE": now_local, "PREFER_DATES_FROM": "future"
                })
                if not parsed_day:
                    raise ValueError(f"I couldn't understand the date '{target_date_str}'.")
                
                search_start = parsed_day.replace(hour=9, minute=0, second=0, microsecond=0)
                search_end = parsed_day.replace(hour=18, minute=0, second=0, microsecond=0)
                # If searching for today, don't look in the past
                if search_start < now_local:
                    search_start = now_local
            else:
                # General search: From now until tomorrow evening
                search_start = now_local
                search_end = (now_local + dt.timedelta(days=1)).replace(hour=18, minute=0)

            print(f"  Searching for {req_duration_mins}m gap between {search_start} and {search_end}")

            # 3. Fetch all events that overlap this window
            events_ref = self.db.collection("users").document(user_id).collection("raw_events")
            start_iso = search_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            end_iso = search_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            
            docs = events_ref.where("end", ">", start_iso).stream()
            blocking_events = []
            for d in docs:
                data = d.to_dict()
                e_start = dt.datetime.fromisoformat(data['start'].replace("Z", "+00:00")).astimezone(user_tz)
                e_end = dt.datetime.fromisoformat(data['end'].replace("Z", "+00:00")).astimezone(user_tz)
                # Filter to only those that actually overlap our search window
                if e_start < search_end:
                    blocking_events.append({'start': e_start, 'end': e_end})

            # Sort by start time
            blocking_events.sort(key=lambda x: x['start'])

            # 4. Find Gaps
            free_slots = []
            current_time = search_start

            for event in blocking_events:
                # If there is enough time before the next event
                gap = (event['start'] - current_time).total_seconds() / 60
                if gap >= req_duration_mins:
                    free_slots.append({'start': current_time, 'end': event['start']})
                
                # Advance current_time to the end of this event (if it moves us forward)
                if event['end'] > current_time:
                    current_time = event['end']

            # Check for one final gap after the last event until search_end
            final_gap = (search_end - current_time).total_seconds() / 60
            if final_gap >= req_duration_mins:
                free_slots.append({'start': current_time, 'end': search_end})

            # 5. Format Response
            if not free_slots:
                day_name = "today" if not dates_list else search_start.strftime("%A")
                return {
                    "status": "success",
                    "message": f"I couldn't find a free {req_duration_mins}-minute slot on {day_name} during standard hours.",
                    "data": {"slots": []}
                }

            # Conversational formatting
            slot_strings = []
            for slot in free_slots[:3]: # Suggest top 3
                time_str = slot['start'].strftime("%-I:%M %p")
                slot_strings.append(time_str)

            if len(slot_strings) == 1:
                msg = f"You are free at {slot_strings[0]}."
            else:
                msg = f"You have free slots at {', '.join(slot_strings[:-1])} and {slot_strings[-1]}."

            print(f"  ✅ Found {len(free_slots)} slots.")
            return {
                "status": "success",
                "message": msg,
                "data": {"slots": [{"start": s['start'].isoformat(), "end": s['end'].isoformat()} for s in free_slots]}
            }

        except Exception as e:
            print(f"❌ [FindFreeTime] Error: {e}")
            raise


    def handle_suggest_time(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [SuggestTime] ENTERED HANDLER <<<")
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
        
        try:
            # ── 1. Extract Event Title & Safety Rescue ────────────────────────
            event_titles = [t for t in entities.get("events", []) if t]
            times_list   = entities.get("times", [])
            
            # HEURISTIC RESCUE: If LLM put an activity in 'times', move it to titles
            activity_keywords = ["lunch", "dinner", "breakfast", "gym", "workout", "meeting", "revision"]
            if not event_titles and times_list:
                for t in times_list:
                    if t.lower() in activity_keywords:
                        event_titles.append(t)
                        print(f"  [Safety Rescue] Moved '{t}' from times to event_titles.")

            has_specific_title = len(event_titles) > 0
            title = event_titles[0] if has_specific_title else "your event"

            # ── 2. The rest of your existing logic ──────────────────────────
            durations_list = entities.get("durations", [])
            req_duration_mins = self._parse_duration_minutes(durations_list[0]) if durations_list else 60

            dates_list = entities.get("dates", [])
            source_date = entities.get("source_date")
            if source_date and not dates_list:
                dates_list.append(source_date)

            now_local = dt.datetime.now(user_tz)

            if dates_list:
                target_date_str = dates_list[-1]
                parsed_day = dateparser.parse(
                    target_date_str, 
                    settings={
                        "TIMEZONE": user_tz_str, "RETURN_AS_TIMEZONE_AWARE": True,
                        "RELATIVE_BASE": now_local, "PREFER_DATES_FROM": "future"
                    }
                )
                if not parsed_day:
                    raise ValueError(f"I couldn't understand the date '{target_date_str}'.")
                current_check_date = parsed_day
                max_days_to_check = 1
            else:
                current_check_date = now_local
                max_days_to_check = 5

            events_ref = self.db.collection("users").document(user_id).collection("raw_events")
            free_slots = []
            existing_similar_events = []
            seen_ids = set()
            days_checked = 0

            # ── 3. Scanning Loop ──────────────────────────────────────────────
            while len(free_slots) < 3 and days_checked < max_days_to_check:
                day_midnight = current_check_date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_start = current_check_date.replace(hour=9, minute=0, second=0, microsecond=0)
                day_end = current_check_date.replace(hour=18, minute=0, second=0, microsecond=0)

                if day_start < now_local:
                    day_start = now_local
                    mins = day_start.minute
                    if mins % 15 != 0:
                        day_start += dt.timedelta(minutes=(15 - (mins % 15)))
                    day_start = day_start.replace(second=0, microsecond=0)

                query_start_iso = day_midnight.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                docs = events_ref.where("end", ">", query_start_iso).stream()
                blocking_events = []

                for d in docs:
                    data = d.to_dict()
                    e_start = dt.datetime.fromisoformat(data['start'].replace("Z", "+00:00")).astimezone(user_tz)
                    e_end = dt.datetime.fromisoformat(data['end'].replace("Z", "+00:00")).astimezone(user_tz)
                    
                    # Exact or fuzzy match for the title to trigger the "You already have..." warning
                    if has_specific_title and title.lower() in data.get('title', '').lower():
                        if e_start.date() == current_check_date.date() and d.id not in seen_ids:
                            existing_similar_events.append({'title': data.get('title'), 'start': e_start, 'end': e_end})
                            seen_ids.add(d.id)

                    if e_end > day_start and e_start < day_end:
                        blocking_events.append({'start': e_start, 'end': e_end})

                blocking_events.sort(key=lambda x: x['start'])

                if day_start < day_end:
                    current_time = day_start
                    for event in blocking_events:
                        if current_time < event['start']:
                            gap_mins = (event['start'] - current_time).total_seconds() / 60
                            if gap_mins >= req_duration_mins:
                                free_slots.append({'start': current_time, 'end': current_time + dt.timedelta(minutes=req_duration_mins)})
                                if len(free_slots) >= 3: break
                        if current_time < event['end']:
                            current_time = event['end']

                    if len(free_slots) < 3 and current_time < day_end:
                        gap_mins = (day_end - current_time).total_seconds() / 60
                        if gap_mins >= req_duration_mins:
                            free_slots.append({'start': current_time, 'end': current_time + dt.timedelta(minutes=req_duration_mins)})

                current_check_date += dt.timedelta(days=1)
                days_checked += 1

            # ── 4. Formatting ─────────────────────────────────────────────────
            if not free_slots:
                return {"status": "success", "message": f"No {req_duration_mins}m slots found for '{title}'."}

            best_slot = free_slots[0]
            best_time_str = best_slot['start'].strftime("%A at %-I:%M %p")

            if existing_similar_events:
                ex = existing_similar_events[0]
                msg = f"You already have '{ex['title']}' on {ex['start'].strftime('%A')} from {ex['start'].strftime('%-I:%M %p')} to {ex['end'].strftime('%-I:%M %p')}. If you'd like another one, I suggest {best_time_str}."
            else:
                msg = f"I suggest scheduling '{title}' for {best_time_str}."

            return {"status": "success", "message": msg, "data": {"slots": [s['start'].isoformat() for s in free_slots]}}

        except Exception as e:
            print(f"❌ [SuggestTime] Error: {e}")
            raise
    
    
    
    def handle_change_recurrence(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [ChangeRecurrence] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        print(f"  raw_text: {raw_text}")

        try:
            event_titles = [t for t in entities.get("events", []) if t]
            
            # HEURISTIC RESCUE: If titles are empty, check the times/tasks slot 
            # for common activities (gym, lunch, etc)
            if not event_titles:
                potential_titles = entities.get("times", []) + entities.get("tasks", [])
                activity_keywords = ["gym", "lunch", "dinner", "meeting", "workout", "revision"]
                for p in potential_titles:
                    if any(kw in p.lower() for kw in activity_keywords):
                        event_titles.append(p)

            if not event_titles:
                raise ValueError("I couldn't identify which event you want to change.")

            # ── 1. Parse the Recurrence Pattern ─────────────────────────────────
            recurrence_raw = entities.get("recurrence", [])
            # We now have the REAL raw_text thanks to the router fix
            text_to_scan = (" ".join(recurrence_raw) + " " + raw_text).lower()

            rec_type = None
            rec_days = []

            # Match "none" patterns
            if re.search(r'\b(stop|none|never|don\'t repeat|cancel recurrence|remove recurrence|delete recurrence|from repeating|no longer repeat)\b', text_to_scan):
                rec_type = "none"
            elif re.search(r'\b(daily|every day|everyday)\b', text_to_scan):
                rec_type = "daily"
            elif re.search(r'\b(monthly|every month)\b', text_to_scan):
                rec_type = "monthly"
            
            day_map = {
                'monday': '1', 'tuesday': '2', 'wednesday': '3', 
                'thursday': '4', 'friday': '5', 'saturday': '6', 'sunday': '0'
            }
            found_days = []
            for day, day_id in day_map.items():
                if re.search(r'\b' + day + r's?\b', text_to_scan):
                    found_days.append(day_id)
            
            if found_days:
                rec_type = "custom"
                rec_days = found_days
            elif not rec_type and re.search(r'\b(weekly|every week)\b', text_to_scan):
                rec_type = "weekly"

            if not rec_type:
                raise ValueError("I couldn't understand the new repeating pattern. Try 'make it weekly' or 'stop repeating'.")

            # ── 2. Find and Update the Events ──────────────────────────────────
            events_ref = self.db.collection("users").document(user_id).collection("raw_events")
            results = []
            messages = []

            for title in event_titles:
                target_event = self._find_event_by_title(user_id, title)
                
                if not target_event:
                    messages.append(f"Could not find an event matching '{title}'.")
                    continue

                doc_id = target_event["_doc_id"]
                update_data = {
                    "recurrence": rec_type,
                    "recurrence_days": rec_days,
                    "sync_action_required": "push_to_provider"
                }

                events_ref.document(doc_id).update(update_data)
                results.append({"eventId": doc_id, "title": title, "recurrence": rec_type})
                print(f"  ✅ Updated '{title}' to: {rec_type}")

            # ── 3. Build Response ──────────────────────────────────────────────
            if not results:
                raise ValueError(" ".join(messages) or "No events were updated.")

            friendly_pattern = "stop repeating" if rec_type == "none" else f"repeat {rec_type}"
            if rec_type == "custom":
                day_names = [k.capitalize() for k, v in day_map.items() if v in rec_days]
                friendly_pattern = f"repeat every {', '.join(day_names)}"

            final_msg = f"I have updated '{results[0]['title']}' to {friendly_pattern}." if len(results) == 1 else f"I have updated {len(results)} events to {friendly_pattern}."

            return {
                "status": "success",
                "message": final_msg,
                "data": {"updated": results}
            }

        except Exception as e:
            print(f"❌ [ChangeRecurrence] Error: {e}")
            raise
    
    
    
    def handle_create_task(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n>>> [CreateTask] ENTERED HANDLER <<<")
        print(f"  entities: {entities}")
        print(f"  raw_text: {raw_text}")
        user_tz_str = self._get_user_tz_str(user_id)

        try:
            # 1. Extract Task Title
            tasks_list = entities.get("tasks", [])
            
            # SAFETY RESCUE: If the LLM put the task in the 'events' array by mistake
            if not tasks_list:
                tasks_list = entities.get("events", [])
                
            title = tasks_list[0] if tasks_list else "Untitled Task"
            
            # 2. Extract Duration
            durations_list = entities.get("durations", [])
            estimated_duration = self._parse_duration_minutes(durations_list[0]) if durations_list else None

            # 3. Extract Due Date (Using the engine's normalized start_timestamp)
            target_ts = entities.get("start_timestamp")
            due_date = target_ts if target_ts else None

            # 4. Heuristic Extraction for Priority and Energy
            text_lower = raw_text.lower()
            
            priority = 3 # Default medium priority
            if re.search(r'\b(urgent|asap|high priority|critical|important)\b', text_lower):
                priority = 1
            elif re.search(r'\b(low priority|whenever|no rush)\b', text_lower):
                priority = 5
                
            energy_level = "medium"
            if re.search(r'\b(quick|easy|fast|simple)\b', text_lower):
                energy_level = "low"
            elif re.search(r'\b(hard|focus|deep work|intense|difficult)\b', text_lower):
                energy_level = "high"

            # 5. Build Task Data
            doc_id = self._generate_id("task")
            
            task_data = {
                "id": doc_id,
                "user_id": user_id,
                "title": title,
                "description": "",
                "sub_tasks": [],
                "estimated_duration": estimated_duration,
                "start_date": None,
                "due_date": due_date,
                "status": "pending",
                "priority": priority,
                "energy_level": energy_level,
                "tags": [],
                "linked_event_id": None,
                "linked_reminder_ids": [],
                "is_locked": False,
                "created_at": dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                
                # --- NEW TELEMETRY FIELDS ---
                "snooze_count": 0,
                "completed_at": None,
                "debt_applied": False,
                "is_perishable": False
            }

            # 6. Write to Firestore
            tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
            tasks_ref.document(doc_id).set(task_data)

            # 7. Format Conversational Response
            msg = f"I have added '{title}' to your tasks."
            
            if due_date:
                friendly_time = self._format_time(due_date, user_tz_str)
                msg = f"I have added '{title}' to your tasks, due {friendly_time}."
                
            # Append extra context if the AI extracted implicit data
            extras = []
            if estimated_duration: extras.append(f"{estimated_duration} mins")
            if priority == 1: extras.append("High Priority")
            if energy_level == "low": extras.append("Quick Task")
            
            if extras:
                msg = msg.replace(".", f" ({' | '.join(extras)}).")

            print(f"  ✅ Created Task: '{title}' (ID: {doc_id})")

            return {
                "status": "success",
                "message": msg,
                "data": {"taskId": doc_id}
            }

        except Exception as e:
            print(f"❌ [CreateTask] Error: {e}")
            raise
    
    


    def handle_update_task(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [UpdateTask] ENTERED HANDLER <<<")
        print("="*60)
        print(f"  [Input] Raw Text: '{raw_text}'")
        print(f"  [Input] Entities: {entities}")
        print(f"  [Input] User ID:  {user_id}")
        
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)

        try:
            from google.cloud import firestore # Needed for Atomic decrement
            
            # --- 1. SMART TASK RESOLUTION ---
            print("\n  [Step 1] Resolving Target Tasks...")
            tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
            
            # Fetch all active tasks to cross-reference with raw text (including missed to allow resurrection)
            active_tasks = []
            print("    -> Fetching active tasks from Firestore for raw text matching...")
            for status in ["pending", "scheduled", "in_progress"]:
                for doc in tasks_ref.where("status", "==", status).stream():
                    t_data = doc.to_dict()
                    t_data["_doc_id"] = doc.id
                    active_tasks.append(t_data)
            print(f"    -> Found {len(active_tasks)} active task(s) in database.")

            target_tasks = []
            text_lower = raw_text.lower()
            
            # Sort tasks by length descending so we match "final year project" before "project"
            active_tasks.sort(key=lambda x: len(x.get("title", "")), reverse=True)
            
            # 1A. Raw Text Exact Match Override (Fixes NER Fragmentation)
            print("    -> Attempting 'Longest String' Raw Text Override...")
            matched_exact = False
            for t in active_tasks:
                t_title = t.get("title", "").lower()
                if t_title and t_title in text_lower:
                    print(f"      * SUCCESS: Found exact task title '{t_title}' in raw text!")
                    target_tasks.append(t)
                    matched_exact = True
                    break 
            
            # 1B. Fallback to NER extracted tokens if Exact Match failed
            if not matched_exact:
                print("    -> No exact matches in raw text. Falling back to NER tokens...")
                task_titles = [t for t in entities.get("tasks", []) if t]
                if not task_titles:
                    task_titles = [t for t in entities.get("events", []) if t]
                    print(f"    -> Heuristic Rescue: Using event tokens as tasks: {task_titles}")
                
                print(f"    -> Extracted NER tokens to resolve: {task_titles}")
                for title in task_titles:
                    direct_match = next((t for t in active_tasks if t["_doc_id"] == title), None)
                    if direct_match:
                        if direct_match not in target_tasks:
                            target_tasks.append(direct_match)
                            print(f"      * Direct ID Match (Ambiguity Bypass): '{direct_match.get('title')}'")
                        continue




                    print(f"      * Calling strict resolver for: '{title}'")
                    matched_task = self._find_task_by_title(user_id, title)
                    if matched_task and matched_task not in target_tasks:
                        target_tasks.append(matched_task)
                        print(f"        -> Resolved to: '{matched_task.get('title')}'")
                    else:
                        print(f"        -> Failed to resolve '{title}' or already added.")

            if not target_tasks:
                raise ValueError("I couldn't identify which task you want to update.")
            
            print(f"  [Step 1 Complete] Targeted Tasks: {[t.get('title') for t in target_tasks]}")

            # --- 2. EXTRACT UPDATES ---
            print("\n  [Step 2] Extracting Updates...")
            
            durations_list = entities.get("durations", [])
            new_duration = self._parse_duration_minutes(durations_list[0]) if durations_list else None

            dates_list = entities.get("dates", [])
            times_list = entities.get("times", [])
            new_date_str = dates_list[-1] if dates_list else None
            new_time_str = times_list[-1] if times_list else None

            new_priority = None
            if re.search(r'\b(urgent|asap|high priority|critical|important)\b', text_lower):
                new_priority = 1
            elif re.search(r'\b(low priority|whenever|no rush)\b', text_lower):
                new_priority = 5

            new_energy = None
            if re.search(r'\b(quick|easy|fast|simple)\b', text_lower):
                new_energy = "low"
            elif re.search(r'\b(hard|focus|deep work|intense|difficult)\b', text_lower):
                new_energy = "high"

            # --- 3. APPLY UPDATES ---
            print("\n  [Step 3] Applying Updates to Firestore...")
            
            def parse_dt(expression: str) -> dt.datetime | None:
                now_local = dt.datetime.now(user_tz)
                return dateparser.parse(
                    expression,
                    settings={
                        "TIMEZONE": user_tz_str, "TO_TIMEZONE": "UTC",
                        "RETURN_AS_TIMEZONE_AWARE": True, "DATE_ORDER": "DMY",
                        "RELATIVE_BASE": now_local, "PREFER_DATES_FROM": "future"
                    }
                )

            results = []
            messages = []

            for target_task in target_tasks:
                doc_id = target_task["_doc_id"]
                title = target_task.get("title")
                print(f"    -> Processing Task: '{title}' (ID: {doc_id})")
                
                update_data = {}
                update_summary = []
                snooze_increment = 0

                # Handle Due Date & Snooze Tracking
                if new_date_str or new_time_str:
                    print("      * Calculating new due date...")
                    orig_due = target_task.get("due_date")
                    new_due_dt = None
                    
                    if new_date_str and new_time_str:
                        new_due_dt = parse_dt(f"{new_date_str} at {new_time_str}")
                    elif new_date_str and orig_due:
                        orig_dt = dt.datetime.fromisoformat(orig_due.replace("Z", "+00:00")).astimezone(user_tz)
                        new_due_dt = parse_dt(f"{new_date_str} at {orig_dt.strftime('%H:%M')}")
                    elif new_date_str and not orig_due:
                        new_due_dt = parse_dt(f"{new_date_str} at 17:00")
                    elif new_time_str and orig_due:
                        orig_dt = dt.datetime.fromisoformat(orig_due.replace("Z", "+00:00")).astimezone(user_tz)
                        new_due_dt = parse_dt(f"{orig_dt.strftime('%d/%m/%Y')} at {new_time_str}")
                    else:
                        raw_ts = entities.get("start_timestamp")
                        if raw_ts:
                            new_due_dt = dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))

                    if new_due_dt:
                        iso_due = new_due_dt.isoformat().replace("+00:00", "Z")
                        update_data["due_date"] = iso_due
                        update_summary.append(f"due {new_date_str or new_time_str}")
                        
                        # Calculate Snooze
                        if orig_due:
                            orig_dt_utc = dt.datetime.fromisoformat(orig_due.replace("Z", "+00:00"))
                            if new_due_dt.timestamp() > orig_dt_utc.timestamp():
                                snooze_increment = 1
                        
                    else:
                        print("        -> Failed to calculate new due date.")
                
                if snooze_increment > 0:
                    update_data["snooze_count"] = target_task.get("snooze_count", 0) + snooze_increment

                # Handle Debt Relief Hook
                old_status = target_task.get("status")
                debt_applied = target_task.get("debt_applied", False)
                is_perish = target_task.get("is_perishable", False)
                
                if old_status == "missed" and snooze_increment > 0:
                    update_data["status"] = "pending" # Resurrect it
                    
                    if debt_applied and not is_perish:
                        refund_mins = 0
                        est_dur = target_task.get("estimated_duration")
                        
                        if est_dur:
                            refund_mins = est_dur
                        else:
                            # Strict calculation from missed events only
                            linked_evs = target_task.get("linked_event_ids", [])
                            if linked_evs:
                                ev_ref = self.db.collection("users").document(user_id).collection("raw_events")
                                for eid in linked_evs:
                                    edoc = ev_ref.document(eid).get()
                                    if edoc.exists:
                                        edata = edoc.to_dict()
                                        if edata.get("completion_status") == "missed":
                                            es_str = edata.get("start")
                                            ee_str = edata.get("end")
                                            if es_str and ee_str:
                                                es = dt.datetime.fromisoformat(es_str.replace("Z", "+00:00"))
                                                ee = dt.datetime.fromisoformat(ee_str.replace("Z", "+00:00"))
                                                refund_mins += int((ee - es).total_seconds() / 60)
                                                
                        if refund_mins > 0:
                            self.db.collection("users").document(user_id).update({
                                "total_time_debt": firestore.Increment(-refund_mins)
                            })
                            print(f"      * 💰 Refunded {refund_mins}m Time Debt via Snooze")
                            
                    update_data["debt_applied"] = False

                # Handle other fields
                if new_duration: update_data["estimated_duration"] = new_duration
                if new_priority is not None: update_data["priority"] = new_priority
                if new_energy: update_data["energy_level"] = new_energy

                if not update_data:
                    messages.append(f"I understood you want to update '{title}', but I wasn't sure what to change.")
                    continue

                # Execute Firestore Update
                try:
                    tasks_ref.document(doc_id).update(update_data)
                    results.append({"taskId": doc_id, "title": title, "updates": update_data})
                    
                    msg_str = f"Updated '{title}'"
                    if update_summary:
                        msg_str += f" ({', '.join(update_summary)})"
                    messages.append(msg_str + ".")
                except Exception as e:
                    print(f"      * ❌ Firestore update failed: {e}")
                    raise

            # --- 4. FORMAT RESPONSE ---
            if not results:
                raise ValueError(" ".join(messages) or "No tasks were updated.")

            print(">>> [UpdateTask] COMPLETE <<<")
            
            return {
                "status": "success",
                "message": " ".join(messages),
                "data": {"updated": results}
            }

        except Exception as e:
            print(f"❌ [UpdateTask] Error: {e}")
            raise


    

    def handle_complete_task(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [CompleteTask] ENTERED HANDLER <<<")
        print("="*60)

        try:
            from google.cloud import firestore # Needed for Atomic decrement
            
            # --- 1. SMART TASK RESOLUTION ---
            print("\n  [Step 1] Resolving Target Tasks...")
            tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
            
            active_tasks = []
            # Include missed tasks so you can complete them late
            for status in ["pending", "scheduled", "in_progress", "missed"]:
                for doc in tasks_ref.where("status", "==", status).stream():
                    t_data = doc.to_dict()
                    t_data["_doc_id"] = doc.id
                    active_tasks.append(t_data)

            target_tasks = []
            text_lower = raw_text.lower()
            active_tasks.sort(key=lambda x: len(x.get("title", "")), reverse=True)
            
            matched_exact = False
            for t in active_tasks:
                t_title = t.get("title", "").lower()
                if t_title and t_title in text_lower:
                    target_tasks.append(t)
                    matched_exact = True
                    break 
            
            if not matched_exact:
                task_titles = [t for t in entities.get("tasks", []) if t]
                if not task_titles:
                    task_titles = [t for t in entities.get("events", []) if t]
                
                print(f"    -> Extracted NER tokens to resolve: {task_titles}")
                for title in task_titles:
                    # --- THE FIX: AMBIGUITY BYPASS ---
                    direct_match = next((t for t in active_tasks if t["_doc_id"] == title), None)
                    if direct_match:
                        if direct_match not in target_tasks:
                            target_tasks.append(direct_match)
                            print(f"      * Direct ID Match (Ambiguity Bypass): '{direct_match.get('title')}'")
                        continue

                    print(f"      * Calling strict resolver for: '{title}'")
                    matched_task = self._find_task_by_title(user_id, title)
                    if matched_task and matched_task not in target_tasks:
                        target_tasks.append(matched_task)
                        print(f"        -> Resolved to: '{matched_task.get('title')}'")
                    else:
                        print(f"        -> Failed to resolve '{title}' or already added.")

            if not target_tasks:
                raise ValueError("I couldn't identify which task you want to check off.")

            # --- 2. APPLY UPDATES ---
            print("\n  [Step 2] Applying Completion Status to Firestore...")
            results = []
            messages = []
            now_dt = dt.datetime.now(timezone.utc)
            now_iso = now_dt.isoformat().replace("+00:00", "Z")

            for target_task in target_tasks:
                doc_id = target_task["_doc_id"]
                title = target_task.get("title")
                old_status = target_task.get("status")
                
                update_data = {
                    "status": "completed",
                    "completed_at": now_iso
                }
                
                # --- A. FUTURE EVENT CLEANUP LOGIC ---
                linked_event_ids = target_task.get("linked_event_ids", [])
                if linked_event_ids:
                    events_ref = self.db.collection("users").document(user_id).collection("raw_events")
                    batch = self.db.batch()
                    events_deleted = 0
                    events_to_keep = []
                    
                    for event_id in linked_event_ids:
                        event_doc = events_ref.document(event_id).get()
                        if event_doc.exists:
                            edata = event_doc.to_dict()
                            es_str = edata.get("start")
                            if es_str:
                                start_dt = dt.datetime.fromisoformat(es_str.replace("Z", "+00:00"))
                                if start_dt > now_dt:
                                    batch.delete(events_ref.document(event_id))
                                    events_deleted += 1
                                else:
                                    events_to_keep.append(event_id)
                            else:
                                events_to_keep.append(event_id)
                                
                    if events_deleted > 0:
                        batch.commit()
                        update_data["linked_event_ids"] = events_to_keep
                        print(f"      * Cleaned up {events_deleted} future calendar events for '{title}'.")

                # --- B. LATE COMPLETION DEBT RELIEF ---
                debt_applied = target_task.get("debt_applied", False)
                is_perish = target_task.get("is_perishable", False)
                
                if old_status == "missed" and debt_applied and not is_perish:
                    refund_mins = 0
                    est_dur = target_task.get("estimated_duration")
                    
                    if est_dur:
                        refund_mins = est_dur
                    else:
                        if linked_event_ids:
                            events_ref = self.db.collection("users").document(user_id).collection("raw_events")
                            for eid in linked_event_ids:
                                edoc = events_ref.document(eid).get()
                                if edoc.exists:
                                    edata = edoc.to_dict()
                                    if edata.get("completion_status") == "missed":
                                        es_str = edata.get("start")
                                        ee_str = edata.get("end")
                                        if es_str and ee_str:
                                            es = dt.datetime.fromisoformat(es_str.replace("Z", "+00:00"))
                                            ee = dt.datetime.fromisoformat(ee_str.replace("Z", "+00:00"))
                                            refund_mins += int((ee - es).total_seconds() / 60)
                                            
                    if refund_mins > 0:
                        self.db.collection("users").document(user_id).update({
                            "total_time_debt": firestore.Increment(-refund_mins)
                        })
                        print(f"      * 💰 Refunded {refund_mins}m Time Debt via Late Completion")
                        
                    update_data["debt_applied"] = False

                # Execute Firestore Update
                try:
                    tasks_ref.document(doc_id).update(update_data)
                    results.append({"taskId": doc_id, "title": title, "status": "completed"})
                    messages.append(f"Marked '{title}' as complete.")
                except Exception as e:
                    print(f"      * ❌ Firestore update failed: {e}")
                    raise

            # --- 3. FORMAT RESPONSE ---
            if not results:
                raise ValueError(" ".join(messages) or "No tasks were completed.")

            if len(results) == 1:
                final_msg = f"I have marked '{results[0]['title']}' as complete. Great job!"
            else:
                final_msg = f"I have marked {len(results)} tasks as complete. Great work!"
            
            print(">>> [CompleteTask] COMPLETE <<<")
            
            return {
                "status": "success",
                "message": final_msg,
                "data": {"completed": results}
            }

        except Exception as e:
            print(f"❌ [CompleteTask] Error: {e}")
            raise




    def handle_delete_task(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [DeleteTask] ENTERED HANDLER <<<")
        print("="*60)
        print(f"  [Input] Raw Text: '{raw_text}'")
        print(f"  [Input] Entities: {entities}")
        print(f"  [Input] User ID:  {user_id}")

        try:
            # --- 1. SMART TASK RESOLUTION ---
            print("\n  [Step 1] Resolving Target Tasks for Deletion...")
            tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
            
            # Fetch active AND completed tasks (users often delete tasks to clean up)
            all_tasks = []
            print("    -> Fetching tasks from Firestore for raw text matching...")
            for status in ["pending", "scheduled", "in_progress", "completed"]:
                for doc in tasks_ref.where("status", "==", status).stream():
                    t_data = doc.to_dict()
                    t_data["_doc_id"] = doc.id
                    all_tasks.append(t_data)
            print(f"    -> Found {len(all_tasks)} total task(s) in database.")

            target_tasks = []
            text_lower = raw_text.lower()
            
            # Sort tasks by length descending (Longest String Override)
            all_tasks.sort(key=lambda x: len(x.get("title", "")), reverse=True)
            
            # 1A. Raw Text Exact Match Override
            print("    -> Attempting 'Longest String' Raw Text Override...")
            matched_exact = False
            for t in all_tasks:
                t_title = t.get("title", "").lower()
                if t_title and t_title in text_lower:
                    print(f"      * SUCCESS: Found exact task title '{t_title}' in raw text!")
                    target_tasks.append(t)
                    matched_exact = True
                    break # Stop after finding the most specific match
            
            # 1B. Fallback to NER extracted tokens if Exact Match failed
            if not matched_exact:
                print("    -> No exact matches in raw text. Falling back to NER tokens...")
                task_titles = [t for t in entities.get("tasks", []) if t]
                
                # Heuristic Rescue: If the AI put the task in the 'events' array
                if not task_titles:
                    task_titles = [t for t in entities.get("events", []) if t]
                    print(f"    -> Heuristic Rescue: Using event tokens as tasks: {task_titles}")
                
                print(f"    -> Extracted NER tokens to resolve: {task_titles}")
                for title in task_titles:
                    direct_match = next((t for t in all_tasks if t["_doc_id"] == title), None)
                    if direct_match:
                        if direct_match not in target_tasks:
                            target_tasks.append(direct_match)
                            print(f"      * Direct ID Match (Ambiguity Bypass): '{direct_match.get('title')}'")
                        continue
                    print(f"      * Calling strict resolver for: '{title}'")
                    matched_task = self._find_task_by_title(user_id, title)
                    if matched_task and matched_task not in target_tasks:
                        target_tasks.append(matched_task)
                        print(f"        -> Resolved to: '{matched_task.get('title')}'")
                    else:
                        print(f"        -> Failed to resolve '{title}' or already added.")

            if not target_tasks:
                raise ValueError("I couldn't identify which task you want to delete.")
            
            print(f"  [Step 1 Complete] Targeted Tasks: {[t.get('title') for t in target_tasks]}")

            # --- 2. APPLY DELETIONS ---
            print("\n  [Step 2] Deleting Documents from Firestore...")
            results = []
            messages = []

            for target_task in target_tasks:
                doc_id = target_task["_doc_id"]
                title = target_task.get("title")
                print(f"    -> Deleting Task: '{title}' (ID: {doc_id})")
                
                try:
                    # Wipe the document entirely
                    tasks_ref.document(doc_id).delete()
                    results.append({"taskId": doc_id, "title": title})
                    messages.append(f"Deleted '{title}'.")
                    print(f"      * ✅ Deletion successful.")
                except Exception as e:
                    print(f"      * ❌ Firestore deletion failed: {e}")
                    raise

            # --- 3. FORMAT RESPONSE ---
            print("\n  [Step 3] Formatting Response...")
            if not results:
                raise ValueError(" ".join(messages) or "No tasks were deleted.")

            if len(results) == 1:
                final_msg = f"I have deleted '{results[0]['title']}' from your tasks."
            else:
                final_msg = f"I have deleted {len(results)} tasks."
            
            print(">>> [DeleteTask] COMPLETE <<<")
            print("="*60 + "\n")
            
            return {
                "status": "success",
                "message": final_msg,
                "data": {"deleted": results}
            }

        except Exception as e:
            print(f"❌ [DeleteTask] Error: {e}")
            raise



    def handle_query_task(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [QueryTask] EXECUTING HANDLER <<<")
        print("="*60)
        print(f"  [Input] Raw Text: '{raw_text}'")
        print(f"  [Input] Entities: {entities}")
        
        user_tz_str = self._get_user_tz_str(user_id)
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
        
        try:
            tasks_ref = self.db.collection("users").document(user_id).collection("raw_tasks")
            text_lower = raw_text.lower().strip()
            
            # --- 1. HEURISTIC METADATA EXTRACTION ---
            print("\n  [Step 1] Extracting Query Parameters...")
            
            # BROADENED STATUS SCANNER: Catch "complete", "completed", "done", etc.
            target_statuses = ["pending", "scheduled", "in_progress"]
            status_label = "pending"
            
            if re.search(r'\b(complete|completed|done|finished|checked off)\b', text_lower):
                target_statuses = ["completed"]
                status_label = "completed"
                print(f"    -> Intent identified as checking COMPLETED tasks.")
            else:
                print(f"    -> Intent identified as checking PENDING tasks.")

            # SCAN FOR "DUE": If the user asks for "due" tasks, we flag that we only want items with dates
            is_due_query = "due" in text_lower
            if is_due_query:
                print("    -> User specifically asked for 'due' tasks. Will filter for deadlines.")

            # Date Extraction (Adapter + Safety Net)
            dates_list = entities.get("dates", [])
            source_date = entities.get("source_date")
            if source_date and not dates_list:
                dates_list.append(source_date)
                
            if not dates_list:
                day_match = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)\b', text_lower)
                if day_match:
                    dates_list.append(day_match.group(1))
                    print(f"    -> [Safety Net] Extracted date from text: {dates_list[-1]}")

            # Identify if specific tasks were requested
            task_titles = [t for t in entities.get("tasks", []) if t]
            if not task_titles and "task" not in text_lower:
                task_titles = [t for t in entities.get("events", []) if t]
            
            found_tasks = []
            query_context_msg = ""

            # --- 2. EXECUTE QUERY ---

            # SCENARIO A: Specific Task Status (e.g., "Is the project done?")
            if task_titles:
                print(f"\n  [Step 2 - Scenario A] Resolving Specific Tasks: {task_titles}")
                all_tasks = []
                for s in ["pending", "scheduled", "in_progress", "completed"]:
                    for doc in tasks_ref.where("status", "==", s).stream():
                        all_tasks.append(doc.to_dict() | {"_doc_id": doc.id})
                
                all_tasks.sort(key=lambda x: len(x.get("title", "")), reverse=True)
                
                for t in all_tasks:
                    if t.get("title", "").lower() in text_lower:
                        print(f"    -> Exact Title Match: '{t.get('title')}'")
                        found_tasks.append(t)
                        break

            # SCENARIO B: Timeframe Query (e.g., "What is due tomorrow?")
            elif dates_list:
                target_date_str = dates_list[-1]
                print(f"\n  [Step 2 - Scenario B] Querying Timeframe: '{target_date_str}'")
                now_local = dt.datetime.now(user_tz)
                
                # Resolve date window
                parsed_date = dateparser.parse(
                    target_date_str,
                    settings={"TIMEZONE": user_tz_str, "RETURN_AS_TIMEZONE_AWARE": True, "RELATIVE_BASE": now_local, "PREFER_DATES_FROM": "future"}
                )
                
                if parsed_date:
                    local_mid = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    window_start = local_mid.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    window_end = (local_mid + dt.timedelta(hours=24)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    
                    query_context_msg = f"due {target_date_str}"
                    print(f"    -> Search Window: {window_start} to {window_end}")
                    
                    for status in target_statuses:
                        docs = tasks_ref.where("status", "==", status).stream()
                        for d in docs:
                            data = d.to_dict()
                            due = data.get("due_date")
                            if due and window_start <= due < window_end:
                                found_tasks.append(data | {"_doc_id": d.id})

            # SCENARIO C: General List Query (e.g., "What tasks do I have?")
            else:
                print(f"\n  [Step 2 - Scenario C] General Query for '{status_label}' tasks")
                query_context_msg = "on your list"
                for status in target_statuses:
                    docs = tasks_ref.where("status", "==", status).stream()
                    for d in docs:
                        data = d.to_dict()
                        # If user said "due", only show tasks that actually have a deadline
                        if is_due_query and not data.get("due_date"):
                            continue
                        found_tasks.append(data | {"_doc_id": d.id})

            # --- 3. FORMAT RESPONSE ---
            print("\n  [Step 3] Formatting Response...")
            if not found_tasks:
                msg = f"You don't have any {status_label} tasks {query_context_msg}."
                print(f"    -> ❌ No matching tasks found for status '{status_label}'.")
                return {"status": "success", "message": msg, "data": {"tasks": []}}

            unique_tasks = {t["_doc_id"]: t for t in found_tasks}.values()
            sorted_tasks = sorted(unique_tasks, key=lambda x: (x.get("priority", 3), x.get("due_date", "Z")))

            if task_titles and len(sorted_tasks) == 1:
                t = sorted_tasks[0]
                status_now = t.get("status")
                due_info = f", due {self._format_time(t.get('due_date'), user_tz_str)}" if t.get('due_date') else ""
                msg = f"The '{t.get('title')}' task is currently {status_now}{due_info}."
            else:
                msg_parts = [f"You have {len(sorted_tasks)} {status_label} tasks {query_context_msg}:"]
                for t in sorted_tasks:
                    prio_flag = " (High Priority)" if t.get("priority") == 1 else ""
                    msg_parts.append(f"- {t.get('title')}{prio_flag}")
                msg = "\n".join(msg_parts)

            print(f"    -> ✅ SUCCESS: Returning {len(sorted_tasks)} tasks.")
            print(">>> [QueryTask] COMPLETE <<<")
            print("="*60 + "\n")
            
            return {
                "status": "success", "message": msg, "data": {"tasks": list(sorted_tasks)}
            }

        except Exception as e:
            print(f"  ❌ ERROR in QueryTask: {str(e)}")
            raise


    def handle_set_reminder(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [SetReminder] EXECUTING HANDLER <<<")
        print("="*60)
        
        user_tz_str = self._get_user_tz_str(user_id)
        
        # Fix 1: Sanitize input text (remove quotes)
        clean_text = raw_text.strip().strip('"').strip("'")
        print(f"  [Input] Clean Text: '{clean_text}'")

        try:
            print("\n  [Step 1] Extracting Reminder Parameters...")
            
            # Fix 2: Explicitly extract the actual string value from NER
            rem_titles = entities.get("reminders", []) or entities.get("tasks", []) or entities.get("events", [])
            title = rem_titles[0] if (rem_titles and isinstance(rem_titles, list)) else "Untitled Reminder"
            print(f"    -> Resolved Title Variable: '{title}'")
            
            trigger_time = entities.get("start_timestamp")
            if not trigger_time:
                raise ValueError("I couldn't determine a time for this reminder.")

            # Fix 3: Ensure priority variable is mapped correctly
            text_lower = clean_text.lower()
            extracted_priority = "standard"
            if any(w in text_lower for w in ["urgent", "asap", "high priority", "important"]):
                extracted_priority = "high"
            print(f"    -> Resolved Priority Variable: {extracted_priority}")

            print("\n  [Step 2] Constructing Pydantic-Ready Payload...")
            doc_id = self._generate_id("rem")
            
            # CRITICAL: We use the variables resolved above
            reminder_data = {
                "id": doc_id,
                "user_id": user_id,
                "title": str(title), # Ensure it's a string, not a list
                "body": "",
                "type": "standalone",
                "reference_id": None,
                "trigger_type": "time",
                "trigger_time": trigger_time,
                "location_data": None,
                "priority": extracted_priority, 
                "repeat": "none",
                "custom_repeat_days": [],
                "status": "pending",
                "created_at": dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }

            print(f"\n  [Step 3] Committing Payload to Firestore: {reminder_data}")
            rem_ref = self.db.collection("users").document(user_id).collection("reminders")
            rem_ref.document(doc_id).set(reminder_data)
            print(f"    -> ✅ SUCCESS: Document Created (ID: {doc_id})")

            return {
                "status": "success",
                "message": f"I have set a reminder to '{title}' for {self._format_time(trigger_time, user_tz_str)}.",
                "data": {"reminderId": doc_id}
            }

        except Exception as e:
            print(f"  ❌ ERROR in SetReminder: {str(e)}")
            raise



    def handle_update_reminder(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [UpdateReminder] EXECUTING HANDLER <<<")
        print("="*60)
        clean_text = raw_text.strip().strip('"').strip("'")
        print(f"  [Input] Clean Text: '{clean_text}'")
        
        try:
            rem_ref = self.db.collection("users").document(user_id).collection("reminders")

            print("\n  [Step 1] Loading Candidate Reminders...")
            active_rems = []
            for status in ["pending"]:
                docs = rem_ref.where("status", "==", status).stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["_doc_id"] = doc.id
                    active_rems.append(d)
            
            print(f"    -> Retrieved {len(active_rems)} candidate(s).")

            # --- SEARCH LOGIC ---
            target_rems = []
            text_lower = clean_text.lower()
            
            # Sort by length to catch specific titles first
            active_rems.sort(key=lambda x: len(x.get("title", "")), reverse=True)
            
            print("    -> Attempting String Matching...")
            for r in active_rems:
                r_title = r.get("title", "").lower()
                # Check if database title exists inside user text
                if r_title and r_title in text_lower:
                    print(f"      * SUCCESS: Match found for '{r_title}'")
                    target_rems.append(r)
                    break # Single target match

            if not target_rems:
                print("    -> No string match. Falling back to NER tokens...")
                tokens = entities.get("reminders", []) + entities.get("tasks", []) + entities.get("events", [])
                print(f"      * Extracted Tokens: {tokens}")
                for token in tokens:
                    for r in active_rems:
                        if token == r["_doc_id"]:
                            print(f"      * Direct ID Match (Ambiguity Bypass): '{r.get('title')}'")
                            target_rems.append(r)
                            break
                        elif token.lower() in r.get("title", "").lower():
                            print(f"        -> Token Match: '{token}' -> '{r.get('title')}'")
                            target_rems.append(r)

            if not target_rems:
                # FINAL DIAGNOSTIC
                print("    -> ⚠️ RESOLUTION FAILED. Final Database Snapshot:")
                for r in active_rems:
                    print(f"       - Title: '{r.get('title')}' | Status: {r.get('status')}")
                raise ValueError("I couldn't identify which reminder you want to update.")

            # --- UPDATE LOGIC ---
            print("\n  [Step 2] Processing Update Fields...")
            update_data = {}
            raw_ts = entities.get("start_timestamp")
            
            if raw_ts:
                update_data["trigger_time"] = raw_ts
                update_data["status"] = "pending" # Reset if missed
                print(f"    -> Update: Rescheduling to {raw_ts}")

            if "standard" in text_lower:
                update_data["priority"] = "standard"
                print("    -> Update: Setting Priority to standard")
            elif "high" in text_lower or "urgent" in text_lower:
                update_data["priority"] = "high"
                print("    -> Update: Setting Priority to high")

            if not update_data:
                raise ValueError("Found the reminder, but I'm not sure what you wanted to change.")

            print(f"\n  [Step 3] Committing Update: {update_data}")
            for r in target_rems:
                rem_ref.document(r["_doc_id"]).update(update_data)
            
            print(">>> [UpdateReminder] SUCCESS <<<\n" + "="*60)
            return {"status": "success", "message": f"Updated the '{target_rems[0]['title']}' reminder."}

        except Exception as e:
            print(f"  ❌ ERROR in UpdateReminder: {str(e)}")
            raise

    def handle_delete_reminder(self, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print("\n" + "="*60)
        print(">>> [DeleteReminder] EXECUTING HANDLER <<<")
        print("="*60)
        clean_text = raw_text.strip().strip('"').strip("'")
        
        try:
            rem_ref = self.db.collection("users").document(user_id).collection("reminders")
            
            print("\n  [Step 1] Loading All Reminders for Search...")
            all_rems = [doc.to_dict() | {"_doc_id": doc.id} for doc in rem_ref.stream()]
            print(f"    -> Found {len(all_rems)} total reminder(s).")

            target_rems = []
            text_lower = clean_text.lower()
            all_rems.sort(key=lambda x: len(x.get("title", "")), reverse=True)

            for r in all_rems:
                r_title = r.get("title", "").lower()
                if r_title and r_title in text_lower:
                    print(f"    -> String Match Found: '{r_title}'")
                    target_rems.append(r)
                    break

            if not target_rems:
                print("    -> String match failed. Checking Tokens...")
                tokens = entities.get("reminders", []) + entities.get("tasks", []) + entities.get("events", [])
                for token in tokens:
                    for r in all_rems:
                        if token == r["_doc_id"]:
                            print(f"      * Direct ID Match (Ambiguity Bypass): '{r.get('title')}'")
                            target_rems.append(r)
                            break
                        elif token.lower() in r.get("title", "").lower():
                            print(f"      * Token Match: '{token}' -> '{r.get('title')}'")
                            target_rems.append(r)

            if not target_rems:
                raise ValueError("I couldn't find that reminder to delete.")

            print("\n  [Step 2] Executing Deletion...")
            for r in target_rems:
                rem_ref.document(r["_doc_id"]).delete()
                print(f"    -> ✅ Deleted: '{r.get('title')}'")

            print(">>> [DeleteReminder] SUCCESS <<<\n" + "="*60)
            return {"status": "success", "message": f"Deleted the '{target_rems[0]['title']}' reminder."}

        except Exception as e:
            print(f"  ❌ ERROR in DeleteReminder: {str(e)}")
            raise


                

    # --- PLACEHOLDER HANDLERS ---
    def _placeholder_handler(self, intent: str, entities: dict, user_id: str, raw_text: str = "") -> dict:
        print(f"[{intent}] Placeholder called with entities: {entities}")
        return {
            "status": "placeholder",
            "message": f"[PLACEHOLDER] {intent} not yet implemented. Entities: {entities}",
            "data": {}
        }



    def handle_set_preferences(self, entities: dict, user_id: str, raw_text: str = "") -> dict: return self._placeholder_handler("SET_PREFERENCES", entities, user_id, raw_text)

    def get_intent_map(self) -> dict:
        return {
            "CREATE_EVENT":      self.handle_create_event,
            "UPDATE_EVENT":      self.handle_update_event,
            "DELETE_EVENT":      self.handle_delete_event,
            "QUERY_EVENT":       self.handle_query_event,
            "FIND_FREE_TIME":    self.handle_find_free_time,
            "SUGGEST_TIME":      self.handle_suggest_time,
            "CHANGE_RECURRENCE": self.handle_change_recurrence,
            "CREATE_TASK":       self.handle_create_task,
            "UPDATE_TASK":       self.handle_update_task,
            "DELETE_TASK":       self.handle_delete_task,
            "COMPLETE_TASK":     self.handle_complete_task,
            "QUERY_TASK":        self.handle_query_task,
            "SET_REMINDER":      self.handle_set_reminder,
            "UPDATE_REMINDER":   self.handle_update_reminder,
            "DELETE_REMINDER":   self.handle_delete_reminder,
            "SET_PREFERENCES":   self.handle_set_preferences,
        }