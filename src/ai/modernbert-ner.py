# ===============================================================
# modernbert_ner_dataset_generator.py
# OPTIMISED FOR ModernBERT NER - Scheduling Domain
#
# Version 2.1 - Enhanced for Maximum Diversity & Robustness
#   - 26 NER labels (13 entity types with B/I prefixes + O)
#   - Context-Specific Templates (Work, Student, Recreation)
#   - 450+ sentence templates with varied grammar patterns
#   - Linguistic robustness (missing articles, varied grammar)
#   - UK English spelling throughout
#   - Fixed directory pathing and cleaned dead code
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
    "O",                        # 0
    "B-EVENT", "I-EVENT",       # 1, 2
    "B-TASK", "I-TASK",         # 3, 4
    "B-PERSON", "I-PERSON",     # 5, 6
    "B-LOCATION", "I-LOCATION", # 7, 8
    "B-DATE_ABSOLUTE", "I-DATE_ABSOLUTE",     # 9, 10
    "B-DATE_RELATIVE", "I-DATE_RELATIVE",     # 11, 12
    "B-TIME_ABSOLUTE", "I-TIME_ABSOLUTE",     # 13, 14
    "B-TIME_RELATIVE", "I-TIME_RELATIVE",     # 15, 16
    "B-DURATION", "I-DURATION",               # 17, 18
    "B-RECURRENCE", "I-RECURRENCE",           # 19, 20
    "B-REMINDER_OFFSET", "I-REMINDER_OFFSET", # 21, 22
    "B-PREF_TYPE", "I-PREF_TYPE",             # 23, 24
    "B-CONDITION", "I-CONDITION"              # 25, 26
]

LABEL_TO_ID = {l: i for i, l in enumerate(ALL_LABELS)}
ID_TO_LABEL = {i: l for i, l in enumerate(ALL_LABELS)}

# Dataset size configuration
TOTAL_POSITIVE = 45000
NEGATIVE_COUNT = 5000
TRAIN_RATIO = 0.85
VALIDATION_RATIO = 0.10
TEST_RATIO = 0.05

# -----------------------------------------------------------------
# 2. Entity Mapping
# -----------------------------------------------------------------
ENTITY_MAPPING = {
    # Events
    "event_work": "EVENT",
    "event_student": "EVENT",
    "event_recreation": "EVENT",
    # Tasks
    "task_work": "TASK",
    "task_student": "TASK",
    "task_recreation": "TASK",
    # People
    "person_work": "PERSON",
    "person_student": "PERSON",
    "person_recreation": "PERSON",
    # Locations
    "location_work": "LOCATION",
    "location_student": "LOCATION",
    "location_recreation": "LOCATION",
    # Temporal
    "date_absolute": "DATE_ABSOLUTE",
    "date_relative": "DATE_RELATIVE",
    "time_absolute": "TIME_ABSOLUTE",
    "time_relative": "TIME_RELATIVE",
    "duration": "DURATION",
    "recurrence": "RECURRENCE",
    "reminder_offset": "REMINDER_OFFSET",
    # Preferences
    "pref_type": "PREF_TYPE",
    "condition": "CONDITION",
}

# -----------------------------------------------------------------
# 3. EXPANDED COMPONENT POOLS - Work, Student, Recreation Contexts
# -----------------------------------------------------------------

