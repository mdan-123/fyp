# ===============================================================
# create_deberta_multilabel_intent_v16.py
# Optimised for DeBERTa-v3 Multi-Label Sequence Classification
#
# Improvements in v16:
#   - Removed GREETING intent to focus model capacity on actionable 
#     scheduling requests and out-of-domain rejection.
#   - 14 core intents + 1 Negative class.
# ===============================================================

import json
import random
import re
import os
from tqdm import tqdm
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

try:
    import language_tool_python
    HAS_GRAMMAR_TOOL = True
except ImportError:
    HAS_GRAMMAR_TOOL = False

# --- CONFIGURATION ---
SCALE_FACTOR = 1.0
TRAIN_RATIO = 0.9
EVAL_PERCENTAGE = 0.10
USE_GRAMMAR_CHECK = True        
MAX_ATTEMPTS_PER_INTENT = 15000 

BASE_DISTRIBUTION = {
    "CREATE_EVENT": 2000,
    "UPDATE_EVENT": 1500,
    "DELETE_EVENT": 1200,
    "QUERY_EVENT": 1500,
    "ADD_PARTICIPANT": 800,
    "REMOVE_PARTICIPANT": 800,
    "NEGATIVE": 1000,  
    "FIND_FREE_TIME": 800,
    "SUGGEST_TIME": 800,
    "SET_REMINDER": 800,
    "CHANGE_RECURRENCE": 800,
    "SHARE_EVENT": 800,
    "DECLINE_EVENT": 800,
    "SET_PREFERENCES": 800
}

INTENT_DISTRIBUTION = {k: int(v * SCALE_FACTOR) for k, v in BASE_DISTRIBUTION.items()}

INTENT_LABELS = list(INTENT_DISTRIBUTION.keys())
LABEL_MAP = {intent: i for i, intent in enumerate(INTENT_LABELS)}
ID_TO_LABEL = {i: intent for intent, i in LABEL_MAP.items()}
NUM_LABELS = len(INTENT_LABELS)

DISTRACTORS = ["actually", "please", "maybe", "I think", "just", "honestly", "if possible", "mate", "cheers", "to be honest", "right", "anyway", "basically", "literally", "as it happens", "look,"]

if USE_GRAMMAR_CHECK and HAS_GRAMMAR_TOOL:
    print("Initialising grammar checker (en-GB)...")
    try:
        grammar_tool = language_tool_python.LanguageTool('en-GB')
    except Exception as e:
        print(f"Warning: Grammar checker failed: {e}")
        grammar_tool = None
else:
    grammar_tool = None

# ----------------------------
# 1. EXPANDED COMPONENT LISTS (UK English)
# ----------------------------

WORK_EVENTS = ["meeting", "conference call", "sync", "standup", "one-on-one", "client meeting", "team meeting", "strategy session", "appraisal", "planning session", "retrospective", "workshop", "training", "demo", "interview", "presentation", "audit", "briefing", "debrief", "board meeting", "budget review", "sales call", "all-hands", "sprint planning", "code review", "design critique", "town hall", "fire drill", "offsite", "onboarding session", "performance review", "client pitch"]
STUDENT_EVENTS = ["lecture", "study session", "lab", "tutorial", "seminar", "group project", "office hours", "exam", "quiz", "workshop", "thesis meeting", "dissertation defense", "research meeting", "library session", "study group", "revision session", "practical", "colloquium", "symposium", "conference", "field trip", "module registration", "careers fair", "mock exam", "freshers fair", "society meeting", "pre-drinks", "flat meeting", "graduation ceremony"]
PERSONAL_EVENTS = ["appointment", "lunch", "dinner", "coffee", "drinks", "gym session", "yoga class", "GP appointment", "dentist", "haircut", "meetup", "date", "party", "concert", "cinema trip", "shopping", "errands", "visitor", "family dinner", "pub quiz", "brunch", "hike", "barbecue", "wedding", "holiday", "MOT", "car service", "boiler service", "viewing", "parents' evening", "Sunday roast", "footy match", "rugby training", "pub lunch", "weekend away", "stag do", "hen do"]

