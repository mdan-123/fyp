# ===============================================================
# create_bert_dataset.py - ENHANCED with Class Imbalance Fix
# Added specialist templates, hyphen handling, and rare entity boosting
# ===============================================================

import json
import random
import re
from tqdm import tqdm
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass
import os
from collections import defaultdict
import language_tool_python

# ===============================================================
# 1. Configuration
# ===============================================================

# Initialize the grammar checker tool
print("Initializing grammar checker (language_tool_python)...")
try:
    grammar_tool = language_tool_python.LanguageTool('en-GB')
    print("Grammar checker initialized successfully.")
except Exception as e:
    print(f"Warning: Could not initialize grammar checker: {e}. Proceeding without grammar checks.")
    grammar_tool = None

# Define all labels (BIO scheme)
ALL_LABELS = [
    # Base
    "O",
    # Core entities
    "B-TASK_TITLE", "I-TASK_TITLE",
    "B-PARTICIPANT", "I-PARTICIPANT", 
    "B-LOCATION", "I-LOCATION",
    # Time entities
    "B-ABS_DATE", "I-ABS_DATE",
    "B-REL_DATE", "I-REL_DATE",
    "B-ABS_TIME", "I-ABS_TIME",
    "B-REL_TIME", "I-REL_TIME",
    "B-DURATION", "I-DURATION",
    "B-RECURRENCE", "I-RECURRENCE",
]

# Create mappings
LABEL_TO_ID = {label: idx for idx, label in enumerate(ALL_LABELS)}
ID_TO_LABEL = {idx: label for idx, label in enumerate(ALL_LABELS)}

# Dataset configuration with boosted rare entities
TARGET_TRAIN_POSITIVE = 4000
TARGET_TRAIN_NEGATIVE = 3000
SPECIALIST_EXAMPLES = 500  # Extra examples for weak classes

# ===============================================================
# 2. Sentence Builder with Enhanced Hyphen Handling
# ===============================================================

@dataclass
class Token:
    """Represents a token with text and BIO tag"""
    text: str
    tag: str  # e.g., "B-PARTICIPANT"

class SentenceBuilder:
    """Builds sentences token-by-token with special hyphen handling"""
    
    def __init__(self):
        self.tokens: List[Token] = []
    
    def add_text(self, text: str, tag: str = "O"):
        """Add text with optional tagging - handles hyphens specially"""
        if not text.strip():
            return
        
        # Check if text contains hyphens that should be part of entities
        if "-" in text and tag != "O":
            # Split on hyphens but keep them as part of the entity
            parts = text.split("-")
            for i, part in enumerate(parts):
                if part:  # Skip empty parts
                    self.tokens.append(Token(part, tag))
                if i < len(parts) - 1 and part:  # Add hyphen if not at end
                    self.tokens.append(Token("-", f"I-{tag.split('-')[1]}" if tag.startswith("I-") else tag))
        else:
            # Regular splitting
            words = text.split()
            
            # Handle BIO tagging for multi-word entities
            if tag.startswith("B-"):
                entity_type = tag.split("-")[1]
                for i, word in enumerate(words):
                    if i == 0:
                        bio_tag = f"B-{entity_type}"
                    else:
                        bio_tag = f"I-{entity_type}"
                    self.tokens.append(Token(word, bio_tag))
            elif tag != "O":
                # Already I- tag or something else
                for word in words:
                    self.tokens.append(Token(word, tag))
            else:
                # O tag
                for word in words:
                    self.tokens.append(Token(word, "O"))
    
    def add_entity(self, entity_text: str, entity_type: str):
        """Add a named entity with proper BIO tagging and hyphen handling"""
        self.add_text(entity_text, f"B-{entity_type}")
    
    def add_connector(self, text: str):
        """Add connecting text (always O tag)"""
        self.add_text(text, "O")
    
    def get_sentence(self) -> Tuple[List[str], List[int]]:
        """Convert to final format"""
        tokens = [token.text for token in self.tokens]
        tags = [LABEL_TO_ID[token.tag] for token in self.tokens]
        return tokens, tags
    
    def get_text(self) -> str:
        """Get the full text as a string"""
        return " ".join([token.text for token in self.tokens])
    
    def clear(self):
        """Reset the builder"""
        self.tokens = []

