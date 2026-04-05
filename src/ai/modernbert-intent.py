# ===============================================================
# modernbert_intent_dataset_generator.py
# Optimised for ModernBERT Multi-Label Sequence Classification
#
# Version 19 - Enhanced for Scheduling Optimisation App
#   - 16 core intents for comprehensive scheduling coverage
#   - Context-based slots: Work, Student, Recreation
#   - 30+ distinct linguistic templates per intent
#   - Added conversational rambling for natural language variance
#   - Added logical compound multi-intent generation
#   - UK English spelling throughout
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
TRAIN_RATIO = 0.85
VALIDATION_RATIO = 0.10
TEST_RATIO = 0.05
USE_GRAMMAR_CHECK = False        
MAX_ATTEMPTS_PER_INTENT = 20000
MULTI_INTENT_PROBABILITY = 0.15 

# 16 Intents as specified (0-15)
BASE_DISTRIBUTION = {
    "CREATE_EVENT": 2500,       
    "UPDATE_EVENT": 2000,       
    "DELETE_EVENT": 1500,       
    "QUERY_EVENT": 2000,        
    "FIND_FREE_TIME": 1500,     
    "SUGGEST_TIME": 1500,       
    "CHANGE_RECURRENCE": 1200,  
    "CREATE_TASK": 2500,        
    "UPDATE_TASK": 2000,        
    "DELETE_TASK": 1500,        
    "COMPLETE_TASK": 1500,      
    "QUERY_TASK": 2000,         
    "SET_REMINDER": 1500,       
    "UPDATE_REMINDER": 1200,    
    "DELETE_REMINDER": 1200,    
    "SET_PREFERENCES": 1500,    
}

INTENT_DISTRIBUTION = {k: int(v * SCALE_FACTOR) for k, v in BASE_DISTRIBUTION.items()}

# Create ordered label map (0-15)
INTENT_LABELS = [
    "CREATE_EVENT", "UPDATE_EVENT", "DELETE_EVENT", "QUERY_EVENT",
    "FIND_FREE_TIME", "SUGGEST_TIME", "CHANGE_RECURRENCE",
    "CREATE_TASK", "UPDATE_TASK", "DELETE_TASK", "COMPLETE_TASK", "QUERY_TASK",
    "SET_REMINDER", "UPDATE_REMINDER", "DELETE_REMINDER", "SET_PREFERENCES"
]
LABEL_MAP = {intent: i for i, intent in enumerate(INTENT_LABELS)}
ID_TO_LABEL = {i: intent for intent, i in LABEL_MAP.items()}
NUM_LABELS = len(INTENT_LABELS)

# Defines which intents logically follow each other in a compound sentence
LOGICAL_INTENT_PAIRS = {
    "CREATE_EVENT": ["SET_REMINDER", "CREATE_TASK", "UPDATE_EVENT"],
    "UPDATE_EVENT": ["SET_REMINDER", "DELETE_EVENT", "CREATE_EVENT"],
    "DELETE_EVENT": ["CREATE_EVENT", "FIND_FREE_TIME", "CREATE_TASK"],
    "QUERY_EVENT": ["FIND_FREE_TIME", "SUGGEST_TIME", "UPDATE_EVENT"],
    "FIND_FREE_TIME": ["CREATE_EVENT", "SUGGEST_TIME"],
    "SUGGEST_TIME": ["CREATE_EVENT"],
    "CREATE_TASK": ["SET_REMINDER", "CREATE_EVENT"],
    "COMPLETE_TASK": ["CREATE_TASK", "QUERY_TASK", "DELETE_TASK"],
    "QUERY_TASK": ["CREATE_TASK", "COMPLETE_TASK"],
    "SET_REMINDER": ["CREATE_EVENT", "CREATE_TASK"],
    "DELETE_REMINDER": ["SET_REMINDER", "DELETE_EVENT", "DELETE_TASK"],
    "UPDATE_REMINDER": ["UPDATE_EVENT", "UPDATE_TASK"]
}

DISTRACTORS = [
    "actually", "please", "maybe", "I think", "just", "honestly", "if possible", 
    "mate", "cheers", "to be honest", "right", "anyway", "basically", "literally", 
    "as it happens", "look,", "so", "well", "um", "erm", "you know", "like",
    "ta", "quick one", "by the way", "also", "oh", "right then"
]

RAMBLE_PREFIXES = [
    "Hi there, ", "Morning, ", "Afternoon, ", "Hey, ", "Listen, ", 
    "I was just looking at my diary and realised ", "Things are a bit hectic today so ",
    "Before I forget, ", "Just a quick request, ", "Hope you're having a good day. ",
    "I've got a lot on my plate, ", "My schedule is a bit of a mess right now, "
]

RAMBLE_POSTFIXES = [
    " Thanks!", " Cheers.", " Speak later.", " Much appreciated.", 
    " Let me know if that's an issue.", " Catch you later.", " Ta very much.",
    " Hopefully that makes sense.", " Sorry for the short notice."
]

CONJUNCTIONS = [
    " and also ", ", plus I need to ", ". After that, ", " and then ", 
    ", oh and could you also ", ". Whilst you're at it, ", " and while we're at it, ",
    " but instead "
]

if USE_GRAMMAR_CHECK and HAS_GRAMMAR_TOOL:
    print("Initialising grammar checker (en-GB)...")
    try:
        grammar_tool = language_tool_python.LanguageTool('en-GB')
    except Exception as e:
        print(f"Warning: Grammar checker failed: {e}")
        grammar_tool = None
else:
    grammar_tool = None

# ============================================================
# COMPONENT LISTS - ORGANISED BY CONTEXT (Work, Student, Recreation)
# ============================================================