PEOPLE = {
    "work": ["John", "Sarah", "Michael", "Emily", "David", "Lisa", "Robert", "Jennifer", "the team", "the client", "marketing", "engineering", "HR", "the board", "the CEO", "the CTO", "the product owner", "the scrum master", "managing director", "line manager", "stakeholders", "suppliers", "contractors"],
    "student": ["professor", "TA", "study group", "lab partner", "course mate", "advisor", "Dr. Smith", "Dr. Johnson", "the tutor", "research group", "my supervisor", "the dean", "flatmates", "my personal tutor", "the lecturer", "course rep", "study buddy"],
    "personal": ["friend", "family", "partner", "mum", "dad", "sibling", "colleague", "neighbour", "Alex", "Chris", "Taylor", "Jordan", "the lads", "the girls", "the missus", "the kids", "the mechanic", "the landlord", "the letting agent"]
}

LOCATIONS = {
    "work": ["conference room", "zoom", "teams", "meet", "office", "boardroom", "canteen", "breakout area", "remote", "client site", "HQ", "city centre", "Boardroom A", "the hot desk", "co-working space", "the regional office", "the branch"],
    "student": ["classroom", "lecture theatre", "lab", "library", "study room", "campus", "online", "student union", "the quad", "the science block", "halls", "the SU", "the library silent zone", "halls of residence", "the student village"],
    "personal": ["home", "restaurant", "cafe", "gym", "park", "shopping centre", "cinema", "pub", "outdoors", "virtual", "the beach", "the local", "the leisure centre", "the high street", "the surgery", "the barbers", "the salon", "the garage", "the allotment"]
}

STATIC_TIMES = ["9am", "10:30", "2pm", "3:15", "4:45", "11am", "1pm", "5pm", "6pm", "7pm", "8am", "09:00", "14:30", "23:00", "morning", "afternoon", "evening", "tonight", "tomorrow morning", "tomorrow afternoon", "tomorrow evening", "today", "tomorrow", "next week", "this Friday", "Monday", "next Monday", "in an hour", "ASAP", "soon", "later today", "end of day", "first thing", "midnight", "noon", "lunchtime", "dinnertime", "crack of dawn", "close of play", "COB", "EOD", "this coming bank holiday"]

RELATIVE_TIME_PATTERNS = ["next {weekday}", "this coming {weekday}", "a week from today", "the day after tomorrow", "two weeks from now", "next month", "the first week of {month}", "the last {weekday} of {month}", "in {num} days", "in {num} hours", "on {weekday} afternoon", "a fortnight today", "tomorrow fortnight"]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TIMEZONES = ["GMT", "BST", "CET", "EST", "PST", "IST"]

BASE_RECURRENCE = ["every Monday", "every Tuesday", "every Wednesday", "every Thursday", "every Friday", "every weekend", "daily", "weekly", "every other day", "every other week", "every other Wednesday", "biweekly", "monthly", "every month", "fortnightly"]
ADVANCED_RECURRENCE = ["every weekday", "every Monday and Wednesday", "every Tuesday and Thursday", "on weekdays except Wednesday", "every other week on Tuesday", "the first Monday of every month", "the last Friday of each month", "every 2 weeks", "every 3 days", "quarterly", "yearly", "annually"]

WORK_ACTIONS = ["review the proposal", "prepare the slides", "finalise the budget", "update the spreadsheet", "send the invoice", "draft the contract", "fix the bug", "deploy the update", "run the report", "clean the database", "organise the files", "respond to the client", "schedule the deployment", "test the feature", "write the documentation", "refactor the code", "approve the timesheets", "order the supplies", "book the travel", "sign off the deliverables"]
STUDENT_ACTIONS = ["read chapter 5", "complete the problem set", "draft the essay", "prepare for the exam", "review the lecture notes", "finish the lab report", "create the presentation", "study for the quiz", "outline the paper", "watch the recorded lecture", "do the reading", "annotate the article", "solve the equations", "memorise the vocabulary", "write the bibliography", "do revision"]
PERSONAL_ACTIONS = ["wash the car", "walk the dog", "buy groceries", "clean the bathroom", "water the plants", "take out the rubbish", "pick up the dry cleaning", "pay the bills", "book the flight", "renew the passport", "change the oil", "mow the lawn", "vacuum the carpet", "dust the shelves", "organise the wardrobe", "return the library books", "get a haircut", "post the parcel", "charge the phone", "feed the cat", "bleed the radiators"]