# ===============================================================
# 3. Enhanced Data Components with Rare Entity Focus
# ===============================================================

# CORE COMPONENTS
VERBS = [
    "Schedule", "Book", "Set up", "Organize", "Plan", "Reserve", 
    "Coordinate", "Arrange", "Block", "Cancel", "Move", "Reschedule"
]

# WORK CONTEXT
WORK_TASKS = [
    "meeting", "sync", "briefing", "audit", "pitch", "demo", "interview",
    "review", "workshop", "conference call", "client presentation",
    "daily standup", "status update", "project retrospective",
    "all-hands meeting", "sales pitch", "project kickoff"
]

# HYPENATED TASKS (CRITICAL FIX)
HYPHENATED_TASKS = [
    "all-day workshop", "back-to-back interviews", "one-on-one meeting",
    "follow-up call", "check-in session", "run-through practice",
    "dry-run test", "walk-through demo", "hands-on training",
    "face-to-face meeting", "day-long conference", "week-long retreat",
    "month-long project", "year-end review", "mid-year assessment",
    "pre-launch meeting", "post-mortem analysis", "off-site retreat",
    "in-person training", "virtual meeting", "on-demand session"
]

WORK_PEOPLE = [
    "John", "Sarah", "Dr. Patel", "project manager", "marketing team",
    "engineering team", "HR department", "CEO", "client representative"
]

WORK_LOCATIONS = [
    "main office", "Room 4", "conference room B", "company HQ",
    "auditorium", "Zoom", "Teams call", "boardroom"
]

# STUDENT CONTEXT
STUDENT_TASKS = [
    "lecture", "lab", "tutorial", "study session", "exam", "quiz",
    "midterm", "final", "assignment", "paper", "essay", "project",
    "presentation", "group study", "thesis meeting"
]

STUDENT_PEOPLE = [
    "professor", "TA", "lab partner", "study group", "roommate",
    "classmates", "academic advisor", "Professor Smith"
]

STUDENT_LOCATIONS = [
    "library", "lecture hall", "science lab", "dorm room",
    "student union", "campus center", "online class", "lab 302"
]

# RECREATION CONTEXT
RECREATION_TASKS = [
    "dinner", "lunch", "brunch", "gym", "yoga", "movie", "concert",
    "game night", "hike", "run", "swim", "doctor appointment",
    "haircut", "therapy session", "personal training"
]

RECREATION_PEOPLE = [
    "friend", "family", "mom", "dad", "partner", "personal trainer",
    "doctor", "dentist", "yoga instructor", "book club"
]

RECREATION_LOCATIONS = [
    "restaurant", "gym", "park", "cinema", "my place", "your place",
    "coffee shop", "beach", "hiking trail", "downtown"
]

# ===============================================================
# 4. TIME COMPONENTS - EXPANDED FOR WEAK ENTITIES
# ===============================================================

# ABSOLUTE DATES
ABS_DATES = [
    "October 25th", "November 2nd", "December 10th", "2025-10-19",
    "10/25/2025", "7/4/2026", "March 15", "April 10th", "May 20 2025"
]

# RELATIVE DATES - EXPANDED (weak entity)
REL_DATES = [
    "tomorrow", "next Friday", "this weekend", "next week",
    "this afternoon", "tonight", "later today", "early next month",
    "end of week", "in two days", "sometime soon",
    "day after tomorrow", "coming Monday", "following Tuesday",
    "early next week", "mid-next month", "late next week",
    "start of next month", "by the weekend", "within a week"
]

# ABSOLUTE TIMES
ABS_TIMES = [
    "9am", "2:30pm", "5pm", "8:45am", "10:15", "7:00pm",
    "3:15pm", "12:00pm", "14:30", "09:00", "5:15 PM"
]