WORK_EVENTS = [
    "meeting", "conference call", "sync", "standup", "one-on-one", "client meeting",
    "team meeting", "strategy session", "appraisal", "planning session", "retrospective",
    "workshop", "training", "demo", "interview", "presentation", "audit", "briefing",
    "debrief", "board meeting", "budget review", "sales call", "all-hands", "sprint planning",
    "code review", "design critique", "town hall", "fire drill", "offsite", "onboarding session",
    "performance review", "client pitch", "quarterly review", "stakeholder update",
    "project kickoff", "status update", "brainstorm", "catch-up", "handover meeting",
    "supplier meeting", "vendor call", "executive briefing", "product demo", "release planning"
]

WORK_TASKS = [
    "review the proposal", "prepare the slides", "finalise the budget", "update the spreadsheet",
    "send the invoice", "draft the contract", "fix the bug", "deploy the update", "run the report",
    "clean the database", "organise the files", "respond to the client", "schedule the deployment",
    "test the feature", "write the documentation", "refactor the code", "approve the timesheets",
    "order the supplies", "book the travel", "sign off the deliverables", "submit expenses",
    "complete the code review", "update the wiki", "prepare the agenda", "send meeting notes",
    "chase the approvals", "finish the quarterly report", "review CVs", "write the job spec",
    "update project status", "create the Jira tickets", "merge the pull request", "respond to emails",
    "prepare for the audit", "complete compliance training", "update the CRM", "log timesheet hours"
]

WORK_PEOPLE = [
    "John", "Sarah", "Michael", "Emily", "David", "Lisa", "Robert", "Jennifer", "the team",
    "the client", "marketing", "engineering", "HR", "the board", "the CEO", "the CTO",
    "the product owner", "the scrum master", "managing director", "line manager", "stakeholders",
    "suppliers", "contractors", "the PM", "the BA", "the QA team", "DevOps", "the account manager",
    "the tech lead", "senior management", "the interns", "the new starter", "external consultants"
]

WORK_LOCATIONS = [
    "conference room", "Zoom", "Teams", "Meet", "office", "boardroom", "canteen",
    "breakout area", "remote", "client site", "HQ", "city centre", "Boardroom A",
    "the hot desk", "co-working space", "the regional office", "the branch", "meeting room 3",
    "the training room", "reception", "the video suite", "Slack huddle", "WebEx"
]

STUDENT_EVENTS = [
    "lecture", "study session", "lab", "tutorial", "seminar", "group project", "office hours",
    "exam", "quiz", "workshop", "thesis meeting", "dissertation defence", "research meeting",
    "library session", "study group", "revision session", "practical", "colloquium", "symposium",
    "conference", "field trip", "module registration", "careers fair", "mock exam", "freshers fair",
    "society meeting", "pre-drinks", "flat meeting", "graduation ceremony", "supervision",
    "viva voce", "coursework deadline", "lab demonstration", "reading group", "guest lecture",
    "drop-in session", "mentoring session", "peer review", "feedback session", "induction"
]

STUDENT_TASKS = [
    "read chapter 5", "complete the problem set", "draft the essay", "prepare for the exam",
    "review the lecture notes", "finish the lab report", "create the presentation", "study for the quiz",
    "outline the paper", "watch the recorded lecture", "do the reading", "annotate the article",
    "solve the equations", "memorise the vocabulary", "write the bibliography", "do revision",
    "submit the coursework", "finish the dissertation chapter", "email the supervisor",
    "book the library room", "return library books", "collect printed notes", "register for modules",
    "apply for extenuating circumstances", "complete the peer assessment", "review past papers",
    "finish the group project slides", "proofread the essay", "cite the references", "format the thesis",
    "attend the workshop", "complete the online quiz", "write up the experiment", "analyse the data"
]

STUDENT_PEOPLE = [
    "professor", "TA", "study group", "lab partner", "course mate", "advisor", "Dr Smith",
    "Dr Johnson", "the tutor", "research group", "my supervisor", "the dean", "flatmates",
    "my personal tutor", "the lecturer", "course rep", "study buddy", "Dr Williams",
    "the seminar leader", "my dissertation supervisor", "the module convenor", "the librarian",
    "welfare officer", "the PhD students", "project group", "the postgrads"
]

STUDENT_LOCATIONS = [
    "classroom", "lecture theatre", "lab", "library", "study room", "campus", "online",
    "student union", "the quad", "the science block", "halls", "the SU", "the library silent zone",
    "halls of residence", "the student village", "computer lab", "the seminar room",
    "the postgrad centre", "the cafeteria", "common room", "the sports centre", "LT1", "LT2"
]

RECREATION_EVENTS = [
    "football match", "pub quiz", "drinks", "dinner", "brunch", "coffee", "cinema trip",
    "concert", "gig", "festival", "barbecue", "house party", "birthday party", "wedding",
    "stag do", "hen do", "weekend away", "road trip", "hiking", "camping", "yoga class",
    "gym session", "swimming", "tennis match", "golf round", "spa day", "shopping trip",
    "theatre trip", "comedy night", "karaoke", "bowling", "escape room", "board game night",
    "Netflix evening", "poker night", "five-a-side", "parkrun", "book club", "wine tasting",
    "cooking class", "art class", "dance class", "spin class", "pilates", "cricket match"
]

RECREATION_TASKS = [
    "wash the car", "walk the dog", "buy groceries", "clean the bathroom", "water the plants",
    "take out the rubbish", "pick up the dry cleaning", "pay the bills", "book the flight",
    "renew the passport", "change the oil", "mow the lawn", "vacuum the carpet", "dust the shelves",
    "organise the wardrobe", "return the library books", "get a haircut", "post the parcel",
    "charge the phone", "feed the cat", "bleed the radiators", "book the restaurant",
    "order the birthday cake", "buy a present for mum", "plan the holiday", "cancel the subscription",
    "call the GP", "book the dentist", "sort out the insurance", "pay council tax",
    "renew car insurance", "defrost the freezer", "fix the bike", "collect the kids",
    "pick up the prescription", "take the dog to the vet", "do the weekly shop"
]

