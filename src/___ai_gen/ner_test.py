# test_ner_model.py
import json
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
import numpy as np
from collections import defaultdict
import random
from pathlib import Path

# ===============================================================
# 1. Configuration
# ===============================================================
class TestConfig:
    MODEL_PATH = "./scheduler_ner_model/checkpoint-500"  # Your best model
    LABEL_MAP_PATH = "./bert_data/label_map.json"
    OUTPUT_HTML = "./ner_test_results.html"
    
config = TestConfig()

# ===============================================================
# 2. Load Model and Labels
# ===============================================================
print("Loading model and labels...")
tokenizer = AutoTokenizer.from_pretrained(config.MODEL_PATH)
model = AutoModelForTokenClassification.from_pretrained(config.MODEL_PATH)
model.eval()

# Load label map
with open(config.LABEL_MAP_PATH, "r") as f:
    label_data = json.load(f)
    
id2label = {int(k): v for k, v in label_data["id2label"].items()}
label2id = label_data["label2id"]

print(f"Model loaded with {len(id2label)} labels")

# ===============================================================
# 3. Test Sentences with Ground Truth
# ===============================================================
test_cases = [
    # 1-10: Simple scheduling
    {
        "text": "Book a strategy session with Alex next Monday at 10am",
        "entities": [
            ("strategy session", "TASK_TITLE"),
            ("Alex", "PARTICIPANT"),
            ("next Monday", "REL_DATE"),
            ("10am", "ABS_TIME")
        ]
    },
    {
        "text": "Schedule quarterly review for March 15th in Boardroom A",
        "entities": [
            ("quarterly review", "TASK_TITLE"),
            ("March 15th", "ABS_DATE"),
            ("Boardroom A", "LOCATION")
        ]
    },
    {
        "text": "Set up team sync every Wednesday at 3pm",
        "entities": [
            ("team sync", "TASK_TITLE"),
            ("every Wednesday", "RECURRENCE"),
            ("3pm", "ABS_TIME")
        ]
    },
    {
        "text": "Arrange client meeting tomorrow afternoon for 2 hours",
        "entities": [
            ("client meeting", "TASK_TITLE"),
            ("tomorrow afternoon", "REL_TIME"),
            ("2 hours", "DURATION")
        ]
    },
    {
        "text": "Reserve conference room B for budget planning",
        "entities": [
            ("conference room B", "LOCATION"),
            ("budget planning", "TASK_TITLE")
        ]
    },
    {
        "text": "Coordinate project kickoff with engineering team next week",
        "entities": [
            ("project kickoff", "TASK_TITLE"),
            ("engineering team", "PARTICIPANT"),
            ("next week", "REL_DATE")
        ]
    },
    {
        "text": "Plan department lunch on Friday at noon",
        "entities": [
            ("department lunch", "TASK_TITLE"),
            ("Friday", "REL_DATE"),
            ("noon", "ABS_TIME")
        ]
    },
    {
        "text": "Organize training session lasting 4 hours",
        "entities": [
            ("training session", "TASK_TITLE"),
            ("4 hours", "DURATION")
        ]
    },
    {
        "text": "Book flight to conference on October 30th",
        "entities": [
            ("flight to conference", "TASK_TITLE"),
            ("October 30th", "ABS_DATE")
        ]
    },
    {
        "text": "Schedule dental cleaning at 2:30pm tomorrow",
        "entities": [
            ("dental cleaning", "TASK_TITLE"),
            ("2:30pm", "ABS_TIME"),
            ("tomorrow", "REL_DATE")
        ]
    },
    
    # 11-20: Academic context
    {
        "text": "Arrange study group with classmates this evening",
        "entities": [
            ("study group", "TASK_TITLE"),
            ("classmates", "PARTICIPANT"),
            ("this evening", "REL_TIME")
        ]
    },
    {
        "text": "Book library room for thesis writing on March 10th",
        "entities": [
            ("library room", "LOCATION"),
            ("thesis writing", "TASK_TITLE"),
            ("March 10th", "ABS_DATE")
        ]
    },
    {
        "text": "Schedule meeting with Professor Smith at 11am",
        "entities": [
            ("meeting", "TASK_TITLE"),
            ("Professor Smith", "PARTICIPANT"),
            ("11am", "ABS_TIME")
        ]
    },
    {
        "text": "Plan lab session for 3 hours tomorrow morning",
        "entities": [
            ("lab session", "TASK_TITLE"),
            ("3 hours", "DURATION"),
            ("tomorrow morning", "REL_TIME")
        ]
    },
    {
        "text": "Organize group presentation practice weekly",
        "entities": [
            ("group presentation practice", "TASK_TITLE"),
            ("weekly", "RECURRENCE")
        ]
    },
    {
        "text": "Book computer lab for coding workshop",
        "entities": [
            ("computer lab", "LOCATION"),
            ("coding workshop", "TASK_TITLE")
        ]
    },
    {
        "text": "Schedule final exam review session next Monday",
        "entities": [
            ("final exam review session", "TASK_TITLE"),
            ("next Monday", "REL_DATE")
        ]
    },
    {
        "text": "Arrange tutoring session with TA for 45 minutes",
        "entities": [
            ("tutoring session", "TASK_TITLE"),
            ("TA", "PARTICIPANT"),
            ("45 minutes", "DURATION")
        ]
    },
    {
        "text": "Plan research meeting every other Thursday",
        "entities": [
            ("research meeting", "TASK_TITLE"),
            ("every other Thursday", "RECURRENCE")
        ]
    },
    {
        "text": "Book auditorium for guest lecture on April 5th",
        "entities": [
            ("auditorium", "LOCATION"),
            ("guest lecture", "TASK_TITLE"),
            ("April 5th", "ABS_DATE")
        ]
    },
    
    # 21-30: Personal/Recreation
    {
        "text": "Schedule dinner with family at 7pm Saturday",
        "entities": [
            ("dinner", "TASK_TITLE"),
            ("family", "PARTICIPANT"),
            ("7pm", "ABS_TIME"),
            ("Saturday", "REL_DATE")
        ]
    },
    {
        "text": "Book yoga class tomorrow morning at the studio",
        "entities": [
            ("yoga class", "TASK_TITLE"),
            ("tomorrow morning", "REL_TIME"),
            ("studio", "LOCATION")
        ]
    },
    {
        "text": "Arrange doctor appointment for next Tuesday",
        "entities": [
            ("doctor appointment", "TASK_TITLE"),
            ("next Tuesday", "REL_DATE")
        ]
    },
    {
        "text": "Plan movie night with friends this weekend",
        "entities": [
            ("movie night", "TASK_TITLE"),
            ("friends", "PARTICIPANT"),
            ("this weekend", "REL_DATE")
        ]
    },
    {
        "text": "Book haircut at salon for 30 minutes",
        "entities": [
            ("haircut", "TASK_TITLE"),
            ("salon", "LOCATION"),
            ("30 minutes", "DURATION")
        ]
    },
    {
        "text": "Schedule gym session daily at 6am",
        "entities": [
            ("gym session", "TASK_TITLE"),
            ("daily", "RECURRENCE"),
            ("6am", "ABS_TIME")
        ]
    },
    {
        "text": "Arrange car service appointment on Monday",
        "entities": [
            ("car service appointment", "TASK_TITLE"),
            ("Monday", "REL_DATE")
        ]
    },
    {
        "text": "Plan birthday party for 3 hours Saturday evening",
        "entities": [
            ("birthday party", "TASK_TITLE"),
            ("3 hours", "DURATION"),
            ("Saturday evening", "REL_TIME")
        ]
    },
    {
        "text": "Book tennis court at park for Sunday",
        "entities": [
            ("tennis court", "LOCATION"),
            ("park", "LOCATION"),
            ("Sunday", "REL_DATE")
        ]
    },
    {
        "text": "Schedule therapy session every two weeks",
        "entities": [
            ("therapy session", "TASK_TITLE"),
            ("every two weeks", "RECURRENCE")
        ]
    },
    
    # 31-40: Complex/multi-entity
    {
        "text": "Coordinate team offsite with marketing department on June 20th at 9am for full day",
        "entities": [
            ("team offsite", "TASK_TITLE"),
            ("marketing department", "PARTICIPANT"),
            ("June 20th", "ABS_DATE"),
            ("9am", "ABS_TIME"),
            ("full day", "DURATION")
        ]
    },
    {
        "text": "Book flight and hotel for conference from November 5th to 8th",
        "entities": [
            ("flight and hotel for conference", "TASK_TITLE"),
            ("November 5th", "ABS_DATE"),
            ("8th", "ABS_DATE")
        ]
    },
    {
        "text": "Schedule product demo with client XYZ tomorrow at 2pm in Meeting Room 3",
        "entities": [
            ("product demo", "TASK_TITLE"),
            ("client XYZ", "PARTICIPANT"),
            ("tomorrow", "REL_DATE"),
            ("2pm", "ABS_TIME"),
            ("Meeting Room 3", "LOCATION")
        ]
    },
    {
        "text": "Arrange monthly budget review with finance team every first Monday",
        "entities": [
            ("monthly budget review", "TASK_TITLE"),
            ("finance team", "PARTICIPANT"),
            ("every first Monday", "RECURRENCE")
        ]
    },
    {
        "text": "Plan summer vacation from July 15th to 22nd",
        "entities": [
            ("summer vacation", "TASK_TITLE"),
            ("July 15th", "ABS_DATE"),
            ("22nd", "ABS_DATE")
        ]
    },
    {
        "text": "Book multiple meeting rooms for all-day workshop on Friday",
        "entities": [
            ("multiple meeting rooms", "LOCATION"),
            ("all-day workshop", "TASK_TITLE"),
            ("Friday", "REL_DATE")
        ]
    },
    {
        "text": "Schedule back-to-back interviews with candidates from 9am to 5pm",
        "entities": [
            ("back-to-back interviews", "TASK_TITLE"),
            ("candidates", "PARTICIPANT"),
            ("9am", "ABS_TIME"),
            ("5pm", "ABS_TIME")
        ]
    },
    {
        "text": "Arrange company retreat at mountain lodge for 3 days",
        "entities": [
            ("company retreat", "TASK_TITLE"),
            ("mountain lodge", "LOCATION"),
            ("3 days", "DURATION")
        ]
    },
    {
        "text": "Plan website launch meeting with dev team and designers",
        "entities": [
            ("website launch meeting", "TASK_TITLE"),
            ("dev team", "PARTICIPANT"),
            ("designers", "PARTICIPANT")
        ]
    },
    {
        "text": "Book catering for team lunch tomorrow at noon in cafeteria",
        "entities": [
            ("catering for team lunch", "TASK_TITLE"),
            ("tomorrow", "REL_DATE"),
            ("noon", "ABS_TIME"),
            ("cafeteria", "LOCATION")
        ]
    },
    
    # 41-50: Edge cases and tricky patterns
    {
        "text": "Schedule meeting meeting about meetings",  # Repetition test
        "entities": [
            ("meeting about meetings", "TASK_TITLE")
        ]
    },
    {
        "text": "Book now for later today",  # Vague time
        "entities": [
            ("later today", "REL_TIME")
        ]
    },
    {
        "text": "Arrange call with John and Sarah at 3",  # Multiple people, short time
        "entities": [
            ("call", "TASK_TITLE"),
            ("John", "PARTICIPANT"),
            ("Sarah", "PARTICIPANT"),
            ("3", "ABS_TIME")
        ]
    },
    {
        "text": "Schedule test test for testing",  # Ambiguous
        "entities": [
            ("test for testing", "TASK_TITLE")
        ]
    },
    {
        "text": "Book room 404 at 4:04 on 4/4",  # Number patterns
        "entities": [
            ("room 404", "LOCATION"),
            ("4:04", "ABS_TIME"),
            ("4/4", "ABS_DATE")
        ]
    },
    {
        "text": "Plan early morning session before sunrise",  # Relative time
        "entities": [
            ("early morning session", "TASK_TITLE"),
            ("before sunrise", "REL_TIME")
        ]
    },
    {
        "text": "Schedule quarterly review Q1 2024",  # Business quarter
        "entities": [
            ("quarterly review", "TASK_TITLE"),
            ("Q1 2024", "ABS_DATE")
        ]
    },
    {
        "text": "Book appointment with Dr. Watson at 221B Baker Street",
        "entities": [
            ("appointment", "TASK_TITLE"),
            ("Dr. Watson", "PARTICIPANT"),
            ("221B Baker Street", "LOCATION")
        ]
    },
    {
        "text": "Arrange call re: project alpha status update",
        "entities": [
            ("call", "TASK_TITLE"),
            ("project alpha status update", "TASK_TITLE")
        ]
    },
    {
        "text": "Schedule team building every other month at resort",
        "entities": [
            ("team building", "TASK_TITLE"),
            ("every other month", "RECURRENCE"),
            ("resort", "LOCATION")
        ]
    }
]

