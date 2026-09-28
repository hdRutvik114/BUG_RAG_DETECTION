import argparse
import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from xgboost import XGBClassifier

from ast_vectorizer import extract_ast_vector_with_tier

# Force UTF-8 encoding on standard output for Windows compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BUG_DESCRIPTIONS = {
    "async_error": "Missing or incorrect handling of an asynchronous operation (e.g. unhandled Promise, missing await).",
    "null_pointer": "Missing null/undefined check before property access or function call.",
    "logic_error": "Flawed conditional expression or business logic calculation.",
    "type_error": "Mismatched type conversion or unsafe type assertion.",
    "api_misuse": "Incorrect API method signature or invalid configuration options.",
    "security_vulnerability": "Security flaw (e.g. un-sanitized input, missing authentication/authorization check).",
    "off_by_one": "Off-by-one boundary comparison error in loop or array indexing.",
    "exception_handling": "Missing try/catch block around risky runtime operation.",
    "resource_leak": "Unclosed database connection, socket, or uncleared timer/event listener.",
    "performance_issue": "Sub-optimal computation, missing memoization, or heavy unindexed query.",
    "input_validation": "Missing boundary validation or schema check on incoming parameters/body.",
    "state_management": "Stale React state closure or improper state mutation in hooks/reducers.",
}

SUGGESTED_FIXES = {
    "async_error": "Add `await` before Promise execution or return `.then()` / `.catch()` chain.",
    "null_pointer": "Add optional chaining (`?.`), nullish coalescing (`??`), or defensive `if (obj)` guard.",
    "logic_error": "Review boolean comparison operators (`===`, `!==`, `&&`, `||`) and branch logic.",
    "type_error": "Use explicit type casting/conversion (`Number()`, `String()`, or TS type guards).",
    "api_misuse": "Verify parameter signatures and option object properties against API documentation.",
    "security_vulnerability": "Apply input sanitization, parameterized queries, or authorization check.",
    "off_by_one": "Check loop condition bounds (`<` vs `<=`) or array index offsets (`i - 1`).",
    "exception_handling": "Wrap risky execution in `try { ... } catch (err) { ... }` block.",
    "resource_leak": "Call `.close()`, `.disconnect()`, `clearInterval()`, or handle cleanup in `finally`.",
    "performance_issue": "Apply `useMemo`, `useCallback`, debouncing, or database indexing.",
    "input_validation": "Validate req.body / req.params using schema validators (Joi, Zod, or type guards).",
    "state_management": "Use functional state updates (`prev => ...`) or include missing dependencies in hooks.",
}