# RELATIVE TIMES - CRITICAL EXPANSION (0% entity)
REL_TIMES = [
    "morning", "afternoon", "evening", "night", "noon",
    "first thing", "end of day", "after work", "late afternoon",
    "early morning", "mid-morning", "midday", "midnight",
    "dawn", "dusk", "sunrise", "sunset", "twilight",
    "around noon", "past midnight", "before dawn", "after sunset",
    "business hours", "office hours", "peak hours", "off-peak hours",
    "morning hours", "afternoon slot", "evening time", "night session"
]

# DURATIONS
DURATIONS = [
    "30 minutes", "an hour", "2 hours", "15 min", "45 minutes",
    "90 minutes", "half day", "full day", "1 hour", "2.5 hours",
    "couple hours", "few hours"
]

# RECURRENCE - EXPANDED WITH CLEAR PATTERNS (32% entity)
RECURRENCES = [
    "daily", "weekly", "every day", "every Friday", "monthly",
    "bi-weekly", "every Monday", "every other week", "quarterly",
    "twice a week", "once a month", "every weekday", "every weekend",
    "each Monday", "on Tuesdays", "Fridays only", "weekends only",
    "alternate days", "three times a week", "four times a month",
    "first Monday monthly", "last Friday each month", "bi-monthly",
    "semi-annually", "yearly", "annually", "each semester",
    "every quarter", "on alternate weeks", "every few days"
]

# CLEAR SHORT RECURRENCES (for better learning)
SHORT_RECURRENCES = [
    "daily", "weekly", "monthly", "yearly", "bi-weekly", "quarterly",
    "annually", "bi-monthly", "semi-annually"
]

# NEGATIVE EXAMPLES
NEGATIVE_PHRASES = [
    ["How", "'s", "the", "weather", "today", "?"],
    ["What", "time", "is", "it", "?"],
    ["Tell", "me", "a", "joke", "."],
    ["I", "like", "pizza", "."],
    ["Open", "the", "calculator", "."],
    ["What", "'s", "your", "name", "?"],
    ["The", "cat", "is", "sleeping", "."],
    ["I", "have", "a", "headache", "."],
    ["This", "is", "a", "test", "."],
    ["Play", "some", "music", "."],
]

# ===============================================================
# 5. Enhanced Template System with Specialist Templates
# ===============================================================