# ===============================================================
# 4. Prediction Function
# ===============================================================
def extract_entities(text):
    """Extract entities from text using the trained model"""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    predictions = torch.argmax(outputs.logits, dim=2).squeeze().numpy()
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"].squeeze())
    
    # Extract entities
    entities = []
    current_entity = {"text": "", "label": None, "start": None, "end": None}
    
    for i, (token, pred_idx) in enumerate(zip(tokens, predictions)):
        if token in ["[CLS]", "[SEP]", "[PAD]"]:
            continue
            
        label = id2label.get(pred_idx, "O")
        clean_token = token.replace("##", "")
        
        if label.startswith("B-"):
            # Save previous entity if exists
            if current_entity["text"]:
                entities.append(current_entity.copy())
            # Start new entity
            current_entity = {
                "text": clean_token,
                "label": label[2:],  # Remove "B-"
                "start": i,
                "end": i
            }
        elif label.startswith("I-") and current_entity["label"] == label[2:]:
            # Continue entity
            if token.startswith("##"):
                current_entity["text"] += clean_token
            else:
                current_entity["text"] += " " + clean_token
            current_entity["end"] = i
        else:
            # Save previous entity if exists
            if current_entity["text"]:
                entities.append(current_entity.copy())
            current_entity = {"text": "", "label": None, "start": None, "end": None}
    
    # Save last entity
    if current_entity["text"]:
        entities.append(current_entity)
    
    return entities

