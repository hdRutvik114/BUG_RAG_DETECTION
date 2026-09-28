import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack, csr_matrix
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from ast_vectorizer import extract_ast_vector, VECTOR_DIM


WORKDIR = Path(__file__).resolve().parent
DATA_PATH = WORKDIR / "dataset_enriched.csv"
if not DATA_PATH.exists():
    DATA_PATH = WORKDIR / "dataset.csv"

MODEL_DIR = WORKDIR / "models"
METRICS_PATH = WORKDIR / "model_metrics.json"


def build_text(row: pd.Series) -> str:
    buggy = str(row.get("buggy_code", "")).strip()
    lang = str(row.get("language", "")).strip()
    if lang:
        return f"//{lang}\n{buggy}"
    return buggy


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n")
    return text.strip()


def train_and_evaluate() -> Dict[str, Dict[str, float]]:
    print(f"Reading dataset from: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=["bug_type", "buggy_code"]).copy()
    
    # Filter classes with at least 5 samples
    class_counts = df["bug_type"].value_counts()
    valid_classes = class_counts[class_counts >= 5].index
    df = df[df["bug_type"].isin(valid_classes)].copy()

    df["text"] = df.apply(build_text, axis=1).apply(clean_text)

    # Load 120-dim AST vectors if available, otherwise compute offline
    if "buggy_ast_vector" in df.columns:
        X_ast = np.array([json.loads(v) for v in df["buggy_ast_vector"]])
    else:
        print("Extracting AST vectors for dataset...")
        X_ast = np.array([extract_ast_vector(c) for c in df["buggy_code"]])

    tfidf = TfidfVectorizer(ngram_range=(2, 4), analyzer="char_wb", sublinear_tf=True, min_df=2, max_features=10000)
    X_text = tfidf.fit_transform(df["text"])
    X_hybrid = hstack([X_text, csr_matrix(X_ast)]).tocsr()

    y = df["bug_type"]
    groups = df["commit_hash"] if "commit_hash" in df.columns else df.index

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(X_hybrid, y, groups))

    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    
    MODEL_DIR.mkdir(exist_ok=True)
    results: Dict[str, Dict[str, float]] = {}

    # Save TF-IDF Vectorizer
    joblib.dump(tfidf, MODEL_DIR / "tfidf_vectorizer.joblib")

    # 1. Text Models
    print("--- Training Code Text Models ---")
    X_text_train, X_text_test = X_text[train_idx], X_text[test_idx]
    text_classifiers = [
        ("text_sgd", SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)),
        ("text_linear_svc", LinearSVC(class_weight="balanced", random_state=42, max_iter=2000)),
        ("text_logistic", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))
    ]
    for name, clf in text_classifiers:
        clf.fit(X_text_train, y_train)
        preds = clf.predict(X_text_test)
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, average="macro", zero_division=0)
        results[name] = {"accuracy": round(float(acc), 4), "f1_macro": round(float(f1), 4)}
        joblib.dump(clf, MODEL_DIR / f"{name}.joblib")
        print(f"  [{name}] -> Accuracy: {acc:.4f} | Macro F1: {f1:.4f}")

    # 2. AST Vector Models (Trained strictly on 120-dim AST features)
    print("\n--- Training AST Vector Models (120-dim AST Features) ---")
    X_ast_train, X_ast_test = X_ast[train_idx], X_ast[test_idx]
    ast_classifiers = [
        ("ast_random_forest", RandomForestClassifier(n_estimators=150, max_depth=25, class_weight="balanced_subsample", random_state=42, n_jobs=1)),
        ("ast_sgd", SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)),
        ("ast_logistic", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))
    ]
    for name, clf in ast_classifiers:
        clf.fit(X_ast_train, y_train)
        preds = clf.predict(X_ast_test)
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, average="macro", zero_division=0)
        results[name] = {"accuracy": round(float(acc), 4), "f1_macro": round(float(f1), 4)}
        joblib.dump(clf, MODEL_DIR / f"{name}.joblib")
        print(f"  [{name}] -> Accuracy: {acc:.4f} | Macro F1: {f1:.4f}")

    # 3. Hybrid Models (AST Vector + Text N-Grams)
    print("\n--- Training Hybrid Multi-Modal Models (AST Vector + Code Text) ---")
    X_hyb_train, X_hyb_test = X_hybrid[train_idx], X_hybrid[test_idx]
    hybrid_classifiers = [
        ("hybrid_sgd", SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)),
        ("hybrid_logistic", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
        ("hybrid_random_forest", RandomForestClassifier(n_estimators=100, max_depth=25, class_weight="balanced_subsample", random_state=42, n_jobs=1))
    ]
    for name, clf in hybrid_classifiers:
        clf.fit(X_hyb_train, y_train)
        preds = clf.predict(X_hyb_test)
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, average="macro", zero_division=0)
        results[name] = {"accuracy": round(float(acc), 4), "f1_macro": round(float(f1), 4)}
        joblib.dump(clf, MODEL_DIR / f"{name}.joblib")
        print(f"  [{name}] -> Accuracy: {acc:.4f} | Macro F1: {f1:.4f}")

    with METRICS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    best_model_name = max(results, key=lambda k: results[k]["f1_macro"])
    print(f"\nBest Overall Model: '{best_model_name}' (Macro F1: {results[best_model_name]['f1_macro']:.4f})")
    return results


