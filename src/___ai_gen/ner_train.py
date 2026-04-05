import os
import json
import numpy as np
import torch
from datasets import load_dataset
import evaluate
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    DataCollatorForTokenClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback
)
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')
os.environ["HF_TOKEN"] = "your_huggingface_token"
# ===============================================================
# 1. Configuration (Improved)
# ===============================================================

class TrainingConfig:
    """Centralized Configuration"""
    MODEL_NAME = "distilbert-base-uncased"
    MAX_LENGTH = 128
    
    # Training Hyperparameters
    BATCH_SIZE = 16
    GRADIENT_ACCUMULATION_STEPS = 2
    EPOCHS = 10
    LEARNING_RATE = 2e-5
    WEIGHT_DECAY = 0.01
    WARMUP_STEPS = 500
    SAVE_STEPS = 500
    EVAL_STEPS = 250
    
    # Paths (VALIDATION SEPARATE FROM TRAINING)
    DATA_DIR = "./bert_data"
    TRAIN_FILE = os.path.join(DATA_DIR, "train.jsonl")
    VALIDATION_FILE = "./validation_data/validation.jsonl"  # From separate script
    TEST_FILE = "./validation_data/test.jsonl"              # From separate script
    LABEL_MAP_FILE = os.path.join(DATA_DIR, "label_map.json")
    
    OUTPUT_DIR = "./scheduler_ner_model"
    LOGGING_DIR = "./logs"
    
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

config = TrainingConfig()

# ===============================================================
# 2. Enhanced Data Processing (Fixes issues)
# ===============================================================

def load_label_map(path):
    """Load label map with error handling"""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        # Convert string keys to int for id2label
        id2label = {int(k): v for k, v in data["id2label"].items()}
        label2id = data["label2id"]
        return id2label, label2id
    except Exception as e:
        print(f"Error loading label map: {e}")
        return {}, {}

def tokenize_and_align_labels(examples, tokenizer, label_all_tokens=False):
    """
    Enhanced alignment that properly handles multi-word entities.
    """
    tokenized_inputs = tokenizer(
        examples["tokens"],
        truncation=True,
        is_split_into_words=True,
        max_length=config.MAX_LENGTH,
        padding="max_length"
    )

    labels = []
    for i, label in enumerate(examples["ner_tags"]):
        word_ids = tokenized_inputs.word_ids(batch_index=i)
        previous_word_idx = None
        label_ids = []
        for word_idx in word_ids:
            if word_idx is None:
                # Special tokens (CLS, SEP, PAD) -> -100
                label_ids.append(-100)
            elif word_idx != previous_word_idx:
                # First token of a word -> use label
                label_ids.append(label[word_idx])
            else:
                # Subsequent token of the same word
                if label_all_tokens:
                    # Keep I- labels for multi-word entities
                    label_ids.append(label[word_idx])
                else:
                    # Use -100 for evaluation (recommended by HF)
                    label_ids.append(-100)
            previous_word_idx = word_idx
        
        # Pad to max_length
        while len(label_ids) < config.MAX_LENGTH:
            label_ids.append(-100)
        
        labels.append(label_ids)

    tokenized_inputs["labels"] = labels
    return tokenized_inputs

