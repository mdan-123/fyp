import json
import numpy as np
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    TrainingArguments, 
    Trainer,
    DataCollatorWithPadding
)
from sklearn.metrics import f1_score, accuracy_score

def main():
    model_name = "roberta-base"
    
    print("Initialising dataset loading...")
    dataset = load_dataset("json", data_files={
        "train": "./deberta_data/multilabel_intent_train.jsonl",
        "validation": "./deberta_data/multilabel_intent_validation.jsonl"
    })

    print("Loading intent label configuration...")
    with open("./deberta_data/intent_label_map.json", "r") as f:
        label_map = json.load(f)
    
    id2label = {int(v): k for k, v in label_map.items()}
    label2id = {k: int(v) for k, v in label_map.items()}
    num_labels = len(id2label)

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def preprocess_function(examples):
        tokenized_inputs = tokenizer(
            examples["text"], 
            truncation=True, 
            max_length=128
        )
        
        tokenized_inputs["labels"] = [
            [float(val) for val in label_list] 
            for label_list in examples["labels"]
        ]
        
        return tokenized_inputs

    print("Tokenising and mapping labels...")
    cols_to_remove = dataset["train"].column_names
    tokenized_dataset = dataset.map(
        preprocess_function, 
        batched=True, 
        remove_columns=cols_to_remove
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, 
        num_labels=num_labels,
        problem_type="multi_label_classification",
        id2label=id2label,
        label2id=label2id
    )

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        
        probs = 1 / (1 + np.exp(-logits))
        predictions = (probs > 0.5).astype(int)
        
        macro_f1 = f1_score(labels, predictions, average="macro", zero_division=0)
        micro_f1 = f1_score(labels, predictions, average="micro", zero_division=0)
        accuracy = accuracy_score(labels, predictions)
        
        return {
            "macro_f1": macro_f1,
            "micro_f1": micro_f1,
            "accuracy": accuracy
        }

    training_args = TrainingArguments(
        output_dir="./roberta-intent-scheduler",
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=5,
        weight_decay=0.01,
        fp16=False,
        bf16=False,
        logging_steps=50,
        load_best_model_at_end=True,
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    print("Beginning intent model training...")
    trainer.train()

    print("Exporting final intent model...")
    trainer.save_model("./scheduler_intent_final")
    tokenizer.save_pretrained("./scheduler_intent_final")
    print("Process finished successfully.")

if __name__ == "__main__":
    main()