class EnhancedTemplateSystem:
    """Manages templates with specialist templates for weak entities"""
    
    def __init__(self):
        self.regular_templates = self._init_regular_templates()
        self.specialist_templates = self._init_specialist_templates()
        self.component_pools = self._init_component_pools()
    
    def _init_regular_templates(self) -> Dict[str, List[List]]:
        """Initialize regular templates"""
        return {
            "work": [
                ["Schedule", "{task}", "with", "{person}", "on", "{date_abs}", "at", "{time_abs}"],
                ["Book", "{task}", "for", "{date_rel}"],
                ["Set up", "{task}", "in", "{location}"],
                ["I", "need", "to", "schedule", "{task}", "with", "{person}", "for", "{duration}"],
                ["Can", "we", "do", "{task}", "{date_rel}", "at", "{time_abs}", "?"],
                ["Please", "arrange", "{task}", "with", "{person}", "in", "{location}"],
            ],
            "student": [
                ["Schedule", "{task}", "with", "{person}", "for", "{date_rel}"],
                ["Book", "{location}", "for", "{task}", "study"],
                ["I", "have", "{task}", "on", "{date_abs}", "at", "{time_abs}"],
                ["Can", "we", "meet", "for", "{task}", "{date_rel}", "?"],
            ],
            "recreation": [
                ["Schedule", "{task}", "with", "{person}", "on", "{date_abs}"],
                ["Book", "{task}", "at", "{location}", "for", "{time_abs}"],
                ["Let's", "do", "{task}", "{date_rel}", "evening"],
                ["I", "want", "to", "book", "{task}", "for", "{duration}"],
            ]
        }
    
    def _init_specialist_templates(self) -> Dict[str, List[List]]:
        """Initialize specialist templates for weak entities"""
        return {
            # REL_TIME focused (our 0% entity)
            "rel_time_focus": [
                ["Schedule", "{task}", "for", "{rel_time}"],
                ["Book", "{task}", "in", "the", "{rel_time}"],
                ["Let's", "meet", "{rel_time}"],
                ["I", "want", "to", "schedule", "{task}", "{rel_time}"],
                ["Can", "we", "do", "it", "{rel_time}", "?"],
                ["Arrange", "{task}", "for", "{rel_time}", "only"],
                ["{rel_time}", "is", "best", "for", "{task}"],
                ["Schedule", "{rel_time}", "{task}", "with", "{person}"],
            ],
            
            # RECURRENCE focused (our 32% entity)
            "recurrence_focus": [
                ["{recurrence_short}", "{task}"],
                ["{task}", "{recurrence_short}"],
                ["Schedule", "{recurrence_short}", "{task}"],
                ["Book", "{task}", "{recurrence_short}"],
                ["We", "need", "{recurrence_short}", "{task}"],
                ["{recurrence}", "is", "good", "for", "{task}"],
                ["Set up", "{task}", "{recurrence}"],
                ["{recurrence}", "{task}", "at", "{time_abs}"],
            ],
            
            # REL_DATE focused (our 38% entity)
            "rel_date_focus": [
                ["Schedule", "{task}", "{rel_date}"],
                ["{rel_date}", "works", "for", "{task}"],
                ["Book", "{task}", "{rel_date}"],
                ["Can", "we", "meet", "{rel_date}", "?"],
                ["{rel_date}", "at", "{time_abs}", "for", "{task}"],
                ["I'm", "free", "{rel_date}", "for", "{task}"],
                ["{task}", "{rel_date}", "sounds", "good"],
                ["{rel_date}", "morning", "for", "{task}"],
            ],
            
            # HYPHENATED TASK focused
            "hyphen_focus": [
                ["Schedule", "{hyphen_task}", "with", "{person}"],
                ["Book", "{hyphen_task}", "for", "{date_rel}"],
                ["We", "need", "a", "{hyphen_task}"],
                ["{hyphen_task}", "is", "necessary"],
                ["Arrange", "{hyphen_task}", "in", "{location}"],
                ["{hyphen_task}", "at", "{time_abs}"],
                ["Plan", "{hyphen_task}", "{rel_date}"],
            ],
            
            # CLEAR DISTINCTIONS between time types
            "time_distinction": [
                ["{rel_date}", "at", "{rel_time}"],  # "tomorrow morning"
                ["{rel_date}", "in", "the", "{rel_time}"],  # "Friday afternoon"
                ["{abs_date}", "at", "{abs_time}"],  # "March 15th at 2pm"
                ["{rel_time}", "on", "{rel_date}"],  # "morning on Monday"
                ["{abs_time}", "on", "{abs_date}"],  # "2pm on March 15th"
                ["{rel_time}", "only", "no", "specific", "date"],  # Force REL_TIME without date
                ["{abs_time}", "sharp", "on", "{abs_date}"],
            ]
        }
    
    def _init_component_pools(self) -> Dict[str, Dict[str, List[str]]]:
        """Initialize component pools with specialist additions"""
        return {
            "work": {
                "task": WORK_TASKS + HYPHENATED_TASKS,  # Added hyphenated tasks
                "person": WORK_PEOPLE,
                "location": WORK_LOCATIONS,
            },
            "student": {
                "task": STUDENT_TASKS,
                "person": STUDENT_PEOPLE,
                "location": STUDENT_LOCATIONS,
            },
            "recreation": {
                "task": RECREATION_TASKS,
                "person": RECREATION_PEOPLE,
                "location": RECREATION_LOCATIONS,
            },
            "global": {
                "date_abs": ABS_DATES,
                "date_rel": REL_DATES,
                "time_abs": ABS_TIMES,
                "time_rel": REL_TIMES,
                "duration": DURATIONS,
                "recurrence": RECURRENCES,
                "recurrence_short": SHORT_RECURRENCES,
                "hyphen_task": HYPHENATED_TASKS,
                "verb": VERBS,
            }
        }
    
    def get_template(self, context: str, use_specialist: bool = False) -> List:
        """Get template - regular or specialist"""
        if use_specialist:
            # Choose which specialist category to focus on
            specialist_types = list(self.specialist_templates.keys())
            weights = [0.25, 0.25, 0.25, 0.15, 0.10]  # Focus on weak entities
            specialist_type = random.choices(specialist_types, weights=weights)[0]
            return random.choice(self.specialist_templates[specialist_type])
        else:
            return random.choice(self.regular_templates[context])
    
    def get_component(self, placeholder: str, context: str) -> str:
        """Get random component for placeholder"""
        if placeholder in self.component_pools[context]:
            return random.choice(self.component_pools[context][placeholder])
        elif placeholder in self.component_pools["global"]:
            return random.choice(self.component_pools["global"][placeholder])
        elif placeholder.endswith("2"):
            base_ph = placeholder[:-1]
            return self.get_component(base_ph, context)
        else:
            return "UNKNOWN"
    
    def get_entity_type(self, placeholder: str) -> str:
        """Map placeholder to entity type"""
        mapping = {
            "task": "TASK_TITLE",
            "hyphen_task": "TASK_TITLE",
            "person": "PARTICIPANT",
            "location": "LOCATION",
            "date_abs": "ABS_DATE",
            "date_rel": "REL_DATE",
            "time_abs": "ABS_TIME",
            "time_rel": "REL_TIME",
            "duration": "DURATION",
            "recurrence": "RECURRENCE",
            "recurrence_short": "RECURRENCE",
        }
        if placeholder.endswith("2"):
            return mapping.get(placeholder[:-1], "O")
        return mapping.get(placeholder, "O")

