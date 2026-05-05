
import json
import random
import re
import os
from tqdm import tqdm
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# --- CONFIGURATION ---
TOTAL_VALIDATION_EXAMPLES = 5000
MULTI_INTENT_PROBABILITY = 0.15 


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

# ============================================================
# COMPONENT LISTS (Identical to training for vocabulary consistency)
# ============================================================

WORK_EVENTS = ["meeting", "conference call", "sync", "standup", "one-on-one", "client meeting", "team meeting", "strategy session", "appraisal", "planning session", "retrospective", "workshop", "training", "demo", "interview", "presentation", "audit", "briefing", "debrief", "board meeting", "budget review", "sales call", "all-hands", "sprint planning", "code review", "design critique", "town hall", "fire drill", "offsite", "onboarding session", "performance review", "client pitch", "quarterly review", "stakeholder update", "project kickoff", "status update", "brainstorm", "catch-up", "handover meeting", "supplier meeting", "vendor call", "executive briefing", "product demo", "release planning"]
WORK_TASKS = ["review the proposal", "prepare the slides", "finalise the budget", "update the spreadsheet", "send the invoice", "draft the contract", "fix the bug", "deploy the update", "run the report", "clean the database", "organise the files", "respond to the client", "schedule the deployment", "test the feature", "write the documentation", "refactor the code", "approve the timesheets", "order the supplies", "book the travel", "sign off the deliverables", "submit expenses", "complete the code review", "update the wiki", "prepare the agenda", "send meeting notes", "chase the approvals", "finish the quarterly report", "review CVs", "write the job spec", "update project status", "create the Jira tickets", "merge the pull request", "respond to emails", "prepare for the audit", "complete compliance training", "update the CRM", "log timesheet hours"]
WORK_PEOPLE = ["John", "Sarah", "Michael", "Emily", "David", "Lisa", "Robert", "Jennifer", "the team", "the client", "marketing", "engineering", "HR", "the board", "the CEO", "the CTO", "the product owner", "the scrum master", "managing director", "line manager", "stakeholders", "suppliers", "contractors", "the PM", "the BA", "the QA team", "DevOps", "the account manager", "the tech lead", "senior management", "the interns", "the new starter", "external consultants"]
WORK_LOCATIONS = ["conference room", "Zoom", "Teams", "Meet", "office", "boardroom", "canteen", "breakout area", "remote", "client site", "HQ", "city centre", "Boardroom A", "the hot desk", "co-working space", "the regional office", "the branch", "meeting room 3", "the training room", "reception", "the video suite", "Slack huddle", "WebEx"]

STUDENT_EVENTS = ["lecture", "study session", "lab", "tutorial", "seminar", "group project", "office hours", "exam", "quiz", "workshop", "thesis meeting", "dissertation defence", "research meeting", "library session", "study group", "revision session", "practical", "colloquium", "symposium", "conference", "field trip", "module registration", "careers fair", "mock exam", "freshers fair", "society meeting", "pre-drinks", "flat meeting", "graduation ceremony", "supervision", "viva voce", "coursework deadline", "lab demonstration", "reading group", "guest lecture", "drop-in session", "mentoring session", "peer review", "feedback session", "induction"]
STUDENT_TASKS = ["read chapter 5", "complete the problem set", "draft the essay", "prepare for the exam", "review the lecture notes", "finish the lab report", "create the presentation", "study for the quiz", "outline the paper", "watch the recorded lecture", "do the reading", "annotate the article", "solve the equations", "memorise the vocabulary", "write the bibliography", "do revision", "submit the coursework", "finish the dissertation chapter", "email the supervisor", "book the library room", "return library books", "collect printed notes", "register for modules", "apply for extenuating circumstances", "complete the peer assessment", "review past papers", "finish the group project slides", "proofread the essay", "cite the references", "format the thesis", "attend the workshop", "complete the online quiz", "write up the experiment", "analyse the data"]
STUDENT_PEOPLE = ["professor", "TA", "study group", "lab partner", "course mate", "advisor", "Dr Smith", "Dr Johnson", "the tutor", "research group", "my supervisor", "the dean", "flatmates", "my personal tutor", "the lecturer", "course rep", "study buddy", "Dr Williams", "the seminar leader", "my dissertation supervisor", "the module convenor", "the librarian", "welfare officer", "the PhD students", "project group", "the postgrads"]
STUDENT_LOCATIONS = ["classroom", "lecture theatre", "lab", "library", "study room", "campus", "online", "student union", "the quad", "the science block", "halls", "the SU", "the library silent zone", "halls of residence", "the student village", "computer lab", "the seminar room", "the postgrad centre", "the cafeteria", "common room", "the sports centre", "LT1", "LT2"]

