"""
Script to transform dataset_enriched_v3.csv into a binary classification dataset
for bug detection (1 = Buggy, 0 = Clean/Fixed).

Original format: 1 row = 1 pair (buggy_code & fixed_code)
New format: 2 rows per pair:
  - Row A: buggy_code (is_bug = 1, label_name = "buggy")
  - Row B: fixed_code (is_bug = 0, label_name = "clean")

The original dataset_enriched_v3.csv is NOT modified.
Output is saved to binary_bug_detection_dataset.csv.
"""

import os
import sys
import pandas as pd

# Fix Windows console UTF-8 printing
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKDIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(WORKDIR, "dataset_enriched_v3.csv")
OUTPUT_CSV = os.path.join(WORKDIR, "binary_bug_detection_dataset.csv")

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Input file not found: {INPUT_CSV}")
        sys.exit(1)

    print(f"[1/3] Loading input dataset: {INPUT_CSV}")
    df_src = pd.read_csv(INPUT_CSV)
    total_src_rows = len(df_src)
    print(f"      Source rows (pairs): {total_src_rows}")

    binary_rows = []
    sample_id = 0

    for pair_idx, row in df_src.iterrows():
        b_code = str(row["buggy_code"]).strip() if pd.notna(row["buggy_code"]) else ""
        f_code = str(row["fixed_code"]).strip() if pd.notna(row["fixed_code"]) else ""

        # Extract common metadata attributes
        common_meta = {
            "pair_id": pair_idx,
            "repository": row.get("repository", ""),
            "commit_hash": row.get("commit_hash", ""),
            "file_path": row.get("file_path", ""),
            "language": row.get("language", ""),
            "bug_type": row.get("bug_type", ""),
            "severity": row.get("severity", ""),
            "ast_tier": row.get("ast_tier", ""),
            "bug_description": row.get("bug_description", ""),
            "root_cause": row.get("root_cause", ""),
            "fix_description": row.get("fix_description", ""),
            "gemini_confidence": row.get("gemini_confidence", ""),
            "gemini_validation_status": row.get("gemini_validation_status", "")
        }

        # 1. Buggy Sample (is_bug = 1)
        if b_code:
            sample_id += 1
            buggy_item = {
                "sample_id": sample_id,
                "is_bug": 1,
                "label_name": "buggy",
                "code": b_code,
                "ast_vector": row.get("buggy_ast_vector", ""),
                **common_meta
            }
            binary_rows.append(buggy_item)

        # 2. Fixed/Clean Sample (is_bug = 0)
        if f_code:
            sample_id += 1
            clean_item = {
                "sample_id": sample_id,
                "is_bug": 0,
                "label_name": "clean",
                "code": f_code,
                "ast_vector": row.get("fixed_ast_vector", ""),
                **common_meta
            }
            binary_rows.append(clean_item)

    df_binary = pd.DataFrame(binary_rows)

    # Reorder columns logically
    cols_order = [
        "sample_id", "pair_id", "is_bug", "label_name", "code", "ast_vector",
        "language", "bug_type", "severity", "repository", "commit_hash",
        "file_path", "ast_tier", "bug_description", "root_cause",
        "fix_description", "gemini_confidence", "gemini_validation_status"
    ]
    # Keep any extra columns if present
    extra_cols = [c for c in df_binary.columns if c not in cols_order]
    final_cols = cols_order + extra_cols
    df_binary = df_binary[final_cols]

    print(f"[2/3] Generated binary dataset:")
    print(f"      Total samples (rows): {len(df_binary)}")
    print(f"      Buggy samples (1)   : {(df_binary['is_bug'] == 1).sum()}")
    print(f"      Clean samples (0)   : {(df_binary['is_bug'] == 0).sum()}")

    print(f"[3/3] Saving output to: {OUTPUT_CSV}")
    df_binary.to_csv(OUTPUT_CSV, index=False)
    file_size_mb = os.path.getsize(OUTPUT_CSV) / (1024 * 1024)
    print(f"      Successfully saved! File size: {file_size_mb:.2f} MB")

if __name__ == "__main__":
    main()
