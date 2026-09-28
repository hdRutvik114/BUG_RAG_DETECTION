import pandas as pd
import numpy as np
import json
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from xgboost import XGBClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

df = pd.read_csv('dataset_revectorized.csv').dropna(subset=['bug_type'])
print(f"Loaded {len(df)} rows from dataset_revectorized.csv")

def parse(v):
    try:
        val = json.loads(v)
        if isinstance(val, list) and len(val) == 120:
            return val
    except:
        pass
    return [0.0] * 120

X_buggy = np.array([parse(v) for v in df['buggy_ast_vector']])
X_fixed = np.array([parse(v) for v in df['fixed_ast_vector']])
X_delta = X_fixed - X_buggy

tfidf = TfidfVectorizer(max_features=300, ngram_range=(1, 2), stop_words='english', sublinear_tf=True)
X_tfidf = tfidf.fit_transform(df['buggy_code'].fillna('')).toarray()

X_full = np.hstack([X_buggy, X_delta, X_tfidf])
le = LabelEncoder()
y = le.fit_transform(df['bug_type'])

X_tr, X_te, y_tr, y_te = train_test_split(X_full, y, test_size=0.20, random_state=42, stratify=y)
sample_weights = compute_sample_weight('balanced', y_tr)

rf = RandomForestClassifier(n_estimators=180, max_depth=18, random_state=42, class_weight='balanced', n_jobs=-1)
rf.fit(X_tr, y_tr)
y_pred_rf = rf.predict(X_te)
print(f"Random Forest Accuracy: {accuracy_score(y_te, y_pred_rf)*100:.2f}% | Macro F1: {f1_score(y_te, y_pred_rf, average='macro'):.4f}")

xgb = XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.1, random_state=42, eval_metric='mlogloss')
xgb.fit(X_tr, y_tr, sample_weight=sample_weights)
y_pred_xgb = xgb.predict(X_te)
print(f"XGBoost Accuracy:       {accuracy_score(y_te, y_pred_xgb)*100:.2f}% | Macro F1: {f1_score(y_te, y_pred_xgb, average='macro'):.4f}")

ens = VotingClassifier(estimators=[('rf', rf), ('xgb', xgb)], voting='soft')
ens.fit(X_tr, y_tr, sample_weight=sample_weights)
y_pred_ens = ens.predict(X_te)
print(f"Ensemble Accuracy:      {accuracy_score(y_te, y_pred_ens)*100:.2f}% | Macro F1: {f1_score(y_te, y_pred_ens, average='macro'):.4f}")

probs = ens.predict_proba(X_te)
top3 = sum(1 for i, t in enumerate(y_te) if t in np.argsort(probs[i])[-3:]) / len(y_te)
print(f"Ensemble Top-3 Accuracy: {top3*100:.2f}%")