# ===============================================================
# 6. Enhanced Training Dataset Generator
# ===============================================================

class EnhancedTrainingDatasetGenerator:
    """Main training dataset generator with class balancing"""
    
    def __init__(self, grammar_tool=None):
        self.template_system = EnhancedTemplateSystem()
        self.grammar_tool = grammar_tool
        self.discarded_count = 0
        
    def generate_positive_example(self, context: str, use_specialist: bool = False) -> Dict[str, Any]:
        """Generate a single positive example"""
        builder = SentenceBuilder()
        
        # Get template
        template = self.template_system.get_template(context, use_specialist)
        
        # Build sentence
        for item in template:
            if item.startswith("{") and item.endswith("}"):
                placeholder = item[1:-1]
                component = self.template_system.get_component(placeholder, context)
                entity_type = self.template_system.get_entity_type(placeholder)
                
                if entity_type != "O":
                    builder.add_entity(component, entity_type)
                else:
                    builder.add_text(component, "O")
            else:
                builder.add_text(item, "O")
        
        tokens, tags = builder.get_sentence()
        
        # Simple augmentation
        if random.random() < 0.3:
            tokens = [t.lower() if random.random() < 0.5 else t for t in tokens]
        
        return {
            "tokens": tokens,
            "ner_tags": tags,
            "context": context,
            "is_positive": True,
            "is_specialist": use_specialist
        }
    
    def generate_specialist_examples(self, count: int) -> List[Dict[str, Any]]:
        """Generate examples focused on weak entities"""
        examples = []
        
        contexts = ["work", "student", "recreation"]
        
        for _ in tqdm(range(count), desc="Generating specialist examples"):
            context = random.choice(contexts)
            example = self.generate_positive_example(context, use_specialist=True)
            examples.append(example)
        
        return examples
    
    def generate_regular_examples(self, count: int) -> List[Dict[str, Any]]:
        """Generate regular examples"""
        examples = []
        
        contexts = ["work", "student", "recreation"]
        context_weights = [0.4, 0.3, 0.3]
        
        for _ in tqdm(range(count), desc="Generating regular examples"):
            context = random.choices(contexts, weights=context_weights)[0]
            example = self.generate_positive_example(context, use_specialist=False)
            examples.append(example)
        
        return examples
    
    def generate_negative_example(self) -> Dict[str, Any]:
        """Generate negative example (all O tags)"""
        tokens = random.choice(NEGATIVE_PHRASES)
        tags = [LABEL_TO_ID["O"]] * len(tokens)
        
        # Add minor variations
        if random.random() < 0.3:
            tokens = [t.lower() if random.random() < 0.5 else t for t in tokens]
        
        return {
            "tokens": tokens,
            "ner_tags": tags,
            "context": "negative",
            "is_positive": False,
            "is_specialist": False
        }
    
    def generate_training_dataset(self, regular_count: int, specialist_count: int, negative_count: int) -> List[Dict[str, Any]]:
        """Generate complete training dataset with balanced classes"""
        dataset = []
        
        # 1. Generate regular examples
        print(f"\n📊 Generating {regular_count} regular examples...")
        regular_examples = self.generate_regular_examples(regular_count)
        dataset.extend(regular_examples)
        
        # 2. Generate specialist examples (for weak entities)
        print(f"\n🎯 Generating {specialist_count} specialist examples (for REL_TIME, RECURRENCE, REL_DATE)...")
        specialist_examples = self.generate_specialist_examples(specialist_count)
        dataset.extend(specialist_examples)
        
        # 3. Generate negative examples
        print(f"\n🚫 Generating {negative_count} negative examples...")
        for _ in tqdm(range(negative_count), desc="Negative examples"):
            example = self.generate_negative_example()
            dataset.append(example)
        
        # 4. Add manual examples with clear distinctions
        print(f"\n📝 Adding manual examples with clear entity distinctions...")
        manual_examples = self._add_manual_examples()
        dataset.extend(manual_examples)
        
        # Shuffle
        random.shuffle(dataset)
        
        return dataset
    
    def _add_manual_examples(self) -> List[Dict[str, Any]]:
        """Add high-quality manual examples with clear distinctions"""
        manual_cases = [
            # Clear REL_TIME examples
            {
                "text": "Schedule meeting in the morning",
                "entities": [("meeting", "TASK_TITLE"), ("morning", "REL_TIME")]
            },
            {
                "text": "Book appointment for noon",
                "entities": [("appointment", "TASK_TITLE"), ("noon", "REL_TIME")]
            },
            {
                "text": "Plan session around midnight",
                "entities": [("session", "TASK_TITLE"), ("midnight", "REL_TIME")]
            },
            {
                "text": "Arrange call during business hours",
                "entities": [("call", "TASK_TITLE"), ("business hours", "REL_TIME")]
            },
            
            # Clear RECURRENCE examples
            {
                "text": "Weekly team sync",
                "entities": [("Weekly", "RECURRENCE"), ("team sync", "TASK_TITLE")]
            },
            {
                "text": "Daily standup meeting",
                "entities": [("Daily", "RECURRENCE"), ("standup meeting", "TASK_TITLE")]
            },
            {
                "text": "Monthly review session",
                "entities": [("Monthly", "RECURRENCE"), ("review session", "TASK_TITLE")]
            },
            
            # Clear REL_DATE examples
            {
                "text": "Tomorrow's briefing",
                "entities": [("Tomorrow", "REL_DATE"), ("briefing", "TASK_TITLE")]
            },
            {
                "text": "Next week planning",
                "entities": [("Next week", "REL_DATE"), ("planning", "TASK_TITLE")]
            },
            {
                "text": "This weekend getaway",
                "entities": [("This weekend", "REL_DATE"), ("getaway", "TASK_TITLE")]
            },
            
            # Hyphenated examples
            {
                "text": "All-day workshop planning",
                "entities": [("All-day workshop", "TASK_TITLE"), ("planning", "TASK_TITLE")]
            },
            {
                "text": "Back-to-back interviews schedule",
                "entities": [("Back-to-back interviews", "TASK_TITLE"), ("schedule", "TASK_TITLE")]
            },
            {
                "text": "One-on-one meeting with manager",
                "entities": [("One-on-one meeting", "TASK_TITLE"), ("manager", "PARTICIPANT")]
            },
            
            # Clear distinctions
            {
                "text": "Morning session on Monday",  # REL_TIME + REL_DATE
                "entities": [("Morning", "REL_TIME"), ("session", "TASK_TITLE"), ("Monday", "REL_DATE")]
            },
            {
                "text": "2pm on March 15th",  # ABS_TIME + ABS_DATE
                "entities": [("2pm", "ABS_TIME"), ("March 15th", "ABS_DATE")]
            },
            {
                "text": "Tomorrow at 3pm",  # REL_DATE + ABS_TIME
                "entities": [("Tomorrow", "REL_DATE"), ("3pm", "ABS_TIME")]
            },
        ]
        
        examples = []
        for case in manual_cases:
            builder = SentenceBuilder()
            text = case["text"]
            
            # Sort entities by position
            entities = sorted(case["entities"], key=lambda x: text.find(x[0]))
            
            # Build sentence with entities
            last_pos = 0
            for entity_text, entity_type in entities:
                pos = text.find(entity_text, last_pos)
                
                # Add text before entity
                if pos > last_pos:
                    before_text = text[last_pos:pos].strip()
                    if before_text:
                        builder.add_text(before_text, "O")
                
                # Add entity
                builder.add_entity(entity_text, entity_type)
                last_pos = pos + len(entity_text)
            
            # Add remaining text
            if last_pos < len(text):
                remaining = text[last_pos:].strip()
                if remaining:
                    builder.add_text(remaining, "O")
            
            tokens, tags = builder.get_sentence()
            
            examples.append({
                "tokens": tokens,
                "ner_tags": tags,
                "context": "manual",
                "is_positive": True,
                "is_specialist": True
            })
        
        return examples

