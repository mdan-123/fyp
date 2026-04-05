# ===============================================================
# create_deberta_ner_validation_v3.py
# ZERO LEAKAGE VALIDATION GENERATOR FOR DeBERTa-v3
# Fully isolated component pools using the 31-Label Schema
# ===============================================================

import json
import random
import re
import os
from tqdm import tqdm
from typing import List, Dict, Tuple
from collections import defaultdict

# -----------------------------------------------------------------
# 1. Configuration & Labels
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

NUM_VAL_POSITIVE = 1500
NUM_VAL_NEGATIVE = 750

VAL_DISTRACTORS = ["frankly", "kindly", "perhaps", "I reckon", "to be fair", "anyhow", "obviously", "essentially", "if you don't mind", "as it happens", "in truth", "needless to say"]

# -----------------------------------------------------------------
# 2. ZERO-LEAKAGE Component Pools
# -----------------------------------------------------------------
# These words do NOT appear in the V8 Training Generator.
COMPONENT_POOLS = {
    "event_type": [
        "huddle", "forum", "gathering", "summit", "conclave", "get-together", 
        "touchbase", "debrief", "assembly", "masterclass", "practicum", "plenary", 
        "powwow", "meetup", "briefing session", "induction"
    ],
    "event_ref": [
        "the aforementioned entry", "this engagement", "the scheduled matter", 
        "that block", "the arranged time", "the current reservation", 
        "this calendar item", "the planned activity", "the fixture"
    ],
    "task_work": [
        "server diagnostics", "brand restructuring", "B2B outreach", 
        "Q1 performance analysis", "infrastructure scaling", "compliance training", 
        "asset reallocation", "merger discussion", "contract renewal", "tax filing",
        "health and safety audit", "shareholder communication"
    ],
    "task_study": [
        "Quantum mechanics homework", "Roman history paper", "French oral exam", 
        "botany fieldwork", "sociology presentation", "archaeology dig prep", 
        "calculus workshop", "grammar study", "geography module review", "art critique"
    ],
    "task_personal": [
        "getting the car serviced", "optician visit", "buying a birthday present", 
        "picking up a parcel", "visiting the in-laws", "cooking dinner", 
        "watching a film", "house viewing", "tax return", "plumbing repair",
        "renewing the broadband", "collecting the kids"
    ],
    "participant": [
        "Mr. Henderson", "the consultants", "Emma", "David", "the visiting lecturer", 
        "the executive committee", "my mentor", "the neighbors", "the mechanics", 
        "Dr. Gupta", "the project sponsor", "the freelancers", "the decorators"
    ],
    "location": [
        "the dining room", "WebEx", "Skype", "Google Hangouts", "the physics building", 
        "Cafe Nero", "the third-floor boardroom", "the recreation center", 
        "the town hall", "the gallery", "Lab 2B", "the squash court", "Building C"
    ],
    "abs_date": [
        "Thanksgiving", "Mother's Day", "4th of April", "22nd September", 
        "03-11-2025", "August 18th", "New Year's Day", "10/10/2024", "the 31st of March"
    ],
    "rel_date": [
        "a month from now", "the end of the year", "this coming autumn", "next spring", 
        "the day before the deadline", "some point next week", "the following evening", 
        "in precisely three days", "a short while from today"
    ],
    "day": [
        "every Thursday", "Tuesday evenings", "Sunday afternoons", 
        "the second Wednesday", "Saturday mornings", "Wednesdays", "Thursdays"
    ],
    "abs_time": [
        "four in the afternoon", "seven fifteen AM", "22:00", "15:45", 
        "ten thirty at night", "exactly 1 PM", "eight forty-five", "five to eight", 
        "eleven in the morning", "thirteen hundred hours"
    ],
    "rel_time": [
        "suppertime", "mid-afternoon", "in the dead of night", 
        "during the morning commute", "right after lunch", "before the shift ends", 
        "at twilight", "first available moment"
    ],
    "end_time": [
        "until eight tonight", "16:00", "four PM exactly", 
        "the end of the working day", "nine forty-five", "until dark", "20:00 hours"
    ],
    "duration": [
        "one full week", "a quick 20 minutes", "exactly forty minutes", 
        "three and a half hours", "a short spell", "forty-eight hours", 
        "an entire month", "ten minutes max", "fifty-five mins"
    ],
    "recurrence": [
        "each and every morning", "on a yearly basis", "every third week", 
        "bimonthly", "six times a year", "daily at dawn", "every leap year", 
        "every ten days", "each trimester"
    ],
    "reminder_time": [
        "forty-five minutes beforehand", "a full day prior", "just before it begins", 
        "one week ahead of time", "three days before", "at the very last minute"
    ],
    "preference": [
        "without fail", "crucial", "make it mandatory", "optional", "if time permits", 
        "as a last resort", "absolute top priority", "keep it flexible", 
        "unconfirmed", "provisional"
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
# 3. Helper Functions & Builders
# -----------------------------------------------------------------
def split_off_punctuation(word: str) -> List[str]:
    if not word: return []
    if re.fullmatch(r'[^\w\s]+', word): return [word]
    if re.search(r'\d+:\d+', word) or re.search(r'\d+\s*[ap]\.?m\.?', word, re.I): return [word]
    m = re.match(r'^(.+?)([^\w\s]+)$', word)
    if m:
        word_part, punct = m.groups()
        return [word_part, punct]
    return [word]

def introduce_val_typo(word: str) -> str:
    if len(word) < 5 or random.random() > 0.08: return word
    qwerty_map = {'a': 's', 's': 'd', 'e': 'w', 'r': 't', 't': 'y', 'o': 'p', 'i': 'u', 'l': 'k'}
    idx = random.randint(1, len(word) - 2)
    char = word[idx].lower()
    if char in qwerty_map and random.random() < 0.5:
        return word[:idx] + (qwerty_map[char] if word[idx].islower() else qwerty_map[char].upper()) + word[idx+1:]
    return word[:idx] + word[idx+1:]

class SentenceBuilder:
    def __init__(self):
        self.tokens = []

    def add_entity(self, text, etype):
        words = text.split()
        for i, word in enumerate(words):
            word = introduce_val_typo(word)
            parts = split_off_punctuation(word)
            for j, part in enumerate(parts):
                tag = f"B-{etype}" if i == 0 and j == 0 else f"I-{etype}"
                self.tokens.append((part, tag))

    def add_text(self, text):
        for word in text.split():
            word = introduce_val_typo(word)
            parts = split_off_punctuation(word)
            for part in parts:
                self.tokens.append((part, "O"))

    def get_output(self):
        return [t[0] for t in self.tokens], [LABEL_TO_ID[t[1]] for t in self.tokens]

# -----------------------------------------------------------------
# 4. Validation Template System
# -----------------------------------------------------------------
class ValidationTemplateSystem:
    def __init__(self):
        self.templates = {
            "validation_complex": [
                "I require a {event_type} focused on {task_work} alongside {participant} located in {location} spanning from {abs_time} to {end_time} .",
                "Ensure {location} is secured for {duration} regarding the {task_study} {preference} .",
                "Are we able to set up {recurrence} {event_type} proceedings with {participant} {day} {rel_time} ?",
                "I would ask you to designate {duration} {rel_date} specifically for {task_personal} {preference} .",
                "Adjust {event_ref} to take place {abs_date} at {abs_time} and alert me {reminder_time} ."
            ],
            "validation_modifications": [
                "Revise {event_ref} , making it fall on {abs_date} {rel_time} .",
                "That is incorrect , shift the {event_type} to commence at {abs_time} {preference} .",
                "In reality , {event_ref} belongs in {location} instead .",
                "I neglected to mention that {participant} needs adding to {event_ref} ."
            ],
            "validation_abstract": [
                "{rel_time} {day} happens to be when {task_personal} {recurrence} is needed .",
                "{preference} locate a vacancy for {task_work} around {rel_date} .",
                "When {participant} is available {rel_date} , lock in a {duration} {event_type} .",
                "My availability is {abs_time} {day} to cover the {event_type} on {task_study} ."
            ],
            "validation_direct": [
                "Fix a {event_type} for {task_work} with {participant} .",
                "I need to sort out {task_personal} {rel_date} .",
                "Alert me {reminder_time} concerning {task_personal} .",
                "Confirm {location} for the {task_study} {preference} ."
            ]
        }

    def generate(self):
        cat = random.choice(list(self.templates.keys()))
        template = random.choice(self.templates[cat])
        builder = SentenceBuilder()
        
        if random.random() < 0.1:
            builder.add_text(random.choice(VAL_DISTRACTORS))

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
# 5. Dataset Generation 
# -----------------------------------------------------------------
def main():
    os.makedirs("./deberta_data", exist_ok=True)
    generator = ValidationTemplateSystem()
    dataset = []

    print("Generating Zero-Leakage Validation Dataset...")
    for _ in tqdm(range(NUM_VAL_POSITIVE)):
        tokens, tags = generator.generate()
        if random.random() < 0.2:
            tokens = [t.lower() if random.random() < 0.5 else t for t in tokens]
        dataset.append({"tokens": tokens, "ner_tags": tags})

    # Strict Negative Phrases (No scheduling vocabulary)
    negative_phrases = [
        "The cat sat on the mat", "Where is the nearest petrol station", 
        "I bought a new pair of shoes yesterday", "The sky is particularly blue today",
        "Could you pass the salt please", "My television is broken",
        "What is the capital of Australia", "I enjoy listening to classical music",
        "The train arrived exactly on time", "She painted the entire house green",
        "How much does a pint of milk cost", "The novel was incredibly boring"
    ]
    
    for _ in range(NUM_VAL_NEGATIVE):
        phrase = random.choice(negative_phrases)
        tokens = phrase.split()
        tags = [LABEL_TO_ID["O"]] * len(tokens)
        dataset.append({"tokens": tokens, "ner_tags": tags})

    random.shuffle(dataset)
    
    with open("./deberta_data/validation.jsonl", "w") as f:
        for ex in dataset:
            f.write(json.dumps(ex) + "\n")

    print(f"\nValidation Generation Complete! Saved {len(dataset)} examples.")
    print("Use this file in your training script by pointing the 'validation' argument to './deberta_data/validation.jsonl'.")

if __name__ == "__main__":
    main()