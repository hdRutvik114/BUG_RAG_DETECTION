"""
High-Accuracy Binary Bug Detector (1 = Bug, 0 = Clean/Not Bug).

Evaluates Binary Classification using:
1. AST Features (64-D)
2. Cloud Code Embeddings (1536-D)
3. Hybrid AST + Code Embedding Representation (1600-D)

Uses GroupKFold cross-validation (grouped by pair_id) to prevent pair data leakage.
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
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
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
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

WORKDIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(WORKDIR, ".env"))

DATASET_PATH = os.path.join(WORKDIR, "binary_bug_detection_dataset.csv")
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


def fetch_cloud_embeddings_batched(code_list: List[str], api_keys: List[str]) -> np.ndarray:
    print(f"[Cloud API] Extracting 1536-D code embeddings for {len(code_list)} samples...")
    embeddings: List[List[float]] = []
    key_idx = 0
    total_batches = (len(code_list) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start_i = batch_num * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(code_list))
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
                    # Ensure ordered by index
                    items = sorted(data["data"], key=lambda x: x["index"])
                    batch_vecs = [item["embedding"] for item in items]
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
            embeddings.extend([[0.0] * 1536 for _ in range(len(batch_codes))])

    return np.array(embeddings, dtype=np.float32)


def train_and_benchmark():
    api_keys = get_api_keys()
    if not api_keys:
        print("[ERROR] No OPENROUTER_API_KEY found in .env!")
        sys.exit(1)

    print(f"[1/4] Loading binary dataset: {os.path.basename(DATASET_PATH)}")
    df = pd.read_csv(DATASET_PATH)

    print(f"      Total Samples : {len(df)}")
    print(f"      Buggy (1)     : {(df['is_bug'] == 1).sum()}")
    print(f"      Clean (0)     : {(df['is_bug'] == 0).sum()}")

    # 1. Parse AST Vectors (64-D)
    print("\n[2/4] Parsing 64-D AST vectors...")
    ast_list = []
    for v in df["ast_vector"]:
        try:
            arr = json.loads(v)
            if len(arr) == 64:
                ast_list.append(arr)
            else:
                ast_list.append([0.0] * 64)
        except Exception:
            ast_list.append([0.0] * 64)
    X_ast = np.array(ast_list, dtype=np.float32)

    # 2. Extract Code Embeddings (1536-D)
    print("\n[3/4] Fetching 1536-D Cloud Code Embeddings...")
    X_code_emb = fetch_cloud_embeddings_batched(df["code"].tolist(), api_keys)

    # 3. Create Hybrid Vector (1600-D)
    scaler = StandardScaler()
    X_ast_scaled = scaler.fit_transform(X_ast)
    X_hybrid = np.hstack([X_ast_scaled, X_code_emb])

    y = df["is_bug"].values
    groups = df["pair_id"].values

    print("\n" + "="*75)
    print("      BINARY BUG DETECTOR BENCHMARK (1 = Bug, 0 = Clean / Not Bug)")
    print("="*75)

    feature_sets = {
        "AST Features Only (64-D)": X_ast_scaled,
        "Code Embeddings Only (1536-D)": X_code_emb,
        "Hybrid AST + Code Embeddings (1600-D)": X_hybrid,
    }

    classifiers = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Support Vector Classifier (SVC)": SVC(kernel="rbf", C=2.0, probability=True, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42),
        "Extra Trees": ExtraTreesClassifier(n_estimators=150, max_depth=12, random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=100, learning_rate=0.05, max_depth=4, random_state=42),
    }

    gkf = GroupKFold(n_splits=5)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    all_summary = []

    for feat_name, X_data in feature_sets.items():
        print(f"\n>>> FEATURE SET: {feat_name}")
        print("-" * 75)

        # Create Group Holdout Train-Test Split (80% Train, 20% Unseen Test)
        train_idx, test_idx = next(gss.split(X_data, y, groups=groups))
        X_train_h, X_test_h = X_data[train_idx], X_data[test_idx]
        y_train_h, y_test_h = y[train_idx], y[test_idx]

        for clf_name, clf in classifiers.items():
            # 1. Group 5-Fold Cross Validation Accuracy
            cv_scores = []
            cv_aucs = []

            for tr_i, te_i in gkf.split(X_data, y, groups=groups):
                X_tr, X_te = X_data[tr_i], X_data[te_i]
                y_tr, y_te = y[tr_i], y[te_i]

                clf.fit(X_tr, y_tr)
                preds = clf.predict(X_te)
                probs = clf.predict_proba(X_te)[:, 1] if hasattr(clf, "predict_proba") else preds

                acc = accuracy_score(y_te, preds)
                auc = roc_auc_score(y_te, probs)

                cv_scores.append(acc)
                cv_aucs.append(auc)

            mean_cv_acc = np.mean(cv_scores) * 100
            std_cv_acc = np.std(cv_scores) * 100
            mean_cv_auc = np.mean(cv_aucs) * 100

            # 2. 20% Unseen Holdout Test Accuracy
            clf.fit(X_train_h, y_train_h)
            y_holdout_pred = clf.predict(X_test_h)
            y_holdout_prob = clf.predict_proba(X_test_h)[:, 1] if hasattr(clf, "predict_proba") else y_holdout_pred

            holdout_acc = accuracy_score(y_test_h, y_holdout_pred) * 100
            holdout_prec = precision_score(y_test_h, y_holdout_pred, zero_division=0) * 100
            holdout_rec = recall_score(y_test_h, y_holdout_pred, zero_division=0) * 100
            holdout_f1 = f1_score(y_test_h, y_holdout_pred, zero_division=0) * 100
            holdout_auc = roc_auc_score(y_test_h, y_holdout_prob) * 100

            print(f"  - {clf_name:32s} | Group CV: {mean_cv_acc:5.2f}% | Holdout Test Acc: {holdout_acc:5.2f}% | Prec: {holdout_prec:5.2f}% | Rec: {holdout_rec:5.2f}% | F1: {holdout_f1:5.2f}%")

            all_summary.append({
                "Feature Set": feat_name,
                "Classifier": clf_name,
                "5-Fold Group CV Acc": f"{mean_cv_acc:.2f}%",
                "Holdout Test Acc": f"{holdout_acc:.2f}%",
                "Test Precision": f"{holdout_prec:.2f}%",
                "Test Recall": f"{holdout_rec:.2f}%",
                "Test F1 Score": f"{holdout_f1:.2f}%",
                "Test ROC-AUC": f"{holdout_auc:.2f}%"
            })

    print("\n" + "="*85)
    print("SUMMARY RESULTS TABLE (5-FOLD CV vs HOLDOUT TEST ACCURACY):")
    print("="*85)
    summary_df = pd.DataFrame(all_summary)
    print(summary_df.to_string(index=False))
    print("="*85)


if __name__ == "__main__":
    train_and_benchmark()
