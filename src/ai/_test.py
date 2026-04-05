# ===============================================================
# modernbert_ner_inference.py
# Interactive Testing Script for Token Classification (NER)
# ===============================================================

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification

# --- CONFIGURATION ---
MODEL_PATH = "./modernbert_ner_model/checkpoint-3987"

def main():
    print("Loading ModernBERT NER Model...")
    try:
        # Load tokenizer with add_prefix_space just as we did in training
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, add_prefix_space=True)
        model = AutoModelForTokenClassification.from_pretrained(MODEL_PATH)
        model.eval()
    except Exception as e:
        print(f"Error loading model: {e}")
        print("Ensure the training script has finished and saved to the correct directory.")
        return

    # Grab the id2label mapping from the model config
    id2label = model.config.id2label

    print("\nModel loaded successfully.")
    print("Type your scheduling request below to see the extracted entities.")
    print("Type 'quit' or 'exit' to stop.")
    print("-" * 60)

    while True:
        user_input = input("\nUser Request: ")
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Exiting interactive testing.")
            break
            
        if not user_input.strip():
            continue

        # For NER inference with a Roberta/ModernBERT tokenizer, it's often cleaner
        # to split the input into words first, matching how we trained it.
        words = user_input.split()

        inputs = tokenizer(
            words,
            is_split_into_words=True,
            return_tensors="pt",
            truncation=True,
            max_length=128
        )

        with torch.no_grad():
            outputs = model(**inputs)
        
        # Get the predicted class ID for each token
        predictions = torch.argmax(outputs.logits, dim=2).squeeze().tolist()
        
        # We need the word_ids to map the sub-word token predictions back to the original words
        word_ids = inputs.word_ids()
        
        extracted_entities = []
        current_entity = {"word": "", "label": None}
        previous_word_idx = None

        for idx, word_idx in enumerate(word_ids):
            # Ignore special tokens
            if word_idx is None:
                continue
                
            predicted_label = id2label[predictions[idx]]
            
            # Only process the first token of a given word to avoid sub-word repetition
            if word_idx != previous_word_idx:
                # If it's a new word, check the tag
                if predicted_label != "O":
                    # If it starts with B-, it's a new entity
                    if predicted_label.startswith("B-"):
                        # Save previous entity if one was building
                        if current_entity["label"] is not None:
                            extracted_entities.append(current_entity)
                        
                        current_entity = {
                            "word": words[word_idx], 
                            "label": predicted_label[2:] # Strip the B-
                        }
                    # If it starts with I-, append it to the current entity
                    elif predicted_label.startswith("I-") and current_entity["label"] == predicted_label[2:]:
                        current_entity["word"] += " " + words[word_idx]
                else:
                    # If it's an "O" tag, close out any building entity
                    if current_entity["label"] is not None:
                        extracted_entities.append(current_entity)
                        current_entity = {"word": "", "label": None}
                        
            previous_word_idx = word_idx
            
        # Catch any trailing entity at the end of the sentence
        if current_entity["label"] is not None:
            extracted_entities.append(current_entity)

        # Display results
        if not extracted_entities:
            print("  Extracted Entities: None found.")
        else:
            print("  Extracted Entities:")
            for ent in extracted_entities:
                print(f"    - [{ent['label']}]: {ent['word']}")

if __name__ == "__main__":
    main()