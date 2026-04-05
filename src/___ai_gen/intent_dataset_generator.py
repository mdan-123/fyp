"""
create_intent_dataset.py - DistilBERT Intent Classification Dataset Generator
Version 2.0 - Scheduler Domain with Grammar Check

Generates synthetic training data for 8 distinct intents with context variation,
noise augmentation, second-clause robustness, and grammar validation.
"""

import json
import random
import re
import time
from typing import Dict, List, Tuple, Optional
import numpy as np
import language_tool_python

# ============================================================================
# CONFIGURATION
# ============================================================================
TOTAL_EXAMPLES = 6000
TRAIN_RATIO = 0.9
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# Grammar checking configuration
USE_GRAMMAR_CHECK = True
GRAMMAR_CHECK_LANGUAGE = 'en-GB'  # or 'en-GB'
MAX_GRAMMAR_ERRORS = 2  # Allow minor errors for naturalness
GRAMMAR_CHECK_TIMEOUT = 10  # seconds
RETRY_LIMIT = 5  # Max retries for grammar check

# Intent distribution (approximate)
INTENT_DISTRIBUTION = {
    "CREATE_EVENT": 1500,
    "UPDATE_EVENT": 1000,
    "DELETE_EVENT": 1000,
    "QUERY_EVENT": 1000,
    "ADD_PARTICIPANT": 400,
    "REMOVE_PARTICIPANT": 400,
    "GREETING": 300,
    "NEGATIVE": 300
}

# Label mapping
LABEL_MAP = {
    "CREATE_EVENT": 0,
    "UPDATE_EVENT": 1,
    "DELETE_EVENT": 2,
    "QUERY_EVENT": 3,
    "ADD_PARTICIPANT": 4,
    "REMOVE_PARTICIPANT": 5,
    "GREETING": 6,
    "NEGATIVE": 7
}

# ============================================================================
# INITIALIZE GRAMMAR CHECKER
# ============================================================================

class GrammarChecker:
    """Wrapper for language_tool_python with error handling"""
    
    def __init__(self, language: str = 'en-US', use_checker: bool = True):
        self.use_checker = use_checker
        self.tool = None
        self.initialized = False
        
        if self.use_checker:
            try:
                print(f"Initializing grammar checker ({language})...")
                self.tool = language_tool_python.LanguageTool(language)
                # Speed up by disabling some less important rules
                self.tool.disabled_rules.update({
                    'EN_QUOTES',  # Single vs double quotes
                    'OXFORD_COMMA',  # Oxford comma
                    'COMMA_PARENTHESIS_WHITESPACE',
                    'WHITESPACE_RULE',
                    'SENTENCE_WHITESPACE',
                    'UPPERCASE_SENTENCE_START'  # We handle case variations
                })
                self.initialized = True
                print("Grammar checker initialized successfully.")
            except Exception as e:
                print(f"Warning: Could not initialize grammar checker: {e}")
                print("Continuing without grammar checking...")
                self.use_checker = False
    
    def check_text(self, text: str, max_errors: int = 2) -> Tuple[bool, List[str]]:
        """Check text for grammar errors, return (is_valid, suggestions)"""
        if not self.use_checker or not self.initialized or not self.tool:
            return True, []
        
        try:
            # Skip empty or very short texts
            if len(text.strip()) < 3:
                return True, []
            
            # Don't check all caps texts (often acronyms or emphasis)
            if text.isupper():
                return True, []
            
            # Run grammar check with timeout
            matches = self.tool.check(text)
            
            # Filter out matches we consider acceptable
            filtered_matches = []
            for match in matches:
                rule_id = match.ruleId
                # Skip certain rule categories for naturalness
                if rule_id in {'EN_UNPAIRED_BRACKETS', 'MORFOLOGIK_RULE_EN_US'}:
                    continue
                # Skip capitalization rules for sentences starting with lowercase
                if rule_id == 'UPPERCASE_SENTENCE_START' and text[0].islower():
                    continue
                # Skip spacing rules
                if 'SPACE' in rule_id or 'WHITESPACE' in rule_id:
                    continue
                filtered_matches.append(match)
            
            if len(filtered_matches) <= max_errors:
                return True, []
            else:
                suggestions = [f"{m.ruleId}: {m.message}" for m in filtered_matches[:3]]
                return False, suggestions
                
        except Exception as e:
            # If grammar check fails, accept the text anyway
            print(f"Grammar check error: {e}")
            return True, []
    
    def close(self):
        """Clean up resources"""
        if self.tool:
            self.tool.close()

