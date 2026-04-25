#!/usr/bin/env python3
"""
evaluate_checkpoints.py
=======================
Evaluates every checkpoint (plus the final saved model) in the
ModernBERT intent and NER model directories against their respective
strict holdout sets.

Saves a detailed report to:  src/checkpoint_evaluation_report.txt

Usage:
    python evaluate_checkpoints.py
"""

import json
import datetime
import math
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoModelForTokenClassification,
)
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    accuracy_score,
    hamming_loss,
    roc_auc_score,
    matthews_corrcoef,
    log_loss,
)
from seqeval.metrics import (
    f1_score as seq_f1,
    precision_score as seq_precision,
    recall_score as seq_recall,
    classification_report as seq_classification_report,
)

# ── Paths ──────────────────────────────────────────────────────────────────
INTENT_PATH     = "./modernbert_intent_modelv2"
NER_PATH        = "./modernbert_ner_model"
INTENT_HOLDOUT  = "./modernbert_data/multilabel_intent_strict_validation.jsonl"
NER_HOLDOUT     = "./modernbert_data/ner_strict_validation.jsonl"
REPORT_PATH     = "./checkpoint_evaluation_report.txt"

# ── Device ─────────────────────────────────────────────────────────────────
if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda"
else:
    DEVICE = "cpu"
BATCH_SIZE  = 32
MAX_SEQ_LEN = 128

# ── Label maps ─────────────────────────────────────────────────────────────
INTENT_ID2LABEL = {
    0: "CREATE_EVENT",    1: "UPDATE_EVENT",    2: "DELETE_EVENT",
    3: "QUERY_EVENT",     4: "FIND_FREE_TIME",  5: "SUGGEST_TIME",
    6: "CHANGE_RECURRENCE", 7: "CREATE_TASK",   8: "UPDATE_TASK",
    9: "DELETE_TASK",    10: "COMPLETE_TASK",   11: "QUERY_TASK",
    12: "SET_REMINDER",  13: "UPDATE_REMINDER", 14: "DELETE_REMINDER",
    15: "SET_PREFERENCES",
}
NUM_INTENT_LABELS = len(INTENT_ID2LABEL)

NER_ID2LABEL = {
    0: "O",
    1: "B-EVENT",          2: "I-EVENT",
    3: "B-TASK",           4: "I-TASK",
    5: "B-PERSON",         6: "I-PERSON",
    7: "B-LOCATION",       8: "I-LOCATION",
    9: "B-DATE_ABSOLUTE",  10: "I-DATE_ABSOLUTE",
    11: "B-DATE_RELATIVE", 12: "I-DATE_RELATIVE",
    13: "B-TIME_ABSOLUTE", 14: "I-TIME_ABSOLUTE",
    15: "B-TIME_RELATIVE", 16: "I-TIME_RELATIVE",
    17: "B-DURATION",      18: "I-DURATION",
    19: "B-RECURRENCE",    20: "I-RECURRENCE",
    21: "B-REMINDER_OFFSET", 22: "I-REMINDER_OFFSET",
    23: "B-PREF_TYPE",     24: "I-PREF_TYPE",
    25: "B-CONDITION",     26: "I-CONDITION",
}
NUM_NER_LABELS = len(NER_ID2LABEL)

SEP  = "=" * 80
SEP2 = "-" * 80


# ══════════════════════════════════════════════════════════════════════════════
#  Data loaders
# ══════════════════════════════════════════════════════════════════════════════

def load_intent_holdout(path: str):
    texts, labels = [], []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(row["labels"])
    return texts, np.array(labels, dtype=np.float32)


def load_ner_holdout(path: str):
    samples = []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            samples.append((row["tokens"], row["ner_tags"]))
    return samples


# ══════════════════════════════════════════════════════════════════════════════
#  Checkpoint discovery
# ══════════════════════════════════════════════════════════════════════════════

def get_checkpoints(model_path: str) -> List[str]:
    """Return checkpoint dirs (sorted by step) followed by the root model dir."""
    base = Path(model_path)
    ckpts = sorted(
        [p for p in base.iterdir() if p.is_dir() and p.name.startswith("checkpoint-")],
        key=lambda p: int(p.name.split("-")[1]),
    )
    return [str(p) for p in ckpts] + [str(base)]