class BugPredictor:
    def __init__(self, dataset_path="dataset_revectorized.csv"):
        self.dataset_path = Path(dataset_path)
        if not self.dataset_path.exists():
            self.dataset_path = Path("dataset_enriched.csv")

        print("=" * 65)
        print(f" INITIALIZING BUG PREDICTOR MODEL ({self.dataset_path.name})")
        print("=" * 65)

        self.df = pd.read_csv(self.dataset_path, on_bad_lines="skip")
        self.df = self.df.dropna(subset=["bug_type", "buggy_ast_vector", "fixed_ast_vector"])

        def parse_vec(v_str):
            try:
                val = json.loads(v_str)
                if isinstance(val, list) and len(val) == 120:
                    return val
            except:
                pass
            return [0.0] * 120

        X_buggy_ast = np.array([parse_vec(v) for v in self.df["buggy_ast_vector"]])
        X_fixed_ast = np.array([parse_vec(v) for v in self.df["fixed_ast_vector"]])
        X_delta_ast = X_fixed_ast - X_buggy_ast

        self.tfidf = TfidfVectorizer(max_features=300, stop_words="english", token_pattern=r"(?u)\b\w+\b")
        X_tfidf = self.tfidf.fit_transform(self.df["buggy_code"].fillna("")).toarray()

        X_full = np.hstack([X_buggy_ast, X_delta_ast, X_tfidf])

        self.label_encoder = LabelEncoder()
        y = self.label_encoder.fit_transform(self.df["bug_type"])
        self.classes = self.label_encoder.classes_

        print(f"Training XGBoost classifier on {len(self.df)} samples across {len(self.classes)} bug classes...")
        self.model = XGBClassifier(n_estimators=120, max_depth=6, learning_rate=0.1, random_state=42, eval_metric="mlogloss")
        self.model.fit(X_full, y)
        print("Model trained successfully!\n")

    def predict(self, code_snippet: str, filename: str = "snippet.tsx"):
        if not code_snippet.strip():
            return {"error": "Code snippet is empty"}

        ast_vec, tier = extract_ast_vector_with_tier(code_snippet, filename)
        delta_ast = np.zeros(120)
        tfidf_vec = self.tfidf.transform([code_snippet]).toarray()[0]
        feature_vector = np.hstack([ast_vec, delta_ast, tfidf_vec]).reshape(1, -1)

        probs = self.model.predict_proba(feature_vector)[0]
        top_indices = np.argsort(probs)[::-1][:3]

        top_predictions = []
        for idx in top_indices:
            bug_type = self.classes[idx]
            confidence = float(probs[idx])
            top_predictions.append({
                "bug_type": bug_type,
                "confidence": confidence,
                "confidence_percent": f"{confidence * 100:.2f}%",
                "description": BUG_DESCRIPTIONS.get(bug_type, ""),
                "suggested_fix": SUGGESTED_FIXES.get(bug_type, "")
            })

        top_pred = top_predictions[0]

        return {
            "snippet": code_snippet,
            "filename": filename,
            "ast_tier_used": tier,
            "top_bug_type": top_pred["bug_type"],
            "top_confidence": top_pred["confidence_percent"],
            "top_predictions": top_predictions,
        }


def format_prediction_report(res: dict) -> str:
    lines = []
    lines.append("=" * 65)
    lines.append(" BUG PREDICTION REPORT")
    lines.append("=" * 65)
    lines.append(f"Input Snippet File : {res['filename']}")
    lines.append(f"AST Parsing Tier    : {res['ast_tier_used']}")
    lines.append("-" * 65)
    lines.append("CODE SNIPPET:")
    lines.append(res['snippet'].strip())
    lines.append("-" * 65)

    lines.append(f"[>] PREDICTED BUG TYPE : {res['top_bug_type'].upper()} ({res['top_confidence']} confidence)")
    lines.append(f"[*] Description        : {BUG_DESCRIPTIONS.get(res['top_bug_type'], '')}")
    lines.append(f"[*] Suggested Fix      : {SUGGESTED_FIXES.get(res['top_bug_type'], '')}")
    lines.append("-" * 65)

    lines.append("TOP 3 CONFIDENCE PROBABILITIES:")
    for i, pred in enumerate(res['top_predictions'], 1):
        bar_len = int(pred['confidence'] * 25)
        bar = "#" * bar_len
        lines.append(f"  {i}. {pred['bug_type']:22s} [{pred['confidence_percent']:7s}] {bar}")

    lines.append("=" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Predict bug type from a code snippet.")
    parser.add_argument("--code", type=str, help="Code snippet string to analyze")
    parser.add_argument("--file", type=str, default="snippet.tsx", help="Filename/extension for AST parsing context")
    args = parser.parse_args()

    predictor = BugPredictor()

    if args.code:
        code_input = args.code
    else:
        print("Enter or paste your buggy code snippet (press Ctrl+Z then Enter on Windows or Ctrl+D on Linux to finish):")
        try:
            code_input = sys.stdin.read()
        except KeyboardInterrupt:
            sys.exit(0)

    if not code_input.strip():
        print("No code snippet provided.")
        sys.exit(1)

    result = predictor.predict(code_input, args.file)
    print(format_prediction_report(result))


if __name__ == "__main__":
    main()