RECREATION_PEOPLE = [
    "friend", "family", "partner", "mum", "dad", "sibling", "colleague", "neighbour",
    "Alex", "Chris", "Taylor", "Jordan", "the lads", "the girls", "the missus", "the kids",
    "the mechanic", "the landlord", "the letting agent", "my bestie", "the gang", "everyone",
    "the in-laws", "grandparents", "the cousins", "my flatmate", "my housemate", "the boys",
    "old school friends", "uni mates", "work friends", "the neighbours"
]

RECREATION_LOCATIONS = [
    "home", "restaurant", "cafe", "gym", "park", "shopping centre", "cinema", "pub",
    "outdoors", "virtual", "the beach", "the local", "the leisure centre", "the high street",
    "the surgery", "the barbers", "the salon", "the garage", "the allotment", "Nando's",
    "Wetherspoons", "the cocktail bar", "the curry house", "the chippy", "the pizza place",
    "the theatre", "the stadium", "the arena", "the club", "the spa", "the pool"
]

STATIC_TIMES = [
    "9am", "10:30", "2pm", "3:15", "4:45", "11am", "1pm", "5pm", "6pm", "7pm", "8am",
    "09:00", "14:30", "23:00", "morning", "afternoon", "evening", "tonight", "tomorrow morning",
    "tomorrow afternoon", "tomorrow evening", "today", "tomorrow", "next week", "this Friday",
    "Monday", "next Monday", "in an hour", "ASAP", "soon", "later today", "end of day",
    "first thing", "midnight", "noon", "lunchtime", "dinnertime", "crack of dawn",
    "close of play", "COB", "EOD", "this coming bank holiday", "half past two", "quarter to three",
    "around midday", "early morning", "late afternoon", "this evening", "Sunday morning"
]

RELATIVE_TIME_PATTERNS = [
    "next {weekday}", "this coming {weekday}", "a week from today", "the day after tomorrow",
    "two weeks from now", "next month", "the first week of {month}", "the last {weekday} of {month}",
    "in {num} days", "in {num} hours", "on {weekday} afternoon", "a fortnight today",
    "tomorrow fortnight", "this time next week", "the week after next", "end of the month",
    "beginning of {month}", "mid-{month}", "early next week", "later this week"
]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TIMEZONES = ["GMT", "BST", "CET", "EST", "PST", "IST"]

BASE_RECURRENCE = [
    "every Monday", "every Tuesday", "every Wednesday", "every Thursday", "every Friday",
    "every weekend", "daily", "weekly", "every other day", "every other week",
    "every other Wednesday", "biweekly", "monthly", "every month", "fortnightly"
]

ADVANCED_RECURRENCE = [
    "every weekday", "every Monday and Wednesday", "every Tuesday and Thursday",
    "on weekdays except Wednesday", "every other week on Tuesday", "the first Monday of every month",
    "the last Friday of each month", "every 2 weeks", "every 3 days", "quarterly", "yearly",
    "annually", "twice a week", "three times a week", "every Sunday evening", "every other fortnight"
]

REMINDER_OFFSETS = [
    "10 minutes before", "30 minutes before", "1 hour before", "2 hours before", "at 9am",
    "in the morning", "the day before", "5 minutes before", "15 minutes before",
    "at the time of the event", "right when it starts", "half an hour before",
    "a quarter of an hour before", "an hour early", "the night before", "a week before",
    "3 days before", "24 hours before", "when I wake up", "first thing in the morning"
]

DURATIONS = [
    "30 mins", "an hour", "2 hours", "15 mins", "half a day", "a solid hour",
    "a couple of hours", "quarter of an hour", "the whole afternoon", "all day",
    "45 minutes", "90 minutes", "20 minutes", "3 hours", "half an hour"
]

PREFERENCE_TYPES = [
    "working hours", "available hours", "focus time", "break time", "all-day event",
    "annual leave", "bank holiday", "out of office", "lunch break", "commute time",
    "meeting-free time", "deep work hours", "admin time"
]

HOUR_RANGES = [
    "9am to 5pm", "10am to 6pm", "8am to 4pm", "9:30 to 5:30", "flexible",
    "remote only", "in office", "8am to 6pm", "7am to 3pm", "mornings only",
    "afternoons only", "evenings only"
]

POLITE_PREFIXES = [
    "Could you please", "Would you mind", "Can you", "Please", "I need to", "I'd like to",
    "If possible,", "Do me a favour and", "Would you be able to", "I was hoping to",
    "I want to", "Mind helping me", "Be a dear and", "I'm looking to"
]

URGENCY_MARKERS = ["ASAP", "urgently", "immediately", "right away", "pronto", "as a priority", "sharpish"]