# Initialize grammar checker
grammar_checker = GrammarChecker(GRAMMAR_CHECK_LANGUAGE, USE_GRAMMAR_CHECK)

# ============================================================================
# CONTEXT POOLS (Work, Student, Personal)
# ============================================================================

# Context-specific events
WORK_EVENTS = [
    "meeting", "conference call", "sync", "standup", "one-on-one",
    "client meeting", "team meeting", "strategy session", "review",
    "planning session", "retrospective", "workshop", "training",
    "demo", "interview", "presentation", "audit", "briefing",
    "debrief", "board meeting", "budget review", "sales call"
]

STUDENT_EVENTS = [
    "lecture", "study session", "lab", "tutorial", "seminar",
    "group project", "office hours", "exam", "quiz", "workshop",
    "thesis meeting", "dissertation defense", "research meeting",
    "library session", "study group", "review session", "practical",
    "colloquium", "symposium", "conference"
]

PERSONAL_EVENTS = [
    "appointment", "lunch", "dinner", "coffee", "drinks",
    "gym session", "yoga class", "doctor appointment", "dentist",
    "haircut", "meetup", "date", "party", "concert", "movie",
    "shopping", "errands", "visitor", "family dinner", "game night"
]

# People/participants
PEOPLE = {
    "work": ["John", "Sarah", "Michael", "Emily", "David", "Lisa", "Robert", "Jennifer",
             "the team", "the client", "marketing", "engineering", "HR", "the board"],
    "student": ["professor", "TA", "study group", "lab partner", "classmate", "advisor",
                "Dr. Smith", "Dr. Johnson", "the tutor", "research group"],
    "personal": ["friend", "family", "partner", "mom", "dad", "sibling", "colleague",
                 "neighbor", "Alex", "Chris", "Taylor", "Jordan"]
}

# Locations
LOCATIONS = {
    "work": ["conference room", "zoom", "teams", "meet", "office", "boardroom",
             "cafeteria", "breakout area", "remote"],
    "student": ["classroom", "lecture hall", "lab", "library", "study room",
                "campus", "online", "student union"],
    "personal": ["home", "restaurant", "cafe", "gym", "park", "mall", "cinema",
                 "pub", "outdoors", "virtual"]
}

# Time expressions
TIMES = [
    "9am", "10:30", "2pm", "3:15", "4:45", "11am", "1pm", "5pm",
    "morning", "afternoon", "evening", "tomorrow", "today", "next week",
    "this Friday", "Monday", "next Monday", "in an hour", "ASAP", "soon",
    "later today", "tonight", "end of day", "first thing"
]

# Durations
DURATIONS = [
    "30 minutes", "an hour", "1 hour", "2 hours", "45 minutes",
    "15 minutes", "half hour", "all day", "the morning", "the afternoon"
]

# Politeness markers
POLITE_PREFIXES = [
    "Could you please", "Would you mind", "I was wondering if you could",
    "Can you", "Please", "I need to", "I'd like to", "I want to",
    "Would you be able to", "Might you", "Could we"
]

# Urgency markers
URGENCY_MARKERS = [
    "ASAP", "urgently", "immediately", "right away", "as soon as possible",
    "this is urgent", "I need this done now", "pronto"
]

# Connectors for second clause robustness
CONNECTORS = [
    "and", "then", "also", "plus", "after that", "next", "furthermore",
    "moreover", "in addition", "on top of that", "similarly", "likewise"
]

