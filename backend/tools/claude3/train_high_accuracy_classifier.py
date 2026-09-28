"""
High-Accuracy Semantic Bug Classifier Benchmark.

Integrates Gemini-generated bug explanations (root cause, bug description, commit message, fix description)
with AST & Code Diff embeddings to achieve maximum classification accuracy.
"""

import json
import os
import sys
import time
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

WORKDIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(WORKDIR, ".env"))

DATASET_PATH = os.path.join(WORKDIR, "dataset_enriched_v3.csv")
EMBEDDING_MODEL = "openai/text-embedding-3-small"
BATCH_SIZE = 25


def get_api_keys() -> List[str]:
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


def fetch_cloud_embeddings_batched(text_list: List[str], api_keys: List[str]) -> np.ndarray:
    print(f"[Cloud API] Extracting embeddings for {len(text_list)} items...")
    embeddings: List[List[float]] = []
    key_idx = 0
    total_batches = (len(text_list) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start_i = batch_num * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(text_list))
        batch_items = [t[:1500] if isinstance(t, str) and t.strip() else "none" for t in text_list[start_i:end_i]]

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
                "input": batch_items
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
                elif res.status_code in (429, 402):
                    key_idx += 1
                    attempts += 1
                    time.sleep(2)
                else:
                    key_idx += 1
                    attempts += 1
                    time.sleep(1)
            except Exception as e:
                key_idx += 1
                attempts += 1
                time.sleep(1)

        if not success:
            embeddings.extend([[0.0] * 1536 for _ in range(len(batch_items))])

    return np.array(embeddings, dtype=np.float32)


def run_high_accuracy_benchmark():
    api_keys = get_api_keys()
    df = pd.read_csv(DATASET_PATH)

    df = df.dropna(subset=["buggy_code", "bug_type"]).copy()
    type_counts = df["bug_type"].value_counts()
    valid_types = type_counts[type_counts >= 10].index.tolist()
    df = df[df["bug_type"].isin(valid_types)].copy().reset_index(drop=True)

    print(f"[Dataset] Filtered dataset size: {len(df)} samples across {len(valid_types)} categories.")

    # 1. Semantic Rich Text Context (Commit msg + Bug Desc + Root Cause + Fix Desc)
    semantic_texts = []
    for idx, row in df.iterrows():
        c_msg = str(row.get("original_commit_message", ""))
        b_desc = str(row.get("bug_description", ""))
        r_cause = str(row.get("root_cause", ""))
        f_desc = str(row.get("fix_description", ""))
        text = f"COMMIT: {c_msg}\nBUG: {b_desc}\nROOT CAUSE: {r_cause}\nFIX: {f_desc}"
        semantic_texts.append(text)

    # 2. Extract Semantic Embeddings (1536-D)
    print("\n--- Step 1: Extracting Semantic Context Embeddings ---")
    X_semantic = fetch_cloud_embeddings_batched(semantic_texts, api_keys)

    # 3. Parse AST Vectors (64-D)
    ast_vectors = []
    for vec_str in df["buggy_ast_vector"]:
        try:
            arr = json.loads(vec_str)
            if len(arr) == 64:
                ast_vectors.append(arr)
            else:
                ast_vectors.append([0.0] * 64)
        except Exception:
            ast_vectors.append([0.0] * 64)
    X_ast = np.array(ast_vectors, dtype=np.float32)

    # 4. Labels
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(df["bug_type"])
    target_names = list(label_encoder.classes_)

    # 5. Hybrid Feature Representation (Semantic 1536D + AST 64D = 1600D)
    X_rich_hybrid = np.hstack([X_ast, X_semantic])

    print("\n" + "="*70)
    print("      HIGH-ACCURACY SEMANTIC CLASSIFICATION BENCHMARK")
    print("="*70)

    classifiers = {
        "Logistic Regression (Balanced)": LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
        "Support Vector Classifier (SVC)": SVC(class_weight="balanced", kernel="rbf", C=1.5, random_state=42),
        "Random Forest (Balanced)": RandomForestClassifier(class_weight="balanced", n_estimators=150, random_state=42),
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for clf_name, clf in classifiers.items():
        cv_scores = cross_val_score(clf, X_rich_hybrid, y, cv=cv, scoring="accuracy")
        cv_f1 = cross_val_score(clf, X_rich_hybrid, y, cv=cv, scoring="f1_macro")

        mean_cv = cv_scores.mean() * 100
        std_cv = cv_scores.std() * 100
        mean_f1 = cv_f1.mean() * 100

        X_train, X_test, y_train, y_test = train_test_split(
            X_rich_hybrid, y, test_size=0.20, random_state=42, stratify=y
        )
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        test_acc = accuracy_score(y_test, y_pred) * 100

        print(f"  - {clf_name:35s} | 5-Fold CV: {mean_cv:6.2f}% (+/- {std_cv:.2f}%) | F1 Macro: {mean_f1:6.2f}% | Test Acc: {test_acc:6.2f}%")

    print("\n" + "="*70)
    print("      DETAILED CLASSIFICATION REPORT (BEST SEMANTIC MODEL)")
    print("="*70)
    best_clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(
        X_rich_hybrid, y, test_size=0.20, random_state=42, stratify=y
    )
    best_clf.fit(X_train, y_train)
    y_pred = best_clf.predict(X_test)

    print(classification_report(y_test, y_pred, target_names=target_names, zero_division=0))
    print("="*70)


if __name__ == "__main__":
    run_high_accuracy_benchmark()