def format_entities_for_html(entities):
    """Format entities for HTML display"""
    if not entities:
        return "<span class='no-entities'>No entities detected</span>"
    
    html_parts = []
    for ent in entities:
        color_map = {
            "TASK_TITLE": "#4CAF50",
            "PARTICIPANT": "#2196F3",
            "LOCATION": "#FF9800",
            "ABS_DATE": "#9C27B0",
            "REL_DATE": "#673AB7",
            "ABS_TIME": "#F44336",
            "REL_TIME": "#E91E63",
            "DURATION": "#00BCD4",
            "RECURRENCE": "#795548"
        }
        color = color_map.get(ent["label"], "#607D8B")
        html_parts.append(
            f'<span class="entity" style="background-color: {color}" '
            f'title="{ent["label"]}">{ent["text"]}</span>'
        )
    
    return " ".join(html_parts)

# ===============================================================
# 5. Run Tests
# ===============================================================
print(f"Running tests on {len(test_cases)} sentences...")

results = []
overall_stats = {
    "total_expected": 0,
    "total_correct": 0,
    "entity_stats": defaultdict(lambda: {"expected": 0, "correct": 0})
}

for idx, test_case in enumerate(test_cases, 1):
    text = test_case["text"]
    expected_entities = test_case["entities"]
    
    # Get predictions
    predicted_entities = extract_entities(text)
    
    # Convert to comparable format
    predicted_set = {(ent["text"].lower(), ent["label"]) for ent in predicted_entities}
    expected_set = {(text.lower(), label) for text, label in expected_entities}
    
    # Calculate matches
    correct_matches = predicted_set.intersection(expected_set)
    
    # Update statistics
    overall_stats["total_expected"] += len(expected_set)
    overall_stats["total_correct"] += len(correct_matches)
    
    for _, label in expected_entities:
        overall_stats["entity_stats"][label]["expected"] += 1
        if (text.lower(), label) in correct_matches:
            overall_stats["entity_stats"][label]["correct"] += 1
    
    # Store results
    results.append({
        "id": idx,
        "text": text,
        "predicted": predicted_entities,
        "expected": expected_entities,
        "correct_matches": len(correct_matches),
        "total_expected": len(expected_set),
        "accuracy": len(correct_matches) / len(expected_set) if expected_set else 0
    })
    
    # Print progress
    if idx % 10 == 0:
        print(f"  Processed {idx}/{len(test_cases)} tests...")