# Out-of-scope queries (NEGATIVE intent)
NEGATIVE_QUERIES = [
    "What's the weather like today?",
    "Tell me a joke",
    "How old are you?",
    "What's the meaning of life?",
    "Play some music",
    "Order a pizza for me",
    "What time is it in Tokyo?",
    "Set an alarm for 7am",
    "Remind me to buy milk",
    "How do I make coffee?",
    "What's on TV tonight?",
    "Translate hello to Spanish",
    "Calculate 15% of 200",
    "Search for restaurants nearby",
    "Open YouTube",
    "What's the capital of France?",
    "How tall is Mount Everest?",
    "What's your favorite color?",
    "Tell me a story",
    "Who won the World Cup?",
    "What's the stock price of Apple?",
    "How many calories in an apple?",
    "Define photosynthesis",
    "Who wrote Hamlet?",
    "What's the square root of 144?"
]

# ============================================================================
# TEMPLATE DEFINITIONS
# ============================================================================

TEMPLATES = {
    "CREATE_EVENT": [
        # Standard commands
        "{polite} {schedule} a {event}",
        "{polite} {schedule} a {event} with {person}",
        "{polite} {schedule} a {event} at {time}",
        "{polite} {schedule} a {event} for {duration}",
        "{polite} {schedule} a {event} in {location}",
        "{polite} {schedule} a {event} with {person} at {time} {urgency}",
        "Book a {event}",
        "Set up a {event}",
        "Create a {event}",
        
        # Declarative/statement forms
        "I have a {event} {urgency}",
        "I need to {schedule} a {event}",
        "We should {schedule} a {event} with {person}",
        "There's a {event} coming up",
        
        # With context
        "{polite} {schedule} a {event} about the project",
        "{polite} {schedule} a {event} to discuss the budget",
        "Let's {schedule} a {event} for planning"
    ],
    
    "UPDATE_EVENT": [
        # Rescheduling
        "{polite} {reschedule} the {event}",
        "{polite} move the {event}",
        "{polite} {reschedule} my {event} to {time}",
        "{polite} push the {event} back",
        "{polite} bring the {event} forward",
        "Change the time of the {event}",
        "Move my {time} {event} to {time}",
        
        # Compound/contextual
        "I'm busy then, {so} {reschedule} it",
        "That doesn't work for me, {so} move it",
        "Can we find another time for the {event}?",
        "The {event} needs to be {reschedule}d"
    ],
    
    "DELETE_EVENT": [
        # Direct cancellation
        "{polite} {cancel} the {event}",
        "{polite} {cancel} my {event}",
        "{polite} {cancel} that",
        "Remove the {event} from my calendar",
        "Delete the {event}",
        "Scrap the {event}",
        
        # Compound/contextual
        "That's wrong, {so} {cancel} it",
        "I can't make it, {so} {cancel} the {event}",
        "The {event} is no longer needed",
        "Please {cancel} that {event} {urgency}"
    ],
    
    "QUERY_EVENT": [
        # Availability queries
        "{polite} check my schedule for {time}",
        "What do I have {time}?",
        "Am I free at {time}?",
        "When is my next {event}?",
        "Show me my calendar for {time}",
        "Do I have any {event}s scheduled?",
        
        # Specific queries
        "What time is the {event}?",
        "Where is the {event}?",
        "Who is attending the {event}?",
        "How long is the {event}?"
    ],
    
    "ADD_PARTICIPANT": [
        "{polite} add {person} to the {event}",
        "{polite} invite {person} to the {event}",
        "Include {person} in the {event}",
        "Can you add {person}?",
        "Also invite {person}",
        "{person} should join the {event}"
    ],
    
    "REMOVE_PARTICIPANT": [
        "{polite} remove {person} from the {event}",
        "{polite} uninvite {person}",
        "Take {person} off the {event}",
        "{person} can't make it, {so} remove them",
        "Exclude {person} from the {event}"
    ],
    
    "GREETING": [
        "Hello",
        "Hi",
        "Hey",
        "Good morning",
        "Good afternoon",
        "Good evening",
        "Hi there",
        "Hello there",
        "Greetings"
    ]
}

# Verb variations
VERBS = {
    "schedule": ["schedule", "book", "set up", "create", "arrange", "plan", "organize"],
    "reschedule": ["reschedule", "move", "change", "shift", "postpone", "push back", "bring forward"],
    "cancel": ["cancel", "delete", "remove", "scrap", "call off"]
}

