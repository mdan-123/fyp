# ===============================================================
# create_deberta_multilabel_intent_val.py
# ZERO-LEAKAGE Validation & Test Generator for DeBERTa-v3
#
# Features:
#   - Multi-label sequence classification arrays ([0.0, 1.0, 0.0...])
#   - 100% Non-overlapping entity pools and templates
#   - 14 Core Intents (GREETING removed, matching training v16)
#   - ASR-style noise simulation (word drops, homophones, stutters)
#   - Multi-intent compound sentences mapped to secondary labels
#   - SequenceMatcher diversity checks to prevent duplicates
# ===============================================================

import json
import random
import re
import os
import time
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
from difflib import SequenceMatcher
import warnings
warnings.filterwarnings('ignore')

try:
    import language_tool_python
    HAS_GRAMMAR_TOOL = True
except ImportError:
    HAS_GRAMMAR_TOOL = False

# --- CONFIGURATION ---
VALIDATION_EXAMPLES = 2000
TEST_EXAMPLES = 1000
TOTAL_EVAL = VALIDATION_EXAMPLES + TEST_EXAMPLES
SEED = 2024  # Completely different seed from training
random.seed(SEED)

USE_GRAMMAR_CHECK = True        
MAX_ATTEMPTS_PER_INTENT = 20000 

# Ensure identical mapping to Training v16 (GREETING removed)
LABEL_MAP = {
    "CREATE_EVENT": 0,
    "UPDATE_EVENT": 1,
    "DELETE_EVENT": 2,
    "QUERY_EVENT": 3,
    "ADD_PARTICIPANT": 4,
    "REMOVE_PARTICIPANT": 5,
    "NEGATIVE": 6,
    "FIND_FREE_TIME": 7,
    "SUGGEST_TIME": 8,
    "SET_REMINDER": 9,
    "CHANGE_RECURRENCE": 10,
    "SHARE_EVENT": 11,
    "DECLINE_EVENT": 12,
    "SET_PREFERENCES": 13
}

ID_TO_LABEL = {i: intent for intent, i in LABEL_MAP.items()}
NUM_LABELS = len(LABEL_MAP)

# Proportional distribution mapping
SCALE_FACTOR = TOTAL_EVAL / 14500 # Relative to training base sizes

INTENT_TARGET_TOTAL = {
    "CREATE_EVENT": int(2000 * SCALE_FACTOR),
    "UPDATE_EVENT": int(1500 * SCALE_FACTOR),
    "DELETE_EVENT": int(1200 * SCALE_FACTOR),
    "QUERY_EVENT": int(1500 * SCALE_FACTOR),
    "ADD_PARTICIPANT": int(800 * SCALE_FACTOR),
    "REMOVE_PARTICIPANT": int(800 * SCALE_FACTOR),
    "NEGATIVE": int(1000 * SCALE_FACTOR),
    "FIND_FREE_TIME": int(800 * SCALE_FACTOR),
    "SUGGEST_TIME": int(800 * SCALE_FACTOR),
    "SET_REMINDER": int(800 * SCALE_FACTOR),
    "CHANGE_RECURRENCE": int(800 * SCALE_FACTOR),
    "SHARE_EVENT": int(800 * SCALE_FACTOR),
    "DECLINE_EVENT": int(800 * SCALE_FACTOR),
    "SET_PREFERENCES": int(800 * SCALE_FACTOR)
}

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
# 1. NON-OVERLAPPING COMPONENT LISTS (Zero Leakage)
# ----------------------------

WORK_EVENTS = ["board review", "vendor meeting", "compliance audit", "product launch", "quarterly planning", "staff assembly", "training workshop", "webinar", "sales pitch", "negotiation", "contract signing", "recruitment drive", "innovation sprint", "deployment planning", "executive huddle"]
STUDENT_EVENTS = ["thesis committee", "research defense", "grad school fair", "career workshop", "peer review", "literature circle", "practicum", "internship interview", "scholarship interview", "mentorship session", "academic advising", "graduation prep", "honors society", "poster session", "journal club", "methodology workshop", "grant writing"]
PERSONAL_EVENTS = ["therapy session", "vet appointment", "parent-teacher", "car service", "home inspection", "tax prep", "estate planning", "vaccination", "physical therapy", "nutrition consult", "financial planning", "travel consult", "real estate viewing", "legal consult", "mediation", "support group", "volunteer shift", "community board", "homeowner meeting"]

