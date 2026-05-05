import os
import json
import re
from google import genai
from google.genai import types

class ConstraintParser:
    def __init__(self, API_KEY):
        if not API_KEY:
            print("⚠️ WARNING: API Key is missing. Set GEMINI_API_KEY env var.")
            return

        self.client = genai.Client(api_key=API_KEY)
        self.model = "gemini-2.5-pro"

        # list all available models
        try:
            models = self.client.models.list()
            print("✅ Connected to Gemini API. Available models:")
            for m in models:
                print(f"   - {m.name}")
        except Exception as e:
            print(f"❌ Failed to connect to Gemini API: {e}")

    def _clean_response(self, text):
        """Removes Markdown backticks to ensure valid JSON."""
        if not text: return ""
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
        return text.strip()

    def parse(self, user_text):
        print(f'   [LLM] Parsing constraint: "{user_text}"...')

        prompt = f"""
        You are a Scheduling Logic Converter. 
        Translate natural language preferences into a structured JSON format for a Constraint Satisfaction Algorithm.
        If the user specifies multiple constraints in one sentence, return an array of JSON objects.

        ### OUTPUT FORMAT:
        {{
            "category": "DEEP_WORK | SHALLOW_WORK | MEETING | WORKOUT | SOCIAL | LEISURE | TRAVEL | MEAL | ALL",
            "type": "WINDOW | BUFFER | DURATION",
            "params": {{ 
                "start": number (0-24), 
                "end": number (0-24),
                "minutes": number (for buffers)
            }},
            "is_hard": boolean, 
            "is_exclusive": boolean,
            "is_routine": boolean,
            "duration": number | null (minutes),
            "weight": 1-10,
            "reasoning": "Brief explanation"
        }}

        ### LOGIC RULES:
        1. "No X after Y" -> WINDOW {{ "start": 0, "end": Y }}
        2. "No X before Y" -> WINDOW {{ "start": Y, "end": 24 }}
        3. "I need a gap/break after X" -> BUFFER {{ "minutes": 15 }}
        4. "Only X is allowed during Y" -> is_exclusive: true
        5. "Every day I do X for [duration] at [time]" -> is_routine: true, duration: [minutes]
        
        ### WEIGHTING & CERTAINTY:
        - If the user sounds certain ("Never", "Must", "Strictly", "Every day"), set is_hard: true and weight: 10.
        - If the user sounds suggestive ("Prefer", "Ideally", "I'd like"), set is_hard: false and assign a weight between 1-9 based on their emphasis.

        ### EXAMPLES:
        "Ideally, I'd like to gym for 45 minutes sometime between 6am and 9am."
        -> category: WORKOUT, type: WINDOW, params: {{"start": 6, "end": 9}}, is_routine: true, duration: 45, is_exclusive: false, is_hard: false, weight: 6

        "Strictly no meetings after 5pm."
        -> category: MEETING, type: WINDOW, params: {{"start": 0, "end": 17}}, is_routine: false, is_exclusive: false, is_hard: true, weight: 10

        "I need a 15 minute breather after any meeting."
        -> category: MEETING, type: BUFFER, params: {{"minutes": 15}}, is_routine: false, is_exclusive: false, is_hard: true, weight: 10

        "Nothing but deep work between 9am and 12pm."
        -> category: DEEP_WORK, type: WINDOW, params: {{"start": 9, "end": 12}}, is_routine: false, is_exclusive: true, is_hard: true, weight: 10

        ### USER INPUT:
        "{user_text}"
        
        Return ONLY JSON.
        """
        
        response = None
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            clean_text = self._clean_response(response.text)
            return json.loads(clean_text)
        except Exception as e:
            err_str = str(e).lower()
            if "resource_exhausted" in err_str or "429" in err_str or "quota" in err_str:
                raise  # let the caller (e.g. pref_queue) handle retries
            print(f"❌ Error: {e}")
            if response is not None and hasattr(response, 'text'):
                print(f"   Raw Output: {response.text}")
            return None