# ===============================================================
# 7. Main Execution
# ===============================================================

def save_label_map(output_dir: str = "./bert_data"):
    """Save label mapping"""
    os.makedirs(output_dir, exist_ok=True)
    
    label_map = {
        "id2label": ID_TO_LABEL,
        "label2id": LABEL_TO_ID
    }
    
    with open(os.path.join(output_dir, "label_map.json"), "w") as f:
        json.dump(label_map, f, indent=2)
    
    print(f"✅ Saved label map with {len(LABEL_TO_ID)} labels")

def save_training_dataset(dataset: List[Dict[str, Any]], output_dir: str = "./bert_data"):
    """Save training dataset in JSONL format"""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "train.jsonl")
    
    with open(filepath, "w") as f:
        for example in dataset:
            # Remove metadata fields for final output
            output_example = {
                "tokens": example["tokens"],
                "ner_tags": example["ner_tags"]
            }
            f.write(json.dumps(output_example) + "\n")
    
    print(f"✅ Saved {len(dataset)} training examples to {filepath}")

def analyze_dataset(dataset: List[Dict[str, Any]]):
    """Analyze dataset statistics with focus on weak entities"""
    total = len(dataset)
    positive = sum(1 for ex in dataset if ex["is_positive"])
    negative = total - positive
    specialist = sum(1 for ex in dataset if ex.get("is_specialist", False))
    
    # Count entities
    entity_counts = defaultdict(int)
    for example in dataset:
        for tag_id in example["ner_tags"]:
            label = ID_TO_LABEL[tag_id]
            if label != "O":
                entity_counts[label] += 1
    
    print(f"\n📊 ENHANCED Dataset Statistics:")
    print(f"   Total examples: {total}")
    print(f"   Positive examples: {positive}")
    print(f"   Negative examples: {negative}")
    print(f"   Specialist examples: {specialist} ({specialist/total*100:.1f}%)")
    
    # Calculate target weak entity ratios
    weak_entities = ["REL_TIME", "RECURRENCE", "REL_DATE"]
    total_entities = sum(entity_counts.values())
    
    print(f"\n🎯 Weak Entity Coverage (Goal: >5% each):")
    for label in weak_entities:
        count = entity_counts.get(label, 0)
        percentage = (count / total_entities * 100) if total_entities > 0 else 0
        target_status = "✅" if percentage >= 5 else "⚠️ "
        print(f"   {target_status} {label:15}: {count:6d} ({percentage:5.1f}%)")
    
    print(f"\n📈 All Entity Distribution:")
    for label in sorted(ALL_LABELS):
        if label != "O":
            count = entity_counts.get(label, 0)
            percentage = (count / total_entities * 100) if total_entities > 0 else 0
            print(f"   {label:20}: {count:6d} ({percentage:5.1f}%)")

