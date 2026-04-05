# ===============================================================
# create_deberta_ner_dataset_v8.py
# OPTIMISED FOR MAXIMUM DIVERSITY & UK CONTEXT
# Context-Specific Templates (Work, Student, Recreation)
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
    "O", "B-TASK_TITLE", "I-TASK_TITLE", "B-EVENT_TYPE", "I-EVENT_TYPE",
    "B-EVENT_REF", "I-EVENT_REF", "B-PARTICIPANT", "I-PARTICIPANT",
    "B-LOCATION", "I-LOCATION", "B-ABS_DATE", "I-ABS_DATE",
    "B-REL_DATE", "I-REL_DATE", "B-DAY", "I-DAY",
    "B-ABS_TIME", "I-ABS_TIME", "B-REL_TIME", "I-REL_TIME",
    "B-END_TIME", "I-END_TIME", "B-DURATION", "I-DURATION",
    "B-RECURRENCE", "I-RECURRENCE", "B-REMINDER_TIME", "I-REMINDER_TIME",
    "B-PREFERENCE", "I-PREFERENCE"
]

LABEL_TO_ID = {l: i for i, l in enumerate(ALL_LABELS)}
ID_TO_LABEL = {i: l for i, l in enumerate(ALL_LABELS)}

TOTAL_POSITIVE = 30000 
NEGATIVE_COUNT = 6000
EVAL_PERCENTAGE = 0.10

# -----------------------------------------------------------------
# 2. Ultra-Expanded Component Pools
# -----------------------------------------------------------------
COMPONENT_POOLS = {
    "event_type": [
        "scrum", "standup", "sprint planning", "backlog grooming", "post-mortem",
        "consultation", "therapy", "coaching", "webinar", "panel", "symposium",
        "colloquium", "roundtable", "fireside chat", "board meeting", "townhall",
        "catch-up", "1-on-1", "sync", "review", "appraisal", "coffee chat", 
        "brainstorming session", "all-hands", "retro", "kick-off", "deep dive", 
        "working session", "check-in", "committee meeting", "progress update",
        "performance review", "client pitch", "strategy session", "away day",
        "tutorial", "seminar", "lecture", "lab session", "study group"
    ],
    "event_ref": [
        "that invite", "the previous slot", "the placeholder", "the original time",
        "that recurring one", "my last booking", "the tentative invite",
        "the booking", "this event", "that meeting", "the session we planned",
        "the diary invite", "my next slot", "the existing appointment",
        "the catch-up", "that slot in the diary"
    ],
    "task_work": [
        "API integration", "Cloud migration", "OAuth debugging", "Unit testing",
        "Project Orion", "the Zeta rollout", "GDPR audit", "ISO certification",
        "Stakeholder interview", "UX research", "Wireframe review", "MVP demo",
        "Legacy code refactor", "System stress test", "Deployment pipeline",
        "writing the report", "finalising the slides", "quarterly taxes", 
        "PR review", "server maintenance", "client onboarding", "drafting the contract", 
        "updating the spreadsheet", "budget forecasting", "inventory check",
        "marketing strategy", "social media planning", "payroll processing",
        "signing off the accounts", "sorting the Q4 figures"
    ],
    "task_study": [
        "Neural Networks lab", "Discrete Math quiz", "Compiler design", 
        "Ethics essay", "Case study 4", "Logic gates homework", "Seminar prep",
        "Library research", "Peer review session", "Mock viva", "Poster design",
        "reading week prep", "dissertation research", "marking papers", 
        "peer programming", "revision", "coursework", "lab prep",
        "group project presentation", "literature review", "data collection",
        "revising for finals", "writing the methodology section", "uni prep"
    ],
    "task_personal": [
        "Boiler service", "Window cleaning", "Passport renewal", "Visa interview",
        "GP checkup", "Physio session", "Personal training", "Bank visit",
        "Car MOT", "Utility bill payment", "Council tax query", "Vet appointment",
        "picking up the dry cleaning", "calling mum", "walking the dog", 
        "dentist appointment", "seeing the GP", "doing the weekly shop", 
        "fixing the boiler", "watching the match", "pub quiz", "getting a haircut",
        "picking up a prescription", "viewing a flat", "renewing insurance",
        "Sunday roast", "five-a-side football", "grabbing a pint", "having a brew"
    ],
    "participant": [
        "the external vendors", "the legal advisors", "the board members", 
        "Professor Sterling", "Dr. Aris", "the tech leads", "the DevOps team",
        "my therapist", "the personal trainer", "the landlord's agent", "the HR rep",
        "the lads", "the girls", "the whole team", "my line manager", "the flatmates", 
        "the electrician", "the plumber", "Dr. Smith", "Professor Jones", "the client", 
        "the investors", "the letting agent", "the academic advisor", "the tutor"
    ],
    "location": [
        "Conference Room Alpha", "Huddle Room 2", "the main hall", "the lab",
        "Starbucks High St", "WeWork 4th floor", "the lobby", "Home Office",
        "Virtual - Zoom", "Teams (Join via link)", "The Quadrangle", "Silent Zone",
        "the local pub", "the SU", "the library silent zone", "meeting room 3", 
        "the breakout area", "the hot desk", "remote", "hybrid", "client office", 
        "the canteen", "the lecture theatre", "the seminar room", "coffee shop",
        "the SU bar", "the student union", "my flat", "halls of residence"
    ],
    "abs_date": [
        "Halloween", "Bank Holiday Monday", "New Year's Eve", "2026-05-15",
        "June 1st", "Next Christmas", "The 14th of Feb", "St Patrick's Day",
        "Christmas Day", "Boxing Day", "Guy Fawkes Night", "5th of November", 
        "1st May", "31st October", "Easter Sunday", "Valentine's Day", "12/08/2026"
    ],
    "rel_date": [
        "the coming Friday", "a week from Tuesday", "the next working day",
        "end of the quarter", "mid-month", "sometime in April", "this weekend",
        "this coming Monday", "the weekend after next", "a fortnight on Tuesday", 
        "sometime next week", "later today", "the day after tomorrow", "next term"
    ],
    "day": [
        "every other Monday", "weekdays only", "weekends", "Tuesday and Thursday",
        "the first Monday of the month", "bi-weekly on Fridays",
        "Monday mornings", "Friday afternoons", "mid-week", "every Wednesday",
        "Saturdays", "Sundays", "any weekday"
    ],
    "abs_time": [
        "08:00", "13:30", "midday", "11:45 PM", "quarter past nine", "half six",
        "ten to ten", "16:15", "noon sharp", "07:30 AM",
        "13:00", "14:00", "half eight", "quarter to ten", "midnight",
        "five o'clock", "half past two", "nine a.m."
    ],
    "rel_time": [
        "over lunch", "post-work", "pre-dawn", "golden hour", "business hours",
        "during my commute", "late night", "first available slot",
        "first thing in the morning", "end of the day", "afternoon break",
        "dinnertime", "early evening", "before breakfast"
    ],
    "end_time": [
        "18:00", "close of play", "until dusk", "six thirty", "5 PM sharp",
        "half past five", "midnight", "two in the afternoon", "19:30"
    ],
    "duration": [
        "90 mins", "a full day", "45 minutes", "a quick 15", "two hours max",
        "half an hour", "three sessions of 20 mins", "an entire afternoon",
        "just ten minutes", "a solid hour", "all morning", "45 mins tops"
    ],
    "recurrence": [
        "quarterly", "semi-annually", "every 3 weeks", "on alternate months",
        "the third Wednesday monthly", "fortnightly on pay day",
        "every single day", "once a term", "annually", "every fortnight",
        "twice a week", "every weekend"
    ],
    "reminder_time": [
        "30 mins prior", "the night before", "2 days ahead", "at the start",
        "10 minutes after", "periodically during", "an hour beforehand",
        "first thing that morning", "five minutes before", "a week in advance"
    ],
    "preference": [
        "as a draft", "must not clash", "high priority", "tentative", 
        "low urgency", "strictly after 10am", "don't double book", "urgent!",
        "pencilled in", "if possible", "ideally", "critical", "low priority",
        "whenever suits", "as a backup plan", "if there is a cancellation"
    ]
}

