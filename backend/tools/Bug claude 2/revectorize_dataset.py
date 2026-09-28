import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from ast_vectorizer import extract_ast_vector_with_tier

csv.field_size_limit(sys.maxsize)


def main():
    parser = argparse.ArgumentParser(description="Re-vectorize AST features for dataset rows.")
    parser.add_argument("--in", dest="input_csv", default="dataset_enriched.csv", help="Input CSV file")
    parser.add_argument("--out", dest="output_csv", default="dataset_revectorized.csv", help="Output CSV file")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)

    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        sys.exit(1)

    print("=" * 60)
    print(f" RE-VECTORIZING AST FEATURES: {input_path.name} -> {output_path.name}")
    print("=" * 60)

    df = pd.read_csv(input_path, on_bad_lines="skip")
    total_rows = len(df)
    print(f"Loaded {total_rows} rows from {input_path}")

    buggy_tiers = Counter()
    fixed_tiers = Counter()

    buggy_vectors = []
    fixed_vectors = []

    for idx, row in df.iterrows():
        buggy_code = str(row.get("buggy_code", "")) if pd.notna(row.get("buggy_code")) else ""
        fixed_code = str(row.get("fixed_code", "")) if pd.notna(row.get("fixed_code")) else ""
        filename = str(row.get("file_path", "snippet.tsx")) if pd.notna(row.get("file_path")) else "snippet.tsx"

        vec_buggy, tier_b = extract_ast_vector_with_tier(buggy_code, filename)
        vec_fixed, tier_f = extract_ast_vector_with_tier(fixed_code, filename)

        buggy_tiers[tier_b] += 1
        fixed_tiers[tier_f] += 1

        buggy_vectors.append(json.dumps([round(float(x), 8) for x in vec_buggy]))
        fixed_vectors.append(json.dumps([round(float(x), 8) for x in vec_fixed]))

        if (idx + 1) % 100 == 0 or (idx + 1) == total_rows:
            print(f"Processed {idx + 1}/{total_rows} rows...")

    df["buggy_ast_vector"] = buggy_vectors
    df["fixed_ast_vector"] = fixed_vectors

    df.to_csv(output_path, index=False)
    print(f"\nSaved revectorized dataset to {output_path}")

    print("\n" + "=" * 60)
    print(" PARSE TIER STATISTICS SUMMARY")
    print("=" * 60)
    print("Buggy Code Parsing Tiers:")
    for tier, count in sorted(buggy_tiers.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_rows) * 100
        print(f"  - {tier:25s}: {count:4d} ({pct:5.2f}%)")

    print("\nFixed Code Parsing Tiers:")
    for tier, count in sorted(fixed_tiers.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_rows) * 100
        print(f"  - {tier:25s}: {count:4d} ({pct:5.2f}%)")

    total_parses = total_rows * 2
    failed_parses = (buggy_tiers.get("parse_error", 0) + buggy_tiers.get("exec_error", 0) +
                    fixed_tiers.get("parse_error", 0) + fixed_tiers.get("exec_error", 0))
    success_rate = ((total_parses - failed_parses) / total_parses) * 100
    print(f"\nOverall AST Parse Success Rate: {success_rate:.2f}% ({total_parses - failed_parses}/{total_parses})")
    print("=" * 60)


if __name__ == "__main__":
    main()
