import csv
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

csv.field_size_limit(sys.maxsize)

WORKDIR = Path(__file__).resolve().parent
DATASET_PATH = WORKDIR / "dataset_enriched.csv"

def audit_dataset():
    if not DATASET_PATH.exists():
        print(f"Error: {DATASET_PATH} not found.")
        return

    print("=" * 65)
    print(f" DATASET QUALITY AUDIT: {DATASET_PATH.name}")
    print("=" * 65)

    df = pd.read_csv(DATASET_PATH, on_bad_lines="skip")
    total_rows = len(df)
    print(f"Total Rows Ingested: {total_rows}")

    # 1. Check Missing / Null values
    null_counts = df[["buggy_code", "fixed_code", "buggy_ast_vector", "fixed_ast_vector", "bug_type"]].isna().sum()
    print("\n--- [1] Missing / Null Values ---")
    for col, count in null_counts.items():
        print(f"  - {col:22s}: {count:4d} missing ({count/total_rows*100:.2f}%)")

    # 2. Check Identical buggy vs fixed code
    identical_code = (df["buggy_code"] == df["fixed_code"]).sum()
    print(f"\n--- [2] Identical Buggy & Fixed Snippets: {identical_code} rows ({identical_code/total_rows*100:.2f}%) ---")

    # 3. Check All-Zero AST Vectors (Failed Vectorization)
    def parse_vec(vec_str):
        try:
            val = json.loads(vec_str)
            if isinstance(val, list) and len(val) == 120:
                return np.array(val)
        except:
            pass
        return None

    zero_buggy = 0
    zero_fixed = 0
    malformed_vectors = 0

    for idx, row in df.iterrows():
        v_b = parse_vec(row.get("buggy_ast_vector", ""))
        v_f = parse_vec(row.get("fixed_ast_vector", ""))
        
        if v_b is None or v_f is None:
            malformed_vectors += 1
        else:
            if np.all(v_b == 0):
                zero_buggy += 1
            if np.all(v_f == 0):
                zero_fixed += 1

    print(f"\n--- [3] AST Vector Quality ---")
    print(f"  - Malformed AST Vectors       : {malformed_vectors:4d} rows ({malformed_vectors/total_rows*100:.2f}%)")
    print(f"  - All-Zero Buggy AST Vectors  : {zero_buggy:4d} rows ({zero_buggy/total_rows*100:.2f}%)")
    print(f"  - All-Zero Fixed AST Vectors  : {zero_fixed:4d} rows ({zero_fixed/total_rows*100:.2f}%)")

    # 4. Check Short / Incomplete Code Snippets
    df['buggy_len'] = df['buggy_code'].fillna('').str.len()
    short_snippets = (df['buggy_len'] < 20).sum()
    print(f"\n--- [4] Code Snippet Lengths ---")
    print(f"  - Very short snippets (< 20 chars) : {short_snippets:4d} rows ({short_snippets/total_rows*100:.2f}%)")
    print(f"  - Median buggy code length         : {df['buggy_len'].median():.0f} chars")

    # 5. Check Duplicate Snippets with Conflicting Labels
    dup_snippets = df.duplicated(subset=['buggy_code'], keep=False)
    num_dups = dup_snippets.sum()
    print(f"\n--- [5] Duplicates & Label Conflicts ---")
    print(f"  - Duplicate Buggy Snippets        : {num_dups:4d} rows ({num_dups/total_rows*100:.2f}%)")

    # Find conflicting label duplicates
    conflicting_label_count = 0
    if num_dups > 0:
        grouped = df[dup_snippets].groupby('buggy_code')['bug_type'].nunique()
        conflicting_snippets = grouped[grouped > 1]
        conflicting_label_count = len(conflicting_snippets)
        print(f"  - Snippets with Conflicting Labels: {conflicting_label_count:4d} unique code patterns")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    audit_dataset()