def compute_metrics(p, id2label):
    """Enhanced metrics with per-entity breakdown"""
    seqeval = evaluate.load("seqeval")
    predictions, labels = p
    
    # Handle both numpy arrays and tensors
    if hasattr(predictions, "numpy"):
        predictions = predictions.numpy()
    if hasattr(labels, "numpy"):
        labels = labels.numpy()
    
    predictions = np.argmax(predictions, axis=2)

    true_predictions = []
    true_labels = []
    
    for prediction, label in zip(predictions, labels):
        preds_list = []
        labels_list = []
        for p, l in zip(prediction, label):
            if l != -100:  # Ignore padding tokens
                preds_list.append(id2label[p])
                labels_list.append(id2label[l])
        true_predictions.append(preds_list)
        true_labels.append(labels_list)

    results = seqeval.compute(
        predictions=true_predictions,
        references=true_labels,
        zero_division=0
    )
    
    # Handle case when results is None or empty
    if results is None or not isinstance(results, dict):
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "accuracy": 0.0,
        }
    
    # Return both overall and per-entity metrics
    formatted_results = {
        "precision": results.get("overall_precision", 0.0),
        "recall": results.get("overall_recall", 0.0),
        "f1": results.get("overall_f1", 0.0),
        "accuracy": results.get("overall_accuracy", 0.0),
    }
    
    # Add per-entity metrics
    for entity_type in results:
        if entity_type not in ["overall_precision", "overall_recall", "overall_f1", "overall_accuracy"]:
            formatted_results[f"{entity_type}_precision"] = results[entity_type]["precision"]
            formatted_results[f"{entity_type}_recall"] = results[entity_type]["recall"]
            formatted_results[f"{entity_type}_f1"] = results[entity_type]["f1"]
    
    return formatted_results

# ===============================================================
# 3. Enhanced Trainer Setup
# ===============================================================

def create_datasets():
    """Load and prepare datasets with validation"""
    print("Loading datasets...")
    
    data_files = {"train": config.TRAIN_FILE}
    if os.path.exists(config.VALIDATION_FILE):
        data_files["validation"] = config.VALIDATION_FILE
    if os.path.exists(config.TEST_FILE):
        data_files["test"] = config.TEST_FILE
    
    raw_datasets = load_dataset("json", data_files=data_files)
    
    # Load label map
    id2label, label2id = load_label_map(config.LABEL_MAP_FILE)
    
    # Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_NAME)
    
    # Tokenize
    tokenized_datasets = raw_datasets.map(
        lambda x: tokenize_and_align_labels(x, tokenizer, label_all_tokens=False),
        batched=True,
        remove_columns=raw_datasets["train"].column_names
    )
    
    return tokenized_datasets, tokenizer, id2label, label2id

# ===============================================================
# 4. Main Training Function
# ===============================================================

