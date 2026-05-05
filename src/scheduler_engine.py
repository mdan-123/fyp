import os
import json
import re
import time
import datetime as dt
from datetime import datetime, timezone
import zoneinfo
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from google import genai
from google.genai import types
import dateparser

class SchedulerNLU:
    def __init__(self, intent_path: str, ner_path: str, gemini_api_key: str = None, confidence_threshold: float = 0.85):
        self.confidence_threshold = confidence_threshold
        
        print(f"Loading Intent Model from {intent_path}...")
        self.tokenizer = AutoTokenizer.from_pretrained(intent_path)
        self.intent_model = AutoModelForSequenceClassification.from_pretrained(intent_path)
        self.intent_labels = list(self.intent_model.config.id2label.values())
        
        print(f"Loading NER Model from {ner_path}...")
        self.ner_pipe = pipeline("token-classification", model=ner_path, aggregation_strategy="simple")
        
        # Gemini is optional — only used when local models lack confidence
        self.gemini_client = None
        if gemini_api_key:
            self.gemini_client = genai.Client(api_key=gemini_api_key)

        # Pre-compiled regex for catching time expressions the NER model may miss
        self._time_regex = re.compile(
            r'\b(\d{1,2}(:\d{2})?\s*(am|pm)|noon|midnight|'
            r'morning|afternoon|evening|tonight|'
            r'\d{1,2}\s*(hour|minute|min)s?\s*(before|after|later)|'
            r'(half|quarter)\s*(past|to)\s*\d{1,2})\b',
            re.IGNORECASE
        )

    def format_entities(self, raw_ner, text):
        entities = {
            "dates": [], "times": [], "people": [], "events": [], "tasks": [],
            "locations": [], "durations": [], "recurrence": [], "reminders": [],
            "preferences": [], "conditions": []
        }

        # Merge adjacent tokens of the same type into single spans using character offsets
        merged_ner = []
        for ent in raw_ner:
            label = ent.get('entity_group', ent.get('entity', '')).lower().replace('b-', '').replace('i-', '')
            
            if 'start' not in ent or 'end' not in ent:
                word = ent.get('word', '').replace('##', '').replace('Ġ', '').strip()
                if label == 'date': entities["dates"].append(word)
                elif label == 'time': entities["times"].append(word)
                elif label == 'person': entities["people"].append(word)
                elif label == 'event': entities["events"].append(word)
                elif label == 'task': entities["tasks"].append(word)
                elif label == 'location': entities["locations"].append(word)
                elif label == 'duration': entities["durations"].append(word)
                elif label == 'recurrence': entities["recurrence"].append(word)
                elif label == 'reminder': entities["reminders"].append(word)
                elif label == 'preference': entities["preferences"].append(word)
                elif label == 'condition': entities["conditions"].append(word)
                continue

            start = ent['start']
            end = ent['end']
            
            if merged_ner and merged_ner[-1]['label'] == label and (start - merged_ner[-1]['end'] <= 1):
                merged_ner[-1]['end'] = end  # extend the previous span
            else:
                merged_ner.append({'label': label, 'start': start, 'end': end})
                
        for ent in merged_ner:
            word = text[ent['start']:ent['end']].strip()
            label = ent['label']
            
            if label == 'date': entities["dates"].append(word)
            elif label == 'time': entities["times"].append(word)
            elif label == 'person': entities["people"].append(word)
            elif label == 'event': entities["events"].append(word)
            elif label == 'task': entities["tasks"].append(word)
            elif label == 'location': entities["locations"].append(word)
            elif label == 'duration': entities["durations"].append(word)
            elif label == 'recurrence': entities["recurrence"].append(word)
            elif label == 'reminder': entities["reminders"].append(word)
            elif label == 'preference': entities["preferences"].append(word)
            elif label == 'condition': entities["conditions"].append(word)
            
        return entities

    def normalise_time(self, entities, user_timezone="UTC"):
        """Convert extracted date/time entities to a UTC ISO string, anchored to the user's timezone."""
        try:
            tz = zoneinfo.ZoneInfo(user_timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            tz = zoneinfo.ZoneInfo("UTC")
            user_timezone = "UTC"

        dates = entities.get("dates", [])
        times = entities.get("times", [])

        # Fall back to sensible defaults when no date/time was extracted
        date_str = dates[0] if dates else "today"
        time_str = times[0] if times else "09:00"

        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        date_lower = date_str.lower().strip()

        # Bare weekday name — resolve to the next upcoming occurrence
        if date_lower in weekdays:
            target_day = weekdays.index(date_lower)
            today = dt.datetime.now(tz)
            today_weekday = today.weekday()
            days_until = (target_day - today_weekday) % 7
            if days_until == 0:
                days_until = 7  # "monday" when today is monday means next monday
            parsed_date = today + dt.timedelta(days=days_until)
        else:
            # "next monday" / "this friday" style phrases
            match = re.match(r'(next|this)\s+(' + '|'.join(weekdays) + r')', date_lower)
            if match:
                prefix, weekday = match.groups()
                target_day = weekdays.index(weekday)
                today = dt.datetime.now(tz)
                today_weekday = today.weekday()
                days_until = (target_day - today_weekday) % 7
                if prefix == 'next' and days_until == 0:
                    days_until = 7
                parsed_date = today + dt.timedelta(days=days_until)
            else:
                combined = f"{date_str} at {time_str}"
                now_local = dt.datetime.now(tz)
                parsed = dateparser.parse(
                    combined,
                    settings={
                        'TIMEZONE': user_timezone,
                        'TO_TIMEZONE': 'UTC',
                        'RETURN_AS_TIMEZONE_AWARE': True,
                        'DATE_ORDER': 'DMY',
                        'RELATIVE_BASE': now_local,
                        'PREFER_DATES_FROM': 'future'
                    }
                )
                if parsed:
                    return parsed.isoformat().replace("+00:00", "Z")
                return None
        
        time_part = dateparser.parse(
            time_str,
            settings={'TIMEZONE': user_timezone}
        )
        if time_part:
            parsed_datetime = parsed_date.replace(
                hour=time_part.hour,
                minute=time_part.minute,
                second=0,
                microsecond=0
            )
            utc_datetime = parsed_datetime.astimezone(timezone.utc)
            return utc_datetime.isoformat().replace("+00:00", "Z")
        
        return None

    def _extract_time_entities_regex(self, text: str) -> dict:
        extracted = {"times": [], "dates": [], "durations": []}

        time_pat = re.compile(
            r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midnight)\b',
            re.IGNORECASE
        )
        extracted["times"] = [m.group().strip() for m in time_pat.finditer(text)]

        date_pat = re.compile(
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday'
            r'|today|tomorrow|yesterday'
            r'|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)'
            r'|\d{1,2}(?:st|nd|rd|th)?\s+'
            r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?'
            r'|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
            r'(?:\s+\d{4})?)\b',
            re.IGNORECASE
        )
        extracted["dates"] = [m.group().strip() for m in date_pat.finditer(text)]

        dur_pat = re.compile(
            r'\b(\d+\s*(?:hours?|hrs?|minutes?|mins?)'
            r'(?:\s+(?:and\s+)?\d+\s*(?:minutes?|mins?))?'
            r'|half\s+(?:an?\s+)?hour'
            r'|quarter\s+(?:of\s+an?\s+)?hour)\b',
            re.IGNORECASE
        )
        extracted["durations"] = [m.group().strip() for m in dur_pat.finditer(text)]

        return extracted

    def calculate_end_time(self, start_iso, entities, user_timezone="UTC"):
        """Derive an end timestamp from a second time entity, a duration, or a default 1-hour window."""
        if not start_iso:
            return None
            
        start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        
        times = entities.get("times", [])
        durations = entities.get("durations", [])

        # Prefer an explicit end time (second time entity) over a duration
        if len(times) > 1:
            dates = entities.get("dates", [])
            date_str = dates[0] if dates else "today"
            
            end_combined = f"{date_str} at {times[1]}"
            
            try:
                now_local = dt.datetime.now(zoneinfo.ZoneInfo(user_timezone))
            except zoneinfo.ZoneInfoNotFoundError:
                now_local = dt.datetime.now(timezone.utc)
                user_timezone = "UTC"
                
            end_parsed = dateparser.parse(
                end_combined, 
                settings={
                    'TIMEZONE': user_timezone, 
                    'TO_TIMEZONE': 'UTC',
                    'RETURN_AS_TIMEZONE_AWARE': True, 
                    'DATE_ORDER': 'DMY',
                    'RELATIVE_BASE': now_local,
                    'PREFER_DATES_FROM': 'future'
                }
            )
            
            if end_parsed:
                # If end parsed as earlier than start, it's likely an am/pm ambiguity — nudge forward
                if end_parsed <= start_dt:
                    end_parsed += dt.timedelta(hours=12)
                    if end_parsed <= start_dt:
                        end_parsed += dt.timedelta(hours=12)
                return end_parsed.isoformat().replace("+00:00", "Z")

        if durations and durations[0]:
            duration_str = durations[0].lower()
            minutes = 60  # default if parsing fails
            
            if "min" in duration_str:
                nums = re.findall(r'\d+', duration_str)
                if nums: minutes = int(nums[0])
            elif "hour" in duration_str or "hr" in duration_str:
                nums = re.findall(r'\d+', duration_str)
                if nums: minutes = int(nums[0]) * 60
                elif "half" in duration_str: minutes = 30
                
            end_dt = start_dt + dt.timedelta(minutes=minutes)
            return end_dt.isoformat().replace("+00:00", "Z")
            
        end_dt = start_dt + dt.timedelta(hours=1)
        return end_dt.isoformat().replace("+00:00", "Z")


    def llm_fallback(self, user_input: str, reason: str, user_context: str = "", chat_history: str = "", user_timezone: str = "UTC"):
        """Escalate to Gemini when local models can't produce a confident result."""
        if not self.gemini_client:
            print("[LLM Escalation] Triggered but no Gemini API key provided.")
            return None

        print(f"[LLM Escalation] Reason: {reason} | Timezone: {user_timezone}")
        try:
            today_dt = datetime.now(zoneinfo.ZoneInfo(user_timezone))
        except zoneinfo.ZoneInfoNotFoundError:
            today_dt = datetime.now(zoneinfo.ZoneInfo("UTC"))
            
        today_str = today_dt.strftime('%A, %Y-%m-%d')
        
        prompt = f"""
        Context: Today is {today_str}.
        
        USER'S CURRENT SCHEDULE & TASKS:
        {user_context if user_context else "No active calendar context provided."}

        RECENT CONVERSATION HISTORY (use this to resolve pronouns and references like "it", "that time", "the one you suggested"):
        {chat_history if chat_history else "No prior conversation."}

        Task: Intent classification and Entity extraction for the LATEST message: "{user_input}"
        Intent Options: {self.intent_labels}
        
        Rules:
        - CRITICAL EVENT RULE: Words like "lunch", "dinner", "breakfast", "gym", "workout", "appointment", or "meeting" are EVENT TITLES. You MUST put them in the "events" array, NEVER PUT THESE WORDS IN THE TIME ARRAY!!!!
        - CRITICAL BULK RULE: If the user wants to move "everything" or "all" from a specific day, you MUST look at the USER'S CURRENT SCHEDULE above and list the EXACT titles of EVERY SINGLE event and task found on that day inside the "events" and "tasks" arrays. Do not summarize or skip any.
        - CRITICAL MOVE RULE: When moving items "from [day] to [day]", extract the origin day (e.g. "friday") into "source_date" and the target day (e.g. "sunday") into the "dates" array.
        - CRITICAL CONTEXT RULE: Never invent names. Use the exact titles from the schedule provided. If a title is "Untitled Event", list it as many times as it appears on that day.
        - CRITICAL EXTRACT RULE: Extract the exact words used for dates and times. Do not convert them to absolute YYYY-MM-DD dates.
        - CRITICAL REFERENCE RULE: If the user says "it", "that", "the one you suggested", "that time" — look at the RECENT CONVERSATION HISTORY above to resolve what they are referring to before classifying the intent.
        - CRITICAL CHAT RULE: If the user refers to something outside of calendar events, such as 'give me study tips', you must handle it appropriately and return a relevant response in chat_response you may leave intent and entities empty.

        Return ONLY valid JSON:
        {{
            "intents": ["UPDATE_EVENT"],
            "entities": {{
                "source_date": "friday",
                "dates": ["sunday"],
                "times": [],
                "events": ["Untitled Event", "Untitled Event", "meeting"],
                "tasks": [],
                "locations": [],
                "durations": [],
                "recurrence": [],
                "reminders": [],
                "preferences": [],
                "conditions": []
            }},
            "chat_response": ""
        }}
        """

        # Retry with exponential backoff in case of transient API errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                data = json.loads(response.text)
                data["source"] = "LLM_Escalation"
                data["text"]   = user_input
                return data
            except Exception as e:
                print(f"[LLM Escalation Error] {e}")
                time.sleep(2 ** attempt)
        return None

    def process(self, text: str, user_context: str = "", chat_history: str = "", user_timezone: str = "UTC"):
        """Run the full NLU pipeline: intent classification → NER → timestamp resolution."""
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            logits = self.intent_model(**inputs).logits

        # Multi-label sigmoid — collect every intent that clears the confidence threshold
        probs = torch.sigmoid(logits).squeeze().cpu().numpy()
        if probs.ndim == 0:
            probs = np.array([probs])

        predicted_intents = []
        intent_scores = {}
        for idx, prob in enumerate(probs):
            if prob >= self.confidence_threshold:
                intent_label = self.intent_model.config.id2label[idx]
                predicted_intents.append(intent_label)
                intent_scores[intent_label] = float(prob)

        raw_ner = self.ner_pipe(text)
        entities = self.format_entities(raw_ner, text)

        # Fill gaps in NER output with regex-extracted time/date/duration spans
        regex_extras = self._extract_time_entities_regex(text)
        for field in ("times", "dates", "durations"):
            if not entities[field] and regex_extras[field]:
                entities[field] = regex_extras[field]

        ent_count = sum(len(v) for v in entities.values() if isinstance(v, list))

        # Hard override: trigger phrase is unambiguous enough to bypass the classifier
        if "remind me" in text.lower() or "set a reminder" in text.lower():
            if "SET_REMINDER" not in predicted_intents:
                predicted_intents.append("SET_REMINDER")
                print("[Intent Override] Forced SET_REMINDER based on trigger phrase.")

        reason = None
        # These intents are valid even with no extracted entities
        entity_optional_intents = {"QUERY_EVENT", "QUERY_TASK", "FIND_FREE_TIME"}

        if not predicted_intents: 
            reason = "No intents reached the confidence threshold."
        elif ent_count == 0 and not any(i in entity_optional_intents for i in predicted_intents):
            reason = f"Intents detected ({', '.join(predicted_intents)}) but zero entities found."
        else:
            if any(i in ["UPDATE_EVENT", "DELETE_EVENT"] for i in predicted_intents):
                if not entities.get("events"):
                    reason = "Event modification intended, but NER failed to extract the target event title."
            
            elif any(i in ["UPDATE_TASK", "DELETE_TASK", "COMPLETE_TASK"] for i in predicted_intents):
                if not entities.get("tasks") and not entities.get("events"):
                    reason = "Task modification intended, but NER failed to extract the target task title."
            
            elif "SET_REMINDER" in predicted_intents:
                if not entities.get("dates") and not entities.get("times"):
                    if not self._time_regex.search(text):
                        reason = "SET_REMINDER intended, but no date or time was extracted for the alert."

        if reason:
            fallback = self.llm_fallback(text, reason, user_context, chat_history, user_timezone)
            print(f"[LLM Fallback] Reason: {reason}")
            if fallback:
                # Resolve the origin day for move/bulk operations into a UTC timestamp
                source_date = fallback["entities"].get("source_date")
                if source_date:
                    source_ts = self.normalise_time(
                        {"dates": [source_date], "times": ["00:00"]},
                        user_timezone=user_timezone
                    )
                    if source_ts:
                        fallback["entities"]["source_timestamp"] = source_ts
                        print(f"[LLM Fallback] source_timestamp resolved: {source_ts}")

                fallback["entities"]["start_timestamp"] = self.normalise_time(fallback["entities"], user_timezone=user_timezone)
                fallback["entities"]["end_timestamp"] = self.calculate_end_time(
                    fallback["entities"]["start_timestamp"],
                    fallback["entities"],
                    user_timezone=user_timezone
                )
                return fallback

        start_iso = self.normalise_time(entities, user_timezone=user_timezone)
        entities["start_timestamp"] = start_iso
        entities["end_timestamp"] = self.calculate_end_time(start_iso, entities, user_timezone=user_timezone)
        
        return {
            "source": "Local_ModernBERT",
            "intents": predicted_intents,
            "confidence_scores": intent_scores,
            "entities": entities,
            "text": text
        }