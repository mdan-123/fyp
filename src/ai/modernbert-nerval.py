# ===============================================================
# modernbert_ner_strict_validation.py
# OPTIMISED FOR ModernBERT NER - Scheduling Domain
#
# Version 1.0 - Strict Holdout Validation Dataset
#   - ZERO template overlap with the training generator
#   - 26 NER labels (13 entity types with B/I prefixes + O)
#   - 100+ completely new structural templates
#   - Generates a standalone JSONL file for unbiased evaluation
#   - UK English spelling throughout
# ===============================================================

import json
import random
import re
import os
from tqdm import tqdm
from typing import List, Dict, Tuple

# -----------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------
ALL_LABELS = [
    "O",                        
    "B-EVENT", "I-EVENT",       
    "B-TASK", "I-TASK",         
    "B-PERSON", "I-PERSON",     
    "B-LOCATION", "I-LOCATION", 
    "B-DATE_ABSOLUTE", "I-DATE_ABSOLUTE",     
    "B-DATE_RELATIVE", "I-DATE_RELATIVE",     
    "B-TIME_ABSOLUTE", "I-TIME_ABSOLUTE",     
    "B-TIME_RELATIVE", "I-TIME_RELATIVE",     
    "B-DURATION", "I-DURATION",               
    "B-RECURRENCE", "I-RECURRENCE",           
    "B-REMINDER_OFFSET", "I-REMINDER_OFFSET", 
    "B-PREF_TYPE", "I-PREF_TYPE",             
    "B-CONDITION", "I-CONDITION"              
]

LABEL_TO_ID = {l: i for i, l in enumerate(ALL_LABELS)}
ID_TO_LABEL = {i: l for i, l in enumerate(ALL_LABELS)}

# Validation set size configuration
TOTAL_POSITIVE = 6000
NEGATIVE_COUNT = 1000

# -----------------------------------------------------------------
# 2. Entity Mapping
# -----------------------------------------------------------------
ENTITY_MAPPING = {
    "event_work": "EVENT",
    "event_student": "EVENT",
    "event_recreation": "EVENT",
    "task_work": "TASK",
    "task_student": "TASK",
    "task_recreation": "TASK",
    "person_work": "PERSON",
    "person_student": "PERSON",
    "person_recreation": "PERSON",
    "location_work": "LOCATION",
    "location_student": "LOCATION",
    "location_recreation": "LOCATION",
    "date_absolute": "DATE_ABSOLUTE",
    "date_relative": "DATE_RELATIVE",
    "time_absolute": "TIME_ABSOLUTE",
    "time_relative": "TIME_RELATIVE",
    "duration": "DURATION",
    "recurrence": "RECURRENCE",
    "reminder_offset": "REMINDER_OFFSET",
    "pref_type": "PREF_TYPE",
    "condition": "CONDITION",
}