RECREATION_EVENTS = ["football match", "pub quiz", "drinks", "dinner", "brunch", "coffee", "cinema trip", "concert", "gig", "festival", "barbecue", "house party", "birthday party", "wedding", "stag do", "hen do", "weekend away", "road trip", "hiking", "camping", "yoga class", "gym session", "swimming", "tennis match", "golf round", "spa day", "shopping trip", "theatre trip", "comedy night", "karaoke", "bowling", "escape room", "board game night", "Netflix evening", "poker night", "five-a-side", "parkrun", "book club", "wine tasting", "cooking class", "art class", "dance class", "spin class", "pilates", "cricket match"]
RECREATION_TASKS = ["wash the car", "walk the dog", "buy groceries", "clean the bathroom", "water the plants", "take out the rubbish", "pick up the dry cleaning", "pay the bills", "book the flight", "renew the passport", "change the oil", "mow the lawn", "vacuum the carpet", "dust the shelves", "organise the wardrobe", "return the library books", "get a haircut", "post the parcel", "charge the phone", "feed the cat", "bleed the radiators", "book the restaurant", "order the birthday cake", "buy a present for mum", "plan the holiday", "cancel the subscription", "call the GP", "book the dentist", "sort out the insurance", "pay council tax", "renew car insurance", "defrost the freezer", "fix the bike", "collect the kids", "pick up the prescription", "take the dog to the vet", "do the weekly shop"]
RECREATION_PEOPLE = ["friend", "family", "partner", "mum", "dad", "sibling", "colleague", "neighbour", "Alex", "Chris", "Taylor", "Jordan", "the lads", "the girls", "the missus", "the kids", "the mechanic", "the landlord", "the letting agent", "my bestie", "the gang", "everyone", "the in-laws", "grandparents", "the cousins", "my flatmate", "my housemate", "the boys", "old school friends", "uni mates", "work friends", "the neighbours"]
RECREATION_LOCATIONS = ["home", "restaurant", "cafe", "gym", "park", "shopping centre", "cinema", "pub", "outdoors", "virtual", "the beach", "the local", "the leisure centre", "the high street", "the surgery", "the barbers", "the salon", "the garage", "the allotment", "Nando's", "Wetherspoons", "the cocktail bar", "the curry house", "the chippy", "the pizza place", "the theatre", "the stadium", "the arena", "the club", "the spa", "the pool"]

