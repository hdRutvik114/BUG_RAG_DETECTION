import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple
import joblib

from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.linear_model import SGDClassifier, LogisticRegression
from sklearn.multioutput import MultiOutputClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, accuracy_score, f1_score, precision_score, recall_score
from ast_vectorizer import extract_ast_vector

WORKDIR = Path(__file__).resolve().parent
DATA_PATH = WORKDIR / "dataset_enriched.csv"
if not DATA_PATH.exists():
    DATA_PATH = WORKDIR / "dataset.csv"

MODEL_DIR = WORKDIR / "models"
MODEL_DIR.mkdir(exist_ok=True)
METRICS_PATH = WORKDIR / "ast_dual_metrics.json"


def parse_vector(val: Any) -> np.ndarray:
    if isinstance(val, str) and val.strip():
        try:
            return np.array(json.loads(val), dtype=np.float64)
        except Exception:
            pass
    elif isinstance(val, (list, np.ndarray)):
        return np.array(val, dtype=np.float64)
    return np.zeros(120, dtype=np.float64)


def load_and_prepare_data() -> Tuple[np.ndarray, pd.DataFrame, pd.Series]:
    print(f"Reading dataset from: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    
    # Drop rows missing crucial fields
    df = df.dropna(subset=["buggy_ast_vector", "fixed_ast_vector", "bug_type", "severity"]).copy()
    
    # Clean text targets
    df["bug_type"] = df["bug_type"].astype(str).str.strip()
    df["severity"] = df["severity"].astype(str).str.strip()
    
    # Filter classes with at least 5 samples
    class_counts = df["bug_type"].value_counts()
    valid_classes = class_counts[class_counts >= 5].index
    df = df[df["bug_type"].isin(valid_classes)].copy()

    print(f"Total valid samples: {len(df)}")
    print(f"Unique Bug Classes ({len(df['bug_type'].unique())}): {df['bug_type'].value_counts().to_dict()}")
    print(f"Severity Levels ({len(df['severity'].unique())}): {df['severity'].value_counts().to_dict()}")

    # Extract Buggy AST Vector (120-dim)
    X_buggy = np.array([parse_vector(v) for v in df["buggy_ast_vector"]])
    
    # Extract Fixed AST Vector (120-dim)
    X_fixed = np.array([parse_vector(v) for v in df["fixed_ast_vector"]])
    
    # Compute AST Delta (Fixed AST - Buggy AST) (120-dim)
    X_delta = X_fixed - X_buggy

    # Concatenate [Buggy AST (120), Fixed AST (120), AST Delta (120)] -> 360-dim AST Feature Matrix
    X_ast = np.hstack([X_buggy, X_fixed, X_delta])
    
    groups = df["commit_hash"] if "commit_hash" in df.columns else df.index

    return X_ast, df[["bug_type", "severity"]], groups


def train_ast_dual_models():
    X, Y, groups = load_and_prepare_data()

    y_class = Y["bug_type"]
    y_severity = Y["severity"]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(X, y_class, groups))

    X_train, X_test = X[train_idx], X[test_idx]
    
    y_class_train, y_class_test = y_class.iloc[train_idx], y_class.iloc[test_idx]
    y_sev_train, y_sev_test = y_severity.iloc[train_idx], y_severity.iloc[test_idx]

    # Models to train separately for Class (bug_type) and Severity (severity)
    class_models = {
        "rf_class": RandomForestClassifier(n_estimators=200, max_depth=30, class_weight="balanced_subsample", random_state=42, n_jobs=-1),
        "extra_trees_class": ExtraTreesClassifier(n_estimators=150, max_depth=30, class_weight="balanced", random_state=42, n_jobs=-1),
        "sgd_class": SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)
    }

    severity_models = {
        "rf_severity": RandomForestClassifier(n_estimators=200, max_depth=20, class_weight="balanced_subsample", random_state=42, n_jobs=-1),
        "extra_trees_severity": ExtraTreesClassifier(n_estimators=150, max_depth=20, class_weight="balanced", random_state=42, n_jobs=-1),
        "sgd_severity": SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)
    }

    results = {}

    print("\n=======================================================")
    print(" 1. TRAINING BUG CLASS PREDICTION MODELS (bug_type)")
    print("=======================================================")
    best_class_model = None
    best_class_f1 = -1.0
    best_class_name = ""

    for name, clf in class_models.items():
        print(f"\n--- Training {name} ---")
        clf.fit(X_train, y_class_train)
        preds = clf.predict(X_test)
        
        acc = accuracy_score(y_class_test, preds)
        macro_f1 = f1_score(y_class_test, preds, average="macro", zero_division=0)
        weighted_f1 = f1_score(y_class_test, preds, average="weighted", zero_division=0)
        
        print(f"[{name}] Accuracy: {acc:.4f} | Macro F1: {macro_f1:.4f} | Weighted F1: {weighted_f1:.4f}")
        joblib.dump(clf, MODEL_DIR / f"{name}.joblib")
        
        results[name] = {"accuracy": round(acc, 4), "macro_f1": round(macro_f1, 4), "weighted_f1": round(weighted_f1, 4)}

        if macro_f1 > best_class_f1:
            best_class_f1 = macro_f1
            best_class_model = clf
            best_class_name = name

    print(f"\n>> Best Bug Class Model: {best_class_name} (Macro F1: {best_class_f1:.4f})")
    print(classification_report(y_class_test, best_class_model.predict(X_test), zero_division=0))

    print("\n=======================================================")
    print(" 2. TRAINING SEVERITY PREDICTION MODELS (severity)")
    print("=======================================================")
    best_sev_model = None
    best_sev_f1 = -1.0
    best_sev_name = ""

    for name, clf in severity_models.items():
        print(f"\n--- Training {name} ---")
        clf.fit(X_train, y_sev_train)
        preds = clf.predict(X_test)
        
        acc = accuracy_score(y_sev_test, preds)
        macro_f1 = f1_score(y_sev_test, preds, average="macro", zero_division=0)
        weighted_f1 = f1_score(y_sev_test, preds, average="weighted", zero_division=0)
        
        print(f"[{name}] Accuracy: {acc:.4f} | Macro F1: {macro_f1:.4f} | Weighted F1: {weighted_f1:.4f}")
        joblib.dump(clf, MODEL_DIR / f"{name}.joblib")
        
        results[name] = {"accuracy": round(acc, 4), "macro_f1": round(macro_f1, 4), "weighted_f1": round(weighted_f1, 4)}

        if macro_f1 > best_sev_f1:
            best_sev_f1 = macro_f1
            best_sev_model = clf
            best_sev_name = name

    print(f"\n>> Best Severity Model: {best_sev_name} (Macro F1: {best_sev_f1:.4f})")
    print(classification_report(y_sev_test, best_sev_model.predict(X_test), zero_division=0))

    # Save metrics summary
    with METRICS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    return best_class_name, best_sev_name, results