# ============================================================================
# AUGMENTATION FUNCTIONS
# ============================================================================

def inject_typos(text: str, probability: float = 0.1) -> str:
    """Inject common typos into text"""
    if random.random() > probability:
        return text
    
    words = text.split()
    if not words:
        return text
    
    # Select a word to modify
    idx = random.randint(0, len(words) - 1)
    word = words[idx]
    
    if len(word) <= 3:
        return text
    
    typo_type = random.choice(["swap", "double", "omit", "replace"])
    
    if typo_type == "swap" and len(word) >= 4:
        # Swap adjacent characters
        pos = random.randint(0, len(word) - 2)
        word = word[:pos] + word[pos+1] + word[pos] + word[pos+2:]
    elif typo_type == "double":
        # Double a character
        pos = random.randint(0, len(word) - 1)
        word = word[:pos] + word[pos] + word[pos] + word[pos+1:]
    elif typo_type == "omit":
        # Omit a character
        pos = random.randint(0, len(word) - 1)
        word = word[:pos] + word[pos+1:]
    elif typo_type == "replace":
        # Replace with nearby key
        pos = random.randint(0, len(word) - 1)
        char = word[pos]
        replacements = {
            'a': 's', 's': 'a', 'e': 'r', 'r': 'e',
            't': 'y', 'y': 't', 'o': 'p', 'p': 'o',
            'i': 'o', 'o': 'i', 'n': 'm', 'm': 'n'
        }
        word = word[:pos] + replacements.get(char, char) + word[pos+1:]
    
    words[idx] = word
    return " ".join(words)

def inject_filler_words(text: str, probability: float = 0.15) -> str:
    """Inject filler words like 'um', 'uh', etc."""
    if random.random() > probability:
        return text
    
    fillers = ["um", "uh", "like", "you know", "so", "well", "actually", "basically"]
    filler = random.choice(fillers)
    
    # Decide where to put filler
    position = random.choice(["start", "middle", "end"])
    
    if position == "start":
        return f"{filler} {text}"
    elif position == "middle" and " " in text:
        words = text.split()
        insert_pos = random.randint(1, len(words) - 1)
        words.insert(insert_pos, filler)
        return " ".join(words)
    else:  # end
        return f"{text} {filler}"

def random_case(text: str, probability: float = 0.2) -> str:
    """Randomly change case of text"""
    if random.random() > probability:
        return text
    
    case_type = random.choice(["lower", "upper", "title", "random"])
    
    if case_type == "lower":
        return text.lower()
    elif case_type == "upper":
        return text.upper()
    elif case_type == "title":
        return text.title()
    else:  # random
        return "".join(
            char.upper() if random.random() > 0.5 else char.lower()
            for char in text
        )

def remove_punctuation(text: str, probability: float = 0.1) -> str:
    """Randomly remove punctuation"""
    if random.random() > probability:
        return text
    
    punct_to_remove = ['.', '?', '!', ',', ';', ':']
    for punct in punct_to_remove:
        if punct in text and random.random() > 0.5:
            text = text.replace(punct, '')
    
    return text.strip()

def ensure_proper_punctuation(text: str, intent: str) -> str:
    """Ensure text has proper ending punctuation"""
    if not text:
        return text
    
    # Remove any trailing punctuation
    text = text.rstrip('.!?;:')
    
    # Add appropriate punctuation based on intent
    if intent == "QUERY_EVENT":
        # Questions should end with question marks
        if not any(text.endswith(word) for word in ['when', 'what', 'where', 'who', 'how', 'why', 'am', 'is', 'are', 'do', 'does', 'can', 'could']):
            # If it doesn't start with a question word, add question mark if it sounds like a question
            if any(word in text.lower() for word in ['?', 'check', 'show me', 'tell me', 'do i', 'am i', 'is there']):
                text = text + '?'
            else:
                text = text + '.'
        else:
            text = text + '?'
    elif intent in ["GREETING", "NEGATIVE"]:
        # Greetings and negative can have various punctuation
        if random.random() > 0.5:
            text = text + '.'
    else:
        # Commands/statements end with period
        text = text + '.'
    
    return text