STATIC_TIMES = ["9am", "10:30", "2pm", "3:15", "4:45", "11am", "1pm", "5pm", "6pm", "7pm", "8am", "09:00", "14:30", "23:00", "morning", "afternoon", "evening", "tonight", "tomorrow morning", "tomorrow afternoon", "tomorrow evening", "today", "tomorrow", "next week", "this Friday", "Monday", "next Monday", "in an hour", "ASAP", "soon", "later today", "end of day", "first thing", "midnight", "noon", "lunchtime", "dinnertime", "crack of dawn", "close of play", "COB", "EOD", "this coming bank holiday", "half past two", "quarter to three", "around midday", "early morning", "late afternoon", "this evening", "Sunday morning"]
RELATIVE_TIME_PATTERNS = ["next {weekday}", "this coming {weekday}", "a week from today", "the day after tomorrow", "two weeks from now", "next month", "the first week of {month}", "the last {weekday} of {month}", "in {num} days", "in {num} hours", "on {weekday} afternoon", "a fortnight today", "tomorrow fortnight", "this time next week", "the week after next", "end of the month", "beginning of {month}", "mid-{month}", "early next week", "later this week"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TIMEZONES = ["GMT", "BST", "CET", "EST", "PST", "IST"]
BASE_RECURRENCE = ["every Monday", "every Tuesday", "every Wednesday", "every Thursday", "every Friday", "every weekend", "daily", "weekly", "every other day", "every other week", "every other Wednesday", "biweekly", "monthly", "every month", "fortnightly"]
ADVANCED_RECURRENCE = ["every weekday", "every Monday and Wednesday", "every Tuesday and Thursday", "on weekdays except Wednesday", "every other week on Tuesday", "the first Monday of every month", "the last Friday of each month", "every 2 weeks", "every 3 days", "quarterly", "yearly", "annually", "twice a week", "three times a week", "every Sunday evening", "every other fortnight"]
REMINDER_OFFSETS = ["10 minutes before", "30 minutes before", "1 hour before", "2 hours before", "at 9am", "in the morning", "the day before", "5 minutes before", "15 minutes before", "at the time of the event", "right when it starts", "half an hour before", "a quarter of an hour before", "an hour early", "the night before", "a week before", "3 days before", "24 hours before", "when I wake up", "first thing in the morning"]
DURATIONS = ["30 mins", "an hour", "2 hours", "15 mins", "half a day", "a solid hour", "a couple of hours", "quarter of an hour", "the whole afternoon", "all day", "45 minutes", "90 minutes", "20 minutes", "3 hours", "half an hour"]
PREFERENCE_TYPES = ["working hours", "available hours", "focus time", "break time", "all-day event", "annual leave", "bank holiday", "out of office", "lunch break", "commute time", "meeting-free time", "deep work hours", "admin time"]
HOUR_RANGES = ["9am to 5pm", "10am to 6pm", "8am to 4pm", "9:30 to 5:30", "flexible", "remote only", "in office", "8am to 6pm", "7am to 3pm", "mornings only", "afternoons only", "evenings only"]

POLITE_PREFIXES = ["Could you please", "Would you mind", "Can you", "Please", "I need to", "I'd like to", "If possible,", "Do me a favour and", "Would you be able to", "I was hoping to", "I want to", "Mind helping me", "Be a dear and", "I'm looking to"]
VERBS = {
    "schedule": ["sort out", "pencil in", "slot in", "pin down", "put together", "whip up", "draft in", "confirm"],
    "reschedule": ["push", "bump", "slide", "shunt", "delay", "bring forward", "postpone"],
    "cancel": ["scrap", "bin", "nix", "wipe", "abandon", "strike off", "scratch"],
    "update": ["tweak", "adjust", "amend", "modify", "overhaul"],
    "complete": ["tick off", "clear out", "finalise", "wrap up", "conclude"]
}

# ============================================================
# NOVEL STRICT VALIDATION TEMPLATES (ZERO OVERLAP)
# ============================================================

STRICT_TEMPLATES = {
    "CREATE_EVENT": [
        "I'd love to get a {event} on the calendar with {person} for {time}",
        "Let's put together a {event} at {location} {time}",
        "Can we squeeze a {event} in {time}?",
        "Fix a {event} for {duration} with {person}",
        "Find a way to accommodate a {event} {time}",
        "Ensure {person} is invited to my {event} {time}",
        "Draw up an invite for a {event} at {location}",
        "I am looking to host a {event} {time}",
        "Reserve {location} for our upcoming {event}",
        "I must sit down with {person} for a {event} {time}",
        "Throw a {event} into my diary for {duration}",
        "Block out my calendar for a {event} {time}"
    ],
    
    "UPDATE_EVENT": [
        "We need to push the {event} to {time}",
        "Alter the time of my {event} to {time} instead",
        "Swap the location of the {event} to {location}",
        "Bump my {event} backwards by {duration}",
        "I'm running late, nudge the {event} to {time}",
        "Adjust the constraints of the {event} to fit {time}",
        "Can we rather do {time} for the {event}?",
        "Make the {event} happen at {location} this time",
        "Extend the {event} so it runs for {duration}",
        "Update the specifics for the {event} with {person}"
    ],
    
    "DELETE_EVENT": [
        "Take the {event} off my plate entirely",
        "Erase the {event} scheduled on {time}",
        "I'm not going to the {event} anymore, remove it",
        "Wipe the {event} from existence",
        "I've decided to abandon the {event} with {person}",
        "Strike the {event} off my agenda",
        "Bin the upcoming {event}",
        "Don't worry about the {event} {time}, it's off",
        "Cancel my attendance for the {event}"
    ],
    
    "QUERY_EVENT": [
        "What does my day look like {time}?",
        "Am I tied up with a {event} at {time}?",
        "Check my itinerary for {time}",
        "Is there a {event} happening at {location}?",
        "Read out the details for the {event} with {person}",
        "Run through my calendar for {time}",
        "Where on earth is my {event} supposed to be?",
        "How long have I got left until the {event}?",
        "Do I need to be anywhere {time}?"
    ],
    
    "FIND_FREE_TIME": [
        "Scan my diary for a {duration} opening",
        "When do I actually have a gap {time}?",
        "Are there any empty slots {time}?",
        "Look for a window of opportunity {time}",
        "Tell me when I am not busy",
        "Identify some downtime for me {time}",
        "I desperately need {duration} of free time, when is it?",
        "Filter my calendar for empty space {time}"
    ],
    
    "SUGGEST_TIME": [
        "What's a clever time for a {event}?",
        "Find a mutually agreeable slot for the {event}",
        "Can you figure out when we should do the {event}?",
        "Advise me on when to book the {event}",
        "Draft some timing options for the {event}",
        "What time makes the most sense for a {event}?",
        "Help me figure out a good window for {event}",
        "I need a recommendation for the {event} timing"
    ],
    
    "CHANGE_RECURRENCE": [
        "Ensure this {event} is happening {recurrence}",
        "Let's make the {event} a {recurrence} occurrence",
        "Update the frequency of the {event} to {recurrence}",
        "Switch the {event} to run {recurrence}",
        "I want to do this {event} {recurrence} from now on",
        "Halt the recurring {event} immediately",
        "Make sure the {event} repeats {recurrence}",
        "Tweak the {event} so it only happens {recurrence}"
    ],
    
    "CREATE_TASK": [
        "Jot down that I must {task}",
        "I have a new chore: {task}",
        "Log {task} into my pipeline",
        "Assign me the responsibility to {task}",
        "Add an action item to {task} {time}",
        "I need a new checklist item for {task}",
        "Document that I have to {task}",
        "Leave a note for me to {task} by {time}",
        "Ensure {task} is on my radar"
    ],
    
    "UPDATE_TASK": [
        "Adjust the due date for {task} to {time}",
        "Modify the {task} deadline",
        "Shift the {task} backward to {time}",
        "Tweak the urgency of {task}",
        "The {task} now needs to be done by {time}",
        "Amend the specifics of {task}",
        "Push the deadline for {task} back a bit",
        "Make {task} a top priority immediately"
    ],
    
    "DELETE_TASK": [
        "I don't need to {task} anymore",
        "Wipe {task} off my to-do list",
        "Forget doing {task}",
        "Clear {task} out of my backlog",
        "I am abandoning the {task} action item",
        "Strike {task} from my chores",
        "Remove the requirement to {task}",
        "Throw out the {task} to-do"
    ],
    
    "COMPLETE_TASK": [
        "I have successfully managed to {task}",
        "Check {task} off",
        "{task} is fully dealt with",
        "I just finished up {task}",
        "Mark the {task} as resolved",
        "Close the loop on {task}",
        "That's {task} sorted",
        "Consider {task} finalized"
    ],
    
    "QUERY_TASK": [
        "What chores are remaining {time}?",
        "Read out my pending tasks",
        "Any urgent action items left?",
        "Give me a rundown of what needs doing",
        "Are there any tasks looming {time}?",
        "Show me my backlog",
        "What have I forgotten to do?",
        "Filter my list for tasks due {time}"
    ],
    
    "SET_REMINDER": [
        "Give me a nudge about the {event} {offset}",
        "I need an alert for {task} {offset}",
        "Make sure my phone pings me {offset} for the {event}",
        "Sound an alarm {offset} the {event}",
        "Drop me a notification so I don't forget to {task}",
        "Keep me in the loop about the {event} {offset}",
        "I want a heads up {offset}",
        "Set a warning bell for {task}"
    ],
    
    "UPDATE_REMINDER": [
        "Change the nudge to {offset}",
        "Alter the alert timing to {offset}",
        "Push the reminder for my {event} to {offset}",
        "Adjust when my phone buzzes to {offset}",
        "Modify the heads up to happen {offset}",
        "Tweak the notification for {task} to {offset}",
        "I'd rather be alerted {offset} instead"
    ],
    
    "DELETE_REMINDER": [
        "Mute the alert for the {event}",
        "I don't need a nudge for the {event} anymore",
        "Turn off the alarm for {time}",
        "Kill the notification about {task}",
        "Silence the reminder for the {event}",
        "Disable alerts for {task}",
        "I'll remember it, delete the nudge"
    ],
    
    "SET_PREFERENCES": [
        "My availability is strictly {hours}",
        "Log {time} as {preference}",
        "Never book me {condition}",
        "Make sure my calendar shows me as {preference} {time}",
        "I am totally unavailable {condition}",
        "Establish my standard working pattern as {hours}",
        "Flag me as {preference} for the duration of {time}",
        "Ensure no one interrupts me {condition}"
    ]
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
    templates = STRICT_TEMPLATES.get(primary_intent, [])
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
    
    template1 = random.choice(STRICT_TEMPLATES.get(primary_intent, []))
    template2 = random.choice(STRICT_TEMPLATES.get(secondary_intent, []))
    
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
    
    print("\nGenerating Strict Validation Intent Classification dataset...")
    print(f"Total intents: {NUM_LABELS}")
    
    # Even distribution across all 16 intents
    count_per_intent = TOTAL_VALIDATION_EXAMPLES // NUM_LABELS
    
    for intent in INTENT_LABELS:
        generated_count = 0
        attempts = 0
        seen_texts = set()
        
        with tqdm(total=count_per_intent, desc=f"Generating {intent}") as pbar:
            while generated_count < count_per_intent and attempts < 10000:
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
    return all_examples

if __name__ == "__main__":
    print("=" * 60)
    print("Strict Validation Intent Generator")
    print("=" * 60)
    
    validation_examples = generate_dataset()
    
    os.makedirs("./modernbert_data", exist_ok=True)

    output_path = "./modernbert_data/multilabel_intent_strict_validation.jsonl"
    with open(output_path, "w") as f:
        for ex in validation_examples:
            f.write(json.dumps(ex) + "\n")
    
    print("\n" + "=" * 60)
    print("Strict Validation Generation Complete")
    print("=" * 60)
    print(f"Total holdout examples: {len(validation_examples)}")
    
    intent_counts = defaultdict(int)
    for ex in validation_examples:
        intent_counts[ex["intent"]] += 1
    
    print("\nIntent distribution:")
    for intent in INTENT_LABELS:
        count = intent_counts[intent]
        print(f"  {LABEL_MAP[intent]:2d}. {intent:20s}: {count}")

    print(f"\nSaved strict holdout set to: {output_path}")