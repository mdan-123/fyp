import os
import json
import re
from google import genai
from google.genai import types

API_KEY = "AIzaSyDxuzF7HX6k_sSEk218ih74-fBXClD5kHM" 

class DurationEstimator:
    def __init__(self):
        key = API_KEY if API_KEY != "BLANK" else os.environ.get("GEMINI_API_KEY")
        if not key:
            print("WARNING: API Key is missing. Set GEMINI_API_KEY env var.")
            self.client = None
        else:
            self.client = genai.Client(api_key=key)
            
        self.model = "gemini-2.0-flash"

    def _clean_response(self, text):
        if not text: return ""
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
        return text.strip()

    def estimate(self, title: str, description: str = "") -> int:
        if not self.client:
            print("Client not initialised. Defaulting to 60 minutes.")
            return 60

        print(f'[LLM] Estimating duration for: "{title}"...')

        prompt = f"""
        You are an expert productivity and scheduling assistant. 
        Your job is to estimate how long a given task will realistically take to complete.

        Analyse the task title and description, and output the estimated duration in minutes.
        Think about average human speed, context switching, and realistic effort.
        Round to the nearest 15 minutes (e.g., 15, 30, 45, 60, 90, 120).
        If it's a very quick task, you can return 5 or 10.
        If the prompt is vague or you cannot determine the time, default to 60.

        ### OUTPUT FORMAT:
        You must return strictly valid JSON in this exact format, with no other text:
        {{
            "estimated_minutes": number
        }}

        ### TASK DETAILS:
        Title: "{title}"
        Description: "{description}"
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            clean_text = self._clean_response(response.text)
            data = json.loads(clean_text)
            return data.get("estimated_minutes", 60)
            
        except Exception as e:
            print(f"Error during estimation: {e}")
            return 60

if __name__ == "__main__":
    estimator = DurationEstimator()
    test_tasks = [
        {"title": "Buy groceries", "desc": "Weekly shop for a family of 4"},
        {"title": "Reply to emails", "desc": ""},
        {"title": "Write quarterly report", "desc": "Need to pull analytics from Q2 and write a 5 page summary."}
    ]
    
    print("--- TESTING DURATION ESTIMATOR ---")
    for t in test_tasks:
        mins = estimator.estimate(t["title"], t["desc"])
        print(f"Task: {t['title']} -> Estimated: {mins} mins")