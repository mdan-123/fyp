import json
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from collections import defaultdict

# 1. Configuration
MODEL_PATH = "./modernbert_intent_modelv2/checkpoint-2160" 
DATA_PATH = "./modernbert_data/multilabel_intent_train.jsonl"
OUTPUT_FILE = "intent_centroids.npy"

print("Loading model and tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModel.from_pretrained(MODEL_PATH)
model.eval() 

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# 2. Load Your JSONL Training Data
print(f"Loading training data from {DATA_PATH}...")
training_data = []
with open(DATA_PATH, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip(): 
            training_data.append(json.loads(line))

# 3. Group texts by their multi-hot labels
intent_texts = defaultdict(list)
for item in training_data:
    text = item.get("text", "")
    labels = item.get("labels", [])
    
    # Enumerate through the 16 floats. If it is 1.0, add the text to that intent's list.
    for intent_idx, is_active in enumerate(labels):
        if is_active == 1.0:
            intent_texts[intent_idx].append(text)

def get_embeddings(text_list):
    """Passes text through ModernBERT and extracts the [CLS] token embedding."""
    inputs = tokenizer(
        text_list, 
        padding=True, 
        truncation=True, 
        return_tensors="pt", 
        max_length=128
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = model(**inputs)
        
    cls_embeddings = outputs.last_hidden_state[:, 0, :]
    return cls_embeddings.cpu().numpy()

# 4. Calculate Centroids
print("Calculating centroids...")
centroids = {}

for intent_id, texts in intent_texts.items():
    print(f"Processing Intent {intent_id} ({len(texts)} samples)...")
    
    batch_size = 32
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_embeddings = get_embeddings(batch_texts)
        all_embeddings.append(batch_embeddings)
        
    stacked_embeddings = np.vstack(all_embeddings)
    centroid = np.mean(stacked_embeddings, axis=0)
    centroids[intent_id] = centroid

# 5. Save the Centroids to Disk
print(f"Saving centroids to {OUTPUT_FILE}...")
centroids_array = np.array([centroids[i] for i in sorted(centroids.keys())])
np.save(OUTPUT_FILE, centroids_array)
print("Done! Centroids are ready for production inference.")