# -----------------------------------------------------------------
# 3. COMPONENT POOLS
# -----------------------------------------------------------------
COMPONENT_POOLS = {
    "event_work": [
        "meeting", "conference call", "sync", "standup", "one-on-one", "client meeting",
        "team meeting", "strategy session", "appraisal", "planning session", "retrospective",
        "workshop", "training", "demo", "interview", "presentation", "audit", "briefing",
        "debrief", "board meeting", "budget review", "sales call", "all-hands", "sprint planning",
        "code review", "design critique", "town hall", "fire drill", "offsite", "onboarding session",
        "performance review", "client pitch", "quarterly review", "stakeholder update",
        "project kickoff", "status update", "brainstorm", "catch-up", "handover meeting",
        "supplier meeting", "vendor call", "executive briefing", "product demo", "release planning",
        "scrum", "backlog grooming", "post-mortem", "webinar", "panel", "roundtable",
        "fireside chat", "townhall", "deep dive", "working session", "check-in", "committee meeting",
        "progress update", "away day", "1-on-1", "retro", "kick-off"
    ],
    "event_student": [
        "lecture", "study session", "lab", "tutorial", "seminar", "group project", "office hours",
        "exam", "quiz", "workshop", "thesis meeting", "dissertation defence", "research meeting",
        "library session", "study group", "revision session", "practical", "colloquium", "symposium",
        "conference", "field trip", "module registration", "careers fair", "mock exam", "freshers fair",
        "society meeting", "pre-drinks", "flat meeting", "graduation ceremony", "supervision",
        "viva voce", "coursework deadline", "lab demonstration", "reading group", "guest lecture",
        "drop-in session", "mentoring session", "peer review", "feedback session", "induction",
        "lab session", "seminar presentation", "poster session", "thesis defence", "project presentation",
        "exam revision", "group study", "one-to-one tutorial", "academic meeting", "course induction"
    ],
    "event_recreation": [
        "football match", "pub quiz", "drinks", "dinner", "brunch", "coffee", "cinema trip",
        "concert", "gig", "festival", "barbecue", "house party", "birthday party", "wedding",
        "stag do", "hen do", "weekend away", "road trip", "hiking", "camping", "yoga class",
        "gym session", "swimming", "tennis match", "golf round", "spa day", "shopping trip",
        "theatre trip", "comedy night", "karaoke", "bowling", "escape room", "board game night",
        "Netflix evening", "poker night", "five-a-side", "parkrun", "book club", "wine tasting",
        "cooking class", "art class", "dance class", "spin class", "pilates", "cricket match",
        "Sunday roast", "pub lunch", "afternoon tea", "date night", "family gathering",
        "garden party", "picnic", "quiz night", "games night", "movie marathon"
    ],

    "task_work": [
        "review the proposal", "prepare the slides", "finalise the budget", "update the spreadsheet",
        "send the invoice", "draft the contract", "fix the bug", "deploy the update", "run the report",
        "clean the database", "organise the files", "respond to the client", "schedule the deployment",
        "test the feature", "write the documentation", "refactor the code", "approve the timesheets",
        "order the supplies", "book the travel", "sign off the deliverables", "submit expenses",
        "complete the code review", "update the wiki", "prepare the agenda", "send meeting notes",
        "chase the approvals", "finish the quarterly report", "review CVs", "write the job spec",
        "update project status", "create the Jira tickets", "merge the pull request", "respond to emails",
        "prepare for the audit", "complete compliance training", "update the CRM", "log timesheet hours",
        "API integration", "Cloud migration", "OAuth debugging", "Unit testing", "Project Orion",
        "the Zeta rollout", "GDPR audit", "ISO certification", "Stakeholder interview", "UX research",
        "Wireframe review", "MVP demo", "Legacy code refactor", "System stress test", "Deployment pipeline",
        "PR review", "server maintenance", "client onboarding", "drafting the contract",
        "budget forecasting", "inventory check", "marketing strategy", "social media planning",
        "payroll processing", "signing off the accounts", "sorting the Q4 figures"
    ],
    "task_student": [
        "read chapter 5", "complete the problem set", "draft the essay", "prepare for the exam",
        "review the lecture notes", "finish the lab report", "create the presentation", "study for the quiz",
        "outline the paper", "watch the recorded lecture", "do the reading", "annotate the article",
        "solve the equations", "memorise the vocabulary", "write the bibliography", "do revision",
        "submit the coursework", "finish the dissertation chapter", "email the supervisor",
        "book the library room", "return library books", "collect printed notes", "register for modules",
        "apply for extenuating circumstances", "complete the peer assessment", "review past papers",
        "finish the group project slides", "proofread the essay", "cite the references", "format the thesis",
        "attend the workshop", "complete the online quiz", "write up the experiment", "analyse the data",
        "Neural Networks lab", "Discrete Math quiz", "Compiler design", "Ethics essay", "Case study 4",
        "Logic gates homework", "Seminar prep", "Library research", "Peer review session", "Mock viva",
        "Poster design", "reading week prep", "dissertation research", "marking papers",
        "peer programming", "revision", "coursework", "lab prep", "group project presentation",
        "literature review", "data collection", "revising for finals", "writing the methodology section"
    ],
    "task_recreation": [
        "wash the car", "walk the dog", "buy groceries", "clean the bathroom", "water the plants",
        "take out the rubbish", "pick up the dry cleaning", "pay the bills", "book the flight",
        "renew the passport", "change the oil", "mow the lawn", "vacuum the carpet", "dust the shelves",
        "organise the wardrobe", "return the library books", "get a haircut", "post the parcel",
        "charge the phone", "feed the cat", "bleed the radiators", "book the restaurant",
        "order the birthday cake", "buy a present for mum", "plan the holiday", "cancel the subscription",
        "call the GP", "book the dentist", "sort out the insurance", "pay council tax",
        "renew car insurance", "defrost the freezer", "fix the bike", "collect the kids",
        "pick up the prescription", "take the dog to the vet", "do the weekly shop",
        "Boiler service", "Window cleaning", "Passport renewal", "Visa interview", "GP checkup",
        "Physio session", "Personal training", "Bank visit", "Car MOT", "Utility bill payment",
        "Council tax query", "Vet appointment", "calling mum", "walking the dog", "dentist appointment",
        "seeing the GP", "doing the weekly shop", "fixing the boiler", "watching the match",
        "pub quiz", "getting a haircut", "picking up a prescription", "viewing a flat",
        "renewing insurance", "Sunday roast", "five-a-side football", "grabbing a pint", "having a brew"
    ],

    "person_work": [
        "John", "Sarah", "Michael", "Emily", "David", "Lisa", "Robert", "Jennifer", "the team",
        "the client", "marketing", "engineering", "HR", "the board", "the CEO", "the CTO",
        "the product owner", "the scrum master", "managing director", "line manager", "stakeholders",
        "suppliers", "contractors", "the PM", "the BA", "the QA team", "DevOps", "the account manager",
        "the tech lead", "senior management", "the interns", "the new starter", "external consultants",
        "the external vendors", "the legal advisors", "the board members", "the tech leads",
        "the DevOps team", "the HR rep", "the whole team", "my line manager", "the investors",
        "James", "Emma", "Oliver", "Charlotte", "William", "Sophie", "George", "Amelia"
    ],
    "person_student": [
        "professor", "TA", "study group", "lab partner", "course mate", "advisor", "Dr Smith",
        "Dr Johnson", "the tutor", "research group", "my supervisor", "the dean", "flatmates",
        "my personal tutor", "the lecturer", "course rep", "study buddy", "Dr Williams",
        "the seminar leader", "my dissertation supervisor", "the module convenor", "the librarian",
        "welfare officer", "the PhD students", "project group", "the postgrads",
        "Professor Sterling", "Dr Aris", "the academic advisor", "Professor Jones",
        "Dr Brown", "Dr Taylor", "the teaching assistant", "the lab demonstrator"
    ],
    "person_recreation": [
        "friend", "family", "partner", "mum", "dad", "sibling", "colleague", "neighbour",
        "Alex", "Chris", "Taylor", "Jordan", "the lads", "the girls", "the missus", "the kids",
        "the mechanic", "the landlord", "the letting agent", "my bestie", "the gang", "everyone",
        "the in-laws", "grandparents", "the cousins", "my flatmate", "my housemate", "the boys",
        "old school friends", "uni mates", "work friends", "the neighbours",
        "my therapist", "the personal trainer", "the landlord's agent", "the flatmates",
        "the electrician", "the plumber", "Sam", "Jamie", "Morgan", "Riley"
    ],

    "location_work": [
        "conference room", "Zoom", "Teams", "Meet", "office", "boardroom", "canteen",
        "breakout area", "remote", "client site", "HQ", "city centre", "Boardroom A",
        "the hot desk", "co-working space", "the regional office", "the branch", "meeting room 3",
        "the training room", "reception", "the video suite", "Slack huddle", "WebEx",
        "Conference Room Alpha", "Huddle Room 2", "the main hall", "WeWork 4th floor",
        "the lobby", "Home Office", "Virtual - Zoom", "Teams (Join via link)",
        "Google Meet", "the client office", "headquarters", "the London office"
    ],
    "location_student": [
        "classroom", "lecture theatre", "lab", "library", "study room", "campus", "online",
        "student union", "the quad", "the science block", "halls", "the SU", "the library silent zone",
        "halls of residence", "the student village", "computer lab", "the seminar room",
        "the postgrad centre", "the cafeteria", "common room", "the sports centre", "LT1", "LT2",
        "The Quadrangle", "Silent Zone", "the SU bar", "the student union", "my flat",
        "Room 101", "Building A", "the engineering block", "the humanities building"
    ],
    "location_recreation": [
        "home", "restaurant", "cafe", "gym", "park", "shopping centre", "cinema", "pub",
        "outdoors", "virtual", "the beach", "the local", "the leisure centre", "the high street",
        "the surgery", "the barbers", "the salon", "the garage", "the allotment", "Nando's",
        "Wetherspoons", "the cocktail bar", "the curry house", "the chippy", "the pizza place",
        "the theatre", "the stadium", "the arena", "the club", "the spa", "the pool",
        "Starbucks High St", "Costa", "Pret", "the local pub", "the park", "the gym"
    ],

    "date_absolute": [
        "Halloween", "Bank Holiday Monday", "New Year's Eve", "2026-05-15", "June 1st",
        "Next Christmas", "The 14th of Feb", "St Patrick's Day", "Christmas Day", "Boxing Day",
        "Guy Fawkes Night", "5th of November", "1st May", "31st October", "Easter Sunday",
        "Valentine's Day", "12/08/2026", "15th March", "22nd April", "3rd September",
        "Monday 5th", "Tuesday the 10th", "Wednesday 23rd", "1st of December", "28th February",
        "10th January", "20th June", "4th July", "November 11th", "December 25th",
        "March 17th", "August 15th", "September 1st", "October 31st", "April 23rd"
    ],
    "date_relative": [
        "the coming Friday", "a week from Tuesday", "the next working day", "end of the quarter",
        "mid-month", "sometime in April", "this weekend", "this coming Monday",
        "the weekend after next", "a fortnight on Tuesday", "sometime next week", "later today",
        "the day after tomorrow", "next term", "today", "tomorrow", "next week", "this Friday",
        "next Monday", "this coming Wednesday", "end of the week", "beginning of next month",
        "a fortnight today", "tomorrow fortnight", "this time next week", "the week after next",
        "end of the month", "beginning of June", "mid-March", "early next week", "later this week",
        "in a few days", "in a couple of weeks", "next fortnight", "this quarter"
    ],
    "time_absolute": [
        "08:00", "13:30", "midday", "11:45 PM", "quarter past nine", "half six", "ten to ten",
        "16:15", "noon sharp", "07:30 AM", "13:00", "14:00", "half eight", "quarter to ten",
        "midnight", "five o'clock", "half past two", "nine a.m.", "9am", "10:30", "2pm",
        "3:15", "4:45", "11am", "1pm", "5pm", "6pm", "7pm", "8am", "09:00", "14:30", "23:00",
        "noon", "half past two", "quarter to three", "ten past four", "twenty to six",
        "six thirty", "seven fifteen", "8:45", "10:15", "11:30", "12:45", "3:30", "4:00"
    ],
    "time_relative": [
        "over lunch", "post-work", "pre-dawn", "golden hour", "business hours", "during my commute",
        "late night", "first available slot", "first thing in the morning", "end of the day",
        "afternoon break", "dinnertime", "early evening", "before breakfast", "morning",
        "afternoon", "evening", "tonight", "tomorrow morning", "tomorrow afternoon",
        "tomorrow evening", "later today", "first thing", "lunchtime", "crack of dawn",
        "close of play", "COB", "EOD", "early morning", "late afternoon", "this evening",
        "after work", "before lunch", "mid-morning", "mid-afternoon"
    ],
    "duration": [
        "90 mins", "a full day", "45 minutes", "a quick 15", "two hours max", "half an hour",
        "three sessions of 20 mins", "an entire afternoon", "just ten minutes", "a solid hour",
        "all morning", "45 mins tops", "30 mins", "an hour", "2 hours", "15 mins", "half a day",
        "a couple of hours", "quarter of an hour", "the whole afternoon", "all day",
        "45 minutes", "90 minutes", "20 minutes", "3 hours", "about an hour", "roughly 30 mins",
        "no more than an hour", "at least 2 hours", "a good hour", "a quick half hour"
    ],
    "recurrence": [
        "quarterly", "semi-annually", "every 3 weeks", "on alternate months",
        "the third Wednesday monthly", "fortnightly on pay day", "every single day",
        "once a term", "annually", "every fortnight", "twice a week", "every weekend",
        "every Monday", "every Tuesday", "every Wednesday", "every Thursday", "every Friday",
        "daily", "weekly", "every other day", "every other week", "every other Wednesday",
        "biweekly", "monthly", "every month", "every weekday", "every Monday and Wednesday",
        "every Tuesday and Thursday", "on weekdays except Wednesday", "every other week on Tuesday",
        "the first Monday of every month", "the last Friday of each month", "every 2 weeks",
        "every 3 days", "yearly", "three times a week", "every Sunday evening"
    ],
    "reminder_offset": [
        "30 mins prior", "the night before", "2 days ahead", "at the start", "10 minutes after",
        "periodically during", "an hour beforehand", "first thing that morning",
        "five minutes before", "a week in advance", "10 minutes before", "30 minutes before",
        "1 hour before", "2 hours before", "at 9am", "in the morning", "the day before",
        "5 minutes before", "15 minutes before", "at the time of the event", "right when it starts",
        "half an hour before", "a quarter of an hour before", "an hour early",
        "the night before", "a week before", "3 days before", "24 hours before",
        "when I wake up", "first thing in the morning"
    ],

    "pref_type": [
        "working hours", "available hours", "focus time", "break time", "all-day event",
        "annual leave", "bank holiday", "out of office", "lunch break", "commute time",
        "meeting-free time", "deep work hours", "admin time", "high priority", "low priority",
        "tentative", "low urgency", "urgent", "critical", "pencilled in", "if possible",
        "ideally", "whenever suits", "as a backup plan", "strictly confidential"
    ],
    "condition": [
        "before 9am", "after 7pm", "on weekends", "during lunch", "on bank holidays",
        "when I'm out of office", "during focus time", "in the evening", "on Fridays",
        "before noon", "must not clash", "strictly after 10am", "don't double book",
        "if there is a cancellation", "only if free", "weather permitting",
        "unless something comes up", "if the room is available", "provided everyone can make it",
        "as long as it doesn't clash", "assuming no conflicts", "when convenient"
    ],
}

