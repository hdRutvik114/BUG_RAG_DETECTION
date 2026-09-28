import csv
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder

from ast_vectorizer import extract_ast_vector_with_tier

csv.field_size_limit(sys.maxsize)

def run_improved_pipeline():
    print("=" * 65)
    print(" ACCURACY BOOST PIPELINE (TARGET: 53% -> 70%+)")
    print("=" * 65)

    df = pd.read_csv("dataset_enriched.csv", on_bad_lines="skip")
    print(f"Initial Dataset Rows: {len(df)}")

    # Data Cleaning Rule 1: Drop NaNs
    df = df.dropna(subset=["bug_type", "buggy_code", "buggy_ast_vector", "fixed_ast_vector"])

    # Data Cleaning Rule 2: Remove identical buggy vs fixed snippets
    df = df[df["buggy_code"] != df["fixed_code"]]

    # Data Cleaning Rule 3: Remove very short uninformative snippets (< 20 chars)
    df = df[df["buggy_code"].str.len() >= 20]

    # Data Cleaning Rule 4: Remove exact duplicates with label conflicts
    df = df.drop_duplicates(subset=["buggy_code", "bug_type"])
    print(f"Cleaned Dataset Rows after Quality Filters: {len(df)}")

    def parse_vec(v_str):
        try:
            val = json.loads(v_str)
            if isinstance(val, list) and len(val) == 120:
                return val
        except:
            pass
        return [0.0] * 120

    print("\n1. Extracting Re-vectorized 120-dim AST Features...")
    X_buggy_ast = np.array([parse_vec(v) for v in df["buggy_ast_vector"]])
    X_fixed_ast = np.array([parse_vec(v) for v in df["fixed_ast_vector"]])
    X_delta_ast = X_fixed_ast - X_buggy_ast

    print("2. Extracting Enhanced Unigram + Bigram TF-IDF Features (600 max features)...")
    tfidf = TfidfVectorizer(
        max_features=600,
        ngram_range=(1, 2),
        stop_words="english",
        sublinear_tf=True,
        token_pattern=r"(?u)\b\w+\b"
    )
    X_tfidf = tfidf.fit_transform(df["buggy_code"].fillna("")).toarray()

    X_full = np.hstack([X_buggy_ast, X_delta_ast, X_tfidf])
    print(f"Combined Feature Matrix Shape: {X_full.shape}")

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(df["bug_type"])
    classes = label_encoder.classes_

    X_train, X_test, y_train, y_test = train_test_split(
        X_full, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"Train set: {len(X_train)} | Test set: {len(X_test)}")

    # Enhanced Classifier 1: Tuned Random Forest
    rf = RandomForestClassifier(
        n_estimators=250,
        max_depth=22,
        min_samples_split=3,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced"
    )
    rf.fit(X_train, y_train)
    rf_acc = accuracy_score(y_test, rf.predict(X_test))
    print(f"\n[1] Tuned Random Forest Accuracy: {rf_acc*100:.2f}%")

    # Enhanced Classifier 2: Tuned XGBoost
    xgb = XGBClassifier(
        n_estimators=200,
        max_depth=8,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="mlogloss"
    )
    xgb.fit(X_train, y_train)
    xgb_acc = accuracy_score(y_test, xgb.predict(X_test))
    print(f"[2] Tuned XGBoost Accuracy:       {xgb_acc*100:.2f}%")

    # Enhanced Classifier 3: Soft-Voting Ensemble (RF + XGB)
    ensemble = VotingClassifier(
        estimators=[('rf', rf), ('xgb', xgb)],
        voting='soft'
    )
    ensemble.fit(X_train, y_train)
    y_pred_ens = ensemble.predict(X_test)
    ens_acc = accuracy_score(y_test, y_pred_ens)
    ens_f1 = f1_score(y_test, y_pred_ens, average="macro")

    # Compute Top-3 Accuracy
    probs = ensemble.predict_proba(X_test)
    top3_hits = sum(1 for idx, true_lbl in enumerate(y_test) if true_lbl in np.argsort(probs[idx])[-3:])
    top3_acc = top3_hits / len(y_test)

    print(f"[3] Soft-Voting Ensemble Accuracy: {ens_acc*100:.2f}% | Macro F1: {ens_f1:.4f}")
    print(f"[*] Top-3 Ensemble Accuracy:      {top3_acc*100:.2f}%")
    print("=" * 65)

if __name__ == "__main__":
    run_improved_pipeline()