# ===============================================================
# 6. Generate HTML Report
# ===============================================================
print("Generating HTML report...")

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NER Model Test Results</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #3498db, #2ecc71);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .accuracy-high {{ color: #2ecc71; }}
        .accuracy-medium {{ color: #f39c12; }}
        .accuracy-low {{ color: #e74c3c; }}
        
        .entity-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            padding: 20px;
            background: #f8f9fa;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 15px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            font-size: 0.9rem;
        }}
        
        .legend-color {{
            width: 15px;
            height: 15px;
            border-radius: 3px;
        }}
        
        .test-results {{
            padding: 30px;
        }}
        
        .test-case {{
            background: white;
            margin-bottom: 25px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            border-left: 5px solid #3498db;
        }}
        
        .test-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .test-id {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 1.1rem;
        }}
        
        .test-accuracy {{
            font-weight: bold;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
        }}
        
        .test-content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0;
        }}
        
        .test-column {{
            padding: 25px;
        }}
        
        .test-column:first-child {{
            border-right: 2px dashed #e9ecef;
        }}
        
        .column-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
            display: inline-block;
        }}
        
        .original-text {{
            font-size: 1.2rem;
            line-height: 1.5;
            margin-bottom: 25px;
            color: #2c3e50;
            font-weight: 500;
        }}
        
        .entity {{
            display: inline-block;
            padding: 3px 8px;
            margin: 2px;
            border-radius: 4px;
            color: white;
            font-weight: 500;
            font-size: 0.9rem;
            position: relative;
            cursor: help;
        }}
        
        .entity:hover::after {{
            content: attr(title);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: white;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.8rem;
            white-space: nowrap;
            z-index: 1000;
        }}
        
        .no-entities {{
            color: #95a5a6;
            font-style: italic;
        }}
        
        .entity-list {{
            margin-top: 15px;
        }}
        
        .entity-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px;
            margin-bottom: 5px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9rem;
            border-top: 1px solid #e9ecef;
        }}
        
        @media (max-width: 768px) {{
            .test-content {{
                grid-template-columns: 1fr;
            }}
            
            .test-column:first-child {{
                border-right: none;
                border-bottom: 2px dashed #e9ecef;
            }}
            
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NER Model Test Results</h1>
            <p>Model: DistilBERT NER | Test Cases: {total_tests} | Unseen Sentences</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Overall Accuracy</div>
                <div class="stat-value accuracy-high">{overall_accuracy}%</div>
                <div>{total_correct}/{total_expected} entities correct</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Test Cases</div>
                <div class="stat-value">{total_tests}</div>
                <div>Unseen sentences</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Entity Types</div>
                <div class="stat-value">{entity_types}</div>
                <div>Different entity labels</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Perfect Scores</div>
                <div class="stat-value accuracy-high">{perfect_tests}</div>
                <div>100% accurate test cases</div>
            </div>
        </div>
        
        <div class="entity-legend">
            {legend_html}
        </div>
        
        <div class="test-results">
            {test_cases_html}
        </div>
        
        <div class="footer">
            Generated on {timestamp} | Model: {model_name} | Test Set: 50 unseen sentences
        </div>
    </div>
    
    <script>
        // Add interactivity
        document.addEventListener('DOMContentLoaded', function() {{
            // Highlight matching entities
            const entities = document.querySelectorAll('.entity');
            entities.forEach(entity => {{
                entity.addEventListener('click', function() {{
                    const label = this.getAttribute('title');
                    const matches = document.querySelectorAll(`.entity[title="${{label}}"]`);
                    
                    // Toggle highlight
                    matches.forEach(match => {{
                        match.classList.toggle('highlighted');
                    }});
                }});
            }});
            
            // Add search functionality
            const searchInput = document.createElement('input');
            searchInput.type = 'text';
            searchInput.placeholder = 'Search test cases...';
            searchInput.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 10px 15px;
                border: none;
                border-radius: 25px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                width: 250px;
                z-index: 1000;
            `;
            
            document.body.appendChild(searchInput);
            
            searchInput.addEventListener('input', function(e) {{
                const searchTerm = e.target.value.toLowerCase();
                const testCases = document.querySelectorAll('.test-case');
                
                testCases.forEach(testCase => {{
                    const text = testCase.textContent.toLowerCase();
                    if (text.includes(searchTerm)) {{
                        testCase.style.display = 'block';
                    }} else {{
                        testCase.style.display = 'none';
                    }}
                }});
            }});
            
            // Add entity statistics modal
            const statsBtn = document.createElement('button');
            statsBtn.textContent = '📈 Entity Stats';
            statsBtn.style.cssText = `
                position: fixed;
                top: 20px;
                left: 20px;
                padding: 10px 20px;
                background: linear-gradient(45deg, #3498db, #2ecc71);
                color: white;
                border: none;
                border-radius: 25px;
                cursor: pointer;
                z-index: 1000;
                font-weight: bold;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            `;
            
            document.body.appendChild(statsBtn);
            
            statsBtn.addEventListener('click', function() {{
                alert(`Entity Statistics:\\n\\n{entity_stats_text}`);
            }});
        }});
    </script>
</body>
</html>
"""

# Generate legend HTML
entity_colors = {
    "TASK_TITLE": "#4CAF50",
    "PARTICIPANT": "#2196F3",
    "LOCATION": "#FF9800",
    "ABS_DATE": "#9C27B0",
    "REL_DATE": "#673AB7",
    "ABS_TIME": "#F44336",
    "REL_TIME": "#E91E63",
    "DURATION": "#00BCD4",
    "RECURRENCE": "#795548"
}

legend_html = ""
for label, color in entity_colors.items():
    if label in overall_stats["entity_stats"]:
        legend_html += f'''
        <div class="legend-item">
            <div class="legend-color" style="background-color: {color}"></div>
            <span>{label}</span>
        </div>
        '''

# Generate test cases HTML
test_cases_html = ""
perfect_tests = 0

for result in results:
    # Format accuracy badge
    accuracy = result["accuracy"]
    if accuracy == 1:
        accuracy_class = "accuracy-high"
        perfect_tests += 1
    elif accuracy >= 0.5:
        accuracy_class = "accuracy-medium"
    else:
        accuracy_class = "accuracy-low"
    
    # Format predicted entities
    predicted_html = format_entities_for_html(result["predicted"])
    
    # Format expected entities
    expected_entities_html = []
    for text, label in result["expected"]:
        color = entity_colors.get(label, "#607D8B")
        expected_entities_html.append(
            f'<span class="entity" style="background-color: {color}" '
            f'title="{label}">{text}</span>'
        )
    expected_html = " ".join(expected_entities_html) if expected_entities_html else "<span class='no-entities'>No entities expected</span>"
    
    # Create entity lists
    predicted_list = ""
    for ent in result["predicted"]:
        color = entity_colors.get(ent["label"], "#607D8B")
        predicted_list += f'''
        <div class="entity-item">
            <div class="legend-color" style="background-color: {color}"></div>
            <span><strong>{ent["label"]}:</strong> {ent["text"]}</span>
        </div>
        '''
    
    expected_list = ""
    for text, label in result["expected"]:
        color = entity_colors.get(label, "#607D8B")
        expected_list += f'''
        <div class="entity-item">
            <div class="legend-color" style="background-color: {color}"></div>
            <span><strong>{label}:</strong> {text}</span>
        </div>
        '''
    
    test_cases_html += f'''
    <div class="test-case">
        <div class="test-header">
            <div class="test-id">Test #{result["id"]}</div>
            <div class="test-accuracy {accuracy_class}">
                Accuracy: {accuracy*100:.1f}% ({result["correct_matches"]}/{result["total_expected"]})
            </div>
        </div>
        <div class="test-content">
            <div class="test-column">
                <div class="column-title">🤖 AI Predictions</div>
                <div class="original-text">{result["text"]}</div>
                <div class="entity-display">
                    {predicted_html}
                </div>
                <div class="entity-list">
                    {predicted_list if predicted_list else "<div class='no-entities'>No entities detected</div>"}
                </div>
            </div>
            <div class="test-column">
                <div class="column-title">🎯 Expected Results</div>
                <div class="original-text">{result["text"]}</div>
                <div class="entity-display">
                    {expected_html}
                </div>
                <div class="entity-list">
                    {expected_list if expected_list else "<div class='no-entities'>No entities expected</div>"}
                </div>
            </div>
        </div>
    </div>
    '''

# Calculate overall accuracy
overall_accuracy = (overall_stats["total_correct"] / overall_stats["total_expected"] * 100) if overall_stats["total_expected"] > 0 else 0

# Generate entity stats text
entity_stats_text = ""
for label, stats in overall_stats["entity_stats"].items():
    accuracy = (stats["correct"] / stats["expected"] * 100) if stats["expected"] > 0 else 0
    entity_stats_text += f"{label}: {stats['correct']}/{stats['expected']} ({accuracy:.1f}%)\\n"

# Fill template
from datetime import datetime
html_content = html_template.format(
    total_tests=len(test_cases),
    overall_accuracy=f"{overall_accuracy:.1f}",
    total_correct=overall_stats["total_correct"],
    total_expected=overall_stats["total_expected"],
    entity_types=len(entity_colors),
    perfect_tests=perfect_tests,
    legend_html=legend_html,
    test_cases_html=test_cases_html,
    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    model_name="DistilBERT NER Scheduler",
    entity_stats_text=entity_stats_text
)

# Save HTML file
with open(config.OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html_content)

# ===============================================================
# 7. Print Summary
# ===============================================================
print(f"\n{'='*60}")
print("📊 TEST SUMMARY")
print(f"{'='*60}")

print(f"\n📈 Overall Statistics:")
print(f"  • Total test cases: {len(test_cases)}")
print(f"  • Expected entities: {overall_stats['total_expected']}")
print(f"  • Correct predictions: {overall_stats['total_correct']}")
print(f"  • Overall accuracy: {overall_accuracy:.1f}%")
print(f"  • Perfect scores: {perfect_tests}/{len(test_cases)} test cases")

print(f"\n🏆 Entity Performance:")
for label, stats in sorted(overall_stats["entity_stats"].items()):
    if stats["expected"] > 0:
        accuracy = stats["correct"] / stats["expected"] * 100
        print(f"  • {label:15}: {stats['correct']:3}/{stats['expected']:3} ({accuracy:5.1f}%)")

print(f"\n📁 Output Files:")
print(f"  • HTML Report: {config.OUTPUT_HTML}")
print(f"  • Best Model: {config.MODEL_PATH}")

print(f"\n🎯 Recommendations:")
if overall_accuracy < 70:
    print("  ⚠️  Model needs improvement. Consider:")
    print("     - More training data for weak entities")
    print("     - Hyperparameter tuning")
    print("     - Data augmentation")
elif overall_accuracy < 85:
    print("  ✅ Good performance! For improvement:")
    print("     - Focus on weak entity types")
    print("     - Add more diverse examples")
else:
    print("  🎉 Excellent performance! Model is ready for deployment.")

# Open HTML in browser
import webbrowser
import os

html_path = os.path.abspath(config.OUTPUT_HTML)
print(f"\n🌐 Opening results in browser...")
webbrowser.open(f"file://{html_path}")

print(f"\n✅ Test completed! Open {config.OUTPUT_HTML} to see detailed results.")