def main():
    print("="*60)
    print("🚀 Enhanced DistilBERT NER Training")
    print("="*60)
    
    # Set seed for reproducibility
    torch.manual_seed(42)
    np.random.seed(42)
    
    # 1. Prepare datasets
    tokenized_datasets, tokenizer, id2label, label2id = create_datasets()
    
    print(f"\n📊 Dataset Sizes:")
    for split, dataset in tokenized_datasets.items():
        print(f"   {split}: {len(dataset)} examples")
    
    # 2. Initialize model
    model = AutoModelForTokenClassification.from_pretrained(
        config.MODEL_NAME,
        num_labels=len(id2label),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True
    )
    model.to(config.DEVICE)
    
    print(f"\n🎯 Labels: {len(id2label)}")
    print(f"🏋️‍♂️  Model parameters: {sum(p.numel() for p in model.parameters()):,}")
    
    # 3. Training arguments (enhanced)
    args = TrainingArguments(
        output_dir=config.OUTPUT_DIR,
        eval_strategy="steps" if "validation" in tokenized_datasets else "epoch",
        eval_steps=config.EVAL_STEPS,
        save_strategy="steps",
        save_steps=config.SAVE_STEPS,
        learning_rate=config.LEARNING_RATE,
        per_device_train_batch_size=config.BATCH_SIZE,
        per_device_eval_batch_size=config.BATCH_SIZE,
        gradient_accumulation_steps=config.GRADIENT_ACCUMULATION_STEPS,
        num_train_epochs=config.EPOCHS,
        weight_decay=config.WEIGHT_DECAY,
        warmup_steps=config.WARMUP_STEPS,
        load_best_model_at_end=True if "validation" in tokenized_datasets else False,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_dir=config.LOGGING_DIR,
        logging_steps=50,
        report_to="none",
        fp16=config.DEVICE == "cuda",
        push_to_hub=False,
        save_total_limit=2,
    )
    
    # 4. Create compute_metrics function with label mapping
    compute_metrics_func = lambda p: compute_metrics(p, id2label)
    
    # 5. Trainer
    data_collator = DataCollatorForTokenClassification(tokenizer)
    
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets.get("validation"),
        data_collator=data_collator,
        compute_metrics=compute_metrics_func,
        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=3,
                early_stopping_threshold=0.001
            )
        ] if "validation" in tokenized_datasets else []
    )
    
    # 6. Train
    print("\n🔥 Starting training...")
    train_result = trainer.train()
    
    # 7. Save everything
    print(f"\n💾 Saving model to {config.OUTPUT_DIR}...")
    trainer.save_model()
    tokenizer.save_pretrained(config.OUTPUT_DIR)
    
    # Save training metrics
    train_metrics = train_result.metrics
    with open(os.path.join(config.OUTPUT_DIR, "training_metrics.json"), "w") as f:
        json.dump(train_metrics, f, indent=2)
    
    # Save label map
    with open(os.path.join(config.OUTPUT_DIR, "label_map.json"), "w") as f:
        json.dump({"id2label": id2label, "label2id": label2id}, f, indent=2)
    
    # 8. Evaluate on test set if available
    if "test" in tokenized_datasets:
        print("\n📊 Evaluating on test set...")
        test_results = trainer.evaluate(eval_dataset=tokenized_datasets["test"])  # type: ignore
        
        print(f"\n🎯 Test Results:")
        print(f"   F1 Score: {test_results.get('eval_f1', 0):.4f}")
        print(f"   Precision: {test_results.get('eval_precision', 0):.4f}")
        print(f"   Recall: {test_results.get('eval_recall', 0):.4f}")
        print(f"   Accuracy: {test_results.get('eval_accuracy', 0):.4f}")
        
        # Save test metrics
        with open(os.path.join(config.OUTPUT_DIR, "test_metrics.json"), "w") as f:
            json.dump(test_results, f, indent=2)
    
    # 9. Quick inference test
    print("\n" + "="*60)
    print("🎯 Quick Inference Test")
    print("="*60)
    
    test_sentences = [
        "Schedule a meeting with Sarah next Friday at 2pm in Room 4.",
        "Book dental appointment on March 15th at 3pm.",
        "Cancel my gym session and book yoga class instead.",
    ]
    
    # Simple inference function
    def predict_simple(text, model, tokenizer, id2label):
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(config.DEVICE)
        with torch.no_grad():
            outputs = model(**inputs)
        
        predictions = torch.argmax(outputs.logits, dim=2).squeeze().cpu().numpy()
        tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"].squeeze())
        
        # Extract entities
        entities = []
        current_entity = {"text": "", "label": None}
        
        for token, pred in zip(tokens, predictions):
            if token in ["[CLS]", "[SEP]", "[PAD]"]:
                continue
            
            label = id2label[pred]
            clean_token = token.replace("##", "")
            
            if label.startswith("B-"):
                if current_entity["text"]:
                    entities.append(current_entity)
                current_entity = {"text": clean_token, "label": label[2:]}
            elif label.startswith("I-") and current_entity["label"] == label[2:]:
                current_entity["text"] += " " + clean_token if not token.startswith("##") else clean_token
            else:
                if current_entity["text"]:
                    entities.append(current_entity)
                current_entity = {"text": "", "label": None}
        
        if current_entity["text"]:
            entities.append(current_entity)
        
        return entities
    
    # Test predictions
    for sentence in test_sentences:
        print(f"\n📝 Input: {sentence}")
        entities = predict_simple(sentence, model, tokenizer, id2label)
        if entities:
            for ent in entities:
                print(f"   - {ent['label']}: {ent['text']}")
        else:
            print("   No entities detected")
    
    print("\n" + "="*60)
    print("✅ Training completed successfully!")
    print(f"\n📁 Model saved to: {config.OUTPUT_DIR}")
    print(f"📊 Metrics saved in: {os.path.join(config.OUTPUT_DIR, '*.json')}")

if __name__ == "__main__":
    main()