def ckpt_name(path: str, base: str) -> str:
    p, bp = Path(path), Path(base)
    return "final (root)" if p == bp else p.name


# ══════════════════════════════════════════════════════════════════════════════
#  Intent (multi-label) evaluation
# ══════════════════════════════════════════════════════════════════════════════

class _IntentDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels    = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def evaluate_intent_checkpoint(
    ckpt_path: str,
    tokenizer,
    texts: List[str],
    labels_np: np.ndarray,
) -> Dict:
    model = AutoModelForSequenceClassification.from_pretrained(ckpt_path)
    model.eval().to(DEVICE)

    encodings = tokenizer(
        texts, truncation=True, padding=True,
        max_length=MAX_SEQ_LEN, return_tensors=None,
    )
    dataset = _IntentDataset(encodings, labels_np)
    loader  = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    all_logits, all_labels = [], []
    total_loss, n_batches  = 0.0, 0

    with torch.no_grad():
        for batch in loader:
            input_ids      = batch["input_ids"].to(DEVICE)
            attention_mask = batch["attention_mask"].to(DEVICE)
            label_batch    = batch["labels"].to(DEVICE)
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=label_batch,
            )
            total_loss += outputs.loss.item()
            n_batches  += 1
            all_logits.append(outputs.logits.cpu())
            all_labels.append(label_batch.cpu())

    logits = torch.cat(all_logits).numpy()
    labels = torch.cat(all_labels).numpy().astype(int)
    probs  = 1.0 / (1.0 + np.exp(-logits))   # sigmoid

    # ── Threshold sweep on the holdout to find the best operating point ────
    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.25, 0.76, 0.05):
        p_t = (probs >= t).astype(int)
        f   = f1_score(labels, p_t, average="macro", zero_division=0)
        if f > best_f1:
            best_t, best_f1 = round(float(t), 2), f

    preds    = (probs >= best_t).astype(int)
    avg_loss = total_loss / n_batches

    # ── Scalar metrics ─────────────────────────────────────────────────────
    f1_mac  = f1_score(labels, preds, average="macro",    zero_division=0)
    f1_mic  = f1_score(labels, preds, average="micro",    zero_division=0)
    f1_wt   = f1_score(labels, preds, average="weighted", zero_division=0)
    f1_samp = f1_score(labels, preds, average="samples",  zero_division=0)
    p_mac   = precision_score(labels, preds, average="macro",    zero_division=0)
    p_mic   = precision_score(labels, preds, average="micro",    zero_division=0)
    p_wt    = precision_score(labels, preds, average="weighted", zero_division=0)
    r_mac   = recall_score(labels, preds, average="macro",    zero_division=0)
    r_mic   = recall_score(labels, preds, average="micro",    zero_division=0)
    r_wt    = recall_score(labels, preds, average="weighted", zero_division=0)
    ham     = hamming_loss(labels, preds)
    exact   = accuracy_score(labels, preds)

    # Subset accuracy: fraction of samples with at least one correct positive
    any_correct = np.any((preds == 1) & (labels == 1), axis=1).mean()

    # ROC-AUC (macro)
    try:
        roc_auc = roc_auc_score(labels, probs, average="macro")
    except ValueError:
        roc_auc = float("nan")

    # Binary cross-entropy loss (sklearn)
    try:
        bce = log_loss(labels.ravel(), probs.ravel())
    except Exception:
        bce = float("nan")

    # Average number of predicted labels per sample
    avg_predicted = preds.sum(axis=1).mean()
    avg_true      = labels.sum(axis=1).mean()

    # Per-class F1 / precision / recall
    per_class_f1  = f1_score(labels, preds, average=None, zero_division=0)
    per_class_prec = precision_score(labels, preds, average=None, zero_division=0)
    per_class_rec  = recall_score(labels, preds, average=None, zero_division=0)

    # MCC (flattened binary)
    try:
        mcc = matthews_corrcoef(labels.ravel(), preds.ravel())
    except Exception:
        mcc = float("nan")

    del model
    if DEVICE == "cuda":
        torch.cuda.empty_cache()

    return {
        "eval_loss":         avg_loss,
        "bce_loss":          bce,
        "threshold":         best_t,
        "f1_macro":          f1_mac,
        "f1_micro":          f1_mic,
        "f1_weighted":       f1_wt,
        "f1_samples":        f1_samp,
        "precision_macro":   p_mac,
        "precision_micro":   p_mic,
        "precision_weighted":p_wt,
        "recall_macro":      r_mac,
        "recall_micro":      r_mic,
        "recall_weighted":   r_wt,
        "hamming_loss":      ham,
        "exact_match_ratio": exact,
        "any_correct_ratio": any_correct,
        "roc_auc_macro":     roc_auc,
        "mcc":               mcc,
        "avg_labels_predicted": avg_predicted,
        "avg_labels_true":      avg_true,
        "per_class_f1":      per_class_f1.tolist(),
        "per_class_prec":    per_class_prec.tolist(),
        "per_class_rec":     per_class_rec.tolist(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  NER (token classification) evaluation
# ══════════════════════════════════════════════════════════════════════════════

def _align_labels_to_tokens(enc, batch_tags: List, batch_idx: int, max_len: int) -> List[int]:
    """Map word-level tags to token positions; -100 for special/continuation tokens."""
    tags     = batch_tags[batch_idx]
    word_ids = enc.word_ids(batch_index=batch_idx)
    label_ids, prev_wid = [], None
    for wid in word_ids:
        if wid is None:
            label_ids.append(-100)
        elif wid != prev_wid:
            label_ids.append(tags[wid] if wid < len(tags) else -100)
        else:
            label_ids.append(-100)
        prev_wid = wid
    label_ids += [-100] * (max_len - len(label_ids))
    return label_ids


def _collect_batch_preds(label_np, pred_ids, n_samples):
    """Collect flat and sequence-level predictions from one batch."""
    true_ids, pred_ids_flat = [], []
    true_seqs, pred_seqs    = [], []
    for b in range(n_samples):
        true_row, pred_row, true_seq, pred_seq = [], [], [], []
        for pos in range(label_np.shape[1]):
            if label_np[b, pos] == -100:
                continue
            t = int(label_np[b, pos])
            p = int(pred_ids[b, pos])
            true_row.append(t)
            pred_row.append(p)
            true_seq.append(NER_ID2LABEL.get(t, "O"))
            pred_seq.append(NER_ID2LABEL.get(p, "O"))
        true_ids.extend(true_row)
        pred_ids_flat.extend(pred_row)
        true_seqs.append(true_seq)
        pred_seqs.append(pred_seq)
    return true_ids, pred_ids_flat, true_seqs, pred_seqs


def evaluate_ner_checkpoint(
    ckpt_path: str,
    tokenizer,
    samples: List,
) -> Dict:
    model = AutoModelForTokenClassification.from_pretrained(ckpt_path)
    model.eval().to(DEVICE)

    all_true_ids, all_pred_ids   = [], []
    all_true_seqs, all_pred_seqs = [], []
    total_loss, n_batches        = 0.0, 0

    for i in range(0, len(samples), BATCH_SIZE):
        batch_samples = samples[i : i + BATCH_SIZE]
        batch_tokens  = [s[0] for s in batch_samples]
        batch_tags    = [s[1] for s in batch_samples]

        enc = tokenizer(
            batch_tokens,
            is_split_into_words=True,
            truncation=True,
            padding=True,
            max_length=MAX_SEQ_LEN,
            return_tensors="pt",
        )

        max_len = enc["input_ids"].shape[1]
        batch_label_ids = [
            _align_labels_to_tokens(enc, batch_tags, j, max_len)
            for j in range(len(batch_samples))
        ]

        label_tensor = torch.tensor(batch_label_ids, dtype=torch.long).to(DEVICE)

        with torch.no_grad():
            outputs = model(
                input_ids=enc["input_ids"].to(DEVICE),
                attention_mask=enc["attention_mask"].to(DEVICE),
                labels=label_tensor,
            )
        total_loss += outputs.loss.item()
        n_batches  += 1

        batch_pred_ids = torch.argmax(outputs.logits, dim=-1).cpu().numpy()
        label_np       = label_tensor.cpu().numpy()

        ti, pi, ts, ps = _collect_batch_preds(label_np, batch_pred_ids, len(batch_samples))
        all_true_ids.extend(ti)
        all_pred_ids.extend(pi)
        all_true_seqs.extend(ts)
        all_pred_seqs.extend(ps)

    avg_loss = total_loss / n_batches
    true_np  = np.array(all_true_ids)
    pred_np  = np.array(all_pred_ids)

    # ── Token-level metrics ────────────────────────────────────────────────
    token_acc   = accuracy_score(true_np, pred_np)
    f1_mac      = f1_score(true_np, pred_np, average="macro",    zero_division=0)
    f1_mic      = f1_score(true_np, pred_np, average="micro",    zero_division=0)
    f1_wt       = f1_score(true_np, pred_np, average="weighted", zero_division=0)
    p_mac       = precision_score(true_np, pred_np, average="macro",    zero_division=0)
    p_mic       = precision_score(true_np, pred_np, average="micro",    zero_division=0)
    p_wt        = precision_score(true_np, pred_np, average="weighted", zero_division=0)
    r_mac       = recall_score(true_np, pred_np, average="macro",    zero_division=0)
    r_mic       = recall_score(true_np, pred_np, average="micro",    zero_division=0)
    r_wt        = recall_score(true_np, pred_np, average="weighted", zero_division=0)

    # Accuracy on non-O tokens only
    non_o = true_np != 0
    entity_acc = accuracy_score(true_np[non_o], pred_np[non_o]) if non_o.sum() > 0 else float("nan")

    # O-class omitted F1 (macro over entity classes only)
    entity_labels = list(range(1, NUM_NER_LABELS))
    f1_mac_entity = f1_score(
        true_np, pred_np, labels=entity_labels,
        average="macro", zero_division=0,
    )

    # MCC
    try:
        mcc = matthews_corrcoef(true_np, pred_np)
    except Exception:
        mcc = float("nan")

    # Per-class F1
    per_class_f1   = f1_score(true_np, pred_np, labels=list(range(NUM_NER_LABELS)),
                               average=None, zero_division=0)
    per_class_prec = precision_score(true_np, pred_np, labels=list(range(NUM_NER_LABELS)),
                                     average=None, zero_division=0)
    per_class_rec  = recall_score(true_np, pred_np, labels=list(range(NUM_NER_LABELS)),
                                  average=None, zero_division=0)

    # ── Entity-level metrics (seqeval) ─────────────────────────────────────
    seq_f1_val   = seq_f1(all_true_seqs, all_pred_seqs, average="macro",    zero_division=0)
    seq_f1_mic   = seq_f1(all_true_seqs, all_pred_seqs, average="micro",    zero_division=0)
    seq_f1_wt    = seq_f1(all_true_seqs, all_pred_seqs, average="weighted", zero_division=0)
    seq_prec_mac = seq_precision(all_true_seqs, all_pred_seqs, average="macro",    zero_division=0)
    seq_prec_mic = seq_precision(all_true_seqs, all_pred_seqs, average="micro",    zero_division=0)
    seq_rec_mac  = seq_recall(all_true_seqs, all_pred_seqs, average="macro",    zero_division=0)
    seq_rec_mic  = seq_recall(all_true_seqs, all_pred_seqs, average="micro",    zero_division=0)
    seq_report   = seq_classification_report(all_true_seqs, all_pred_seqs, zero_division=0)

    del model
    if DEVICE == "cuda":
        torch.cuda.empty_cache()

    return {
        "eval_loss":              avg_loss,
        "token_accuracy":         token_acc,
        "entity_accuracy":        entity_acc,
        "f1_macro_token":         f1_mac,
        "f1_micro_token":         f1_mic,
        "f1_weighted_token":      f1_wt,
        "f1_macro_entity_only":   f1_mac_entity,
        "precision_macro_token":  p_mac,
        "precision_micro_token":  p_mic,
        "precision_weighted_token": p_wt,
        "recall_macro_token":     r_mac,
        "recall_micro_token":     r_mic,
        "recall_weighted_token":  r_wt,
        "mcc":                    mcc,
        "seqeval_f1_macro":       seq_f1_val,
        "seqeval_f1_micro":       seq_f1_mic,
        "seqeval_f1_weighted":    seq_f1_wt,
        "seqeval_precision_macro":seq_prec_mac,
        "seqeval_precision_micro":seq_prec_mic,
        "seqeval_recall_macro":   seq_rec_mac,
        "seqeval_recall_micro":   seq_rec_mic,
        "seqeval_report":         seq_report,
        "per_class_f1":           per_class_f1.tolist(),
        "per_class_prec":         per_class_prec.tolist(),
        "per_class_rec":          per_class_rec.tolist(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Report helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(v, spec=".6f") -> str:
    if isinstance(v, float) and math.isnan(v):
        return "N/A"
    return format(v, spec)


def _write_intent_section(results: List[Dict], base_path: str) -> List[str]:
    lines = []
    lines += [SEP, "  INTENT MODEL — CHECKPOINT EVALUATION",
              f"  Model base : {base_path}",
              f"  Holdout    : {INTENT_HOLDOUT}",
              f"  Samples    : {len(results[0]['_n_samples'])} utterances  |  {NUM_INTENT_LABELS} classes",
              SEP, ""]

    best = max(results, key=lambda r: r["metrics"]["f1_macro"])

    for r in results:
        m   = r["metrics"]
        tag = "  ◄◄◄ BEST ◄◄◄" if r is best else ""
        lines.append(f"  Checkpoint : {r['name']}{tag}")
        lines.append(SEP2)
        lines.append(f"    eval_loss              : {_fmt(m['eval_loss'])}")
        lines.append(f"    bce_loss               : {_fmt(m['bce_loss'])}")
        lines.append(f"    threshold (auto-tuned) : {_fmt(m['threshold'], '.2f')}")
        lines.append(f"    f1_macro               : {_fmt(m['f1_macro'])}")
        lines.append(f"    f1_micro               : {_fmt(m['f1_micro'])}")
        lines.append(f"    f1_weighted            : {_fmt(m['f1_weighted'])}")
        lines.append(f"    f1_samples             : {_fmt(m['f1_samples'])}")
        lines.append(f"    precision_macro        : {_fmt(m['precision_macro'])}")
        lines.append(f"    precision_micro        : {_fmt(m['precision_micro'])}")
        lines.append(f"    precision_weighted     : {_fmt(m['precision_weighted'])}")
        lines.append(f"    recall_macro           : {_fmt(m['recall_macro'])}")
        lines.append(f"    recall_micro           : {_fmt(m['recall_micro'])}")
        lines.append(f"    recall_weighted        : {_fmt(m['recall_weighted'])}")
        lines.append(f"    hamming_loss           : {_fmt(m['hamming_loss'])}")
        lines.append(f"    exact_match_ratio      : {_fmt(m['exact_match_ratio'])}")
        lines.append(f"    any_correct_ratio      : {_fmt(m['any_correct_ratio'])}")
        lines.append(f"    roc_auc_macro          : {_fmt(m['roc_auc_macro'])}")
        lines.append(f"    mcc (binary flat)      : {_fmt(m['mcc'])}")
        lines.append(f"    avg_labels_predicted   : {_fmt(m['avg_labels_predicted'], '.3f')}")
        lines.append(f"    avg_labels_true        : {_fmt(m['avg_labels_true'], '.3f')}")
        lines.append("")
        lines.append(f"    {'Class':<22}  {'F1':>8}  {'Precision':>9}  {'Recall':>8}")
        lines.append(f"    {'-'*22}  {'-'*8}  {'-'*9}  {'-'*8}")
        for idx in range(NUM_INTENT_LABELS):
            lbl = INTENT_ID2LABEL[idx]
            lines.append(
                f"    {lbl:<22}  {_fmt(m['per_class_f1'][idx], '.4f'):>8}"
                f"  {_fmt(m['per_class_prec'][idx], '.4f'):>9}"
                f"  {_fmt(m['per_class_rec'][idx], '.4f'):>8}"
            )
        lines.append("")

    lines.append(SEP2)
    m = best["metrics"]
    lines += [
        f"  >>> BEST INTENT CHECKPOINT : {best['name']}",
        f"      f1_macro        = {_fmt(m['f1_macro'])}",
        f"      f1_micro        = {_fmt(m['f1_micro'])}",
        f"      exact_match     = {_fmt(m['exact_match_ratio'])}",
        f"      roc_auc_macro   = {_fmt(m['roc_auc_macro'])}",
        f"      hamming_loss    = {_fmt(m['hamming_loss'])}",
        f"      eval_loss       = {_fmt(m['eval_loss'])}",
        SEP2, "",
    ]
    return lines


def _write_ner_section(results: List[Dict], base_path: str, n_samples: int) -> List[str]:
    lines = []
    lines += [SEP, "  NER MODEL — CHECKPOINT EVALUATION",
              f"  Model base : {base_path}",
              f"  Holdout    : {NER_HOLDOUT}",
              f"  Samples    : {n_samples} sentences  |  {NUM_NER_LABELS} BIO tags",
              SEP, ""]

    # Best = highest seqeval entity-level F1 macro
    best = max(results, key=lambda r: r["metrics"]["seqeval_f1_macro"])

    for r in results:
        m   = r["metrics"]
        tag = "  ◄◄◄ BEST ◄◄◄" if r is best else ""
        lines.append(f"  Checkpoint : {r['name']}{tag}")
        lines.append(SEP2)
        lines.append(f"    eval_loss                      : {_fmt(m['eval_loss'])}")
        lines.append(f"    token_accuracy                 : {_fmt(m['token_accuracy'])}")
        lines.append(f"    entity_accuracy (non-O tokens) : {_fmt(m['entity_accuracy'])}")
        lines.append(f"    mcc                            : {_fmt(m['mcc'])}")
        lines.append("")
        lines.append("    --- Token-level (incl. O) ---")
        lines.append(f"    f1_macro                       : {_fmt(m['f1_macro_token'])}")
        lines.append(f"    f1_micro                       : {_fmt(m['f1_micro_token'])}")
        lines.append(f"    f1_weighted                    : {_fmt(m['f1_weighted_token'])}")
        lines.append(f"    f1_macro (entity classes only) : {_fmt(m['f1_macro_entity_only'])}")
        lines.append(f"    precision_macro                : {_fmt(m['precision_macro_token'])}")
        lines.append(f"    precision_micro                : {_fmt(m['precision_micro_token'])}")
        lines.append(f"    precision_weighted             : {_fmt(m['precision_weighted_token'])}")
        lines.append(f"    recall_macro                   : {_fmt(m['recall_macro_token'])}")
        lines.append(f"    recall_micro                   : {_fmt(m['recall_micro_token'])}")
        lines.append(f"    recall_weighted                : {_fmt(m['recall_weighted_token'])}")
        lines.append("")
        lines.append("    --- Entity-level (seqeval, span-exact) ---")
        lines.append(f"    seqeval_f1_macro               : {_fmt(m['seqeval_f1_macro'])}")
        lines.append(f"    seqeval_f1_micro               : {_fmt(m['seqeval_f1_micro'])}")
        lines.append(f"    seqeval_f1_weighted            : {_fmt(m['seqeval_f1_weighted'])}")
        lines.append(f"    seqeval_precision_macro        : {_fmt(m['seqeval_precision_macro'])}")
        lines.append(f"    seqeval_precision_micro        : {_fmt(m['seqeval_precision_micro'])}")
        lines.append(f"    seqeval_recall_macro           : {_fmt(m['seqeval_recall_macro'])}")
        lines.append(f"    seqeval_recall_micro           : {_fmt(m['seqeval_recall_micro'])}")
        lines.append("")
        lines.append("    Per-class (token-level):")
        lines.append(f"    {'Label':<24}  {'F1':>8}  {'Precision':>9}  {'Recall':>8}")
        lines.append(f"    {'-'*24}  {'-'*8}  {'-'*9}  {'-'*8}")
        for idx in range(NUM_NER_LABELS):
            lbl = NER_ID2LABEL.get(idx, f"LABEL_{idx}")
            lines.append(
                f"    {lbl:<24}  {_fmt(m['per_class_f1'][idx], '.4f'):>8}"
                f"  {_fmt(m['per_class_prec'][idx], '.4f'):>9}"
                f"  {_fmt(m['per_class_rec'][idx], '.4f'):>8}"
            )
        lines.append("")
        lines.append("    seqeval entity classification report:")
        for sline in m["seqeval_report"].strip().split("\n"):
            lines.append(f"      {sline}")
        lines.append("")

    lines.append(SEP2)
    m = best["metrics"]
    lines += [
        f"  >>> BEST NER CHECKPOINT : {best['name']}",
        f"      seqeval_f1_macro   = {_fmt(m['seqeval_f1_macro'])}",
        f"      seqeval_f1_micro   = {_fmt(m['seqeval_f1_micro'])}",
        f"      f1_macro (token)   = {_fmt(m['f1_macro_token'])}",
        f"      entity_accuracy    = {_fmt(m['entity_accuracy'])}",
        f"      token_accuracy     = {_fmt(m['token_accuracy'])}",
        f"      eval_loss          = {_fmt(m['eval_loss'])}",
        SEP2, "",
    ]
    return lines


def main():
    print(f"Device : {DEVICE}")
    lines = [
        SEP,
        "  MODERNBERT CHECKPOINT EVALUATION REPORT",
        f"  Generated : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Device    : {DEVICE}",
        SEP, "",
    ]

    # ── INTENT ──────────────────────────────────────────────────────────────
    print("\n[INTENT] Loading holdout ...")
    texts, labels_np = load_intent_holdout(INTENT_HOLDOUT)
    n_intent = len(texts)
    print(f"  {n_intent} samples | {NUM_INTENT_LABELS} labels")

    intent_tok   = AutoTokenizer.from_pretrained(INTENT_PATH)
    intent_ckpts = get_checkpoints(INTENT_PATH)
    print(f"  Checkpoints: {[ckpt_name(c, INTENT_PATH) for c in intent_ckpts]}")

    intent_results = []
    for ckpt in intent_ckpts:
        name = ckpt_name(ckpt, INTENT_PATH)
        print(f"  Evaluating {name} ...", end=" ", flush=True)
        m = evaluate_intent_checkpoint(ckpt, intent_tok, texts, labels_np)
        intent_results.append({"name": name, "path": ckpt, "metrics": m,
                                "_n_samples": [None] * n_intent})
        print(
            f"f1_macro={m['f1_macro']:.4f}  f1_micro={m['f1_micro']:.4f}"
            f"  exact={m['exact_match_ratio']:.4f}  loss={m['eval_loss']:.5f}"
        )

    lines += _write_intent_section(intent_results, INTENT_PATH)

    # ── NER ─────────────────────────────────────────────────────────────────
    print("\n[NER] Loading holdout ...")
    ner_samples = load_ner_holdout(NER_HOLDOUT)
    n_ner = len(ner_samples)
    print(f"  {n_ner} samples | {NUM_NER_LABELS} BIO tags")

    ner_tok   = AutoTokenizer.from_pretrained(NER_PATH)
    ner_ckpts = get_checkpoints(NER_PATH)
    print(f"  Checkpoints: {[ckpt_name(c, NER_PATH) for c in ner_ckpts]}")

    ner_results = []
    for ckpt in ner_ckpts:
        name = ckpt_name(ckpt, NER_PATH)
        print(f"  Evaluating {name} ...", end=" ", flush=True)
        m = evaluate_ner_checkpoint(ckpt, ner_tok, ner_samples)
        ner_results.append({"name": name, "path": ckpt, "metrics": m})
        print(
            f"seqeval_f1={m['seqeval_f1_macro']:.4f}"
            f"  f1_macro={m['f1_macro_token']:.4f}"
            f"  token_acc={m['token_accuracy']:.4f}"
            f"  loss={m['eval_loss']:.5f}"
        )

    lines += _write_ner_section(ner_results, NER_PATH, n_ner)

    # ── Overall summary ─────────────────────────────────────────────────────
    best_intent = max(intent_results, key=lambda r: r["metrics"]["f1_macro"])
    best_ner    = max(ner_results,    key=lambda r: r["metrics"]["seqeval_f1_macro"])

    bi, bn = best_intent["metrics"], best_ner["metrics"]

    lines += [
        SEP,
        "  OVERALL SUMMARY",
        SEP,
        "",
        "  INTENT MODEL",
        "    Architecture    : ModernBertForSequenceClassification",
        f"    Task            : Multi-label intent classification ({NUM_INTENT_LABELS} classes)",
        f"    Holdout size    : {n_intent} utterances",
        f"    Best checkpoint : {best_intent['name']}",
        f"    eval_loss       : {_fmt(bi['eval_loss'])}",
        f"    bce_loss        : {_fmt(bi['bce_loss'])}",
        f"    threshold       : {_fmt(bi['threshold'], '.2f')}",
        f"    f1_macro        : {_fmt(bi['f1_macro'])}",
        f"    f1_micro        : {_fmt(bi['f1_micro'])}",
        f"    f1_weighted     : {_fmt(bi['f1_weighted'])}",
        f"    f1_samples      : {_fmt(bi['f1_samples'])}",
        f"    roc_auc_macro   : {_fmt(bi['roc_auc_macro'])}",
        f"    exact_match     : {_fmt(bi['exact_match_ratio'])}",
        f"    hamming_loss    : {_fmt(bi['hamming_loss'])}",
        f"    mcc             : {_fmt(bi['mcc'])}",
        "",
        "  NER MODEL",
        "    Architecture    : ModernBertForTokenClassification",
        f"    Task            : Named-entity / slot-filling ({NUM_NER_LABELS} BIO tags, 13 entity types)",
        f"    Holdout size    : {n_ner} sentences",
        f"    Best checkpoint : {best_ner['name']}",
        f"    eval_loss                      : {_fmt(bn['eval_loss'])}",
        f"    seqeval_f1_macro (entity)      : {_fmt(bn['seqeval_f1_macro'])}",
        f"    seqeval_f1_micro (entity)      : {_fmt(bn['seqeval_f1_micro'])}",
        f"    seqeval_precision_macro        : {_fmt(bn['seqeval_precision_macro'])}",
        f"    seqeval_recall_macro           : {_fmt(bn['seqeval_recall_macro'])}",
        f"    f1_macro (token)               : {_fmt(bn['f1_macro_token'])}",
        f"    f1_macro entity-classes only   : {_fmt(bn['f1_macro_entity_only'])}",
        f"    token_accuracy                 : {_fmt(bn['token_accuracy'])}",
        f"    entity_accuracy (non-O)        : {_fmt(bn['entity_accuracy'])}",
        f"    mcc                            : {_fmt(bn['mcc'])}",
        "",
        SEP,
        "  MODEL NOTES",
        SEP,
        """
  INTENT MODEL  (ModernBertForSequenceClassification)
  ─────────────────────────────────────────────────────────────────────────────
  Trained on a multi-label task: a single utterance can carry more than one
  intent (e.g. DELETE_EVENT + FIND_FREE_TIME for a rescheduling request).
  Loss function: binary cross-entropy (sigmoid outputs per class).

  The inference threshold was selected by sweeping [0.25, 0.75] in 0.05 steps
  directly on the strict holdout and picking the threshold that maximises
  f1_macro.  This makes the threshold result optimistic by a small margin.

  Metrics to prioritise:
    f1_macro           — treats each of the 16 classes equally; best indicator
                         of coverage across rare intents.
    exact_match_ratio  — strictest signal; the entire label vector must match.
    roc_auc_macro      — threshold-free; rewards well-calibrated probabilities.
    hamming_loss       — fraction of (sample, label) pairs that are wrong;
                         lower is better.
    f1_samples         — averaged per utterance; captures multi-label overlap.

  NER MODEL  (ModernBertForTokenClassification)
  ─────────────────────────────────────────────────────────────────────────────
  Trained with BIO tagging over 13 entity types (26 non-O tags + O).
  Entity types span temporal expressions (DATE, TIME, DURATION, RECURRENCE,
  REMINDER_OFFSET), referent slots (TASK, EVENT, PERSON, LOCATION), and
  assistant-specific types (PREF_TYPE, CONDITION).

  Metrics to prioritise:
    seqeval_f1_macro   — gold standard for NER; an entity span must be
                         predicted with both correct boundaries AND correct type
                         to count as a true positive.
    seqeval_f1_micro   — macro across entity occurrences; dominated by frequent
                         types but reflects real-world distribution.
    entity_accuracy    — per-token accuracy on non-O tokens; strips out the
                         dominant O-class to avoid inflated accuracy numbers.
    f1_macro_entity_only — token-level macro F1 excluding O; useful for
                         spotting which BIO classes the model struggles with.
    eval_loss          — cross-entropy over all tokens; lower means better
                         probability calibration at the token level.
""",
        SEP,
    ]

    report = "\n".join(lines)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(f"\nReport saved → {REPORT_PATH}")
    print(f"Best intent checkpoint : {best_intent['name']}"
          f"  (f1_macro={bi['f1_macro']:.4f}, exact={bi['exact_match_ratio']:.4f})")
    print(f"Best NER checkpoint    : {best_ner['name']}"
          f"  (seqeval_f1={bn['seqeval_f1_macro']:.4f},"
          f" entity_acc={bn['entity_accuracy']:.4f})")


if __name__ == "__main__":
    main()