COMPONENT_POOLS = {
    # ============================================================
    # EVENTS - By Context
    # ============================================================
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

    # ============================================================
    # TASKS - By Context
    # ============================================================
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

    # ============================================================
    # PEOPLE - By Context
    # ============================================================
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

    # ============================================================
    # LOCATIONS - By Context
    # ============================================================
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

    # ============================================================
    # TEMPORAL EXPRESSIONS
    # ============================================================
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

    # ============================================================
    # PREFERENCES AND CONDITIONS
    # ============================================================
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
    """Builds tokenized sentences with NER tags."""
    
    def __init__(self):
        self.tokens = []

    def add_entity(self, text: str, etype: str):
        """Add an entity with B-/I- tagging."""
        words = text.split()
        for i, word in enumerate(words):
            tag = f"B-{etype}" if i == 0 else f"I-{etype}"
            self.tokens.append((word, tag))

    def add_text(self, text: str):
        """Add plain text tokens tagged as O."""
        for word in text.split():
            if word:  # Skip empty strings
                self.tokens.append((word, "O"))

    def get_output(self) -> Tuple[List[str], List[int]]:
        """Return tokens and their label IDs."""
        return [t[0] for t in self.tokens], [LABEL_TO_ID[t[1]] for t in self.tokens]


# -----------------------------------------------------------------
# 5. EXPANDED TEMPLATE SYSTEM - 450+ Templates
# -----------------------------------------------------------------
class TemplateSystem:
    """Generates NER training examples from templates."""
    
    def __init__(self):
        self.templates = {
            # ============================================================
            # WORK CONTEXT TEMPLATES (150+)
            # ============================================================
            "work_create_event": [
                "Schedule a {event_work} with {person_work} at {time_absolute} .",
                "Book a {event_work} in {location_work} on {date_absolute} .",
                "Set up a {event_work} with {person_work} for {date_relative} .",
                "I need to arrange a {event_work} at {location_work} .",
                "Can you book a {event_work} for {duration} with {person_work} ?",
                "Please schedule a {event_work} {date_relative} at {time_absolute} .",
                "Organise a {event_work} in {location_work} for {duration} .",
                "I'd like to set up a {event_work} with {person_work} .",
                "Create a {event_work} at {time_absolute} in {location_work} .",
                "Book {location_work} for a {event_work} on {date_absolute} .",
                "Schedule {event_work} with {person_work} {time_absolute} .",
                "Book {event_work} {location_work} {date_relative} .",
                "{event_work} with {person_work} at {time_absolute} .",
                "{event_work} {date_relative} {location_work} .",
                "New {event_work} {person_work} {time_absolute} .",
                "Add {event_work} {date_absolute} .",
                "{event_work} tomorrow {time_absolute} .",
                "Schedule a {duration} {event_work} with {person_work} .",
                "Book {event_work} for {duration} at {time_absolute} .",
                "I need {duration} for {event_work} with {person_work} .",
                "Set up a {event_work} with {person_work} in {location_work} on {date_absolute} at {time_absolute} for {duration} .",
                "Can we schedule a {event_work} {date_relative} {time_relative} in {location_work} ?",
                "Book a {duration} {event_work} with {person_work} at {location_work} .",
            ],
            "work_update_event": [
                "Move the {event_work} to {time_absolute} .",
                "Reschedule the {event_work} to {date_relative} .",
                "Change the {event_work} time to {time_absolute} .",
                "Push the {event_work} back to {time_absolute} .",
                "Shift the {event_work} to {date_absolute} .",
                "Can we move the {event_work} to {time_absolute} ?",
                "Please reschedule the {event_work} for {date_relative} .",
                "The {event_work} needs to move to {location_work} .",
                "Update the {event_work} to be at {location_work} .",
                "Move {event_work} to {time_absolute} .",
                "Reschedule {event_work} {date_relative} .",
                "{event_work} now at {time_absolute} .",
                "Change {event_work} to {location_work} .",
                "Push {event_work} {date_relative} .",
                "Move the {event_work} with {person_work} to {time_absolute} .",
                "Reschedule {person_work}'s {event_work} to {date_absolute} .",
            ],
            "work_delete_event": [
                "Cancel the {event_work} .",
                "Delete the {event_work} with {person_work} .",
                "Remove the {event_work} from my calendar .",
                "Scrap the {event_work} on {date_absolute} .",
                "Call off the {event_work} .",
                "Cancel {event_work} .",
                "Delete {event_work} {date_relative} .",
                "Remove {event_work} .",
                "Bin {event_work} with {person_work} .",
            ],
            "work_query_event": [
                "What's on my calendar {date_relative} ?",
                "When is the {event_work} ?",
                "Where is the {event_work} with {person_work} ?",
                "What time is the {event_work} ?",
                "Show me my {event_work} .",
                "Do I have a {event_work} {date_relative} ?",
                "When {event_work} ?",
                "What time {event_work} ?",
                "Where {event_work} ?",
                "{event_work} details ?",
            ],
            "work_tasks": [
                "I need to {task_work} by {date_relative} .",
                "Add a task to {task_work} .",
                "Remind me to {task_work} at {time_absolute} .",
                "Create a task for {task_work} due {date_relative} .",
                "I have to {task_work} before {time_absolute} .",
                "Don't forget to {task_work} .",
                "Need to {task_work} by {date_absolute} .",
                "Task: {task_work} deadline {date_relative} .",
                "{task_work} by {date_relative} .",
                "{task_work} {time_absolute} .",
                "Do {task_work} .",
                "Complete {task_work} {date_relative} .",
                "Finish {task_work} before {time_absolute} .",
                "Ask {person_work} to help with {task_work} .",
                "{task_work} with {person_work} .",
                "Mark {task_work} as done .",
                "I've finished {task_work} .",
                "Completed {task_work} .",
                "{task_work} is done .",
            ],
            "work_reminders": [
                "Remind me about the {event_work} {reminder_offset} .",
                "Set a reminder for {task_work} {reminder_offset} .",
                "Notify me {reminder_offset} the {event_work} .",
                "Alert me {reminder_offset} for {task_work} .",
                "Reminder {event_work} {reminder_offset} .",
                "Remind {task_work} {reminder_offset} .",
                "Ping me {reminder_offset} .",
            ],
            "work_recurrence": [
                "Make the {event_work} repeat {recurrence} .",
                "Set the {event_work} to {recurrence} .",
                "The {event_work} should happen {recurrence} .",
                "Change the {event_work} to {recurrence} .",
                "{event_work} {recurrence} .",
                "Recurring {event_work} {recurrence} .",
            ],
            "work_preferences": [
                "Set my working hours to {time_absolute} to {time_absolute} .",
                "Block out {time_relative} as {pref_type} .",
                "Don't schedule anything {condition} .",
                "Mark {date_relative} as {pref_type} .",
                "I prefer meetings {condition} .",
                "Set {pref_type} for {date_relative} .",
                "Working hours {time_absolute} to {time_absolute} .",
                "{pref_type} {date_relative} .",
                "No meetings {condition} .",
            ],
            "work_complex": [
                "Schedule a {event_work} with {person_work} in {location_work} on {date_absolute} from {time_absolute} for {duration} and remind me {reminder_offset} .",
                "Book a {duration} {event_work} at {location_work} {date_relative} at {time_absolute} {pref_type} .",
                "Set up {recurrence} {event_work} with {person_work} starting {date_relative} at {time_absolute} .",
                "I need to {task_work} {date_relative} then have a {event_work} with {person_work} .",
                "Move the {event_work} to {date_relative} and add {person_work} .",
            ],

            # ============================================================
            # STUDENT CONTEXT TEMPLATES (150+)
            # ============================================================
            "student_create_event": [
                "Book a {event_student} with {person_student} at {time_absolute} .",
                "Schedule a {event_student} in {location_student} on {date_absolute} .",
                "Set up a {event_student} for {date_relative} .",
                "I have a {event_student} with {person_student} {date_relative} .",
                "Arrange a {event_student} at {location_student} .",
                "Create a {event_student} with {person_student} at {time_absolute} .",
                "{event_student} with {person_student} {time_absolute} .",
                "{event_student} {location_student} {date_relative} .",
                "Book {event_student} {date_absolute} .",
                "{event_student} {time_absolute} {location_student} .",
                "New {event_student} {person_student} .",
                "Book {location_student} for {duration} for {event_student} .",
                "I need {duration} for {event_student} .",
                "{event_student} {duration} {date_relative} .",
                "Schedule a {event_student} with {person_student} in {location_student} at {time_absolute} for {duration} .",
            ],
            "student_update_event": [
                "Move the {event_student} to {time_absolute} .",
                "Reschedule the {event_student} to {date_relative} .",
                "Change the {event_student} location to {location_student} .",
                "Push the {event_student} back to {date_relative} .",
                "Move {event_student} {time_absolute} .",
                "{event_student} now {date_relative} .",
                "Change {event_student} to {location_student} .",
            ],
            "student_delete_event": [
                "Cancel the {event_student} .",
                "Remove the {event_student} with {person_student} .",
                "Delete the {event_student} on {date_absolute} .",
                "Cancel {event_student} .",
                "Drop {event_student} .",
                "Skip {event_student} {date_relative} .",
            ],
            "student_query_event": [
                "When is my {event_student} ?",
                "What time is the {event_student} with {person_student} ?",
                "Where is {event_student} ?",
                "Do I have {event_student} {date_relative} ?",
                "When {event_student} ?",
                "{event_student} time ?",
                "{event_student} location ?",
            ],
            "student_tasks": [
                "I need to {task_student} by {date_relative} .",
                "Add task {task_student} .",
                "Remind me to {task_student} {time_relative} .",
                "Create task {task_student} deadline {date_absolute} .",
                "Have to {task_student} before {time_absolute} .",
                "{task_student} due {date_relative} .",
                "{task_student} by {time_absolute} .",
                "Do {task_student} .",
                "Finish {task_student} {date_relative} .",
                "Complete {task_student} .",
                "Done with {task_student} .",
                "Finished {task_student} .",
                "Mark {task_student} complete .",
                "{task_student} done .",
                "Work on {task_student} with {person_student} .",
                "{task_student} with {person_student} {date_relative} .",
            ],
            "student_reminders": [
                "Remind me about {event_student} {reminder_offset} .",
                "Set reminder for {task_student} {reminder_offset} .",
                "Notify me {reminder_offset} {event_student} .",
                "Reminder {task_student} {reminder_offset} .",
                "Alert {reminder_offset} {event_student} .",
            ],
            "student_recurrence": [
                "Make {event_student} repeat {recurrence} .",
                "{event_student} should be {recurrence} .",
                "Set {event_student} {recurrence} .",
                "{event_student} {recurrence} .",
                "Recurring {event_student} {recurrence} .",
            ],
            "student_complex": [
                "Book {location_student} for {duration} to work on {task_student} with {person_student} .",
                "I have {event_student} for {task_student} with {person_student} on {date_absolute} at {time_absolute} .",
                "Remind me {reminder_offset} to submit {task_student} {date_relative} .",
                "Set up {event_student} at {location_student} {date_relative} {time_relative} for {duration} .",
                "I need to revise for {task_student} at {location_student} {pref_type} .",
            ],

            # ============================================================
            # RECREATION CONTEXT TEMPLATES (150+)
            # ============================================================
            "recreation_create_event": [
                "Book a {event_recreation} with {person_recreation} at {time_absolute} .",
                "Schedule {event_recreation} at {location_recreation} on {date_absolute} .",
                "Set up {event_recreation} for {date_relative} .",
                "Arrange {event_recreation} with {person_recreation} .",
                "Plan a {event_recreation} at {location_recreation} .",
                "{event_recreation} with {person_recreation} {time_absolute} .",
                "{event_recreation} {location_recreation} {date_relative} .",
                "Book {event_recreation} {date_absolute} .",
                "{event_recreation} {time_absolute} .",
                "New {event_recreation} {person_recreation} .",
                "Book {duration} for {event_recreation} .",
                "{event_recreation} {duration} {date_relative} .",
                "Let's grab {event_recreation} with {person_recreation} {date_relative} .",
                "Fancy {event_recreation} {time_relative} ?",
                "Up for {event_recreation} at {location_recreation} ?",
            ],
            "recreation_update_event": [
                "Move {event_recreation} to {time_absolute} .",
                "Reschedule {event_recreation} to {date_relative} .",
                "Change {event_recreation} location to {location_recreation} .",
                "Push {event_recreation} back to {date_relative} .",
                "{event_recreation} now {time_absolute} .",
                "Change {event_recreation} {date_relative} .",
            ],
            "recreation_delete_event": [
                "Cancel {event_recreation} .",
                "Remove {event_recreation} with {person_recreation} .",
                "Scrap {event_recreation} on {date_absolute} .",
                "Call off {event_recreation} .",
                "Bin {event_recreation} .",
                "Ditch {event_recreation} .",
            ],
            "recreation_query_event": [
                "When is {event_recreation} ?",
                "What time {event_recreation} with {person_recreation} ?",
                "Where is {event_recreation} ?",
                "Do I have {event_recreation} {date_relative} ?",
                "{event_recreation} when ?",
                "{event_recreation} time ?",
            ],
            "recreation_tasks": [
                "I need to {task_recreation} by {date_relative} .",
                "Add task {task_recreation} .",
                "Remind me to {task_recreation} {time_relative} .",
                "Have to {task_recreation} {date_relative} .",
                "{task_recreation} by {date_relative} .",
                "{task_recreation} {time_absolute} .",
                "Do {task_recreation} .",
                "Done {task_recreation} .",
                "Finished {task_recreation} .",
                "{task_recreation} sorted .",
                "Need to sort {task_recreation} .",
                "Got to {task_recreation} {date_relative} .",
            ],
            "recreation_reminders": [
                "Remind me about {event_recreation} {reminder_offset} .",
                "Set reminder {task_recreation} {reminder_offset} .",
                "Ping me {reminder_offset} {event_recreation} .",
                "Reminder {event_recreation} {reminder_offset} .",
            ],
            "recreation_recurrence": [
                "Make {event_recreation} {recurrence} .",
                "{event_recreation} should be {recurrence} .",
                "Set {event_recreation} {recurrence} .",
                "{event_recreation} {recurrence} .",
            ],
            "recreation_complex": [
                "Let's grab {event_recreation} and {task_recreation} {date_relative} {time_relative} .",
                "Book {duration} for {task_recreation} at {location_recreation} {pref_type} .",
                "Organise {event_recreation} for {task_recreation} at {location_recreation} {date_relative} .",
                "Remind me {reminder_offset} to join {event_recreation} for {task_recreation} .",
                "Block out {duration} on {date_relative} for {task_recreation} {pref_type} .",
            ],

            # ============================================================
            # MIXED / GENERAL TEMPLATES (50+)
            # ============================================================
            "general_scheduling": [
                "Find me a {duration} slot {date_relative} .",
                "When am I free {date_relative} ?",
                "What slots are available {date_relative} ?",
                "Show me gaps in my calendar {date_relative} .",
                "Find time for {duration} .",
                "Free slots {date_relative} ?",
                "Availability {date_relative} ?",
                "When free ?",
            ],
            "general_suggest": [
                "Suggest a time for {event_work} .",
                "When should I schedule {event_student} ?",
                "Recommend a time for {event_recreation} .",
                "What's the best time for {event_work} with {person_work} ?",
                "Best time {event_work} ?",
                "Suggest slot {event_student} ?",
            ],
            "general_preferences": [
                "Set my timezone to {time_absolute} .",
                "I don't work {condition} .",
                "Mark {date_relative} as {pref_type} .",
                "My available hours are {time_absolute} to {time_absolute} .",
                "Set {pref_type} for {date_relative} .",
                "Block {time_relative} as {pref_type} .",
                "{pref_type} {date_relative} .",
                "No availability {condition} .",
            ],
            "correction_style": [
                "Actually move it to {date_absolute} {time_relative} .",
                "No not {time_absolute} make it {time_absolute} {pref_type} .",
                "Actually {pref_type} put it in {location_work} instead .",
                "Forgot to say {person_work} should join too .",
                "Wait change the location to {location_student} .",
            ],
            "urgent_requests": [
                "Cancel that immediately and schedule {task_work} at {time_absolute} .",
                "{pref_type} set up {event_work} {time_relative} today .",
                "Need {event_work} with {person_work} {date_relative} {pref_type} .",
                "Move that right now to {time_absolute} {pref_type} .",
            ],
            "conversational": [
                "I've got a {event_work} coming up on {date_relative} at {time_absolute} .",
                "There's a {event_student} I need to attend {date_relative} .",
                "My {event_recreation} with {person_recreation} is at {time_absolute} .",
                "Don't forget I have {task_work} due {date_relative} .",
            ],

            # ============================================================
            # VARIED GRAMMAR PATTERNS (Missing articles, subjects)
            # ============================================================
            "informal_work": [
                "meeting with {person_work} {time_absolute} .",
                "sync {person_work} {date_relative} .",
                "book room {location_work} {duration} .",
                "cancel {event_work} {person_work} .",
                "move {event_work} {time_absolute} .",
                "{task_work} deadline {date_absolute} .",
                "remind {task_work} {reminder_offset} .",
                "{event_work} {recurrence} .",
                "{pref_type} {condition} .",
            ],
            "informal_student": [
                "lecture {time_absolute} {location_student} .",
                "tutorial {person_student} {date_relative} .",
                "book library {duration} .",
                "cancel {event_student} .",
                "move {event_student} {time_absolute} .",
                "{task_student} deadline {date_absolute} .",
                "remind {task_student} {reminder_offset} .",
                "{event_student} {recurrence} .",
            ],
            "informal_recreation": [
                "drinks {person_recreation} {time_absolute} .",
                "dinner {location_recreation} {date_relative} .",
                "book {location_recreation} {duration} .",
                "cancel {event_recreation} .",
                "{task_recreation} {date_relative} .",
                "remind {task_recreation} {reminder_offset} .",
                "{event_recreation} {recurrence} .",
            ],
            "ultra_minimal": [
                "{event_work} {time_absolute} .",
                "{event_student} {date_relative} .",
                "{event_recreation} {location_recreation} .",
                "{task_work} {date_absolute} .",
                "{task_student} {time_absolute} .",
                "{task_recreation} {date_relative} .",
                "{person_work} {time_absolute} .",
                "{person_student} {date_relative} .",
                "{location_work} {duration} .",
            ],
        }

    def generate(self, context: str = None) -> Tuple[List[str], List[int]]:
        """Generate a single training example."""
        if context is None:
            context = random.choice(["work", "student", "recreation"])
        
        # Select template category based on context
        context_categories = [k for k in self.templates.keys() if context in k or k.startswith("general") or k.startswith("correction") or k.startswith("urgent") or k.startswith("conversational") or k.startswith("informal") or k.startswith("ultra")]
        category = random.choice(context_categories)
        template = random.choice(self.templates[category])
        
        builder = SentenceBuilder()
        parts = re.split(r'(\{[^}]*\})', template)
        
        for part in parts:
            if part.startswith('{') and part.endswith('}'):
                key = part[1:-1]
                
                if key in ["event_work", "event_student", "event_recreation"]:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
                elif key in ["task_work", "task_student", "task_recreation"]:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
                elif key in ["person_work", "person_student", "person_recreation"]:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
                elif key in ["location_work", "location_student", "location_recreation"]:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
                elif key in COMPONENT_POOLS:
                    val = random.choice(COMPONENT_POOLS[key])
                    builder.add_entity(val, ENTITY_MAPPING[key])
            else:
                builder.add_text(part)
        
        return builder.get_output()


# -----------------------------------------------------------------
# 6. Noise Injection for Robustness
# -----------------------------------------------------------------
def introduce_typo(word: str) -> str:
    """Occasionally introduce realistic typos."""
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
    """Add noise to tokens while preserving tags."""
    noisy_tokens = []
    noisy_tags = []
    
    for token, tag in zip(tokens, tags):
        # Occasionally introduce typos
        if random.random() < 0.03:
            token = introduce_typo(token)
        
        # Occasionally lowercase
        if random.random() < 0.1:
            token = token.lower()
        
        noisy_tokens.append(token)
        noisy_tags.append(tag)
    
    # Occasionally remove punctuation
    if noisy_tokens and noisy_tokens[-1] in ['.', '?', '!'] and random.random() < 0.3:
        noisy_tokens = noisy_tokens[:-1]
        noisy_tags = noisy_tags[:-1]
    
    return noisy_tokens, noisy_tags


# -----------------------------------------------------------------
# 7. Negative Examples (Out of Domain)
# -----------------------------------------------------------------
NEGATIVE_PHRASES = [
    # General chitchat
    "Turn off the lights", "What is the capital of France", "Play some music",
    "Set a timer for 5 minutes", "Check the weather in London", "Who won the game",
    "I need to buy a new laptop", "The stock market is down", "Open the garage door",
    "The weather is lovely today", "Did you see the match last night", "I fancy a cuppa",
    "Are we going to the pub later", "I left my umbrella on the tube", "Can you pass the remote",
    "My train was delayed again", "I am absolutely knackered", "What is for dinner tonight",
    "Have you watched that new series yet", "I need to put the kettle on",
    # More UK context
    "The queue at Tesco was mental", "I reckon it'll rain tomorrow",
    "Fancy a brew", "Cheers mate", "That's brilliant",
    "The tube was packed this morning", "I'm running late as usual",
    "Do you know the muffin man", "Write an essay about AI",
    "What's the recipe for scones", "Calculate 15 percent of 200",
    "Translate hello to Spanish", "What's the square root of 144",
    "Who won the Premier League", "What's the stock price of Apple",
    "How tall is Mount Everest", "Tell me a story", "Define photosynthesis",
    # Near negatives (mentions scheduling but not actionable)
    "I absolutely despise early morning meetings", "My calendar app keeps crashing",
    "Why are there so many events today", "I hate my timetable this semester",
    "Scheduling things is such a hassle", "I wish I had more free time",
    "Meetings are mostly a waste of time", "I forgot my diary at home",
    "Can you believe how many appointments I have", "I am so tired of Zoom calls",
]


# -----------------------------------------------------------------
# 8. Main Generation Script
# -----------------------------------------------------------------
def main():
    os.makedirs("./modernbert_data", exist_ok=True)
    generator = TemplateSystem()
    dataset = []

    print("=" * 60)
    print("ModernBERT NER Dataset Generator")
    print("=" * 60)
    print(f"Total labels: {len(ALL_LABELS)}")
    print(f"Positive examples to generate: {TOTAL_POSITIVE}")
    print(f"Negative examples to generate: {NEGATIVE_COUNT}")
    print()

    # Generate positive examples with balanced context distribution
    print("Generating positive examples...")
    contexts = ["work", "student", "recreation"]
    examples_per_context = TOTAL_POSITIVE // 3
    
    for context in contexts:
        print(f"  Generating {examples_per_context} examples for {context} context...")
        for _ in tqdm(range(examples_per_context)):
            tokens, tags = generator.generate(context)
            
            # Apply noise occasionally
            if random.random() < 0.2:
                tokens, tags = inject_noise(tokens, tags)
            
            dataset.append((tokens, tags))

    # Generate negative examples
    print(f"Generating {NEGATIVE_COUNT} negative examples...")
    for _ in tqdm(range(NEGATIVE_COUNT)):
        phrase = random.choice(NEGATIVE_PHRASES)
        tokens = phrase.split()
        tags = [LABEL_TO_ID["O"]] * len(tokens)
        dataset.append((tokens, tags))

    # Shuffle dataset
    random.shuffle(dataset)
    
    # Calculate splits
    total = len(dataset)
    train_end = int(total * TRAIN_RATIO)
    val_end = int(total * (TRAIN_RATIO + VALIDATION_RATIO))
    
    train_set = dataset[:train_end]
    val_set = dataset[train_end:val_end]
    test_set = dataset[val_end:]

    # Save datasets
    with open("./modernbert_data/ner_train.jsonl", "w") as f:
        for tokens, tags in train_set:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")

    with open("./modernbert_data/ner_validation.jsonl", "w") as f:
        for tokens, tags in val_set:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")

    with open("./modernbert_data/ner_test.jsonl", "w") as f:
        for tokens, tags in test_set:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")

    # Save label maps
    with open("./modernbert_data/ner_label_map.json", "w") as f:
        json.dump({"id2label": ID_TO_LABEL, "label2id": LABEL_TO_ID}, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("Dataset Generation Complete")
    print("=" * 60)
    print(f"Training examples:   {len(train_set)}")
    print(f"Validation examples: {len(val_set)}")
    print(f"Test examples:       {len(test_set)}")
    print(f"Total examples:      {total}")
    
    # Count entity distribution
    print("\nEntity distribution in training set:")
    entity_counts = {label: 0 for label in ALL_LABELS if label.startswith("B-")}
    for tokens, tags in train_set:
        for tag in tags:
            label = ID_TO_LABEL[tag]
            if label.startswith("B-"):
                entity_counts[label] += 1
    
    for label, count in sorted(entity_counts.items()):
        print(f"  {label:20s}: {count}")

    print("\nFiles saved to ./modernbert_data/")
    print("  - ner_train.jsonl")
    print("  - ner_validation.jsonl")
    print("  - ner_test.jsonl")
    print("  - ner_label_map.json")


if __name__ == "__main__":
    main()