def augment_text(text: str, intent: str) -> str:
    """Apply all augmentations to text"""
    # Store original for grammar checking
    original_text = text
    
    text = inject_typos(text, probability=0.1)
    text = inject_filler_words(text, probability=0.15)
    text = random_case(text, probability=0.2)
    text = remove_punctuation(text, probability=0.1)
    text = ensure_proper_punctuation(text, intent)
    
    return text

def add_connector(text: str, probability: float = 0.2) -> str:
    """Add connector prefix to simulate second clause"""
    if random.random() > probability:
        return text
    
    connector = random.choice(CONNECTORS)
    
    # Handle capitalization
    if text and text[0].isupper():
        text = text[0].lower() + text[1:]
    
    return f"{connector} {text}"

# ============================================================================
# GENERATION FUNCTIONS WITH GRAMMAR CHECKING
# ============================================================================

def get_context_pools(context: str) -> Dict:
    """Get appropriate pools for a given context"""
    if context == "work":
        return {
            "events": WORK_EVENTS,
            "people": PEOPLE["work"],
            "locations": LOCATIONS["work"]
        }
    elif context == "student":
        return {
            "events": STUDENT_EVENTS,
            "people": PEOPLE["student"],
            "locations": LOCATIONS["student"]
        }
    else:  # personal
        return {
            "events": PERSONAL_EVENTS,
            "people": PEOPLE["personal"],
            "locations": LOCATIONS["personal"]
        }

def generate_clean_text(intent: str, context: str = None) -> Tuple[str, Dict]:
    """Generate clean text without augmentation"""
    
    # Special handling for NEGATIVE intent
    if intent == "NEGATIVE":
        text = random.choice(NEGATIVE_QUERIES)
        return text, {"text": text, "label": LABEL_MAP[intent], "label_name": intent}
    
    # Special handling for GREETING intent
    if intent == "GREETING":
        text = random.choice(TEMPLATES[intent])
        return text, {"text": text, "label": LABEL_MAP[intent], "label_name": intent}
    
    # For other intents, select context if not provided
    if context is None:
        context = random.choice(["work", "student", "personal"])
    
    pools = get_context_pools(context)
    
    # Select template and fill placeholders
    template = random.choice(TEMPLATES[intent])
    
    # Fill placeholders
    filled = template
    
    # Replace {polite}
    if "{polite}" in filled:
        filled = filled.replace("{polite}", random.choice(POLITE_PREFIXES) if random.random() > 0.3 else "")
    
    # Replace {urgency}
    if "{urgency}" in filled:
        filled = filled.replace("{urgency}", random.choice(URGENCY_MARKERS) if random.random() > 0.7 else "")
    
    # Replace {so}
    if "{so}" in filled:
        filled = filled.replace("{so}", random.choice(["so", "therefore", ""]))
    
    # Replace verbs
    for verb_type, verb_list in VERBS.items():
        if f"{{{verb_type}}}" in filled:
            filled = filled.replace(f"{{{verb_type}}}", random.choice(verb_list))
    
    # Replace other placeholders
    placeholders = re.findall(r'\{(\w+)\}', filled)
    for ph in placeholders:
        if ph == "event":
            replacement = random.choice(pools["events"])
        elif ph == "person":
            replacement = random.choice(pools["people"])
        elif ph == "location":
            replacement = random.choice(pools["locations"])
        elif ph == "time":
            replacement = random.choice(TIMES)
        elif ph == "duration":
            replacement = random.choice(DURATIONS)
        else:
            replacement = f"[{ph}]"  # Fallback
        
        filled = filled.replace(f"{{{ph}}}", replacement)
    
    # Clean up extra spaces
    text = re.sub(r'\s+', ' ', filled).strip()
    
    # Add connector for second clause robustness
    if random.random() < 0.2:
        text = add_connector(text)
    
    # Ensure proper punctuation for clean text
    text = ensure_proper_punctuation(text, intent)
    
    return text, {"text": text, "label": LABEL_MAP[intent], "label_name": intent}