REMINDER_OFFSETS = ["10 minutes before", "30 minutes before", "1 hour before", "2 hours before", "at 9am", "in the morning", "the day before", "5 minutes before", "15 minutes before", "at the time of the event", "right when it starts", "half an hour before", "a quarter of an hour before"]
PREFERENCE_TYPES = ["working hours", "available hours", "focus time", "break time", "all-day event", "annual leave", "bank holiday", "out of office"]
HOUR_RANGES = ["9am to 5pm", "10am to 6pm", "8am to 4pm", "9:30 to 5:30", "flexible", "remote only", "in office"]
DURATIONS = ["30 mins", "an hour", "2 hours", "15 mins", "half a day", "a solid hour", "a couple of hours", "quarter of an hour", "the whole afternoon", "all day"]

NEGATIVE_QUERIES = [
    "What's the weather like in London today?", "Tell me a joke", "How old are you?", "What's the meaning of life?", 
    "Play some music", "Order a takeaway for me", "What time is it in Tokyo?", "Set an alarm for 7am", 
    "How do I make a proper cup of tea?", "What's on TV tonight?", "Translate hello to Spanish", 
    "Calculate 15% of 200", "Search for restaurants nearby", "Open YouTube", "What's the capital of France?", 
    "How tall is Mount Everest?", "Tell me a story", "Who won the Premier League?", "What's the stock price of Apple?", 
    "Define photosynthesis", "What's the square root of 144?", "Pull an all-nighter for the history paper", 
    "Cram for the chemistry test", "Clean the whiteboard after the session", "Setup the projector in room A", 
    "Organise the shared drive", "Get the keys", "Bring the umbrella", "Charge the phone", 
    "What's the best route to work?", "How's the traffic on the M25?", "What's the score of the match?", 
    "Book a flight to Paris", "Reserve a table for two", "What's the exchange rate for euros?",
    "Do you know the muffin man?", "Write an essay about AI.", "What's the recipe for scones?"
]

NEAR_NEGATIVES = [
    "I absolutely despise early morning meetings.", "My calendar app keeps crashing on my phone.", 
    "Why are there so many events scheduled today?", "I hate my timetable this semester.", 
    "Scheduling things is such a hassle.", "I wish I had more free time.", 
    "Do you think 9am is too early for a call?", "Meetings are mostly a waste of time.", 
    "I forgot my diary at home.", "I need to buy a new wall planner.", "Time flies when you are having fun.",
    "Can you believe how many appointments I have?", "My agenda is totally packed.", "I am so tired of Zoom calls."
]

# ----------------------------
# 2. HELPER FUNCTIONS
# ----------------------------

def generate_relative_time() -> str:
    pattern = random.choice(RELATIVE_TIME_PATTERNS)
    if "{weekday}" in pattern: pattern = pattern.replace("{weekday}", random.choice(WEEKDAYS))
    if "{month}" in pattern: pattern = pattern.replace("{month}", random.choice(MONTHS))
    if "{num}" in pattern:
        num = random.randint(2, 14) if "days" in pattern else random.randint(2, 12)
        pattern = pattern.replace("{num}", str(num))
    return pattern

def get_time_expression() -> str: return generate_relative_time() if random.random() < 0.4 else random.choice(STATIC_TIMES)
def maybe_add_timezone(time_str: str) -> str: return f"{time_str} {random.choice(TIMEZONES)}" if random.random() < 0.1 and any(c.isdigit() for c in time_str) else time_str
def get_recurrence_pattern() -> str: return random.choice(BASE_RECURRENCE + ADVANCED_RECURRENCE)
def get_preference_type() -> str: return random.choice(PREFERENCE_TYPES)
def get_hours_range() -> str: return random.choice(HOUR_RANGES)
def get_reminder_offset() -> str: return random.choice(REMINDER_OFFSETS)
def get_condition() -> str: return random.choice(["before 9am", "after 7pm", "on weekends", "during lunch", "on bank holidays", "when I'm out of office"])

