import csv
import json
import sys
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd

from ast_vectorizer import extract_ast_vector_with_tier, _python_fallback_counts, NODE_INDEX, BAG_DIM, VECTOR_DIM

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

csv.field_size_limit(sys.maxsize)

WORKDIR = Path(__file__).resolve().parent
INPUT_PATH = WORKDIR / "dataset_enriched_backup.csv" if (WORKDIR / "dataset_enriched_backup.csv").exists() else WORKDIR / "dataset_enriched.csv"
OUTPUT_PATH = WORKDIR / "dataset_revectorized.csv"
ENRICHED_PATH = WORKDIR / "dataset_enriched.csv"

def robust_extract_vector(code: str, filename: str = "snippet.tsx"):
    vec, tier = extract_ast_vector_with_tier(code, filename)
    # If vector is all zeros, apply fallback regex vectorizer
    if np.all(vec == 0) or tier == "parse_error":
        counts = _python_fallback_counts(code)
        vec = np.zeros(VECTOR_DIM, dtype=float)
        for node_type, count in counts.items():
            if node_type in NODE_INDEX:
                vec[NODE_INDEX[node_type]] = float(count)
        tier = "python_fallback"
    return vec, tier

def clean_and_revectorize():
    print("=" * 65)
    print(" ROBUST CLEANING & RE-VECTORIZING DATASET (100% COVERAGE)")
    print("=" * 65)

    if not INPUT_PATH.exists():
        print(f"Error: {INPUT_PATH} not found.")
        return

    df = pd.read_csv(INPUT_PATH, on_bad_lines="skip")
    initial_count = len(df)
    print(f"Loaded {initial_count} raw rows from {INPUT_PATH.name}")

    # 1. Quality Filter: Drop missing critical columns
    df = df.dropna(subset=["bug_type", "buggy_code", "fixed_code"])

    # 2. Quality Filter: Drop rows where buggy_code == fixed_code
    df = df[df["buggy_code"].astype(str).str.strip() != df["fixed_code"].astype(str).str.strip()]
    print(f"Rows after removing identical buggy==fixed snippets: {len(df)}")

    # 3. Quality Filter: Drop very short snippets (< 15 characters)
    df = df[df["buggy_code"].astype(str).str.len() >= 15]
    print(f"Rows after removing snippets < 15 chars: {len(df)}")

    # 4. Quality Filter: Deduplicate exact (buggy_code, bug_type) pairs
    df = df.drop_duplicates(subset=["buggy_code", "bug_type"])
    print(f"Rows after deduplication: {len(df)}")

    # 5. Re-Vectorize with fallback guarantee
    print("\nExtracting AST vectors (with Tier 1 Babel + Robust Fallback)...")
    buggy_vectors = []
    fixed_vectors = []
    buggy_tiers = Counter()
    fixed_tiers = Counter()

    total_clean = len(df)
    for idx, (_, row) in enumerate(df.iterrows()):
        buggy_code = str(row["buggy_code"])
        fixed_code = str(row["fixed_code"])
        filename = str(row.get("file_path", "snippet.tsx")) if pd.notna(row.get("file_path")) else "snippet.tsx"

        vec_b, tier_b = robust_extract_vector(buggy_code, filename)
        vec_f, tier_f = robust_extract_vector(fixed_code, filename)

        buggy_tiers[tier_b] += 1
        fixed_tiers[tier_f] += 1

        buggy_vectors.append(json.dumps([round(float(x), 8) for x in vec_b]))
        fixed_vectors.append(json.dumps([round(float(x), 8) for x in vec_f]))

        if (idx + 1) % 500 == 0 or (idx + 1) == total_clean:
            print(f"  Processed AST vectors: {idx + 1}/{total_clean} rows...")

    df["buggy_ast_vector"] = buggy_vectors
    df["fixed_ast_vector"] = fixed_vectors

    # Save cleaned and revectorized dataset
    df.to_csv(OUTPUT_PATH, index=False)
    df.to_csv(ENRICHED_PATH, index=False)
    print(f"\nSaved {len(df)} high-quality clean rows to {OUTPUT_PATH.name} and {ENRICHED_PATH.name}")

    print("\n--- Parse Tier Distribution Summary ---")
    print(f"Buggy Code Parsing Tiers: {dict(buggy_tiers)}")
    print(f"Fixed Code Parsing Tiers: {dict(fixed_tiers)}")
    print("=" * 65)

if __name__ == "__main__":
    clean_and_revectorize()