# -----------------------------------------------------------------
# 4. Sentence Builder Class
# -----------------------------------------------------------------
class SentenceBuilder:
    def __init__(self):
        self.tokens = []

    def add_entity(self, text: str, etype: str):
        words = text.split()
        for i, word in enumerate(words):
            tag = f"B-{etype}" if i == 0 else f"I-{etype}"
            self.tokens.append((word, tag))

    def add_text(self, text: str):
        for word in text.split():
            if word: 
                self.tokens.append((word, "O"))

    def get_output(self) -> Tuple[List[str], List[int]]:
        return [t[0] for t in self.tokens], [LABEL_TO_ID[t[1]] for t in self.tokens]


# -----------------------------------------------------------------
# 5. STRICT VALIDATION TEMPLATE SYSTEM
# -----------------------------------------------------------------
# -----------------------------------------------------------------
# 5. EXPANDED STRICT VALIDATION TEMPLATE SYSTEM
# -----------------------------------------------------------------
class StrictValidationSystem:
    def __init__(self):
        self.templates = {
            "val_work_events": [
                "Could you pencil in {event_work} for {date_relative} at {time_absolute} ?",
                "I've got to arrange {event_work} involving {person_work} in {location_work} .",
                "Make sure {person_work} is invited to {event_work} lasting {duration} .",
                "We need to shift {event_work} to {date_absolute} .",
                "Can we delay {event_work} until {time_absolute} ?",
                "Adjust the timing of {event_work} to {time_absolute} instead .",
                "Please wipe {event_work} from my diary entirely .",
                "Abort {event_work} with {person_work} please .",
                "Ensure {event_work} occurs {recurrence} going forward .",
                "At what time does {event_work} start ?",
                "I require {duration} blocked out for {event_work} {date_relative} .",
                "Drop {person_work} a calendar invite for {event_work} on {date_absolute} .",
                "Are there any gaps to fit in {event_work} {condition} ?",
                "Amend the location of {event_work} to {location_work} .",
                # --- NEW TEMPLATES ---
                "Can we find a window for {event_work} {date_relative} ?",
                "Let's lock in {event_work} at {time_absolute} with {person_work} .",
                "Is {location_work} available for {event_work} {date_absolute} ?",
                "We should probably delay {event_work} by {duration} .",
                "Notify {person_work} that {event_work} is pushed to {time_absolute} .",
                "I need to slot in {event_work} before {time_absolute} .",
                "Clear my diary for {event_work} {date_relative} ."
            ],
            
            "val_student_events": [
                "I need a slot for {event_student} at {location_student} on {date_absolute} .",
                "Get {person_student} to join {event_student} {time_relative} .",
                "Extend {event_student} by {duration} .",
                "Postpone {event_student} to {date_relative} .",
                "Erase {event_student} from my timetable .",
                "Where exactly is {event_student} taking place ?",
                "I want {event_student} to happen {recurrence} without fail .",
                "See if {person_student} can do {event_student} at {time_absolute} .",
                "Will I be busy during {event_student} ?",
                "Check if {location_student} is free for {event_student} {date_relative} .",
                # --- NEW TEMPLATES ---
                "Check my timetable for {event_student} on {date_absolute} .",
                "I am supposed to attend {event_student} at {location_student} {time_relative} .",
                "Can {person_student} make {event_student} for {duration} ?",
                "Bump {event_student} forward to {time_absolute} .",
                "I am skipping {event_student} {date_relative} .",
                "Make sure {event_student} is noted down for {time_absolute} .",
                "Does {event_student} clash with anything {date_relative} ?"
            ],
            
            "val_recreation_events": [
                "See if we can do {event_recreation} around {time_relative} .",
                "Let us switch {event_recreation} to {date_absolute} .",
                "Take {event_recreation} off my radar completely .",
                "Who else is coming to {event_recreation} ?",
                "I fancy {event_recreation} at {location_recreation} {date_relative} .",
                "Can we make {event_recreation} a {recurrence} habit ?",
                "Find an opening for {duration} so I can do {event_recreation} .",
                "Is {person_recreation} still attending {event_recreation} at {time_absolute} ?",
                "We should push {event_recreation} to {time_absolute} .",
                "Ensure {location_recreation} is booked for {event_recreation} {date_absolute} .",
                # --- NEW TEMPLATES ---
                "Are we still on for {event_recreation} {time_relative} ?",
                "Let's sort out {event_recreation} with {person_recreation} for {date_absolute} .",
                "I'd love to squeeze in {event_recreation} {date_relative} .",
                "Bring {event_recreation} forward to {time_absolute} if possible .",
                "Forget about {event_recreation} , I can't be bothered .",
                "How long is {event_recreation} expected to last ?",
                "I am hosting {event_recreation} at {location_recreation} {date_relative} ."
            ],
            
            "val_tasks": [
                "Add a to-do for {task_work} before {date_absolute} .",
                "My next priority is {task_student} {time_relative} .",
                "Put {task_recreation} on my agenda for {date_relative} .",
                "I have completed {task_work} just now .",
                "Change the deadline for {task_student} to {time_absolute} .",
                "Never mind doing {task_recreation} , take it away .",
                "Check if {task_work} is overdue .",
                "I require {duration} to solely focus on {task_work} .",
                "Set up an alert to {task_student} {reminder_offset} .",
                "Ensure {task_recreation} happens {recurrence} .",
                # --- NEW TEMPLATES ---
                "Jot down {task_work} for {date_relative} .",
                "I must tackle {task_student} {time_relative} .",
                "Tick {task_recreation} off the list please .",
                "How much time do I need for {task_work} ?",
                "Remind {person_work} to finish {task_work} before {date_absolute} .",
                "I am giving myself {duration} to complete {task_student} .",
                "Shift the due date of {task_work} to {date_relative} ."
            ],
            
            "val_preferences_and_reminders": [
                "Ensure I am marked as {pref_type} {condition} .",
                "My calendar should reflect {pref_type} from {time_absolute} to {time_absolute} .",
                "I want an alarm for {event_work} {reminder_offset} .",
                "Stop pinging me about {event_student} .",
                "Change my notification to {reminder_offset} .",
                "Apply {pref_type} to my entire {date_relative} schedule .",
                "Do not allow bookings {condition} .",
                # --- NEW TEMPLATES ---
                "Give me a nudge about {event_work} {reminder_offset} .",
                "I need a prompt {reminder_offset} {event_student} .",
                "Update my status to {pref_type} {condition} .",
                "I am strictly {pref_type} {date_relative} .",
                "Clear all alarms for {event_recreation} .",
                "Can you set my calendar to {pref_type} from {time_absolute} ?",
                "Ensure I am undisturbed {condition} ."
            ],
            
            "val_queries_and_general": [
                "Is there an opening for {duration} {date_relative} ?",
                "When is my next free hour {condition} ?",
                "Show me my itinerary for {date_absolute} .",
                "What am I meant to be doing {time_relative} ?",
                "Find a window to collaborate with {person_work} {date_relative} .",
                # --- NEW TEMPLATES ---
                "What does my day look like {date_relative} ?",
                "Scan my diary for a {duration} gap {date_absolute} .",
                "Am I completely booked up {time_relative} ?",
                "Point out any clashes {date_relative} .",
                "Give me the rundown for {time_relative} ."
            ]
        }

    def generate(self) -> Tuple[List[str], List[int]]:
        category = random.choice(list(self.templates.keys()))
        template = random.choice(self.templates[category])
        
        builder = SentenceBuilder()
        parts = re.split(r'(\{[^}]*\})', template)
        
        for part in parts:
            if part.startswith('{') and part.endswith('}'):
                key = part[1:-1]
                if key in COMPONENT_POOLS:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
            else:
                builder.add_text(part)
        
        return builder.get_output()