def main():
    """Main execution function - ENHANCED with class balancing"""
    print("=" * 60)
    print("🚀 ENHANCED DistilBERT NER Training Dataset Generator")
    print("🎯 Focus: Fixing REL_TIME (0%), RECURRENCE (32%), REL_DATE (38%)")
    print("=" * 60)
    
    # Initialize
    generator = EnhancedTrainingDatasetGenerator(grammar_tool)
    
    # Calculate balanced counts
    regular_positive = TARGET_TRAIN_POSITIVE - SPECIALIST_EXAMPLES
    specialist_positive = SPECIALIST_EXAMPLES
    
    print(f"\n📊 Target Distribution:")
    print(f"   Regular examples: {regular_positive}")
    print(f"   Specialist examples: {specialist_positive} (for weak entities)")
    print(f"   Negative examples: {TARGET_TRAIN_NEGATIVE}")
    print(f"   Total: {regular_positive + specialist_positive + TARGET_TRAIN_NEGATIVE}")
    
    # Generate dataset
    dataset = generator.generate_training_dataset(
        regular_count=regular_positive,
        specialist_count=specialist_positive,
        negative_count=TARGET_TRAIN_NEGATIVE
    )
    
    # Analyze
    analyze_dataset(dataset)
    
    # Save
    print(f"\n💾 Saving files...")
    save_label_map()
    save_training_dataset(dataset)
    
    # Save metadata for analysis
    metadata = {
        "total_examples": len(dataset),
        "regular_count": regular_positive,
        "specialist_count": specialist_positive,
        "negative_count": TARGET_TRAIN_NEGATIVE,
        "weak_entity_focus": ["REL_TIME", "RECURRENCE", "REL_DATE"],
        "hyphenated_tasks_included": True,
        "generation_date": "2024"
    }
    
    with open("./bert_data/dataset_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    # Show examples of each type
    print(f"\n📝 SAMPLE EXAMPLES OF FIXES:")
    print("-" * 60)
    
    # Find examples of each weak entity
    weak_entity_examples = []
    for example in dataset:
        tags = [ID_TO_LABEL[t] for t in example["ner_tags"]]
        if any(weak in tags for weak in ["REL_TIME", "RECURRENCE", "REL_DATE"]):
            weak_entity_examples.append(example)
            if len(weak_entity_examples) >= 3:
                break
    
    for i, example in enumerate(weak_entity_examples[:3], 1):
        tokens = example["tokens"]
        tags = [ID_TO_LABEL[t] for t in example["ner_tags"]]
        
        print(f"\nExample {i} ({example.get('context', 'unknown')}):")
        print(f"Text: {' '.join(tokens)}")
        
        # Show entities
        current_entity = None
        for token, tag in zip(tokens, tags):
            if tag != "O":
                if tag.startswith("B-"):
                    if current_entity:
                        print(f"  Entity: {current_entity}")
                    current_entity = f"{token} ({tag[2:]})"
                elif tag.startswith("I-") and current_entity:
                    current_entity = f"{current_entity.split(' (')[0]} {token} ({tag[2:]})"
        if current_entity:
            print(f"  Entity: {current_entity}")
    
    print("-" * 60)
    print(f"\n✅ ENHANCED dataset generation complete!")
    print(f"\n🎯 Key improvements:")
    print(f"   1. Added {SPECIALIST_EXAMPLES} specialist examples for weak entities")
    print(f"   2. Included {len(HYPHENATED_TASKS)} hyphenated tasks")
    print(f"   3. Expanded REL_TIMES from 10 to {len(REL_TIMES)}")
    print(f"   4. Added clear distinction templates")
    print(f"   5. Special hyphen handling in SentenceBuilder")
    print(f"\n📁 Files saved to ./bert_data/")
    print(f"   - train.jsonl ({len(dataset)} examples)")
    print(f"   - label_map.json")
    print(f"   - dataset_metadata.json")

if __name__ == "__main__":
    main()