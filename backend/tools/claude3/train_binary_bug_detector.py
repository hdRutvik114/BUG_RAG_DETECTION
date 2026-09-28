"""
Zero-Storage Cloud Embedding Binary Bug Detector (1 = Buggy, 0 = Fixed/Clean).

This script:
1. Reshapes dataset_enriched_v3.csv by converting each row into 2 samples:
   - buggy_code -> Label = 1 (Buggy)
   - fixed_code -> Label = 0 (Clean / Fixed)
2. Extracts 1536-dimensional embeddings for all functions via OpenRouter Cloud API
   (ZERO laptop storage/RAM used for model weights).
3. Trains and benchmarks binary classification models:
   - Logistic Regression
   - Random Forest
   - Support Vector Classifier (SVC)
   - Gradient Boosting Classifier
4. Outputs 5-Fold Cross-Validation Accuracy, ROC-AUC Score, Precision, Recall,
   and detailed Confusion Matrices.
"""

import json
import os
import sys
import time
from typing import List, Tuple

# Fix Windows console UTF-8 printing
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, StratifiedKFold, cross_val_score, train_test_split
from sklearn.svm import SVC

WORKDIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(WORKDIR, ".env"))

DATASET_PATH = os.path.join(WORKDIR, "dataset_enriched_v3.csv")
EMBEDDING_MODEL = "openai/text-embedding-3-small"
BATCH_SIZE = 25


def get_api_keys() -> List[str]:
    """Loads all OPENROUTER_API_KEY_1..N keys from environment."""
    keys = []
    i = 1
    while True:
        val = os.environ.get(f"OPENROUTER_API_KEY_{i}", "").strip()
        if not val:
            break
        keys.append(val)
        i += 1
    if not keys:
        single = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if single:
            keys.append(single)
    return keys


def fetch_cloud_embeddings_batched(code_list: List[str], api_keys: List[str]) -> np.ndarray:
    """Fetch 1536-D embeddings from OpenRouter Cloud API with safe truncation & key rotation."""
    print(f"\n[Cloud API] Extracting embeddings for {len(code_list)} code samples...")
    print(f"[Cloud API] Model: {EMBEDDING_MODEL} (1536 dimensions, ZERO local RAM/storage)")

    embeddings: List[List[float]] = []
    key_idx = 0
    total_batches = (len(code_list) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start_i = batch_num * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(code_list))
        # Truncate each snippet to 1500 chars to avoid token limit errors
        batch_codes = [c[:1500] if isinstance(c, str) and c.strip() else "// empty" for c in code_list[start_i:end_i]]

        success = False
        attempts = 0
        while not success and attempts < len(api_keys) * 2:
            current_key = api_keys[key_idx % len(api_keys)]
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": EMBEDDING_MODEL,
                "input": batch_codes
            }

            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/embeddings",
                    headers=headers,
                    json=payload,
                    timeout=25
                )
                if res.status_code == 200:
                    data = res.json()
                    batch_vecs = [item["embedding"] for item in data["data"]]
                    embeddings.extend(batch_vecs)
                    success = True
                    print(f"  -> Batch {batch_num + 1}/{total_batches} complete ({len(batch_codes)} items)")
                elif res.status_code in (429, 402):
                    print(f"  -> Key slot {key_idx+1} rate-limited ({res.status_code}). Rotating key...")
                    key_idx += 1
                    attempts += 1
                    time.sleep(2)
                else:
                    print(f"  -> Error {res.status_code}: {res.text[:150]}")
                    key_idx += 1
                    attempts += 1
                    time.sleep(1)
            except Exception as e:
                print(f"  -> Request exception: {e}")
                key_idx += 1
                attempts += 1
                time.sleep(1)

        if not success:
            print(f"  -> Warning: Batch {batch_num + 1} failed. Filling zero vector.")
            embeddings.extend([[0.0] * 1536 for _ in range(len(batch_codes))])

    return np.array(embeddings, dtype=np.float32)


def create_binary_dataset() -> Tuple[List[str], np.ndarray]:
    """Reads dataset_enriched_v3.csv and expands buggy_code (1) and fixed_code (0) into rows."""
    print(f"[Dataset] Loading from {os.path.basename(DATASET_PATH)}...")
    df = pd.read_csv(DATASET_PATH)

    df_clean = df.dropna(subset=["buggy_code", "fixed_code"]).copy()

    code_samples: List[str] = []
    labels: List[int] = []

    for _, row in df_clean.iterrows():
        b_code = str(row["buggy_code"]).strip()
        f_code = str(row["fixed_code"]).strip()

        if b_code and f_code:
            code_samples.append(b_code)
            labels.append(1)  # 1 = Buggy

            code_samples.append(f_code)
            labels.append(0)  # 0 = Clean / Fixed

    y = np.array(labels, dtype=np.int32)
    print(f"[Dataset] Reshaped binary dataset size: {len(code_samples)} samples")
    print(f"  - Label 1 (Buggy Code): {np.sum(y == 1)} samples")
    print(f"  - Label 0 (Clean Code): {np.sum(y == 0)} samples")

    return code_samples, y