def get_context_pools(context: str) -> Dict:
    pools = {
        "work": {
            "events": WORK_EVENTS, "people": PEOPLE["work"], "locations": LOCATIONS["work"], "actions": WORK_ACTIONS,
            "imperative_verbs": ["review", "prepare", "finalise", "update", "send", "draft", "fix", "deploy", "run", "clean", "organise", "respond", "test", "write", "refactor", "approve", "order", "book"],
            "objects": ["the proposal", "the slides", "the budget", "the spreadsheet", "the invoice", "the contract", "the bug", "the update", "the report", "the database", "the files", "the client", "the deployment", "the feature", "the documentation", "the code", "the timesheets", "the supplies", "the travel"]
        },
        "student": {
            "events": STUDENT_EVENTS, "people": PEOPLE["student"], "locations": LOCATIONS["student"], "actions": STUDENT_ACTIONS,
            "imperative_verbs": ["read", "complete", "draft", "prepare", "review", "finish", "create", "study", "outline", "watch", "do", "annotate", "solve", "memorise", "write"],
            "objects": ["chapter 5", "the problem set", "the essay", "the exam", "the lecture notes", "the lab report", "the presentation", "the quiz", "the paper", "the recorded lecture", "the reading", "the article", "the equations", "the vocabulary", "the bibliography"]
        },
        "personal": {
            "events": PERSONAL_EVENTS, "people": PEOPLE["personal"], "locations": LOCATIONS["personal"], "actions": PERSONAL_ACTIONS,
            "imperative_verbs": ["wash", "walk", "buy", "clean", "water", "take out", "pick up", "pay", "book", "renew", "change", "mow", "vacuum", "dust", "organise", "return", "get", "post", "charge", "feed"],
            "objects": ["the car", "the dog", "groceries", "the bathroom", "the plants", "the rubbish", "the dry cleaning", "the bills", "the flight", "the passport", "the oil", "the lawn", "the carpet", "the shelves", "the wardrobe", "the library books", "a haircut", "the parcel", "the phone", "the cat"]
        }
    }
    return pools[context]

def introduce_typo(word: str) -> str:
    if len(word) < 5 or random.random() > 0.05: return word
    qwerty_map = {'a': 's', 's': 'd', 'e': 'w', 'r': 't', 't': 'y', 'o': 'p', 'i': 'u', 'l': 'k', 'm': 'n'}
    idx = random.randint(1, len(word) - 2)
    char = word[idx].lower()
    if char in qwerty_map and random.random() < 0.5:
        return word[:idx] + (qwerty_map[char] if word[idx].islower() else qwerty_map[char].upper()) + word[idx+1:]
    return word[:idx] + word[idx+1:]

def inject_noise(text: str) -> str:
    if random.random() < 0.15: text = f"{random.choice(DISTRACTORS)} {text}"
    words = [introduce_typo(w) for w in text.split()]
    text = " ".join(words)
    if random.random() < 0.2: text = text.lower()
    for punct in ['.', '?', '!', ',', ';', ':']:
        if punct in text and random.random() > 0.5: text = text.replace(punct, '')
    return text.strip()

# ----------------------------
# 4. MASSIVELY EXPANDED TEMPLATES
# ----------------------------

VERBS = {
    "schedule": ["schedule", "book", "set up", "create", "arrange", "plan", "organise", "add", "pencil in", "slot in", "lock in", "diary"],
    "reschedule": ["reschedule", "move", "change", "shift", "postpone", "push back", "bring forward", "delay", "advance", "bump", "slide"],
    "cancel": ["cancel", "delete", "remove", "scrap", "call off", "skip", "bin", "nix", "abort"]
}