def generate_compound_example() -> Tuple[str, Dict]:
    """Generate compound sentence with clear primary intent"""
    compound_types = [
        ("I'm busy then, so reschedule it.", "UPDATE_EVENT"),
        ("That's wrong, cancel it.", "DELETE_EVENT"),
        ("I can't make it, so please cancel.", "DELETE_EVENT"),
        ("We need to discuss this, schedule a meeting.", "CREATE_EVENT"),
        ("The time doesn't work, move it to 3pm.", "UPDATE_EVENT"),
        ("Add Sarah and also invite John.", "ADD_PARTICIPANT"),
        ("Remove Mark, he can't make it.", "REMOVE_PARTICIPANT"),
        ("Check my schedule and book a slot.", "CREATE_EVENT"),  # Primary: CREATE
        ("What's on my calendar and am I free?", "QUERY_EVENT")  # Primary: QUERY
    ]
    
    text, intent = random.choice(compound_types)
    return text, {"text": text, "label": LABEL_MAP[intent], "label_name": intent}

def generate_example_with_grammar_check(intent: str, context: str = None) -> Dict:
    """Generate an example with grammar validation"""
    
    # For NEGATIVE and GREETING, skip intensive grammar checking
    if intent in ["NEGATIVE", "GREETING"]:
        if intent == "NEGATIVE":
            text = random.choice(NEGATIVE_QUERIES)
            # Apply minimal augmentation
            if random.random() < 0.5:
                text = augment_text(text, intent)
            return {"text": text, "label": LABEL_MAP[intent], "label_name": intent}
        else:  # GREETING
            text = random.choice(TEMPLATES[intent])
            if random.random() < 0.3:
                text = augment_text(text, intent)
            return {"text": text, "label": LABEL_MAP[intent], "label_name": intent}
    
    retry_count = 0
    while retry_count < RETRY_LIMIT:
        # Decide if this will be a compound example
        if random.random() < 0.1:  # 10% compound
            text, example_data = generate_compound_example()
            clean_text = text
        else:
            # Generate clean text
            if context is None:
                context = random.choice(["work", "student", "personal"])
            clean_text, example_data = generate_clean_text(intent, context)
        
        # Check grammar on clean text (before augmentation)
        if grammar_checker.use_checker and grammar_checker.initialized:
            # Decide whether to check grammar (80% chance for non-augmented text)
            if random.random() < 0.8:
                is_valid, suggestions = grammar_checker.check_text(clean_text, MAX_GRAMMAR_ERRORS)
                if not is_valid:
                    retry_count += 1
                    continue  # Try again
        
        # Apply augmentation with probability
        if random.random() < 0.5:
            # For augmented text, we're more lenient with grammar
            augmented_text = augment_text(clean_text, intent)
            
            # Quick grammar check on augmented text (more lenient)
            if grammar_checker.use_checker and grammar_checker.initialized:
                # Only check 30% of augmented texts
                if random.random() < 0.3:
                    is_valid, suggestions = grammar_checker.check_text(augmented_text, MAX_GRAMMAR_ERRORS + 2)
                    if not is_valid:
                        retry_count += 1
                        continue  # Try again
            
            example_data["text"] = augmented_text
        else:
            example_data["text"] = clean_text
        
        return example_data
    
    # If we've retried too many times, return the last attempt anyway
    if retry_count >= RETRY_LIMIT:
        print(f"Warning: Retry limit reached for intent {intent}. Using last generated text.")
    
    return example_data