# -----------------------------------------------------------------
# 6. Noise Injection
# -----------------------------------------------------------------
def introduce_typo(word: str) -> str:
    if len(word) < 4 or random.random() > 0.03:
        return word
    qwerty_map = {'a': 's', 's': 'd', 'e': 'w', 'r': 't', 't': 'y', 'o': 'p', 'i': 'u', 'l': 'k', 'm': 'n'}
    idx = random.randint(1, len(word) - 2)
    char = word[idx].lower()
    if char in qwerty_map and random.random() < 0.5:
        replacement = qwerty_map[char] if word[idx].islower() else qwerty_map[char].upper()
        return word[:idx] + replacement + word[idx+1:]
    return word

def inject_noise(tokens: List[str], tags: List[int]) -> Tuple[List[str], List[int]]:
    noisy_tokens = []
    noisy_tags = []
    
    for token, tag in zip(tokens, tags):
        if random.random() < 0.03:
            token = introduce_typo(token)
        if random.random() < 0.1:
            token = token.lower()
        
        noisy_tokens.append(token)
        noisy_tags.append(tag)
    
    if noisy_tokens and noisy_tokens[-1] in ['.', '?', '!'] and random.random() < 0.3:
        noisy_tokens = noisy_tokens[:-1]
        noisy_tags = noisy_tags[:-1]
    
    return noisy_tokens, noisy_tags