def train_and_evaluate_binary():
    api_keys = get_api_keys()
    if not api_keys:
        print("[ERROR] No OPENROUTER_API_KEY found in .env file!")
        sys.exit(1)

    code_samples, y = create_binary_dataset()

    # Fetch 1536-D embeddings for all code snippets
    X_emb = fetch_cloud_embeddings_batched(code_samples, api_keys)

    print("\n" + "="*70)
    print("      BENCHMARKING BINARY BUG DETECTOR (1 = Buggy, 0 = Clean)")
    print("="*70)
    print(f"Total Dataset Size : {X_emb.shape[0]} samples")
    print(f"Embedding Vector   : {X_emb.shape[1]} dimensions (Cloud Neural Embedding)")
    print("="*70)

    # Create pair groups to prevent data leakage (Buggy and Fixed of same pair must stay in same split)
    groups = np.repeat(np.arange(len(code_samples) // 2), 2)

    classifiers = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=150, random_state=42),
        "Support Vector Classifier (SVC)": SVC(kernel="rbf", C=1.5, probability=True, random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=100, random_state=42),
    }

    results = []

    # Use GroupKFold so Buggy & Fixed from the SAME pair are NEVER split between train and test
    gkf = GroupKFold(n_splits=5)

    for clf_name, clf in classifiers.items():
        print(f"\n>>> Training & Evaluating: {clf_name} (GroupKFold by Pair ID)...")

        # 5-Fold Group CV
        cv_scores = cross_val_score(clf, X_emb, y, cv=gkf, groups=groups, scoring="accuracy")
        cv_roc = cross_val_score(clf, X_emb, y, cv=gkf, groups=groups, scoring="roc_auc")

        mean_cv_acc = cv_scores.mean() * 100
        std_cv_acc = cv_scores.std() * 100
        mean_cv_roc = cv_roc.mean() * 100

        # Group-aware Train-Test Split (80/20)
        gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
        train_idx, test_idx = next(gss.split(X_emb, y, groups=groups))
        X_train, X_test = X_emb[train_idx], X_emb[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else y_pred

        test_acc = accuracy_score(y_test, y_pred) * 100
        test_prec = precision_score(y_test, y_pred, zero_division=0) * 100
        test_rec = recall_score(y_test, y_pred, zero_division=0) * 100
        test_f1 = f1_score(y_test, y_pred, zero_division=0) * 100
        test_auc = roc_auc_score(y_test, y_prob) * 100

        results.append({
            "Classifier": clf_name,
            "5-Fold Group CV Accuracy": f"{mean_cv_acc:.2f}% (+/- {std_cv_acc:.2f}%)",
            "5-Fold ROC-AUC": f"{mean_cv_roc:.2f}%",
            "Holdout Accuracy": f"{test_acc:.2f}%",
            "Precision": f"{test_prec:.2f}%",
            "Recall": f"{test_rec:.2f}%",
            "F1-Score": f"{test_f1:.2f}%",
        })

        print(f"  - 5-Fold CV Accuracy : {mean_cv_acc:6.2f}% (+/- {std_cv_acc:.2f}%)")
        print(f"  - 5-Fold ROC-AUC     : {mean_cv_roc:6.2f}%")
        print(f"  - Holdout Test Acc   : {test_acc:6.2f}%")
        print(f"  - Precision          : {test_prec:6.2f}% | Recall: {test_rec:6.2f}% | F1: {test_f1:6.2f}%")

    print("\n" + "="*70)
    print("      DETAILED CONFUSION MATRIX FOR BEST MODEL (SVC)")
    print("="*70)

    best_clf = SVC(kernel="rbf", C=1.5, probability=True, random_state=42)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X_emb, y, groups=groups))
    X_train, X_test = X_emb[train_idx], X_emb[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    best_clf.fit(X_train, y_train)
    y_pred = best_clf.predict(X_test)

    print("Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["Clean (0)", "Buggy (1)"], zero_division=0))

    cm = confusion_matrix(y_test, y_pred)
    print("Confusion Matrix:")
    print(f"  True Clean (TN) : {cm[0][0]:3d} | False Buggy (FP): {cm[0][1]:3d}")
    print(f"  False Clean(FN) : {cm[1][0]:3d} | True Buggy  (TP): {cm[1][1]:3d}")

    print("\n" + "="*70)
    print("SUMMARY RESULTS (BINARY BUG DETECTION WITH GROUP SPLITTING):")
    print("="*70)
    res_df = pd.DataFrame(results)[["Classifier", "5-Fold Group CV Accuracy", "5-Fold ROC-AUC", "Holdout Accuracy", "Precision", "Recall", "F1-Score"]]
    print(res_df.to_string(index=False))
    print("="*70)
    print("\nSUCCESS! Binary Bug Detector trained & evaluated with ZERO local RAM/storage.")


if __name__ == "__main__":
    train_and_evaluate_binary()