VERBS = {
    "schedule": ["schedule", "book", "set up", "create", "arrange", "plan", "organise", "add", "pencil in", "slot in", "lock in", "diary", "put in", "pop in"],
    "reschedule": ["reschedule", "move", "change", "shift", "postpone", "push back", "bring forward", "delay", "advance", "bump", "slide", "adjust"],
    "cancel": ["cancel", "delete", "remove", "scrap", "call off", "skip", "bin", "nix", "abort", "drop", "ditch", "scratch"],
    "update": ["update", "change", "modify", "edit", "alter", "revise", "amend", "tweak", "adjust"],
    "complete": ["complete", "finish", "done", "tick off", "mark as done", "wrap up", "close out", "finalise"]
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_relative_time() -> str:
    pattern = random.choice(RELATIVE_TIME_PATTERNS)
    if "{weekday}" in pattern:
        pattern = pattern.replace("{weekday}", random.choice(WEEKDAYS))
    if "{month}" in pattern:
        pattern = pattern.replace("{month}", random.choice(MONTHS))
    if "{num}" in pattern:
        num = random.randint(2, 14) if "days" in pattern else random.randint(2, 12)
        pattern = pattern.replace("{num}", str(num))
    return pattern

def get_time_expression() -> str:
    return generate_relative_time() if random.random() < 0.4 else random.choice(STATIC_TIMES)

def maybe_add_timezone(time_str: str) -> str:
    if random.random() < 0.1 and any(c.isdigit() for c in time_str):
        return f"{time_str} {random.choice(TIMEZONES)}"
    return time_str

def get_recurrence_pattern() -> str:
    return random.choice(BASE_RECURRENCE + ADVANCED_RECURRENCE)

def get_preference_type() -> str:
    return random.choice(PREFERENCE_TYPES)

def get_hours_range() -> str:
    return random.choice(HOUR_RANGES)

def get_reminder_offset() -> str:
    return random.choice(REMINDER_OFFSETS)

def get_duration() -> str:
    return random.choice(DURATIONS)

def get_condition() -> str:
    return random.choice([
        "before 9am", "after 7pm", "on weekends", "during lunch", 
        "on bank holidays", "when I'm out of office", "during focus time",
        "in the evening", "on Fridays", "before noon"
    ])

def get_context_pools(context: str) -> Dict:
    pools = {
        "work": {
            "events": WORK_EVENTS,
            "tasks": WORK_TASKS,
            "people": WORK_PEOPLE,
            "locations": WORK_LOCATIONS,
        },
        "student": {
            "events": STUDENT_EVENTS,
            "tasks": STUDENT_TASKS,
            "people": STUDENT_PEOPLE,
            "locations": STUDENT_LOCATIONS,
        },
        "recreation": {
            "events": RECREATION_EVENTS,
            "tasks": RECREATION_TASKS,
            "people": RECREATION_PEOPLE,
            "locations": RECREATION_LOCATIONS,
        }
    }
    return pools[context]

def introduce_typo(word: str) -> str:
    if len(word) < 5 or random.random() > 0.05:
        return word
    qwerty_map = {'a': 's', 's': 'd', 'e': 'w', 'r': 't', 't': 'y', 'o': 'p', 'i': 'u', 'l': 'k', 'm': 'n'}
    idx = random.randint(1, len(word) - 2)
    char = word[idx].lower()
    if char in qwerty_map and random.random() < 0.5:
        replacement = qwerty_map[char] if word[idx].islower() else qwerty_map[char].upper()
        return word[:idx] + replacement + word[idx+1:]
    return word[:idx] + word[idx+1:]

def inject_noise(text: str) -> str:
    if random.random() < 0.15:
        text = f"{random.choice(DISTRACTORS)} {text}"
    
    words = [introduce_typo(w) for w in text.split()]
    text = " ".join(words)
    
    if random.random() < 0.2:
        text = text.lower()
    
    for punct in ['.', '?', '!', ',', ';', ':']:
        if punct in text and random.random() > 0.5:
            text = text.replace(punct, '')
    
    return text.strip()

def apply_rambling(text: str) -> str:
    if random.random() < 0.2:
        text = random.choice(RAMBLE_PREFIXES) + text
    if random.random() < 0.15:
        text = text + random.choice(RAMBLE_POSTFIXES)
    return text

# ============================================================
# TEMPLATES 
# ============================================================

TEMPLATES = {
    "CREATE_EVENT": [
        "{polite} {schedule} a {event} with {person} at {time}",
        "{polite} {schedule} a {event} for {time}",
        "I need to {schedule} a {event} in {location}",
        "I'd like to {schedule} a {event} with {person}",
        "Can we {schedule} a {event} for {duration}?",
        "Let's {schedule} a {event} {time}",
        "We should {schedule} a {event} with {person}",
        "I want to {schedule} a {event} at {time}",
        "Need to {schedule} a {event} {time}",
        "Time to {schedule} a {event} with {person}",
        "{schedule} {event} with {person} {time}",
        "{schedule} {event} {time}",
        "Book {event} {location} {time}",
        "New {event} with {person}",
        "{event} with {person} at {time}",
        "{event} {time} {location}",
        "Add {event} to calendar {time}",
        "I have a {event} at {time}",
        "Put {event} in diary {time}",
        "Pencil in {event} {time}",
        "Slot in {event} with {person}",
        "Get a {event} in the diary for {time}",
        "Lock in a {event} with {person}",
        "Sort out a {event} for {time}",
        "Fix up a {event} in {location}",
        "Pop a {event} in for {time}",
        "Chuck a {event} in the calendar {time}",
        "Stick a {event} in for {time}",
        "Whack a {event} in the diary {time}",
        "Can you {schedule} a {event} for me {time}?",
        "Could we set up a {event} {time}?",
    ],
    
    "UPDATE_EVENT": [
        "{polite} {reschedule} the {event} to {time}",
        "{polite} change the {event} to {time}",
        "I need to {reschedule} my {event} to {time}",
        "Can we {reschedule} the {event} to {time}?",
        "The {event} needs to be moved to {time}",
        "I want to {reschedule} the {event} to {time}",
        "We need to {reschedule} the {event} with {person}",
        "Could you {reschedule} my {time} {event}?",
        "I'd like to {reschedule} the {event} to {time}",
        "{reschedule} {event} to {time}",
        "Move {event} to {time}",
        "Change {event} time to {time}",
        "Shift {event} to {time}",
        "Push {event} back by {duration}",
        "Bring {event} forward to {time}",
        "Bump {event} to {time}",
        "{event} now at {time}",
        "Update {event} location to {location}",
        "Can we do {time} instead for the {event}?",
        "Let's make it {time} for the {event}",
        "Slide the {event} to {time}",
        "Shunt the {event} to {time} instead",
        "The {event} is moving to {time}",
        "Change the location of the {event} to {location}",
        "Move the {event} from {location} to online",
        "Make the {event} {duration} longer",
        "Shorten the {event} to {duration}",
        "Extend the {event} by {duration}",
        "I'm running late, move the {event} to {time}",
        "Delay the {event} by {duration}",
    ],
    
    "DELETE_EVENT": [
        "{polite} {cancel} the {event}",
        "{polite} {cancel} my {event} with {person}",
        "I need to {cancel} the {event} {time}",
        "Can you {cancel} the {event} for me?",
        "I want to {cancel} my {time} {event}",
        "The {event} needs to be cancelled",
        "I'd like to {cancel} the {event} with {person}",
        "We need to {cancel} the {event} {time}",
        "{cancel} {event} {time}",
        "{cancel} the {time} {event}",
        "Remove {event} from calendar",
        "Delete {event} with {person}",
        "Drop the {event} {time}",
        "Scrap the {event} with {person}",
        "Bin the {event} {time}",
        "Nix the {event} with {person}",
        "The {event} {time} is off",
        "Forget about the {event} with {person}",
        "Kill the {event} on {time}",
        "Ditch the {event} {time}",
        "Pull the plug on the {event}",
        "Cancel the {event} {time} because I'm ill",
        "I can't make the {event}, cancel it",
        "{cancel} the {event} as I'm double-booked",
        "Something came up, {cancel} the {event}",
        "I'm not feeling well, {cancel} the {event}",
        "Can we {cancel} the {event} {time}?",
        "Could you remove the {event} from my diary?",
        "Take the {event} off my schedule",
        "Clear the {event} from my calendar",
    ],
    
    "QUERY_EVENT": [
        "What's on my calendar {time}?",
        "What events do I have {time}?",
        "What am I doing {time}?",
        "Do I have anything scheduled {time}?",
        "What's happening {time}?",
        "Can you show me my calendar for {time}?",
        "I want to see my schedule for {time}",
        "What does my diary look like {time}?",
        "When is my {event}?",
        "Where is the {event}?",
        "Who is attending the {event}?",
        "How long is the {event}?",
        "What time does the {event} start?",
        "Where's the {event} happening?",
        "Who's coming to the {event}?",
        "Show calendar {time}",
        "Check schedule {time}",
        "List events {time}",
        "What's on {time}?",
        "My diary at {time}",
        "Events at {time}",
        "Am I free at this {time}?",
        "Do I have any clashes at {time}?",
        "Have I got anything on at {time}?",
        "What's my agenda for {time}?",
        "How many meetings do I have at {time}?",
        "Is there anything in my calendar at {time}?",
        "Pull up my diary for {time}",
        "Check my schedule for {time}",
        "What've I got on {time}?",
    ],
    
    "FIND_FREE_TIME": [
        "When am I free {time}?",
        "Find me a free slot {time}",
        "What times are available {time}?",
        "I need to find some free time {time}",
        "Can you find a gap in my calendar {time}?",
        "Where do I have availability {time}?",
        "I'm looking for a free {duration} slot",
        "Find me an opening {time}",
        "Find free time {time}",
        "Check availability {time}",
        "Free slots {time}",
        "Gaps in calendar {time}",
        "Available times {time}",
        "Open slots {time}",
        "When free {time}?",
        "Find a time for a {duration} {event}",
        "I need a {duration} slot for a {event}",
        "Find a gap for a {event}",
        "When can I fit in a {event}?",
        "Where can I squeeze in a {event}?",
        "Do I have any free time {time}?",
        "Is there space in my diary {time}?",
        "Any gaps {time}?",
        "What's my earliest free slot {time}?",
        "When's my next free hour {time}?",
        "Have I got any openings {time}?",
        "Show me the gaps in my diary {time}",
        "Find a time when {person} is free",
        "When are {person} and I both available?",
        "Check mutual availability with {person}",
    ],
    
    "SUGGEST_TIME": [
        "{polite} suggest a time for the {event}",
        "When should I schedule the {event}?",
        "Can you recommend a time for the {event}?",
        "What's a good time for the {event}?",
        "Propose some times for the {event}",
        "What time would work best for a {event}?",
        "I need suggestions for when to have the {event}",
        "Can you pick a time for the {event}?",
        "Suggest time for {event}",
        "Recommend slot for {event}",
        "Best time for {event}?",
        "Optimal time for {event}",
        "When best for {event}?",
        "Propose times for {event}",
        "Suggest a {duration} window for a {event}",
        "What's the best time for a {duration} {event}?",
        "When's ideal for a {event} in {location}?",
        "Suggest a time that works for {person}",
        "What times work for the {event}?",
        "When would be good for the {event}?",
        "What do you suggest for the {event}?",
        "Any recommendations for the {event} time?",
        "What's optimal for the {event}?",
        "Throw out some times for the {event}",
        "Give me some options for the {event}",
        "Chuck some times at me for the {event}",
        "What times look good for the {event}?",
        "Suggest a few options for the {event}",
        "When works for {person} and the {event}?",
        "Pick a suitable time for the {event}",
    ],
    
    "CHANGE_RECURRENCE": [
        "Make this {event} repeat {recurrence}",
        "Change the recurrence of the {event} to {recurrence}",
        "Set the {event} to repeat {recurrence}",
        "I want this {event} to happen {recurrence}",
        "Can you make the {event} recurring {recurrence}?",
        "The {event} should repeat {recurrence}",
        "Turn the {event} into a recurring event {recurrence}",
        "I need the {event} to repeat {recurrence}",
        "Make {event} {recurrence}",
        "Set {event} to {recurrence}",
        "{event} should be {recurrence}",
        "Repeat {event} {recurrence}",
        "Recurring {event} {recurrence}",
        "{recurrence} for the {event}",
        "Stop repeating the {event}",
        "Cancel the recurring {event}",
        "End the {event} series",
        "Make the {event} one-off",
        "Remove recurrence from {event}",
        "Stop the {event} from repeating",
        "Change the {event} from weekly to {recurrence}",
        "Update the {event} recurrence to {recurrence}",
        "Switch the {event} to {recurrence}",
        "Alter the {event} repeat pattern to {recurrence}",
        "Can the {event} repeat {recurrence}?",
        "Make the {event} a {recurrence} thing",
        "Would it be possible to repeat the {event} {recurrence}?",
        "Let's do this {event} {recurrence}",
        "Make it a regular {event} {recurrence}",
        "Put this {event} on repeat {recurrence}",
    ],
    
    "CREATE_TASK": [
        "{polite} add a task to {task}",
        "I need to add a task: {task}",
        "Create a task to {task}",
        "Add {task} to my to-do list",
        "I have a task to {task}",
        "Put {task} on my list",
        "I need to remember to {task}",
        "Can you create a task for me to {task}?",
        "Add task: {task}",
        "New task: {task}",
        "Task: {task}",
        "To-do: {task}",
        "Remember to {task}",
        "Don't forget to {task}",
        "Need to {task}",
        "Must {task}",
        "Got to {task}",
        "Add a task to {task} by {time}",
        "Create a task to {task} for {time}",
        "I need to {task} by {time}",
        "{task} deadline {time}",
        "{task} due {time}",
        "Task: {task} - due {time}",
        "Can you add {task} to my tasks?",
        "Would you create a task to {task}?",
        "Chuck {task} on my to-do list",
        "Stick {task} on my list",
        "Pop {task} in my tasks",
        "Whack {task} on the list",
        "Log a task to {task}",
    ],
    
    "UPDATE_TASK": [
        "{polite} {update} the task {task}",
        "I need to {update} my task {task}",
        "Can you {update} the {task} deadline to {time}?",
        "Change the task {task} deadline",
        "The task {task} needs to be updated",
        "I want to {update} my to-do {task}",
        "Could you {update} the task {task} details?",
        "Modify the task description to {task}",
        "{update} task: {task}",
        "Change task {task} to {time}",
        "Edit task: {task}",
        "Modify {task} deadline to {time}",
        "Task {task} deadline now {time}",
        "Push task {task} to {time}",
        "Move {task} deadline to {time}",
        "Change the {task} deadline to {time}",
        "Extend the {task} deadline to {time}",
        "Move the {task} due date to {time}",
        "Push the {task} deadline back to {time}",
        "Bring the {task} deadline forward to {time}",
        "Make the task {task} high priority",
        "Lower the priority of {task}",
        "Mark the task {task} as urgent",
        "Change {task} priority",
        "Can I change the task {task}?",
        "Could you update the {task} due date?",
        "Is it possible to extend the {task} deadline?",
        "Tweak the task {task} a bit",
        "Adjust the {task} deadline",
        "Shift the task {task} to {time}",
    ],
    
    "DELETE_TASK": [
        "{polite} delete the task {task}",
        "I need to remove the task {task}",
        "Can you delete my task to {task}?",
        "Remove {task} from my list",
        "I want to delete the task {task}",
        "The task {task} needs to be removed",
        "Take the task {task} off my list",
        "I'd like to delete the to-do {task}",
        "Delete task {task}",
        "Remove task: {task}",
        "Delete: {task}",
        "Remove from to-do: {task}",
        "Bin the task {task}",
        "Scrap the task {task}",
        "Drop the task {task}",
        "Nix the task {task}",
        "Get rid of the task {task}",
        "Chuck the task {task}",
        "Ditch the task {task}",
        "Kill the task {task}",
        "Forget the task {task}",
        "Never mind the task {task}",
        "Can you remove the task {task}?",
        "Could you delete this task {task}?",
        "Would you take {task} off my list?",
        "I don't need to {task} anymore",
        "The task {task} is no longer needed",
        "The task {task} is obsolete, remove it",
        "Strike {task} off my list",
        "Take {task} off my action items",
    ],
    
    "COMPLETE_TASK": [
        "{polite} mark the task {task} as {complete}",
        "I've {complete}d the task {task}",
        "The task {task} is {complete}",
        "Can you mark {task} as done?",
        "I want to {complete} the task {task}",
        "Mark my task {task} as {complete}",
        "I've done the task {task}",
        "The task {task} has been completed",
        "{complete} task {task}",
        "Task {task} done",
        "Mark done: {task}",
        "Tick off: {task}",
        "{task} - done",
        "{task} - complete",
        "Done: {task}",
        "Finished: {task}",
        "Completed: {task}",
        "Tick off the task {task}",
        "Cross off the task {task}",
        "That {task} is done",
        "Sorted the task {task}",
        "Knocked {task} off",
        "Smashed that task {task}",
        "Got {task} done",
        "Can I mark {task} as complete?",
        "Could you tick off the task {task}?",
        "Would you mark {task} done?",
        "I finished {task}",
        "I managed to {task}",
        "Finally {complete}d {task}",
    ],
    
    "QUERY_TASK": [
        "What tasks do I have {time}?",
        "what tasks do I have",
        "Show me my tasks for {time}",
        "What's on my to-do list {time}?",
        "What tasks are due {time}?",
        "What tasks are incomplete?",
        "What tasks are complete?",
        "What tasks are in progress?",
        "What are the tasks with the highest priority?",
        "What tasks are due within the next {time}?",
        "Do I have any tasks {time}?",
        "What do I need to do on {time}?",
        "Can you show me my to-do list {time}?",
        "What tasks are pending?",
        "Show tasks for {time}",
        "List tasks due {time}",
        "My tasks {time}",
        "To-do list for {time}",
        "Tasks due {time}",
        "Pending tasks for {time}",
        "Outstanding tasks {time}",
        "Open tasks for {time}",
        "How many tasks do I have {time}?",
        "What's the next task due {time}?",
        "What are my tasks for {time}?",
        "What's my most urgent task {time}?",
        "What tasks are overdue {time}?",
        "Any high priority tasks {time}?",
        "What's due {time}?",
        "Do I have any tasks due {time}?",
        "Are there any pending tasks {time}?",
        "Have I got any tasks left {time}?",
        "What needs doing {time}?",
        "What haven't I done yet {time}?",
        "What've I got on my list {time}?",
        "What's left to do {time}?",
        "Give me my to-do list for {time}",
    ],
    
    "SET_REMINDER": [
        "Remind me {offset} the {event}",
        "Set a reminder for {offset} before {event}",
        "I need a reminder {offset} the {event}",
        "Can you remind me about the {event}?",
        "Create a reminder for {time} about {event}",
        "I want a reminder for the {event}",
        "Set up a notification {offset} the {event}",
        "Remind me to {task}",
        "Reminder: {task} at {time}",
        "Remind me: {task}",
        "Set reminder {offset} for {event}",
        "Alert {offset} {event}",
        "Notify me {offset} about {event}",
        "Ping me {offset} for {event}",
        "Nudge me {offset} about {event}",
        "Remind me at {time} about {event}",
        "Set a reminder for {time} to {task}",
        "Notification at {time} for {event}",
        "Alert me at {time} about {event}",
        "Buzz me at {time} for {event}",
        "Remind me to {task} at {time}",
        "Don't let me forget to {task}",
        "Make sure I remember to {task}",
        "I need reminding to {task}",
        "Can you set a reminder for the {event}?",
        "Could you remind me {offset} about {event}?",
        "Give me a heads-up {offset} for {event}",
        "Drop me a reminder {offset} about {event}",
        "Send me a nudge {offset} for {event}",
        "Pop a reminder in for {time} about {event}",
    ],
    
    "UPDATE_REMINDER": [
        "{polite} change the reminder for {event} to {offset}",
        "I need to update the reminder for {event}",
        "Can you move the reminder for {event} to {offset}?",
        "Change my reminder for {event} to {time}",
        "The reminder for {event} needs to be updated",
        "I want to adjust the reminder time for {event}",
        "Could you modify the reminder for {event}?",
        "Update the notification time for {event} to {offset}",
        "Change reminder for {event} to {offset}",
        "Move reminder for {event} to {time}",
        "Update reminder for {event}: {offset}",
        "Adjust reminder time for {event}",
        "Shift reminder for {event} to {offset}",
        "Reminder for {event} now {offset}",
        "Make the reminder for {event} earlier",
        "Push the reminder for {event} back",
        "Change the {event} reminder from {offset} to later",
        "Move the notification for {event} to {offset}",
        "Reschedule the reminder for {event}",
        "Can I change the reminder time for {event}?",
        "Could you update the notification for {event}?",
        "Is it possible to move the reminder for {event}?",
        "Would you adjust the alert time for {event}?",
        "Tweak the reminder for {event}",
        "Shift the notification for {event} a bit",
        "Bump the reminder for {event} to {offset}",
        "Amend the reminder time for {event}",
        "Sort out the reminder for {event} to be {offset}",
        "Change when I get reminded about {event}",
        "Update the {event} alert to {offset}",
    ],
    
    "DELETE_REMINDER": [
        "{polite} delete the reminder for {event}",
        "I need to remove the reminder for {event}",
        "Can you cancel the reminder for {event}?",
        "Remove the notification for the {event}",
        "I want to delete the alert for {event}",
        "The reminder for {event} needs to be removed",
        "Turn off the reminder for {event}",
        "Cancel my reminder for the {event}",
        "Delete reminder for {event}",
        "Remove reminder for {event}",
        "Cancel reminder for {event}",
        "Clear reminder for {event}",
        "No reminder needed for {event}",
        "Forget the reminder for {event}",
        "Scrap the reminder for {event}",
        "Kill the reminder for {event}",
        "Turn off notifications for the {event}",
        "Stop reminding me about the {event}",
        "Remove the alert for {event} at {time}",
        "Cancel the notification for {event}",
        "Don't remind me about the {event}",
        "Can you remove the reminder for {event}?",
        "Could you cancel the notification for {event}?",
        "Would you delete the alert for {event}?",
        "Can I turn off the reminder for {event}?",
        "Bin the reminder for {event}",
        "Chuck the notification for {event}",
        "Ditch the alert for {event}",
        "Get rid of the reminder for {event}",
        "Take off the reminder for {event}",
    ],
    
    "SET_PREFERENCES": [
        "{polite} set my working hours to {hours}",
        "I want to set my preferences to {hours}",
        "Can you update my settings to {hours}?",
        "Change my available hours to {hours}",
        "Set my timezone to {timezone}",
        "I'd like to configure my calendar to {hours}",
        "Update my scheduling preferences to {hours}",
        "Can you adjust my default settings to {hours}?",
        "Set working hours: {hours}",
        "Update preferences to {hours}",
        "Configure settings: {hours}",
        "Change timezone to {timezone}",
        "Set availability: {hours}",
        "Working hours {hours}",
        "Preferences: {preference}",
        "Don't schedule anything {condition}",
        "I prefer no meetings {condition}",
        "Set {time} as focus time",
        "Block out {time} for lunch",
        "I don't work {condition}",
        "Mark {time} as unavailable",
        "Set my default meeting duration to {duration}",
        "Can I change my working hours to {hours}?",
        "Could you update my availability to {hours}?",
        "Would you adjust my preferences to {hours}?",
        "Sort out my preferences to {hours}",
        "Tweak my settings to {hours}",
        "Add annual leave on {time}",
        "I'm on holiday {time}",
        "Set my status to out of office {time}",
    ],
}

# ============================================================
# GENERATOR FUNCTIONS
# ============================================================

def fill_template(template: str, pools: Dict, context: str) -> Optional[str]:
    filled = template
    
    base_event = random.choice(pools["events"])
    base_task = random.choice(pools["tasks"])
    base_person = random.choice(pools["people"])
    base_location = random.choice(pools["locations"])
    base_time = maybe_add_timezone(get_time_expression())
    base_duration = get_duration()
    base_offset = get_reminder_offset()
    base_recurrence = get_recurrence_pattern()
    
    if "{polite}" in filled:
        polite = random.choice(POLITE_PREFIXES) if random.random() > 0.4 else ""
        filled = filled.replace("{polite}", polite)
    
    for verb_type, verb_list in VERBS.items():
        placeholder = "{" + verb_type + "}"
        if placeholder in filled:
            filled = filled.replace(placeholder, random.choice(verb_list))
    
    filled = filled.replace("{event}", base_event)
    filled = filled.replace("{task}", base_task)
    filled = filled.replace("{person}", base_person)
    filled = filled.replace("{location}", base_location)
    filled = filled.replace("{time}", base_time)
    filled = filled.replace("{duration}", base_duration)
    filled = filled.replace("{offset}", base_offset)
    filled = filled.replace("{recurrence}", base_recurrence)
    filled = filled.replace("{hours}", get_hours_range())
    filled = filled.replace("{timezone}", random.choice(TIMEZONES))
    filled = filled.replace("{preference}", get_preference_type())
    filled = filled.replace("{condition}", get_condition())
    
    filled = re.sub(r'\s+', ' ', filled).strip()
    
    if filled and not filled[0].isupper() and random.random() > 0.3:
        filled = filled[0].upper() + filled[1:]
    
    if re.search(r'\{\w+\}', filled):
        return None
    
    return filled

def generate_single_intent_text(primary_intent: str, context: str) -> Tuple[Optional[str], List[str]]:
    pools = get_context_pools(context)
    templates = TEMPLATES.get(primary_intent, [])
    if not templates:
        return None, []
    
    template = random.choice(templates)
    filled = fill_template(template, pools, context)
    
    if filled is None:
        return None, []
    
    filled = apply_rambling(filled)
    return filled, [primary_intent]

def generate_multi_intent_text(primary_intent: str, context: str) -> Tuple[Optional[str], List[str]]:
    pools = get_context_pools(context)
    
    valid_secondaries = LOGICAL_INTENT_PAIRS.get(primary_intent, [])
    
    if not valid_secondaries:
        return generate_single_intent_text(primary_intent, context)
        
    secondary_intent = random.choice(valid_secondaries)
    
    template1 = random.choice(TEMPLATES.get(primary_intent, []))
    template2 = random.choice(TEMPLATES.get(secondary_intent, []))
    
    filled1 = fill_template(template1, pools, context)
    filled2 = fill_template(template2, pools, context)
    
    if not filled1 or not filled2:
        return None, []
    
    if filled2 and filled2[0].isupper():
        filled2 = filled2[0].lower() + filled2[1:]
        
    conjunction = random.choice(CONJUNCTIONS)
    combined = f"{filled1}{conjunction}{filled2}"
    
    combined = apply_rambling(combined)
    return combined, [primary_intent, secondary_intent]

def generate_dataset():
    all_examples = []
    
    print("\nGenerating ModernBERT intent classification dataset...")
    print(f"Total intents: {NUM_LABELS}")
    print(f"Intent mapping: {LABEL_MAP}\n")
    
    for intent, count in INTENT_DISTRIBUTION.items():
        print(f"Generating {count} examples for {intent}...")
        
        generated_count = 0
        attempts = 0
        seen_texts = set()
        
        with tqdm(total=count) as pbar:
            while generated_count < count and attempts < MAX_ATTEMPTS_PER_INTENT:
                attempts += 1
                
                context = ["work", "student", "recreation"][generated_count % 3]
                
                if random.random() < MULTI_INTENT_PROBABILITY:
                    text, active_intents = generate_multi_intent_text(intent, context)
                else:
                    text, active_intents = generate_single_intent_text(intent, context)
                
                if text is None:
                    continue
                
                text_lower = text.lower()
                if text_lower in seen_texts:
                    continue
                seen_texts.add(text_lower)
                
                if grammar_tool and random.random() < 0.3:
                    matches = grammar_tool.check(text)
                    if len(matches) > 2:
                        continue
                
                if random.random() < 0.25:
                    text = inject_noise(text)
                
                binary_labels = [0.0] * NUM_LABELS
                for active_intent in active_intents:
                    binary_labels[LABEL_MAP[active_intent]] = 1.0
                
                all_examples.append({
                    "text": text,
                    "labels": binary_labels,
                    "intent": intent, 
                    "label_id": LABEL_MAP[intent]
                })
                
                generated_count += 1
                pbar.update(1)
    
    random.shuffle(all_examples)
    
    total = len(all_examples)
    train_end = int(total * TRAIN_RATIO)
    val_end = int(total * (TRAIN_RATIO + VALIDATION_RATIO))
    
    train_set = all_examples[:train_end]
    val_set = all_examples[train_end:val_end]
    test_set = all_examples[val_end:]
    
    return train_set, val_set, test_set

if __name__ == "__main__":
    print("=" * 60)
    print("ModernBERT Intent Classification Dataset Generator")
    print("=" * 60)
    
    train_examples, val_examples, test_examples = generate_dataset()
    
    os.makedirs("./modernbert_data", exist_ok=True)

    with open("./modernbert_data/intent_label_map.json", "w") as f:
        json.dump(LABEL_MAP, f, indent=2)

    with open("./modernbert_data/id_to_label.json", "w") as f:
        json.dump(ID_TO_LABEL, f, indent=2)

    with open("./modernbert_data/multilabel_intent_train.jsonl", "w") as f:
        for ex in train_examples:
            f.write(json.dumps(ex) + "\n")

    with open("./modernbert_data/multilabel_intent_validation.jsonl", "w") as f:
        for ex in val_examples:
            f.write(json.dumps(ex) + "\n")

    with open("./modernbert_data/multilabel_intent_test.jsonl", "w") as f:
        for ex in test_examples:
            f.write(json.dumps(ex) + "\n")
    
    print("\n" + "=" * 60)
    print("Dataset Generation Complete")
    print("=" * 60)
    print(f"Training examples:   {len(train_examples)}")
    print(f"Validation examples: {len(val_examples)}")
    print(f"Test examples:       {len(test_examples)}")
    print(f"Total examples:      {len(train_examples) + len(val_examples) + len(test_examples)}")
    print("\nIntent distribution in training set:")
    
    intent_counts = defaultdict(int)
    for ex in train_examples:
        intent_counts[ex["intent"]] += 1
    
    for intent in INTENT_LABELS:
        count = intent_counts[intent]
        print(f"  {LABEL_MAP[intent]:2d}. {intent:20s}: {count}")

    print("\nFiles saved to ./modernbert_data/")
    print("  - intent_label_map.json")
    print("  - id_to_label.json")
    print("  - multilabel_intent_train.jsonl")
    print("  - multilabel_intent_validation.jsonl")
    print("  - multilabel_intent_test.jsonl")