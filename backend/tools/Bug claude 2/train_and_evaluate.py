import csv
import json
import sys
import time
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder

csv.field_size_limit(sys.maxsize)

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Train and evaluate ML models.")
parser.add_argument("--data", type=str, default=None, help="Dataset CSV path")
args = parser.parse_args()

if args.data:
    dataset_file = args.data
elif Path('dataset_revectorized.csv').exists():
    dataset_file = 'dataset_revectorized.csv'
else:
    dataset_file = 'dataset_enriched.csv'

print("="*60)
print(f" STARTING ML MODEL TRAINING ON {dataset_file.upper()}")
print("="*60)

# Load dataset
df = pd.read_csv(dataset_file, on_bad_lines='skip')
print(f"Loaded {len(df)} rows from {dataset_file}")

# Filter out empty or corrupted categories
df = df.dropna(subset=['bug_type', 'buggy_ast_vector', 'fixed_ast_vector'])
print(f"Clean samples after dropping NaNs: {len(df)}")

# Parse JSON AST vectors
def parse_vector(vec_str):
    try:
        val = json.loads(vec_str)
        if isinstance(val, list) and len(val) == 120:
            return val
    except:
        pass
    return [0.0] * 120

print("Parsing AST feature vectors...")
X_buggy_ast = np.array([parse_vector(v) for v in df['buggy_ast_vector']])
X_fixed_ast = np.array([parse_vector(v) for v in df['fixed_ast_vector']])
X_delta_ast = X_fixed_ast - X_buggy_ast

print(f"AST Buggy Matrix Shape: {X_buggy_ast.shape}")
print(f"AST Delta Matrix Shape: {X_delta_ast.shape}")

# Extract Text TF-IDF features from buggy_code
print("Extracting TF-IDF text features from buggy code snippets...")
tfidf = TfidfVectorizer(max_features=300, stop_words='english', token_pattern=r'(?u)\b\w+\b')
X_tfidf = tfidf.fit_transform(df['buggy_code'].fillna('')).toarray()

# Combine Feature Matrix: Buggy AST (120) + Delta AST (120) + TF-IDF (300) = 540 features
X_full = np.hstack([X_buggy_ast, X_delta_ast, X_tfidf])
print(f"Combined Feature Matrix Shape: {X_full.shape}")

# Encode labels
label_encoder = LabelEncoder()
y = label_encoder.fit_transform(df['bug_type'])
classes = label_encoder.classes_
print(f"Target Categories ({len(classes)} classes): {list(classes)}")

# Train/Test Split (80/20 Stratified)
X_train, X_test, y_train, y_test = train_test_split(
    X_full, y, test_size=0.20, random_state=42, stratify=y
)
print(f"Train samples: {len(X_train)} | Test samples: {len(X_test)}")

# Model 1: Random Forest
print("\n--- [1] Training Random Forest Classifier ---")
t0 = time.time()
rf = RandomForestClassifier(n_estimators=150, max_depth=18, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
y_pred_rf = rf.predict(X_test)
acc_rf = accuracy_score(y_test, y_pred_rf)
f1_rf = f1_score(y_test, y_pred_rf, average='macro')
print(f"Random Forest - Accuracy: {acc_rf*100:.2f}% | Macro F1: {f1_rf:.4f} (Time: {time.time()-t0:.2f}s)")

# Model 2: XGBoost Classifier
print("\n--- [2] Training XGBoost Classifier ---")
t0 = time.time()
xgb = XGBClassifier(n_estimators=120, max_depth=6, learning_rate=0.1, random_state=42, eval_metric='mlogloss')
xgb.fit(X_train, y_train)
y_pred_xgb = xgb.predict(X_test)
acc_xgb = accuracy_score(y_test, y_pred_xgb)
f1_xgb = f1_score(y_test, y_pred_xgb, average='macro')
print(f"XGBoost - Accuracy: {acc_xgb*100:.2f}% | Macro F1: {f1_xgb:.4f} (Time: {time.time()-t0:.2f}s)")

# Model 3: MLP Classifier (Neural Network)
print("\n--- [3] Training MLP Neural Network Classifier ---")
t0 = time.time()
mlp = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=250, random_state=42)
mlp.fit(X_train, y_train)
y_pred_mlp = mlp.predict(X_test)
acc_mlp = accuracy_score(y_test, y_pred_mlp)
f1_mlp = f1_score(y_test, y_pred_mlp, average='macro')
print(f"MLP Neural Net - Accuracy: {acc_mlp*100:.2f}% | Macro F1: {f1_mlp:.4f} (Time: {time.time()-t0:.2f}s)")

# Select best model for detailed evaluation
best_model_name = "XGBoost" if acc_xgb >= acc_rf else "Random Forest"
best_preds = y_pred_xgb if acc_xgb >= acc_rf else y_pred_rf
best_model = xgb if acc_xgb >= acc_rf else rf

print("\n" + "="*60)
print(f" DETAILED CLASSIFICATION REPORT (BEST MODEL: {best_model_name})")
print("="*60)
report_str = classification_report(y_test, best_preds, target_names=classes, digits=4)
print(report_str)

# Calculate Top-3 Accuracy
probs = best_model.predict_proba(X_test)
top3_hits = 0
for idx, true_label in enumerate(y_test):
    top3_preds = np.argsort(probs[idx])[-3:]
    if true_label in top3_preds:
        top3_hits += 1
top3_acc = top3_hits / len(y_test)
print(f"Top-1 Accuracy ({best_model_name}): {max(acc_rf, acc_xgb)*100:.2f}%")
print(f"Top-3 Accuracy ({best_model_name}): {top3_acc*100:.2f}%")

# Save results for presentation
results = {
    'total_samples': len(df),
    'num_classes': len(classes),
    'rf_acc': float(acc_rf),
    'rf_f1': float(f1_rf),
    'xgb_acc': float(acc_xgb),
    'xgb_f1': float(f1_xgb),
    'mlp_acc': float(acc_mlp),
    'mlp_f1': float(f1_mlp),
    'best_model': best_model_name,
    'best_top1_acc': float(max(acc_rf, acc_xgb)),
    'best_top3_acc': float(top3_acc),
    'categories': list(classes),
    'report': report_str
}

with open('training_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\nSaved training_results.json successfully!")