POLITE_PREFIXES = ["Could you please", "Would you mind", "Can you", "Please", "I need to", "I'd like to", "If possible,", "Do me a favour and"]
URGENCY_MARKERS = ["ASAP", "urgently", "immediately", "right away", "pronto", "as a priority"]

TEMPLATES = {
    "CREATE_EVENT": [
        "{action}", "{imperative_verb} the {object}", "I need to {action}", "Don't forget to {action}",
        "{imperative_verb} the {object} {time}", "{polite} {schedule} a {event}",
        "{polite} {schedule} a {event} with {person} at {time}", "Book a {event} for {duration}",
        "Set up a {event} in {location}", "We should {schedule} a {event} with {person}",
        "Let's {schedule} a {event} for planning", "{polite} {schedule} a {event} {recurrence}",
        "{action} at {time}", "Mark {time} as a {event} day", "Block out {time} for {event}",
        "Pencil me in for a {event} with {person}", "Get a {event} in the diary for {time}",
        "Can we squeeze in a {event} {time}?", "I need to block out time for a {event}",
        "Put me down for a {event} {time}", "Fix me up with a {event} in {location}",
        "Action: {schedule} {event}", "Can you sort out a {event} for {duration}?",
        "Make a note to {schedule} a {event}", "{polite} lock down a {event} {time}",
        "I've got a {event} coming up on {time}", "I have a {event} with {person} at {time}"
    ],
    "UPDATE_EVENT": [
        "{polite} {reschedule} the {event}", "{polite} {reschedule} my {event} to {time}",
        "Change the time of the {event} to {time}", "Move my {time} {event} to {time}",
        "Shift the {event} by {duration}", "Reschedule the {event} for {time}",
        "Bring the call forward to 10am", "Move the {event} to {time}",
        "Change the location of the {event} to {location}", "Can we bump the {event} to {time}?",
        "Push back the {event} by {duration}", "The {event} needs to be shifted to {time}",
        "I'm running late, move the {event} to {time}", "Delay the {event} until {time}",
        "Adjust the time for my {event}", "Update the {event} so it's at {time}",
        "We need to change the {event} details", "Make the {event} {duration} later",
        "Slide the {event} to {time} instead", "Can we do {time} instead for the {event}?"
    ],
    "DELETE_EVENT": [
        "{polite} {cancel} the {event}", "{polite} {cancel} my {event}",
        "Remove the {event} from my calendar", "Delete the {event}",
        "Take the {event} off my schedule", "I can't make the {event}, {so} {cancel} it",
        "Cancel the {event} because I'm sick", "Call off the {event}",
        "Bin the {event}", "Scrap the {event}", "The {event} is off",
        "Cancel the {event} as I'm double-booked", "Wipe the {event} from my diary",
        "Forget about the {event}", "I won't be attending the {event}, remove it",
        "Clear my schedule of the {event}", "Abort the {event}", "Take the {event} off the books"
    ],
    "QUERY_EVENT": [
        "What's on my calendar {time}?", "Show me my calendar for {time}",
        "What events do I have {time}?", "What am I doing {time}?",
        "When is my {event}?", "Where is the {event}?", "Who is attending the {event}?",
        "How long is the {event}?", "What's happening on Friday?",
        "How many meetings do I have {time}?", "Which events conflict with my {event}?",
        "Show me all events with {person}", "What events are in {location} {time}?",
        "List all recurring events", "What does my diary look like {time}?",
        "Have I got any clashes {time}?", "What's my agenda for {time}?",
        "When am I supposed to be at the {event}?", "Check my schedule for {time}",
        "Pull up my diary for {time}", "Do I have anything on {time}?", "Am I free {time}?"
    ],
    "ADD_PARTICIPANT": [
        "{polite} add {person} to the {event}", "{polite} invite {person} to the {event}",
        "Include {person} in the {event}", "Also invite {person}",
        "{person} should join the {event}", "Add {person} to the invite list",
        "Make sure {person} is invited", "Add {person} as a participant",
        "Make sure {person} is on the invite", "Forward the invite to {person}",
        "Loop in {person} to the {event}", "Send an invite to {person}",
        "Can we get {person} in on the {event}?", "Chuck {person} on the attendee list"
    ],
    "REMOVE_PARTICIPANT": [
        "{polite} remove {person} from the {event}", "{polite} uninvite {person}",
        "Take {person} off the {event}", "{person} can't make it, {so} remove them",
        "Exclude {person} from the {event}", "Cancel {person}'s invitation",
        "Drop {person} from the invite", "{person} doesn't need to be there",
        "Take {person} off the list", "Remove {person} from the attendee list",
        "Uninvite {person} from the {event}", "Strike {person} off the list"
    ],
    "NEGATIVE": [],  
    "FIND_FREE_TIME": [
        "When am I free {time}?", "Find a time for a {duration} {event}",
        "What slots are available on {time}?", "Do I have any free time {time}?",
        "I need a {duration} slot for a {event}", "What's my earliest free slot {time}?",
        "Find a time when everyone is free", "What times work for a {duration} meeting?",
        "When is the next free hour in my calendar?", "When can we squeeze this in?",
        "Find a gap for a {event}", "When's my next free slot?", 
        "Show me the gaps in my diary {time}", "Is there any space {time}?",
        "Find some availability {time} for a {event}"
    ],
    "SUGGEST_TIME": [
        "{polite} suggest a time for the {event}", "When should I schedule the {event}?",
        "Propose a time for {event} with {person}", "Suggest a few options for {event}",
        "What's a good time for everyone?", "Pick a time for the {event}",
        "Suggest a {duration} window for {event}", "Throw out some times for the {event}",
        "What works for you regarding the {event}?", "Give me some options for a {time} {event}",
        "Recommend a slot for the {event}", "When is best to hold the {event}?"
    ],
    "SET_REMINDER": [
        "Remind me {offset} the {event}", "Set a reminder for {offset} of the {event}",
        "Notify me {offset} the meeting", "I want a reminder {offset} my {event}",
        "Add a reminder to the {event} for {offset}", "Set an alert {offset} the {event}",
        "Create a reminder for {event} at {time}", "Give me a heads-up {offset} the call",
        "Give me a nudge {offset} the {event}", "Ping me {offset} the {event}",
        "Drop me a notification {offset} the {event}", "Don't let me forget the {event}",
        "Make my phone buzz {offset} the {event}"
    ],
    "CHANGE_RECURRENCE": [
        "Make this {event} {recurrence}", "Change the recurrence of the {event} to {recurrence}",
        "Set the event to repeat {recurrence}", "Make it a recurring {event} {recurrence}",
        "Stop repeating the {event}", "Change the {event} from {recurrence1} to {recurrence2}",
        "Convert to recurring {recurrence}", "Make this a weekly thing", 
        "Let's do this every fortnight", "Put this {event} on repeat {recurrence}",
        "Update the series so it happens {recurrence}", "I want this to occur {recurrence}"
    ],
    "SHARE_EVENT": [
        "{polite} share the {event} with {person}", "Forward the invite to {person}",
        "Send the {event} details to {person}", "Share my calendar with {person}",
        "Give {person} access to my calendar", "Email the {event} information to {person}",
        "Share this event via email", "Send the details over to {person}",
        "Share my diary with {person}", "Export the {event} and send to {person}",
        "Let {person} see my schedule"
    ],
    "DECLINE_EVENT": [
        "{polite} decline the {event}", "RSVP no to the {event}", "Say no to the invitation",
        "I can't attend the {event}", "Politely decline the {event}", "Send regrets for the {event}",
        "Refuse the meeting invitation", "I'll have to pass on the {event}", 
        "Reject the {event}", "Mark me as unavailable for the {event}",
        "Turn down the invite for the {event}", "Tell them I can't make the {event}"
    ],
    "SET_PREFERENCES": [
        "{polite} set my working hours to {hours}", "Don't schedule anything {condition}",
        "Block out {time} for lunch every day", "Set my available hours to {hours}",
        "I prefer no meetings before {time}", "Set {time} as focus time",
        "Update my calendar preferences: {preference}", "Set my default event duration to {duration}",
        "Prefer {location} for meetings", "Add annual leave on {time}",
        "I'm on annual leave {time}", "I don't work {days}", "Set my timezone to {timezone}",
        "Mark {time} as a bank holiday", "Set my status to out of office {time}"
    ],
}