ENTITY_MAPPING = {
    "event_type": "EVENT_TYPE", "event_ref": "EVENT_REF",
    "task_work": "TASK_TITLE", "task_study": "TASK_TITLE", "task_personal": "TASK_TITLE",
    "participant": "PARTICIPANT", "location": "LOCATION",
    "abs_date": "ABS_DATE", "rel_date": "REL_DATE", "day": "DAY",
    "abs_time": "ABS_TIME", "rel_time": "REL_TIME", "end_time": "END_TIME",
    "duration": "DURATION", "recurrence": "RECURRENCE",
    "reminder_time": "REMINDER_TIME", "preference": "PREFERENCE"
}

# -----------------------------------------------------------------
# 3. Component Builder Logic
# -----------------------------------------------------------------
class SentenceBuilder:
    def __init__(self):
        self.tokens = []

    def add_entity(self, text, etype):
        words = text.split()
        for i, word in enumerate(words):
            tag = f"B-{etype}" if i == 0 else f"I-{etype}"
            self.tokens.append((word, tag))

    def add_text(self, text):
        for word in text.split():
            self.tokens.append((word, "O"))

    def get_output(self):
        return [t[0] for t in self.tokens], [LABEL_TO_ID[t[1]] for t in self.tokens]

class FinalTemplateSystem:
    def __init__(self):
        self.templates = {
            "work_specific": [
                "Schedule a {event_type} regarding {task_work} with {participant} in {location} .",
                "Can we push the {task_work} {event_type} to {rel_date} {rel_time} ?",
                "I need to do a {duration} {event_type} for {task_work} before {end_time} .",
                "Could you kindly pencil in a {event_type} for {task_work} with {participant} at {location} on {abs_date} around {abs_time} ?",
                "Please ensure {event_ref} is updated to include {participant} and relocated to {location} .",
                "We must organise a {event_type} to discuss {task_work} no later than {rel_date} .",
                "Set up a {duration} {event_type} regarding {task_work} bringing in {participant} {day} ."
            ],
            "student_specific": [
                "Book a {location} for {duration} so we can work on the {task_study} .",
                "I have a {event_type} for {task_study} with {participant} on {day} at {abs_time} .",
                "Remind me {reminder_time} to submit the {task_study} {rel_date} .",
                "Let's sort out {location} for {task_study} {rel_date} {rel_time} for about {duration} .",
                "I need to revise for {task_study} at {location} {preference} .",
                "Make sure to book {location} for {task_study} {preference} .",
                "I 'm free {abs_time} {day} for a {event_type} regarding {task_study} ."
            ],
            "recreation_specific": [
                "Let's grab a pint and do {task_personal} {rel_date} {rel_time} .",
                "I need to sort out {task_personal} {day} morning .",
                "Book {duration} for {task_personal} at {location} {preference} .",
                "Need to organise a {event_type} for {task_personal} at the pub {day} .",
                "Remind me {reminder_time} to join the {event_type} for {task_personal} .",
                "Please block out {duration} on {rel_date} for {task_personal} {preference} .",
                "{rel_time} on {day} is when I want the {task_personal} {recurrence} ."
            ],
            "correction_style": [
                "Change {event_ref} , actually move it to {abs_date} {rel_time} .",
                "No , not {abs_time} , make the {event_type} start at {abs_time} {preference} .",
                "Actually {preference} , make {event_ref} in {location} instead .",
                "Forgot to say , {participant} should be invited to {event_ref} too ."
            ],
            "urgent_requests": [
                "Cancel {event_ref} immediately and instead schedule {task_work} at {abs_time} .",
                "{preference} set up a {event_type} for {task_work} {rel_time} today .",
                "I need a {event_type} with {participant} {rel_date} {preference} .",
                "Move {event_ref} right now to {abs_time} {preference} ."
            ],
            "complex_mixed": [
                "Schedule {event_type} for {task_work} with {participant} in {location} on {abs_date} from {abs_time} to {end_time} .",
                "Can we arrange {recurrence} {event_type} sessions with {participant} every {day} {rel_time} ?",
                "Move {event_ref} to {abs_date} at {abs_time} and set a reminder {reminder_time} .",
                "Book {location} for a {event_type} with {participant} and {participant} {rel_date} ."
            ]
        }

    def generate(self):
        cat = random.choice(list(self.templates.keys()))
        template = random.choice(self.templates[cat])
        builder = SentenceBuilder()
        parts = re.split(r'(\{.*?\})', template)
        for part in parts:
            if part.startswith('{') and part.endswith('}'):
                key = part[1:-1]
                val = random.choice(COMPONENT_POOLS[key])
                etype = ENTITY_MAPPING[key]
                builder.add_entity(val, etype)
            else:
                builder.add_text(part)
        return builder.get_output()

