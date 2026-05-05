import os
from google import genai
from google.genai import types


from dotenv import load_dotenv
load_dotenv("./.env.local")

API_KEY = os.getenv("GEMINI_API_KEY")


def categorise_event(
    title: str, 
    description: str = "", 
    attendees_count: int = 0, 
    has_video_link: bool = False
) -> str:
    """
    Categorises a calendar event using a three-tier hybrid system:
    1. Metadata Heuristics
    2. Comprehensive Keyword Dictionary (Student & Professional)
    3. LLM Fallback (Gemini 2.0 Flash)
    """
    
    # Tier 1: Metadata Heuristics
    # If it has a Zoom/Meet link or multiple attendees, it is almost certainly a meeting.
    if has_video_link or attendees_count > 1:
        return "MEETING"

    # Tier 2: Keyword Dictionary
    title_lower = title.lower().strip() if title else ""
    
    keyword_map = {
        # STUDENT & ACADEMIC (MEETINGS)
        "lecture": "MEETING",
        "seminar": "MEETING",
        "tutorial": "MEETING",
        "office hours": "MEETING",
        "study group": "MEETING",
        "group project": "MEETING",
        "advisor meeting": "MEETING",
        "supervision": "MEETING",
        "class": "MEETING",
        "workshop": "MEETING",
        "lab class": "MEETING",
        "demo session": "MEETING",
        "viva": "MEETING",
        "defence": "MEETING",
        "defense": "MEETING",
        "progress meeting": "MEETING",
        "academic advising": "MEETING",
        "committee meeting": "MEETING",
        "panel": "MEETING",
        "orientation": "MEETING",

        # STUDENT & ACADEMIC (DEEP WORK)
        "revision": "DEEP_WORK",
        "studying": "DEEP_WORK",
        "study session": "DEEP_WORK",
        "exam": "DEEP_WORK",
        "midterm": "DEEP_WORK",
        "final": "DEEP_WORK",
        "assignment": "DEEP_WORK",
        "essay": "DEEP_WORK",
        "thesis": "DEEP_WORK",
        "dissertation": "DEEP_WORK",
        "lab session": "DEEP_WORK",
        "research": "DEEP_WORK",
        "coursework": "DEEP_WORK",
        "reading week": "DEEP_WORK",
        "mock exam": "DEEP_WORK",
        "practice exam": "DEEP_WORK",
        "literature review": "DEEP_WORK",
        "problem set": "DEEP_WORK",
        "note taking": "DEEP_WORK",
        "notetaking": "DEEP_WORK",
        "project work": "DEEP_WORK",
        "independent study": "DEEP_WORK",
        "past papers": "DEEP_WORK",
        "flashcards": "DEEP_WORK",

        # PROFESSIONAL (MEETING)
        "sync": "MEETING",
        "1:1": "MEETING",
        "catch up": "MEETING",
        "catch-up": "MEETING",
        "standup": "MEETING",
        "stand-up": "MEETING",
        "huddle": "MEETING",
        "review": "MEETING",
        "interview": "MEETING",
        "all hands": "MEETING",
        "all-hands": "MEETING",
        "brainstorming": "MEETING",
        "touchbase": "MEETING",
        "touch-base": "MEETING",
        "discussion": "MEETING",
        "one-on-one": "MEETING",
        "1on1": "MEETING",
        "board meeting": "MEETING",
        "client call": "MEETING",
        "kickoff": "MEETING",
        "kick-off": "MEETING",
        "retrospective": "MEETING",
        "retro": "MEETING",
        "debrief": "MEETING",
        "onboarding": "MEETING",
        "town hall": "MEETING",
        "webinar": "MEETING",
        "conference call": "MEETING",
        "video call": "MEETING",
        "roundtable": "MEETING",
        "pitch": "MEETING",
        "stakeholder": "MEETING",
        "scrum": "MEETING",
        "team meeting": "MEETING",
        "project meeting": "MEETING",
        "call with": "MEETING",
        "meeting with": "MEETING",
        "presentation": "MEETING",

        # PROFESSIONAL (DEEP WORK)
        "coding": "DEEP_WORK",
        "programming": "DEEP_WORK",
        "writing": "DEEP_WORK",
        "drafting": "DEEP_WORK",
        "strategising": "DEEP_WORK",
        "strategy": "DEEP_WORK",
        "planning": "DEEP_WORK",
        "deep work": "DEEP_WORK",
        "focus time": "DEEP_WORK",
        "designing": "DEEP_WORK",
        "architecture": "DEEP_WORK",
        "analysis": "DEEP_WORK",
        "report": "DEEP_WORK",
        "editing": "DEEP_WORK",
        "code review": "DEEP_WORK",
        "sprint planning": "DEEP_WORK",
        "development": "DEEP_WORK",
        "debugging": "DEEP_WORK",
        "prototyping": "DEEP_WORK",
        "modelling": "DEEP_WORK",
        "modeling": "DEEP_WORK",
        "wireframing": "DEEP_WORK",
        "data analysis": "DEEP_WORK",
        "deep dive": "DEEP_WORK",
        "focus block": "DEEP_WORK",
        "audit": "DEEP_WORK",
        "testing": "DEEP_WORK",
        "unit test": "DEEP_WORK",
        "summarising": "DEEP_WORK",
        "summarizing": "DEEP_WORK",

        # SHALLOW WORK & ADMIN
        "emails": "SHALLOW_WORK",
        "inbox": "SHALLOW_WORK",
        "admin": "SHALLOW_WORK",
        "paperwork": "SHALLOW_WORK",
        "filing": "SHALLOW_WORK",
        "expenses": "SHALLOW_WORK",
        "invoice": "SHALLOW_WORK",
        "scheduling": "SHALLOW_WORK",
        "triage": "SHALLOW_WORK",
        "slack": "SHALLOW_WORK",
        "messages": "SHALLOW_WORK",
        "quick tasks": "SHALLOW_WORK",
        "follow up": "SHALLOW_WORK",
        "course registration": "SHALLOW_WORK",
        "enrolment": "SHALLOW_WORK",
        "enrollment": "SHALLOW_WORK",
        "notifications": "SHALLOW_WORK",
        "form filling": "SHALLOW_WORK",
        "uploading": "SHALLOW_WORK",
        "respond": "SHALLOW_WORK",
        "check-in": "SHALLOW_WORK",
        "to-do list": "SHALLOW_WORK",
        "checklist": "SHALLOW_WORK",
        "organising": "SHALLOW_WORK",
        "organizing": "SHALLOW_WORK",
        "booking": "SHALLOW_WORK",
        "reservation": "SHALLOW_WORK",
        "confirmation": "SHALLOW_WORK",
        "renewal": "SHALLOW_WORK",
        "survey": "SHALLOW_WORK",
        "feedback form": "SHALLOW_WORK",
        "processing": "SHALLOW_WORK",
        "sorting": "SHALLOW_WORK",
        "receipts": "SHALLOW_WORK",

        # WORKOUT & SPORTS
        "gym": "WORKOUT",
        "workout": "WORKOUT",
        "run": "WORKOUT",
        "running": "WORKOUT",
        "yoga": "WORKOUT",
        "pilates": "WORKOUT",
        "cycling": "WORKOUT",
        "spin class": "WORKOUT",
        "weightlifting": "WORKOUT",
        "lifting": "WORKOUT",
        "swim": "WORKOUT",
        "swimming": "WORKOUT",
        "tennis": "WORKOUT",
        "squash": "WORKOUT",
        "football": "WORKOUT",
        "5-a-side": "WORKOUT",
        "pt session": "WORKOUT",
        "personal training": "WORKOUT",
        "intramural": "WORKOUT",
        "sports practice": "WORKOUT",
        "hike": "WORKOUT",
        "hiking": "WORKOUT",
        "jogging": "WORKOUT",
        "jog": "WORKOUT",
        "hiit": "WORKOUT",
        "crossfit": "WORKOUT",
        "boxing": "WORKOUT",
        "kickboxing": "WORKOUT",
        "martial arts": "WORKOUT",
        "basketball": "WORKOUT",
        "volleyball": "WORKOUT",
        "badminton": "WORKOUT",
        "golf": "WORKOUT",
        "cricket": "WORKOUT",
        "rowing": "WORKOUT",
        "climbing": "WORKOUT",
        "bouldering": "WORKOUT",
        "walk": "WORKOUT",
        "walking": "WORKOUT",
        "stretching": "WORKOUT",
        "physio": "WORKOUT",
        "bootcamp": "WORKOUT",
        "boot camp": "WORKOUT",
        "training session": "WORKOUT",
        "track session": "WORKOUT",
        "rugby": "WORKOUT",

        # SOCIAL
        "drinks": "SOCIAL",
        "pub": "SOCIAL",
        "party": "SOCIAL",
        "dinner with": "SOCIAL",
        "lunch with": "SOCIAL",
        "coffee with": "SOCIAL",
        "birthday": "SOCIAL",
        "gathering": "SOCIAL",
        "networking": "SOCIAL",
        "meet up": "SOCIAL",
        "meetup": "SOCIAL",
        "celebration": "SOCIAL",
        "anniversary": "SOCIAL",
        "date night": "SOCIAL",
        "society meeting": "SOCIAL",
        "fraternity": "SOCIAL",
        "sorority": "SOCIAL",
        "club social": "SOCIAL",
        "pre-drinks": "SOCIAL",
        "night out": "SOCIAL",
        "bar": "SOCIAL",
        "karaoke": "SOCIAL",
        "bowling": "SOCIAL",
        "escape room": "SOCIAL",
        "house party": "SOCIAL",
        "bbq": "SOCIAL",
        "barbecue": "SOCIAL",
        "game night": "SOCIAL",
        "board games": "SOCIAL",
        "potluck": "SOCIAL",
        "farewell": "SOCIAL",
        "leaving do": "SOCIAL",
        "housewarming": "SOCIAL",
        "baby shower": "SOCIAL",
        "hen do": "SOCIAL",
        "stag do": "SOCIAL",
        "graduation": "SOCIAL",
        "wedding": "SOCIAL",
        "reunion": "SOCIAL",
        "catch up with": "SOCIAL",
        "brunch with": "SOCIAL",

        # LEISURE
        "cinema": "LEISURE",
        "movie": "LEISURE",
        "theatre": "LEISURE",
        "gig": "LEISURE",
        "concert": "LEISURE",
        "reading": "LEISURE",
        "gaming": "LEISURE",
        "playstation": "LEISURE",
        "xbox": "LEISURE",
        "spa": "LEISURE",
        "massage": "LEISURE",
        "holiday": "LEISURE",
        "vacation": "LEISURE",
        "day off": "LEISURE",
        "chilling": "LEISURE",
        "relaxing": "LEISURE",
        "museum": "LEISURE",
        "gallery": "LEISURE",
        "hobby": "LEISURE",
        "podcast": "LEISURE",
        "tv show": "LEISURE",
        "netflix": "LEISURE",
        "book club": "LEISURE",
        "art class": "LEISURE",
        "drawing": "LEISURE",
        "painting": "LEISURE",
        "photography": "LEISURE",
        "gardening": "LEISURE",
        "cooking class": "LEISURE",
        "crafting": "LEISURE",
        "knitting": "LEISURE",
        "journaling": "LEISURE",
        "meditation": "LEISURE",
        "mindfulness": "LEISURE",
        "nap": "LEISURE",
        "downtime": "LEISURE",
        "free time": "LEISURE",
        "staycation": "LEISURE",

        # TRAVEL
        "flight": "TRAVEL",
        "airport": "TRAVEL",
        "train": "TRAVEL",
        "tube": "TRAVEL",
        "underground": "TRAVEL",
        "commute": "TRAVEL",
        "drive": "TRAVEL",
        "driving": "TRAVEL",
        "travel": "TRAVEL",
        "bus": "TRAVEL",
        "coach": "TRAVEL",
        "transit": "TRAVEL",
        "boarding": "TRAVEL",
        "ferry": "TRAVEL",
        "taxi": "TRAVEL",
        "uber": "TRAVEL",
        "cab": "TRAVEL",
        "pickup": "TRAVEL",
        "departure": "TRAVEL",
        "arrival": "TRAVEL",
        "layover": "TRAVEL",
        "road trip": "TRAVEL",
        "cruise": "TRAVEL",
        "check in at": "TRAVEL",

        # MEAL
        "breakfast": "MEAL",
        "lunch": "MEAL",
        "dinner": "MEAL",
        "supper": "MEAL",
        "brunch": "MEAL",
        "snack": "MEAL",
        "eat": "MEAL",
        "cooking": "MEAL",
        "meal prep": "MEAL",
        "restaurant": "MEAL",
        "cafe": "MEAL",
        "dining": "MEAL",
        "takeaway": "MEAL",
        "takeout": "MEAL",
        "food delivery": "MEAL",
        "groceries": "MEAL",
        "grocery shopping": "MEAL",
        "tea break": "MEAL",
        "lunch break": "MEAL",
    }
    
    # Check for exact matches or keywords within the title
    for keyword, category in keyword_map.items():
        if keyword in title_lower:
            return category
            
    # Tier 3: LLM Classification Fallback using Gemini 2.0 Flash
    try:
        prompt = f"""
        You are an Event Categoriser for a student and professional productivity app. 
        Assign one of the following exact categories to the calendar event:
        DEEP_WORK, SHALLOW_WORK, MEETING, WORKOUT, SOCIAL, LEISURE, TRAVEL, MEAL
        
        Event Title: {title}
        Event Description: {description or 'None'}
        
        Rules:
        - If it involves other people, discussions, or lectures, it is a MEETING.
        - If it requires intense focus (coding, writing, strategy, studying, revision, exams), it is DEEP_WORK.
        - If it is admin, emails, course registration, or quick tasks, it is SHALLOW_WORK.
        - Return ONLY the category string. Nothing else.
        """
        
        # Initialise the client using the new google-genai SDK
        client = genai.Client(api_key=API_KEY)
        
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=10,
            )
        )
        
        if response.text:
            category = response.text.strip().upper()
        else:
            return "DEEP_WORK"
        
        valid_categories = [
            "DEEP_WORK", "SHALLOW_WORK", "MEETING", "WORKOUT", 
            "SOCIAL", "LEISURE", "TRAVEL", "MEAL"
        ]
        
        if category in valid_categories:
            return category
            
    except Exception as e:
        print(f"Gemini Categorisation failed: {e}")
        
    # Default fallback if all tiers fail
    return "MEETING"