# MULTI-SENTENCE EXTENSIONS MAPPED TO SECONDARY INTENTS
FOLLOW_UPS = {
    "CREATE_EVENT": [
        ("Invite {person} as well.", "ADD_PARTICIPANT"), 
        ("Make sure it sends a notification.", "SET_REMINDER"),
        ("And remind me {offset}.", "SET_REMINDER"),
        ("Also make it a recurring meeting {recurrence}.", "CHANGE_RECURRENCE"),
        ("Share it with {person}.", "SHARE_EVENT")
    ],
    "UPDATE_EVENT": [
        ("Let {person} know about the change.", "SHARE_EVENT"), 
        ("Remind me {offset} beforehand.", "SET_REMINDER"),
        ("And add {person} to the invite list.", "ADD_PARTICIPANT")
    ],
    "DELETE_EVENT": [
        ("I will decline the invitation now.", "DECLINE_EVENT"),
        ("Send my regrets to {person}.", "SHARE_EVENT"),
        ("Can we suggest a new time instead?", "SUGGEST_TIME")
    ],
    "FIND_FREE_TIME": [
        ("Propose those times to {person}.", "SUGGEST_TIME")
    ],
    "QUERY_EVENT": [
        ("If I am free, schedule a {event}.", "CREATE_EVENT")
    ],
    "ADD_PARTICIPANT": [
        ("And share my diary with them too.", "SHARE_EVENT")
    ]
}