# -----------------------------------------------------------------
# 7. NEW Negative Examples (Strict Validation)
# -----------------------------------------------------------------
NEW_NEGATIVE_PHRASES = [
    "Turn the heating up to twenty degrees",
    "Where did I put my keys this morning",
    "I genuinely cannot stand the rain today",
    "How many miles is it to Manchester",
    "Book me a taxi to the airport",
    "Can you order a pizza for delivery",
    "The wifi is running incredibly slow today",
    "Did you hear the news about the election",
    "I need to wash my clothes later",
    "What is the battery percentage on my phone",
    "Play the latest podcast episode",
    "My computer screen just went blank",
    "I think the milk has gone bad",
    "Do you remember what happened last year",
    "Please lower the volume on the television",
    "The traffic on the M25 is awful right now",
    "I am craving some chocolate bisuits",
    "Turn off the alarm it is too loud",
    "What time does the supermarket shut",
    "Can you read my messages out loud"
]

# -----------------------------------------------------------------
# 8. Main Generation Script
# -----------------------------------------------------------------
def main():
    os.makedirs("./modernbert_data", exist_ok=True)
    generator = StrictValidationSystem()
    dataset = []

    print("=" * 60)
    print("ModernBERT NER Strict Validation Generator")
    print("=" * 60)
    print(f"Total labels: {len(ALL_LABELS)}")
    print(f"Positive examples to generate: {TOTAL_POSITIVE}")
    print(f"Negative examples to generate: {NEGATIVE_COUNT}")
    print()

    print("Generating positive holdout examples...")
    for _ in tqdm(range(TOTAL_POSITIVE)):
        tokens, tags = generator.generate()
        if random.random() < 0.2:
            tokens, tags = inject_noise(tokens, tags)
        dataset.append((tokens, tags))

    print(f"Generating {NEGATIVE_COUNT} negative holdout examples...")
    for _ in tqdm(range(NEGATIVE_COUNT)):
        phrase = random.choice(NEW_NEGATIVE_PHRASES)
        tokens = phrase.split()
        tags = [LABEL_TO_ID["O"]] * len(tokens)
        dataset.append((tokens, tags))

    random.shuffle(dataset)

    output_path = "./modernbert_data/ner_strict_validation.jsonl"
    with open(output_path, "w") as f:
        for tokens, tags in dataset:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")

    print("\n" + "=" * 60)
    print("Strict Validation Dataset Complete")
    print("=" * 60)
    print(f"Total holdout examples: {len(dataset)}")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    main()