def generate_dataset() -> Tuple[List[Dict], List[Dict]]:
    """Generate complete dataset with train/val split"""
    all_examples = []
    
    print("\n📊 Generating dataset with grammar checking...")
    print(f"   Grammar checking: {'ENABLED' if grammar_checker.use_checker and grammar_checker.initialized else 'DISABLED'}")
    
    # Generate examples for each intent according to distribution
    for intent, count in INTENT_DISTRIBUTION.items():
        print(f"\n   Generating {count} examples for {intent}...")
        
        generated_count = 0
        while generated_count < count:
            # Distribute across contexts
            if intent in ["CREATE_EVENT", "UPDATE_EVENT", "DELETE_EVENT", "QUERY_EVENT"]:
                context = random.choice(["work", "student", "personal"])
            elif intent in ["ADD_PARTICIPANT", "REMOVE_PARTICIPANT"]:
                # Participant intents more common in work context
                context = random.choice(["work", "work", "student", "personal"])
            else:
                context = None
            
            example = generate_example_with_grammar_check(intent, context)
            all_examples.append(example)
            generated_count += 1
            
            # Progress indicator
            if generated_count % 100 == 0:
                print(f"      {generated_count}/{count} examples generated...")
    
    # Shuffle the dataset
    random.shuffle(all_examples)
    
    # Split into train and validation
    split_idx = int(len(all_examples) * TRAIN_RATIO)
    train_examples = all_examples[:split_idx]
    val_examples = all_examples[split_idx:]
    
    return train_examples, val_examples

def save_dataset(train_examples: List[Dict], val_examples: List[Dict]):
    """Save dataset to JSONL files and label map"""
    
    # Save label map
    with open("label_map.json", "w") as f:
        json.dump(LABEL_MAP, f, indent=2)
    
    # Save training data
    with open("intent_train.jsonl", "w") as f:
        for example in train_examples:
            f.write(json.dumps(example) + "\n")
    
    # Save validation data
    with open("intent_val.jsonl", "w") as f:
        for example in val_examples:
            f.write(json.dumps(example) + "\n")
    
    # Also save a combined version
    with open("intent_dataset.jsonl", "w") as f:
        for example in train_examples + val_examples:
            f.write(json.dumps(example) + "\n")
    
    print(f"\n✅ Dataset generation complete!")
    print(f"   Total examples: {len(train_examples) + len(val_examples)}")
    print(f"   Training examples: {len(train_examples)}")
    print(f"   Validation examples: {len(val_examples)}")
    print(f"   Grammar checking: {'ENABLED' if grammar_checker.use_checker and grammar_checker.initialized else 'DISABLED'}")
    
    # Print distribution
    print("\n📊 Final distribution:")
    for intent in LABEL_MAP.keys():
        train_count = sum(1 for ex in train_examples if ex["label_name"] == intent)
        val_count = sum(1 for ex in val_examples if ex["label_name"] == intent)
        print(f"   {intent}: {train_count + val_count} total ({train_count} train, {val_count} val)")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("DistilBERT Intent Classification Dataset Generator")
    print("Version 2.0 - Scheduler Domain with Grammar Check")
    print("=" * 60)
    
    print("\n🎯 Generating synthetic dataset...")
    print(f"   Target intents: {list(LABEL_MAP.keys())}")
    print(f"   Contexts: Work, Student, Personal")
    print(f"   Features: Politeness, Urgency, Compound sentences, Noise augmentation")
    print(f"   Second-clause robustness: Connector injection (20% of examples)")
    print(f"   Grammar checking: {USE_GRAMMAR_CHECK}")
    print(f"   Maximum grammar errors allowed: {MAX_GRAMMAR_ERRORS}")
    
    start_time = time.time()
    
    try:
        train_examples, val_examples = generate_dataset()
        save_dataset(train_examples, val_examples)
        
        # Show some example outputs
        print("\n📝 Sample training examples:")
        print("-" * 40)
        for i, example in enumerate(train_examples[:5]):
            print(f"{i+1}. Text: '{example['text']}'")
            print(f"   Label: {example['label_name']} (ID: {example['label']})")
            print()
        
        print("\n📁 Files created:")
        print("   - intent_train.jsonl (Training data)")
        print("   - intent_val.jsonl (Validation data)")
        print("   - intent_dataset.jsonl (Combined dataset)")
        print("   - label_map.json (Label mapping)")
        
        elapsed_time = time.time() - start_time
        print(f"\n⏱️  Generation completed in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        print(f"\n❌ Error during dataset generation: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up grammar checker resources
        grammar_checker.close()
    
    print("\n🚀 Dataset is ready for DistilBERT fine-tuning!")