# ----------------------------
# 5. GENERATOR
# ----------------------------

def generate_clean_text(primary_intent: str, context: Optional[str] = None) -> Tuple[Optional[str], List[str]]:
    active_intents = [primary_intent]
    
    if primary_intent == "NEGATIVE":
        pool = NEGATIVE_QUERIES + NEAR_NEGATIVES
        return random.choice(pool), active_intents
    
    if context is None:
        context = random.choice(["work", "student", "personal"])
        
    pools = get_context_pools(context)
    template = random.choice(TEMPLATES[primary_intent])
    
    base_event = random.choice(pools["events"])
    base_person = random.choice(pools["people"])
    base_location = random.choice(pools["locations"])
    base_time = maybe_add_timezone(get_time_expression())
    base_duration = random.choice(DURATIONS)
    
    if primary_intent in FOLLOW_UPS and random.random() < 0.20: 
        follow_up_text, secondary_intent = random.choice(FOLLOW_UPS[primary_intent])
        template += " " + follow_up_text
        if secondary_intent not in active_intents:
            active_intents.append(secondary_intent)

    filled = template
    
    if "{polite}" in filled: filled = filled.replace("{polite}", random.choice(POLITE_PREFIXES) if random.random() > 0.3 else "")
    if "{urgency}" in filled: filled = filled.replace("{urgency}", random.choice(URGENCY_MARKERS) if random.random() > 0.7 else "")
    if "{so}" in filled: filled = filled.replace("{so}", random.choice(["so", "therefore", ""]))
    
    for verb_type, verb_list in VERBS.items():
        if f"{{{verb_type}}}" in filled: filled = filled.replace(f"{{{verb_type}}}", random.choice(verb_list))
            
    if "{imperative_verb}" in filled and "{object}" in filled:
        filled = filled.replace("{imperative_verb}", random.choice(pools["imperative_verbs"]))
        filled = filled.replace("{object}", random.choice(pools["objects"]))
    elif "{imperative_verb}" in filled: filled = filled.replace("{imperative_verb}", random.choice(pools["imperative_verbs"]))
    elif "{object}" in filled: filled = filled.replace("{object}", random.choice(pools["objects"]))
        
    if "{action}" in filled: filled = filled.replace("{action}", random.choice(pools["actions"]))
        
    if "{event1}" in filled: filled = filled.replace("{event1}", random.choice(pools["events"]))
    if "{event2}" in filled: filled = filled.replace("{event2}", random.choice(pools["events"]))
    if "{time1}" in filled: filled = filled.replace("{time1}", maybe_add_timezone(get_time_expression()))
    if "{time2}" in filled: filled = filled.replace("{time2}", maybe_add_timezone(get_time_expression()))
    if "{recurrence1}" in filled: filled = filled.replace("{recurrence1}", get_recurrence_pattern())
    if "{recurrence2}" in filled: filled = filled.replace("{recurrence2}", get_recurrence_pattern())
    
    filled = filled.replace("{event}", base_event)
    filled = filled.replace("{person}", base_person)
    filled = filled.replace("{location}", base_location)
    filled = filled.replace("{time}", base_time)
    filled = filled.replace("{duration}", base_duration)
    
    placeholders = re.findall(r'\{(\w+)\}', filled)
    for ph in placeholders:
        if ph == "recurrence": replacement = get_recurrence_pattern()
        elif ph == "offset": replacement = get_reminder_offset()
        elif ph == "hours": replacement = get_hours_range()
        elif ph == "preference": replacement = get_preference_type()
        elif ph == "condition": replacement = get_condition()
        elif ph == "days": replacement = random.choice(["weekdays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays"])
        elif ph == "timezone": replacement = random.choice(TIMEZONES)
        else: replacement = ""
        filled = filled.replace(f"{{{ph}}}", replacement)
        
    cleaned_text = re.sub(r'\s+', ' ', filled).strip()
    
    if re.search(r'\{[a-zA-Z0-9_]+\}', cleaned_text):
        return None, []
        
    return cleaned_text, active_intents