def predict_bug_and_severity(buggy_ast: Any, fixed_ast: Any) -> Dict[str, Any]:
    vec_buggy = parse_vector(buggy_ast) if not isinstance(buggy_ast, str) or buggy_ast.startswith("[") else extract_ast_vector(buggy_ast)
    vec_fixed = parse_vector(fixed_ast) if not isinstance(fixed_ast, str) or fixed_ast.startswith("[") else extract_ast_vector(fixed_ast)

    vec_delta = vec_fixed - vec_buggy
    X_feat = np.hstack([vec_buggy, vec_fixed, vec_delta]).reshape(1, -1)

    class_model_path = MODEL_DIR / "rf_class.joblib"
    if not class_model_path.exists():
        class_model_path = MODEL_DIR / "extra_trees_class.joblib"

    sev_model_path = MODEL_DIR / "rf_severity.joblib"
    if not sev_model_path.exists():
        sev_model_path = MODEL_DIR / "extra_trees_severity.joblib"

    class_model = joblib.load(class_model_path)
    sev_model = joblib.load(sev_model_path)

    pred_class = class_model.predict(X_feat)[0]
    pred_sev = sev_model.predict(X_feat)[0]

    class_probs = {}
    if hasattr(class_model, "predict_proba"):
        probas = class_model.predict_proba(X_feat)[0]
        top_c = sorted(zip(class_model.classes_, probas), key=lambda x: x[1], reverse=True)[:3]
        class_probs = {cls: round(float(p), 4) for cls, p in top_c}

    sev_probs = {}
    if hasattr(sev_model, "predict_proba"):
        probas = sev_model.predict_proba(X_feat)[0]
        top_s = sorted(zip(sev_model.classes_, probas), key=lambda x: x[1], reverse=True)[:3]
        sev_probs = {s: round(float(p), 4) for s, p in top_s}

    return {
        "input_features": {
            "buggy_ast_dim": len(vec_buggy),
            "fixed_ast_dim": len(vec_fixed),
            "ast_delta_dim": len(vec_delta),
            "total_feature_dimensions": X_feat.shape[1]
        },
        "predicted_bug_class": {
            "bug_type": pred_class,
            "top_probabilities": class_probs
        },
        "predicted_severity": {
            "severity": pred_sev,
            "top_probabilities": sev_probs
        }
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train AST-only Bug Class and Severity Classifiers")
    parser.add_argument("--train", action="store_true", help="Train AST models for bug_type and severity")
    parser.add_argument("--predict-sample", action="store_true", help="Test prediction on a sample from dataset")
    args = parser.parse_args()

    if args.train or not (MODEL_DIR / "rf_class.joblib").exists():
        best_c, best_s, metrics = train_ast_dual_models()
        print("\nTraining completed successfully!")

    if args.predict_sample or not args.train:
        print("\n=== RUNNING TEST INFERENCE ON A DATASET SAMPLE ===")
        df = pd.read_csv(DATA_PATH).dropna(subset=["buggy_ast_vector", "fixed_ast_vector", "bug_type", "severity"])
        sample = df.iloc[0]
        print(f"Sample Repository: {sample['repository']}")
        print(f"Actual Bug Type  : {sample['bug_type']}")
        print(f"Actual Severity  : {sample['severity']}")
        
        res = predict_bug_and_severity(sample["buggy_ast_vector"], sample["fixed_ast_vector"])
        print("\n--- Model Predictions ---")
        print(json.dumps(res, indent=2))