PEOPLE = {
    "work": ["James", "Patricia", "Christopher", "Barbara", "Richard", "Susan", "the directors", "the stakeholders", "the committee", "operations", "legal team", "compliance", "product team", "sales force", "the vendors"],
    "student": ["Dean", "Chancellor", "Registrar", "Department Chair", "Mentor", "Dr. Williams", "Dr. Brown", "peer mentor", "research advisor", "dissertation chair", "postdoc", "the faculty"],
    "personal": ["spouse", "child", "parent", "cousin", "relative", "roommate", "Morgan", "Casey", "Riley", "Avery", "Dakota", "Quinn", "my neighbor", "the contractor"]
}

LOCATIONS = {
    "work": ["headquarters", "branch office", "satellite", "co-working space", "training center", "executive suite", "war room", "webex", "skype", "conference bridge", "huddle room", "the atrium"],
    "student": ["auditorium", "seminar room", "computer lab", "writing center", "counseling center", "admissions office", "grad lounge", "online portal", "blackboard", "canvas", "moodle", "the amphitheater"],
    "personal": ["clinic", "studio", "salon", "garage", "backyard", "patio", "community center", "place of worship", "gallery", "arena", "the town hall", "the vet"]
}

TIMES = ["9:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "early morning", "mid-morning", "late morning", "early afternoon", "mid-afternoon", "late afternoon", "early evening", "next Tuesday", "Wednesday", "Thursday", "next month", "the week after next"]

DURATIONS = ["20 minutes", "25 minutes", "50 minutes", "75 minutes", "90 minutes", "two hours", "three hours", "four hours", "the whole morning", "the entire afternoon", "all evening", "the full day"]

RECURRENCE_PATTERNS = ["once a week", "each Monday", "every Tuesday without fail", "bi-monthly", "twice a month", "quarterly", "every 14 days", "on alternate Fridays", "the second Tuesday of each month", "each weekday morning", "every other morning", "once per calendar month", "each year"]

REMINDER_OFFSETS = ["5 mins prior", "15 mins ahead", "1 day earlier", "the evening before", "at 8 AM on the day", "24 hours in advance", "2 days before", "on the previous afternoon", "at the start of the day", "when the event is about to begin", "just in time"]

PREFERENCE_TYPES = ["availability window", "office hours", "quiet time", "deep work block", "personal time", "do not disturb", "away status", "core hours", "on-call shift", "remote day"]

HOUR_RANGES = ["8:30 to 4:30", "10-6", "11-7", "7:30 to 3:30", "flexible start", "9-3 with flexible lunch", "8-2 and 6-8", "split shift", "9:45 to 5:45"]

CONDITIONS = ["before 8 AM", "after 8 PM", "on public holidays", "during lunch break", "when I'm marked as away", "during company holidays", "if the event is not mandatory", "outside business hours"]

NEGATIVE_QUERIES = [
    "What's the forecast for tomorrow?", "Tell me a riddle", "What's your age?", "What's 42?", 
    "Play a song", "Order Chinese food", "What's the timezone in London?", "Set a timer for 5 minutes", 
    "How do I bake a cake?", "What movies are playing?", "Translate goodbye to French", 
    "Calculate 25% of 400", "Find coffee shops nearby", "Open Netflix", "What's the capital of Germany?", 
    "How deep is the ocean?", "What's your favorite food?", "Tell me a fun fact", "Who won the Super Bowl?", 
    "What's the stock price of Google?", "How many calories in a banana?", "Define gravity", 
    "Who wrote Macbeth?", "What's 15 squared?"
]

NEAR_NEGATIVES = [
    "My calendar looks like a total disaster.", "Scheduling is such a headache.", 
    "I wish my timetable made more sense.", "Do we really need all these meetings?", 
    "I lost my planner again.", "Time management is not my strong suit.", 
    "My diary is completely full and I hate it.", "Why is finding a free slot so impossible?"
]

# ----------------------------
# 2. VALIDATION PARAPHRASE TEMPLATES
# ----------------------------

TEMPLATES = {
    "CREATE_EVENT": [
        "Can we set something up for a {event}?", "I'd like to pencil in a {event}",
        "We should arrange a {event}", "Let's get a {event} on the calendar",
        "Need to block time for a {event}", "Time to schedule that {event} we talked about",
        "Can you put a {event} on my schedule?", "I'm thinking we need a {event}",
        "Could we organize a {event}?", "Should we plan a {event}?",
        "Please establish a {event} at {time}", "Initiate a {event} lasting {duration}",
        "Register me for a {event} in {location}"
    ],
    "UPDATE_EVENT": [
        "We need to adjust the {event} time", "Can we shift the {event} around?",
        "That {event} needs to be moved", "Let's reschedule that {event}",
        "The timing for the {event} should change", "We have to rearrange the {event}",
        "Can we pick a different time for the {event}?", "That {event} won't work at that time",
        "Need to change when we have the {event}", "The {event} should be at a different time"
    ],
    "DELETE_EVENT": [
        "We should call off the {event}", "Let's cancel that {event}",
        "The {event} isn't happening anymore", "We need to scrap the {event}",
        "Can we remove the {event} from the calendar?", "That {event} should be cancelled",
        "I think we should delete the {event}", "The {event} is off",
        "We won't be having that {event}", "Please take the {event} off the schedule"
    ],
    "QUERY_EVENT": [
        "What's on my calendar for {time}?", "Do you know what I have at {time}?",
        "Can you tell me about my {time} schedule?", "What's scheduled for {time}?",
        "Any {event}s on my calendar?", "When's that {event} happening?",
        "What's the plan for {time}?", "Can you check what's up at {time}?",
        "Tell me about my {time} appointments", "What do I have coming up at {time}?"
    ],
    "ADD_PARTICIPANT": [
        "We should include {person} in the {event}", "Let's add {person} to the {event} invite",
        "{person} needs to be at the {event}", "Can we invite {person} to join the {event}?",
        "Make sure {person} is on the {event}", "We ought to have {person} at the {event}",
        "Add {person} to that {event} please", "{person} should be part of the {event}",
        "Include {person} when you schedule the {event}", "Don't forget to add {person} to the {event}"
    ],
    "REMOVE_PARTICIPANT": [
        "{person} shouldn't be at the {event}", "Take {person} off the {event} list",
        "We don't need {person} at the {event}", "Can we exclude {person} from the {event}?",
        "{person} won't be attending the {event}", "Remove {person} from the {event} roster",
        "{person} doesn't need to be at the {event}", "Let's uninvite {person} from the {event}",
        "{person} is out for the {event}", "Drop {person} from the {event}"
    ],
    "NEGATIVE": [],  
    "FIND_FREE_TIME": [
        "Got any availability on {time}?", "When am I open {time}?",
        "Is there a slot free {time}?", "What times are unoccupied {time}?",
        "I need a free window for a {duration} {event}", "Can you spot a gap in my schedule {time}?",
        "Show me when I'm not busy {time}", "Any openings for a {event}?",
        "Do I have unscheduled time {time}?", "When could I squeeze in a {duration} {event}?"
    ],
    "SUGGEST_TIME": [
        "What time would you propose for the {event}?", "Give me a few time options for {event}",
        "Recommend a slot for the {event}", "When do you think is best for the {event}?",
        "Can you advise on timing for {event}?", "Pick a suitable time for {event}",
        "What's your recommendation for the {event} schedule?", "I'm open to suggestions for the {event} time",
        "Help me choose a time for the {event}", "What hour works best for the {event}?"
    ],
    "SET_REMINDER": [
        "Notify me {offset} the {event} starts", "Give me a nudge {offset} the {event}",
        "Set an alert for the {event} {offset}", "I want to be reminded about the {event} {offset}",
        "Can you ping me {offset} the {event}?", "Don't let me forget the {event} - remind me {offset}",
        "Schedule a reminder for the {event} to pop up {offset}", "Alert me when it's time for the {event}",
        "Put a notification on the {event} for {offset}", "Remind me ahead of the {event} by {offset}"
    ],
    "CHANGE_RECURRENCE": [
        "Make this happen {recurrence} instead", "Switch the repetition to {recurrence}",
        "Update the frequency to {recurrence}", "From now on, have it {recurrence}",
        "Change the repeat cycle to {recurrence}", "I want it recurring {recurrence}",
        "Adjust the recurrence pattern to {recurrence}", "Set this to repeat {recurrence} from now",
        "Modify the series to occur {recurrence}", "Turn this into a {recurrence} event"
    ],
    "SHARE_EVENT": [
        "Send the {event} details over to {person}", "Grant {person} access to my {event}",
        "Publish the {event} and invite {person}", "Let {person} peek at the {event}",
        "Forward the calendar item to {person}", "Share the schedule for {event} with {person}",
        "Make {person} a guest of the {event}", "Email the {event} info to {person}",
        "Copy {person} on the {event} invitation", "Allow {person} to view the {event} details"
    ],
    "DECLINE_EVENT": [
        "I have to pass on the {event}", "Regretfully, I can't join the {event}",
        "Count me out of the {event}", "I'm going to skip the {event}",
        "Please convey my apologies for the {event}", "I won't be participating in the {event}",
        "The {event} doesn't work for me, sorry", "I'll have to give the {event} a miss",
        "Please mark me as not attending the {event}", "I'm unable to commit to the {event}"
    ],
    "SET_PREFERENCES": [
        "I'd prefer not to have meetings {condition}", "Set my default schedule as {hours}",
        "Block out {time} for {preference} daily", "Make {time} my {preference} period",
        "Don't show me as available {condition}", "Configure my calendar to {hours}",
        "I want {time} earmarked for {preference}", "Establish {hours} as my standard work hours",
        "Add a recurring {preference} block at {time}", "Update my availability to {hours}"
    ],
}

# MULTI-SENTENCE EXTENSIONS (Validation specific verbiage)
FOLLOW_UPS = {
    "CREATE_EVENT": [
        ("Make sure to add {person} to the list.", "ADD_PARTICIPANT"), 
        ("Set an alert for {offset}.", "SET_REMINDER"),
        ("Have it repeat {recurrence}.", "CHANGE_RECURRENCE")
    ],
    "UPDATE_EVENT": [
        ("Alert {person} that it moved.", "SHARE_EVENT"), 
        ("Ping me {offset} beforehand.", "SET_REMINDER")
    ],
    "DELETE_EVENT": [
        ("I will RSVP no directly.", "DECLINE_EVENT"),
        ("Pass my apologies onto {person}.", "SHARE_EVENT")
    ],
    "FIND_FREE_TIME": [
        ("Recommend these slots to {person}.", "SUGGEST_TIME")
    ]
}

# ----------------------------
# 3. HELPER FUNCTIONS
# ----------------------------

def simulate_asr_noise(text: str, noise_level: float = 0.3) -> str:
    if random.random() > noise_level: return text
    if random.random() > 0.5: text = text.lower()
    if random.random() > 0.5: text = re.sub(r'[^\w\s]', '', text)
    
    # Word drops
    if random.random() > 0.7:
        words = text.split()
        if len(words) > 3:
            short_words = [i for i, w in enumerate(words) if len(w) <= 3]
            if short_words and random.random() > 0.5:
                words.pop(random.choice(short_words))
                text = ' '.join(words)
                
    # Homophones
    homophones = {'their': 'there', 'there': 'their', 'to': 'too', 'too': 'to', 'your': 'youre', 'then': 'than'}
    if random.random() > 0.8:
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in homophones and random.random() > 0.7:
                words[i] = homophones[word.lower()]
        text = ' '.join(words)
        
    # Stutter
    if random.random() > 0.9:
        words = text.split()
        if words and len(words[0]) > 3:
            first_word = words[0]
            words[0] = f"{first_word[0]}-{first_word}" if random.random() > 0.5 else first_word
            if random.random() > 0.5: words.insert(0, first_word)
        text = ' '.join(words)
        
    # Fillers
    if random.random() > 0.7 and len(text.split()) > 3:
        filler = random.choice(["um", "uh", "like", "i mean"])
        if random.random() > 0.5: text = f"{filler} {text}"
        else:
            words = text.split()
            words.insert(random.randint(1, len(words) - 2), filler)
            text = ' '.join(words)
            
    return text

class ValidationGenerator:
    def __init__(self):
        self.used_texts = set()
        
    def get_context_pools(self, context: str) -> Dict:
        if context == "work": return {"events": WORK_EVENTS, "people": PEOPLE["work"], "locations": LOCATIONS["work"]}
        elif context == "student": return {"events": STUDENT_EVENTS, "people": PEOPLE["student"], "locations": LOCATIONS["student"]}
        else: return {"events": PERSONAL_EVENTS, "people": PEOPLE["personal"], "locations": LOCATIONS["personal"]}

    def generate_clean_text(self, primary_intent: str) -> Tuple[Optional[str], List[str]]:
        active_intents = [primary_intent]
        
        if primary_intent == "NEGATIVE":
            pool = NEGATIVE_QUERIES + NEAR_NEGATIVES
            return random.choice(pool), active_intents
            
        context = random.choice(["work", "student", "personal"])
        pools = self.get_context_pools(context)
        template = random.choice(TEMPLATES[primary_intent])
        
        base_event = random.choice(pools["events"])
        base_person = random.choice(pools["people"])
        base_location = random.choice(pools["locations"])
        base_time = random.choice(TIMES)
        base_duration = random.choice(DURATIONS)
        
        # Multi-sentence addition (15% chance)
        if primary_intent in FOLLOW_UPS and random.random() < 0.15: 
            follow_up_text, secondary_intent = random.choice(FOLLOW_UPS[primary_intent])
            template += " " + follow_up_text
            if secondary_intent not in active_intents:
                active_intents.append(secondary_intent)

        filled = template
        
        filled = filled.replace("{event}", base_event)
        filled = filled.replace("{person}", base_person)
        filled = filled.replace("{location}", base_location)
        filled = filled.replace("{time}", base_time)
        filled = filled.replace("{duration}", base_duration)
        
        placeholders = re.findall(r'\{(\w+)\}', filled)
        for ph in placeholders:
            if ph == "recurrence": replacement = random.choice(RECURRENCE_PATTERNS)
            elif ph == "offset": replacement = random.choice(REMINDER_OFFSETS)
            elif ph == "hours": replacement = random.choice(HOUR_RANGES)
            elif ph == "preference": replacement = random.choice(PREFERENCE_TYPES)
            elif ph == "condition": replacement = random.choice(CONDITIONS)
            else: replacement = ""
            filled = filled.replace(f"{{{ph}}}", replacement)
            
        cleaned_text = re.sub(r'\s+', ' ', filled).strip()
        
        # Ensure proper punctuation
        if not cleaned_text.endswith(('.', '!', '?')):
            cleaned_text += '?' if primary_intent in ["QUERY_EVENT", "FIND_FREE_TIME", "SUGGEST_TIME"] else '.'
            
        # Regex Validation Gate
        if re.search(r'\{[a-zA-Z0-9_]+\}', cleaned_text):
            return None, []
            
        return cleaned_text, active_intents

    def generate_split(self, num_examples: int, split_name: str) -> List[Dict]:
        examples = []
        is_validation = (split_name == "validation")
        split_ratio = VALIDATION_EXAMPLES / TOTAL_EVAL if is_validation else TEST_EXAMPLES / TOTAL_EVAL
        
        intent_counts = {intent: int(total * split_ratio) for intent, total in INTENT_TARGET_TOTAL.items()}
        
        # Distribute remainder
        diff = num_examples - sum(intent_counts.values())
        sorted_intents = sorted(intent_counts.keys(), key=lambda x: intent_counts[x], reverse=True)
        for i in range(abs(diff)):
            intent_counts[sorted_intents[i % len(sorted_intents)]] += 1 if diff > 0 else -1

        print(f"\n   Generating {split_name} set ({num_examples} examples)...")
        
        for intent, target_count in intent_counts.items():
            intent_examples = []
            attempts = 0
            
            while len(intent_examples) < target_count and attempts < MAX_ATTEMPTS_PER_INTENT:
                text, active_intents = self.generate_clean_text(intent)
                
                if text is None:
                    attempts += 1
                    continue

                if grammar_tool and intent != "NEGATIVE" and random.random() < 0.8:
                    matches = grammar_tool.check(text)
                    if len(matches) > 1: 
                        attempts += 1
                        continue
                
                # Apply ASR noise
                noise_level = 0.2 if intent == "NEGATIVE" else random.choice([0.1, 0.3])
                text = simulate_asr_noise(text, noise_level=noise_level)
                
                text_clean = text.lower().strip()
                
                # Check if too similar to existing examples
                too_similar = False
                for existing in intent_examples:
                    if abs(len(text_clean) - len(existing["text"].lower().strip())) < 5:
                        seq_matcher = SequenceMatcher(None, text_clean, existing["text"].lower().strip())
                        if seq_matcher.ratio() > 0.85:
                            too_similar = True
                            break
                            
                if not too_similar and text_clean not in self.used_texts:
                    binary_labels = [0.0] * NUM_LABELS
                    for active_intent in active_intents:
                        binary_labels[LABEL_MAP[active_intent]] = 1.0
                        
                    intent_examples.append({
                        "text": text,
                        "labels": binary_labels,
                        "active_intents": active_intents
                    })
                    self.used_texts.add(text_clean)
                
                attempts += 1
            
            examples.extend(intent_examples)
            print(f"      {intent}: {len(intent_examples)}/{target_count} examples generated")
            
        random.shuffle(examples)
        return examples[:num_examples]

# ----------------------------
# 4. MAIN EXECUTION
# ----------------------------
if __name__ == "__main__":
    print("=" * 80)
    print("DeBERTa-v3 Multi-Label Intent Validation & Test Generator")
    print("Version 16.0 - Zero Data Leakage Guarantee (14 Intents + Negative)")
    print("=" * 80)
    
    start_time = time.time()
    
    try:
        generator = ValidationGenerator()
        validation_examples = generator.generate_split(VALIDATION_EXAMPLES, "validation")
        test_examples = generator.generate_split(TEST_EXAMPLES, "test")
        
        os.makedirs("./deberta_data", exist_ok=True)
        
        with open("./deberta_data/multilabel_intent_validation.jsonl", "w") as f:
            for example in validation_examples:
                f.write(json.dumps(example) + "\n")
                
        with open("./deberta_data/multilabel_intent_test.jsonl", "w") as f:
            for example in test_examples:
                f.write(json.dumps(example) + "\n")
                
        print(f"\n✅ Dataset generation complete!")
        print(f"   Validation examples: {len(validation_examples)}")
        print(f"   Test examples: {len(test_examples)}")
        print(f"   Unique texts generated: {len(generator.used_texts)}")
        
        print("\n📝 Sample Validation Examples (Multi-Label):")
        samples = [ex for ex in validation_examples if len(ex["active_intents"]) > 1][:3]
        if not samples:
            samples = validation_examples[:3]
            
        for i, example in enumerate(samples):
            print(f"   {i+1}. '{example['text']}'")
            print(f"      Active Intents: {example['active_intents']}")
        
    except Exception as e:
        print(f"\n❌ Error during dataset generation: {e}")
        import traceback
        traceback.print_exc()