# -----------------------------------------------------------------
# 4. Final Generation Script
# -----------------------------------------------------------------
def main():
    os.makedirs("./deberta_data", exist_ok=True)
    generator = FinalTemplateSystem()
    dataset = []

    print("Generating Domain-Specific High-Density dataset...")
    for _ in tqdm(range(TOTAL_POSITIVE)):
        dataset.append(generator.generate())

    # Negative Samples with UK context and zero scheduler keywords
    negative_phrases = [
        "Turn off the lights", "What is the capital of France?", "Play some music",
        "Set a timer for 5 minutes", "Check the weather in London", "Who won the game?",
        "I need to buy a new laptop", "The stock market is down", "Open the garage door",
        "The weather is lovely today", "Did you see the match last night", "I fancy a cuppa",
        "Are we going to the pub later", "I left my umbrella on the tube", "Can you pass the remote",
        "My train was delayed again", "I am absolutely knackered", "What is for dinner tonight",
        "Have you watched that new series yet", "I need to put the kettle on"
    ]
    for _ in range(NEGATIVE_COUNT):
        phrase = random.choice(negative_phrases)
        tokens = phrase.split()
        tags = [LABEL_TO_ID["O"]] * len(tokens)
        dataset.append((tokens, tags))

    random.shuffle(dataset)
    split = int(len(dataset) * (1 - EVAL_PERCENTAGE))
    
    with open("./deberta_data/train.jsonl", "w") as f:
        for tokens, tags in dataset[:split]:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")
            
    with open("./deberta_data/eval.jsonl", "w") as f:
        for tokens, tags in dataset[split:]:
            f.write(json.dumps({"tokens": tokens, "ner_tags": tags}) + "\n")

    with open("./deberta_data/label_map.json", "w") as f:
        json.dump({"id2label": ID_TO_LABEL, "label2id": LABEL_TO_ID}, f, indent=2)

    print(f"\nCompleted! Generated {len(dataset)} examples with {len(ALL_LABELS)} labels.")

if __name__ == "__main__":
    main()