def predict_code(code: str) -> Dict[str, Any]:
    clean_c = clean_text(code)
    
    # 1. Extract 120-dim AST Vector for input code
    ast_vec = extract_ast_vector(clean_c)
    
    # 2. Extract Text TF-IDF features
    tfidf = joblib.load(MODEL_DIR / "tfidf_vectorizer.joblib")
    text_feat = tfidf.transform([clean_c])
    
    # 3. Combine into Hybrid Features
    hybrid_feat = hstack([text_feat, csr_matrix(ast_vec.reshape(1, -1))]).tocsr()

    # Load AST Model and Hybrid Model
    ast_model = joblib.load(MODEL_DIR / "ast_random_forest.joblib")
    ast_pred = ast_model.predict(ast_vec.reshape(1, -1))[0]
    
    ast_probs = {}
    if hasattr(ast_model, "predict_proba"):
        probas = ast_model.predict_proba(ast_vec.reshape(1, -1))[0]
        classes = ast_model.classes_
        top_probas = sorted(zip(classes, probas), key=lambda x: x[1], reverse=True)[:3]
        ast_probs = {cls: round(float(p), 4) for cls, p in top_probas}

    hybrid_model = joblib.load(MODEL_DIR / "hybrid_sgd.joblib")
    hybrid_pred = hybrid_model.predict(hybrid_feat)[0]
    
    hybrid_probs = {}
    if hasattr(hybrid_model, "predict_proba"):
        probas = hybrid_model.predict_proba(hybrid_feat)[0]
        classes = hybrid_model.classes_
        top_probas = sorted(zip(classes, probas), key=lambda x: x[1], reverse=True)[:3]
        hybrid_probs = {cls: round(float(p), 4) for cls, p in top_probas}

    non_zero_ast_count = int(np.count_nonzero(ast_vec))

    return {
        "ast_vector_stats": {
            "dimensions": len(ast_vec),
            "non_zero_features": non_zero_ast_count,
            "sample_vector_snippet": [round(float(v), 4) for v in ast_vec[:8]]
        },
        "ast_model_prediction": {
            "model": "ast_random_forest",
            "predicted_bug_type": ast_pred,
            "top_probabilities": ast_probs
        },
        "hybrid_model_prediction": {
            "model": "hybrid_sgd",
            "predicted_bug_type": hybrid_pred,
            "top_probabilities": hybrid_probs
        }
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train and evaluate AST and Code classification models")
    parser.add_argument("--predict", type=str, help="Paste new code to parse AST and classify")
    parser.add_argument("--train", action="store_true", help="Train AST and hybrid models")
    args = parser.parse_args()

    if args.train or not METRICS_PATH.exists():
        metrics = train_and_evaluate()
        print("\nTraining complete. All Model Metrics:")
        print(json.dumps(metrics, indent=2))

    if args.predict:
        res = predict_code(args.predict)
        print("\n=== AST & HYBRID CLASSIFICATION RESULT ===")
        print(json.dumps(res, indent=2))
    elif not args.train:
        print("No action specified. Run with --train to train models or --predict 'your code here'.")