def generate_dataset():
    all_examples = []
    
    print("\nGenerating MULTI-LABEL intent dataset (v16) for DeBERTa-v3...")
    for intent, count in INTENT_DISTRIBUTION.items():
        print(f"Generating {count} examples for {intent}...")
        
        generated_count = 0
        attempts = 0
        
        with tqdm(total=count) as pbar:
            while generated_count < count and attempts < MAX_ATTEMPTS_PER_INTENT:
                attempts += 1
                text, active_intents = generate_clean_text(intent)
                
                if text is None:
                    continue
                    
                if grammar_tool and intent != "NEGATIVE" and random.random() < 0.5:
                    matches = grammar_tool.check(text)
                    if len(matches) > 1: 
                        continue
                
                if random.random() < 0.3:
                    text = inject_noise(text)
                
                binary_labels = [0.0] * NUM_LABELS
                for active_intent in active_intents:
                    binary_labels[LABEL_MAP[active_intent]] = 1.0
                    
                all_examples.append({
                    "text": text,
                    "labels": binary_labels,
                    "active_intents": active_intents
                })
                
                generated_count += 1
                pbar.update(1)
                
    random.shuffle(all_examples)
    split_idx = int(len(all_examples) * TRAIN_RATIO)
    train_set = all_examples[:split_idx]
    eval_set = all_examples[split_idx:]
    
    return train_set, eval_set

# ----------------------------
# 6. EXECUTION
# ----------------------------
if __name__ == "__main__":
    train_examples, eval_examples = generate_dataset()
    
    os.makedirs("./deberta_data", exist_ok=True)
    
    with open("./deberta_data/intent_label_map.json", "w") as f:
        json.dump(LABEL_MAP, f, indent=2)
        
    with open("./deberta_data/multilabel_intent_train.jsonl", "w") as f:
        for ex in train_examples:
            f.write(json.dumps(ex) + "\n")
            
    with open("./deberta_data/multilabel_intent_eval.jsonl", "w") as f:
        for ex in eval_examples:
            f.write(json.dumps(ex) + "\n")

    print(f"\nMulti-Label Intent Generation Complete.")
    print(f"Training Docs: {len(train_examples)}")
    print(f"Evaluation Docs: {len(eval_examples)}")
    print("Files saved to ./deberta_data/")