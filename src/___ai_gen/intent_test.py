import json
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import os
from datetime import datetime
import webbrowser

# ===============================================================
# 1. Configuration
# ===============================================================
class TestConfig:
    # Path to your trained INTENT model
    MODEL_PATH = "./scheduler_intent_model/checkpoint-500" 
    # Output file
    OUTPUT_HTML = "./intent_test_results.html"
    
config = TestConfig()

# ===============================================================
# 2. Define Label Map (As provided)
# ===============================================================
# We define this explicitly to ensure the test matches your requested schema
label2id = {
  "CREATE_EVENT": 0,
  "UPDATE_EVENT": 1,
  "DELETE_EVENT": 2,
  "QUERY_EVENT": 3,
  "ADD_PARTICIPANT": 4,
  "REMOVE_PARTICIPANT": 5,
  "GREETING": 6,
  "NEGATIVE": 7
}

id2label = {v: k for k, v in label2id.items()}

# ===============================================================
# 3. Load Model
# ===============================================================
print("Loading model...")

try:
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(config.MODEL_PATH)
    model.eval()
    print(f"Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    print(f"Make sure {config.MODEL_PATH} exists and is a SequenceClassification model.")
    # For testing purposes without a real model, we might exit here
    # exit(1)

# ===============================================================
# 4. Test Sentences (50 Examples)
# ===============================================================
test_cases = [
    # --- CREATE_EVENT (1-8) ---
    {"text": "Schedule a meeting with Sarah for tomorrow at 2pm.", "intent": "CREATE_EVENT"},
    {"text": "Book the conference room for the weekly sync.", "intent": "CREATE_EVENT"},
    {"text": "Set up a dentist appointment for Monday morning.", "intent": "CREATE_EVENT"},
    {"text": "Create a new calendar event for the project kickoff.", "intent": "CREATE_EVENT"},
    {"text": "Block out time for deep work this afternoon.", "intent": "CREATE_EVENT"},
    {"text": "Organize a lunch with the client next Friday.", "intent": "CREATE_EVENT"},
    {"text": "Put a reminder on my calendar to call Mom.", "intent": "CREATE_EVENT"},
    {"text": "I need to arrange a quick call with IT support.", "intent": "CREATE_EVENT"},

    # --- UPDATE_EVENT (9-16) ---
    {"text": "Reschedule my 3pm meeting to 4pm.", "intent": "UPDATE_EVENT"},
    {"text": "Move the team sync to Wednesday instead.", "intent": "UPDATE_EVENT"},
    {"text": "Push back the interview by 30 minutes.", "intent": "UPDATE_EVENT"},
    {"text": "Change the location to the main boardroom.", "intent": "UPDATE_EVENT"},
    {"text": "Can we meet at 10am instead of 9am?", "intent": "UPDATE_EVENT"},
    {"text": "Update the description to include the Zoom link.", "intent": "UPDATE_EVENT"},
    {"text": "Delay the start time until everyone arrives.", "intent": "UPDATE_EVENT"},
    {"text": "Shift the workshop to next week please.", "intent": "UPDATE_EVENT"},

    # --- DELETE_EVENT (17-23) ---
    {"text": "Cancel my appointment with Dr. Smith.", "intent": "DELETE_EVENT"},
    {"text": "Remove the recurring stand-up from my calendar.", "intent": "DELETE_EVENT"},
    {"text": "I can't make it to lunch, please delete it.", "intent": "DELETE_EVENT"},
    {"text": "Clear my schedule for the rest of the day.", "intent": "DELETE_EVENT"},
    {"text": "Call off the meeting with marketing.", "intent": "DELETE_EVENT"},
    {"text": "Scrap the event I just created.", "intent": "DELETE_EVENT"},
    {"text": "Delete all events on Sunday.", "intent": "DELETE_EVENT"},

    # --- QUERY_EVENT (24-30) ---
    {"text": "What do I have on today?", "intent": "QUERY_EVENT"},
    {"text": "Show me my schedule for next Tuesday.", "intent": "QUERY_EVENT"},
    {"text": "Am I free tomorrow afternoon?", "intent": "QUERY_EVENT"},
    {"text": "When is my next meeting with John?", "intent": "QUERY_EVENT"},
    {"text": "Do I have any conflicts between 2 and 4?", "intent": "QUERY_EVENT"},
    {"text": "List all appointments for March 15th.", "intent": "QUERY_EVENT"},
    {"text": "Where is my next meeting located?", "intent": "QUERY_EVENT"},

    # --- ADD_PARTICIPANT (31-36) ---
    {"text": "Add Sarah to the project review meeting.", "intent": "ADD_PARTICIPANT"},
    {"text": "Invite the engineering team to this event.", "intent": "ADD_PARTICIPANT"},
    {"text": "Please include Mark in the invite list.", "intent": "ADD_PARTICIPANT"},
    {"text": "Send an invite to alex@example.com.", "intent": "ADD_PARTICIPANT"},
    {"text": "Add John Doe as a required attendee.", "intent": "ADD_PARTICIPANT"},
    {"text": "Make sure the CEO is on the invite.", "intent": "ADD_PARTICIPANT"},

    # --- REMOVE_PARTICIPANT (37-41) ---
    {"text": "Remove Tom from the guest list.", "intent": "REMOVE_PARTICIPANT"},
    {"text": "Uninvite the interns from the strategy session.", "intent": "REMOVE_PARTICIPANT"},
    {"text": "Take Sarah off the meeting invite.", "intent": "REMOVE_PARTICIPANT"},
    {"text": "Don't include the sales team anymore.", "intent": "REMOVE_PARTICIPANT"},
    {"text": "Remove everyone except the managers.", "intent": "REMOVE_PARTICIPANT"},

    # --- GREETING (42-45) ---
    {"text": "Hello assistant.", "intent": "GREETING"},
    {"text": "Good morning.", "intent": "GREETING"},
    {"text": "Hi there, are you ready?", "intent": "GREETING"},
    {"text": "Hey.", "intent": "GREETING"},

    # --- NEGATIVE (46-50) ---
    {"text": "No, cancel that.", "intent": "NEGATIVE"},
    {"text": "Stop.", "intent": "NEGATIVE"},
    {"text": "I didn't mean to do that.", "intent": "NEGATIVE"},
    {"text": "No, that is incorrect.", "intent": "NEGATIVE"},
    {"text": "Don't save.", "intent": "NEGATIVE"}
]

# ===============================================================
# 5. Prediction Logic
# ===============================================================
def predict_intent(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Calculate probabilities
    probs = F.softmax(outputs.logits, dim=-1)
    
    # Get highest probability
    confidence, pred_idx = torch.max(probs, dim=-1)
    
    pred_idx = pred_idx.item()
    confidence = confidence.item()
    
    # Map ID to Label
    label = id2label.get(pred_idx, "UNKNOWN")
    
    return label, confidence

# ===============================================================
# 6. Run Tests and Collect Data
# ===============================================================
print(f"Running tests on {len(test_cases)} sentences...")

results = []
correct_count = 0
category_stats = {k: {"total": 0, "correct": 0} for k in label2id.keys()}

for idx, case in enumerate(test_cases, 1):
    text = case["text"]
    expected = case["intent"]
    
    # Predict
    predicted, confidence = predict_intent(text)
    
    # Check accuracy
    is_correct = (predicted == expected)
    if is_correct:
        correct_count += 1
        
    # Update stats
    if expected in category_stats:
        category_stats[expected]["total"] += 1
        if is_correct:
            category_stats[expected]["correct"] += 1
        
    results.append({
        "id": idx,
        "text": text,
        "expected": expected,
        "predicted": predicted,
        "confidence": confidence,
        "is_correct": is_correct
    })

accuracy = (correct_count / len(test_cases)) * 100

# ===============================================================
# 7. Generate HTML Report
# ===============================================================
print("Generating HTML report...")

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Intent Model Test Results</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f6; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; }}
        
        h1 {{ text-align: center; color: #2c3e50; margin-bottom: 10px; }}
        .summary {{ display: flex; justify-content: space-around; margin-bottom: 30px; border-bottom: 2px solid #eee; padding-bottom: 20px; }}
        .stat {{ text-align: center; }}
        .stat-val {{ font-size: 2.5rem; font-weight: bold; display: block; }}
        .stat-lbl {{ color: #7f8c8d; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; }}
        
        .pass {{ color: #27ae60; }}
        .fail {{ color: #c0392b; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ text-align: left; padding: 15px; background: #34495e; color: white; border-radius: 4px 4px 0 0; }}
        td {{ padding: 12px 15px; border-bottom: 1px solid #eee; vertical-align: middle; }}
        tr:hover {{ background-color: #f8f9fa; }}
        
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: 600; display: inline-block; }}
        .badge-expected {{ background: #e0e0e0; color: #333; }}
        .badge-correct {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .badge-wrong {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        
        .progress-bg {{ background: #e9ecef; border-radius: 4px; height: 8px; width: 100px; display: inline-block; margin-right: 10px; }}
        .progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
        
        .filters {{ margin-bottom: 15px; text-align: right; }}
        input[type="text"] {{ padding: 8px; border: 1px solid #ddd; border-radius: 4px; width: 200px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Intent Classification Report</h1>
        <p style="text-align: center; color: #666;">Model: {model_path}</p>
        
        <div class="summary">
            <div class="stat">
                <span class="stat-val {acc_class}">{accuracy:.1f}%</span>
                <span class="stat-lbl">Accuracy</span>
            </div>
            <div class="stat">
                <span class="stat-val">{correct}/{total}</span>
                <span class="stat-lbl">Correct Predictions</span>
            </div>
            <div class="stat">
                <span class="stat-val">{intents}</span>
                <span class="stat-lbl">Unique Intents</span>
            </div>
        </div>

        <div class="filters">
            <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="Search results...">
        </div>

        <table id="resultsTable">
            <thead>
                <tr>
                    <th width="50">#</th>
                    <th>Text</th>
                    <th>Expected</th>
                    <th>Predicted</th>
                    <th>Confidence</th>
                    <th>Result</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable() {{
            var input, filter, table, tr, td, i, txtValue;
            input = document.getElementById("searchInput");
            filter = input.value.toUpperCase();
            table = document.getElementById("resultsTable");
            tr = table.getElementsByTagName("tr");
            for (i = 0; i < tr.length; i++) {{
                tds = tr[i].getElementsByTagName("td");
                var found = false;
                if (tds.length > 0) {{
                    // Check text, expected, and predicted columns
                    if (tds[1].textContent.toUpperCase().indexOf(filter) > -1 || 
                        tds[2].textContent.toUpperCase().indexOf(filter) > -1 || 
                        tds[3].textContent.toUpperCase().indexOf(filter) > -1) {{
                        found = true;
                    }}
                }}
                if (tr[i].getElementsByTagName("th").length > 0) {{ found = true; }} // Keep header
                tr[i].style.display = found ? "" : "none";
            }}
        }}
    </script>
</body>
</html>
"""

rows_html = ""
for res in results:
    # Determine styles
    status_text = "PASS" if res["is_correct"] else "FAIL"
    status_class = "pass" if res["is_correct"] else "fail"
    pred_class = "badge-correct" if res["is_correct"] else "badge-wrong"
    
    # Confidence bar color
    conf_pct = res["confidence"] * 100
    if conf_pct > 85: bar_color = "#2ecc71"
    elif conf_pct > 60: bar_color = "#f1c40f"
    else: bar_color = "#e74c3c"
    
    rows_html += f"""
    <tr>
        <td>{res['id']}</td>
        <td>{res['text']}</td>
        <td><span class="badge badge-expected">{res['expected']}</span></td>
        <td><span class="badge {pred_class}">{res['predicted']}</span></td>
        <td style="min-width: 160px;">
            <div class="progress-bg"><div class="progress-fill" style="width: {conf_pct}%; background: {bar_color}"></div></div>
            <small>{conf_pct:.1f}%</small>
        </td>
        <td class="{status_class}" style="font-weight: bold;">{status_text}</td>
    </tr>
    """

# Final summary color
acc_class = "pass" if accuracy >= 80 else "fail"

# Write HTML
html_content = html_template.format(
    model_path=config.MODEL_PATH,
    accuracy=accuracy,
    correct=correct_count,
    total=len(test_cases),
    intents=len(label2id),
    acc_class=acc_class,
    rows=rows_html
)

with open(config.OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html_content)

# ===============================================================
# 8. Print Terminal Summary
# ===============================================================
print("\n" + "="*50)
print("📊 TEST SUMMARY")
print("="*50)
print(f"Accuracy: {accuracy:.1f}% ({correct_count}/{len(test_cases)})")
print("-" * 50)
print(f"{'INTENT':<25} {'ACCURACY':<10} {'COUNT'}")
print("-" * 50)

for intent, data in category_stats.items():
    if data["total"] > 0:
        acc = (data["correct"] / data["total"]) * 100
        print(f"{intent:<25} {acc:6.1f}%     {data['correct']}/{data['total']}")

print("\n" + "="*50)
print(f"Report generated at: {os.path.abspath(config.OUTPUT_HTML)}")
webbrowser.open(f"file://{os.path.abspath(config.OUTPUT_HTML)}")