import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm import tqdm

WORKDIR = Path(__file__).resolve().parent
ENV_PATH = WORKDIR / ".env"
CONFIG_PATH = WORKDIR / "config.json"

# Load environment variables
load_dotenv(ENV_PATH)


class EnrichmentRecord(BaseModel):
    bug_type: str = Field(
        description="The corrected bug category from the approved taxonomy list."
    )
    bug_description: str = Field(
        description="20-60 words technical explanation of what the bug is, why it matters, and impact caused."
    )
    root_cause: str = Field(
        description="Concise technical explanation describing why the bug exists (e.g. Missing null validation)."
    )
    fix_description: str = Field(
        description="Technical explanation of what changed and how the fix resolves the defect."
    )
    severity: str = Field(
        description="Severity classification: low, medium, high, or critical."
    )
    bug_pattern: str = Field(
        description="Short pattern name (e.g. Missing Null Check, Invalid State Transition, Missing Await)."
    )
    affected_component: str = Field(
        description="Affected component: frontend, backend, database, network, authentication, authorization, storage, api, ui, filesystem, configuration, build_system, unknown."
    )
    confidence_score: float = Field(
        description="Confidence score between 0.00 and 1.00."
    )


class APIKeyManager:
    """Manages rotation and failover across multiple Gemini API keys."""

    def __init__(self):
        self.keys: List[str] = self._discover_keys()
        self.current_index: int = 0
        self.exhausted_keys: Set[str] = set()

    def _discover_keys(self) -> List[str]:
        keys = []
        # Look for explicit numbered keys (GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.)
        for key, value in sorted(os.environ.items()):
            if (key.startswith("GEMINI_API_KEY") or key.startswith("GOOGLE_API_KEY")) and value.strip():
                if value.strip() not in keys:
                    keys.append(value.strip())
        return keys

    def get_client(self) -> Tuple[genai.Client, str]:
        if not self.keys:
            print("\n[ERROR] No Gemini API keys found in .env file!")
            print("Please add GEMINI_API_KEY_1=your_key to your .env file and restart.\n")
            sys.exit(1)

        available_keys = [k for k in self.keys if k not in self.exhausted_keys]
        if not available_keys:
            print("\n" + "=" * 70)
            print("[RATE LIMIT WARNING] All configured Gemini API keys have hit quota/rate limits!")
            print("Please update your `.env` file with additional GEMINI_API_KEY_N values.")
            print("Press Enter once you have updated `.env`, or Ctrl+C to stop cleanly.")
            print("=" * 70 + "\n")
            input("Press Enter to reload .env and retry...")
            load_dotenv(ENV_PATH, override=True)
            self.keys = self._discover_keys()
            self.exhausted_keys.clear()
            available_keys = self.keys

        key = available_keys[self.current_index % len(available_keys)]
        return genai.Client(api_key=key), key

    def mark_key_exhausted(self, key: str):
        print(f"\n[KEY ROTATION] Key ending in ...{key[-6:]} hit rate limit. Rotating to next key...")
        self.exhausted_keys.add(key)
        self.current_index += 1


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "input_dataset": "dataset.csv",
        "output_dataset": "dataset_enriched.csv",
        "checkpoint_file": "checkpoint.json",
        "batch_size": 10,
        "model_name": "gemini-2.5-flash",
        "temperature": 0.1,
        "approved_bug_types": ["async_error", "null_pointer", "logic_error", "type_error", "api_misuse",
                               "security_vulnerability", "off_by_one", "exception_handling", "resource_leak",
                               "performance_issue", "input_validation", "state_management"],
        "approved_components": ["frontend", "backend", "database", "network", "authentication", "authorization",
                                "storage", "api", "ui", "filesystem", "configuration", "build_system", "unknown"],
        "approved_severities": ["low", "medium", "high", "critical"]
    }


def build_prompt(row: pd.Series, config: Dict[str, Any]) -> str:
    buggy_code = str(row.get("buggy_code", "")).strip()
    fixed_code = str(row.get("fixed_code", "")).strip()
    commit_msg = str(row.get("original_commit_message", row.get("commit_message", ""))).strip()
    language = str(row.get("language", "")).strip()
    existing_bug_type = str(row.get("bug_type", "")).strip()

    bug_types_str = ", ".join(f'"{bt}"' for bt in config["approved_bug_types"])
    components_str = ", ".join(f'"{c}"' for c in config["approved_components"])

    prompt = f"""You are an expert software engineering and security defect analyst.
Analyze the following code commit change, commit message, and bug details to produce a structured bug enrichment record.

--- PRIMARY SOURCE OF TRUTH PRIORITIES ---
1. buggy_code vs fixed_code diff analysis (Highest Priority)
2. commit message context
3. existing bug_type label
4. existing description

--- APPROVED BUG TAXONOMY ---
Choose bug_type EXACTLY from this list:
[{bug_types_str}]

* Minimize assigning "other". Reclassify vague, inaccurate, or "other" labels into specific defect categories.

--- APPROVED AFFECTED COMPONENTS ---
Choose affected_component EXACTLY from:
[{components_str}]

--- APPROVED SEVERITY LEVELS ---
Choose severity EXACTLY from: ["low", "medium", "high", "critical"]
- critical: auth bypass, privilege escalation, data corruption, severe security vulnerabilities
- high: crashes, service failures, major logic defects
- medium: incorrect functionality, recoverable runtime errors
- low: minor performance issues, cosmetic fixes, maintainability improvements

--- INPUT DATA FOR THIS COMMIT ---
Language: {language}
Original Commit Message: {commit_msg}
Existing Bug Type: {existing_bug_type}

--- BUGGY CODE ---
{buggy_code}

--- FIXED CODE ---
{fixed_code}

Produce a JSON response matching the required schema. Ensure bug_description is 20-60 words long, highly technical, and non-generic.
"""
    return prompt


def analyze_record(
    row: pd.Series,
    config: Dict[str, Any],
    key_manager: APIKeyManager,
    max_retries: int = 3
) -> EnrichmentRecord:
    prompt = build_prompt(row, config)
    models_to_try = [config.get("model_name", "gemini-2.0-flash"), "gemini-2.0-flash", "gemini-1.5-flash"]
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        client, active_key = key_manager.get_client()

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=EnrichmentRecord,
                        temperature=config.get("temperature", 0.1),
                    ),
                )

                result_text = response.text
                record = EnrichmentRecord.model_validate_json(result_text)

                # Validate categorical constraints
                if record.bug_type not in config["approved_bug_types"]:
                    record.bug_type = "other"
                if record.affected_component not in config["approved_components"]:
                    record.affected_component = "unknown"
                if record.severity not in config["approved_severities"]:
                    record.severity = "medium"

                record.confidence_score = max(0.0, min(1.0, float(record.confidence_score)))
                return record

            except APIError as api_err:
                err_msg = str(api_err).lower()
                if "404" in err_msg or "not_found" in err_msg:
                    # Model name not found, try next model in list
                    continue
                elif "429" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
                    key_manager.mark_key_exhausted(active_key)
                    time.sleep(5)
                    break
                else:
                    print(f"[API ERROR] {api_err}. Retrying in {2 ** attempt}s...")
                    time.sleep(2 ** attempt)
            except Exception as ex:
                print(f"[PROCESSING ERROR] Attempt {attempt}/{max_retries} failed: {ex}")
                time.sleep(2 ** attempt)

    # Fallback default if all retries fail
    return EnrichmentRecord(
        bug_type="logic_error",
        bug_description="Automated analysis fallback due to processing exception.",
        root_cause="Unresolved error during LLM enrichment execution.",
        fix_description="Code modified to address issue.",
        severity="medium",
        bug_pattern="Unknown Defect",
        affected_component="unknown",
        confidence_score=0.50,
    )


def load_checkpoint(checkpoint_path: Path) -> Tuple[Set[int], Dict[str, Any]]:
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                completed = set(data.get("completed_indices", []))
                stats = data.get("stats", {"processed": 0, "errors": 0})
                return completed, stats
        except Exception as e:
            print(f"[CHECKPOINT WARNING] Could not read checkpoint file: {e}. Starting fresh.")
    return set(), {"processed": 0, "errors": 0}


def save_checkpoint(checkpoint_path: Path, completed_indices: Set[int], stats: Dict[str, Any]):
    data = {
        "completed_indices": sorted(list(completed_indices)),
        "total_completed": len(completed_indices),
        "stats": stats,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Bug Dataset Enrichment Pipeline")
    parser.add_argument("--input", type=str, help="Path to input dataset CSV")
    parser.add_argument("--output", type=str, help="Path to output enriched dataset CSV")
    parser.add_argument("--batch-size", type=int, help="Batch size for saving progress")
    parser.add_argument("--max-records", type=int, help="Maximum records to process (for testing)")
    parser.add_argument("--reset-checkpoint", action="store_true", help="Reset checkpoint and output file")
    args = parser.parse_args()

    config = load_config()

    input_file = Path(args.input or config.get("input_dataset", "dataset.csv"))
    output_file = Path(args.output or config.get("output_dataset", "dataset_enriched.csv"))
    checkpoint_file = WORKDIR / config.get("checkpoint_file", "checkpoint.json")
    batch_size = args.batch_size or config.get("batch_size", 10)

    if not input_file.exists():
        print(f"[ERROR] Input dataset file '{input_file}' not found.")
        sys.exit(1)

    print(f"\n========================================================")
    print(f"       BUG DATASET ENRICHMENT PIPELINE")
    print(f"========================================================")
    print(f"Input Dataset  : {input_file}")
    print(f"Output Dataset : {output_file}")
    print(f"Checkpoint File: {checkpoint_file}")
    print(f"Batch Size     : {batch_size}")
    print(f"========================================================\n")

    if args.reset_checkpoint:
        if checkpoint_file.exists():
            checkpoint_file.unlink()
        if output_file.exists():
            output_file.unlink()
        print("[RESET] Checkpoint and output files reset.")

    # Load dataset
    df = pd.read_csv(input_file)

    # Select main informative columns
    main_cols = [
        "repository", "commit_hash", "file_path", "language",
        "bug_type", "original_commit_message", "buggy_code", "fixed_code"
    ]
    available_main_cols = [col for col in main_cols if col in df.columns]
    df_main = df[available_main_cols].copy()

    completed_indices, stats = load_checkpoint(checkpoint_file)
    print(f"Total dataset records: {len(df_main)}")
    print(f"Already processed     : {len(completed_indices)}")

    records_to_process = [i for i in range(len(df_main)) if i not in completed_indices]
    if args.max_records:
        records_to_process = records_to_process[:args.max_records]

    print(f"Records to process in this run: {len(records_to_process)}\n")

    if not records_to_process:
        print("All records have been processed! Output is complete in:", output_file)
        return

    key_manager = APIKeyManager()

    # Determine if output file exists and needs headers
    output_exists = output_file.exists() and output_file.stat().st_size > 0

    batch_buffer: List[pd.Series] = []

    for idx in tqdm(records_to_process, desc="Enriching Records"):
        row = df_main.iloc[idx].copy()

        # Run LLM analysis
        enrichment = analyze_record(row, config, key_manager)

        # Append new columns to row
        row["bug_type"] = enrichment.bug_type  # updated reclassified bug_type
        row["bug_description"] = enrichment.bug_description
        row["root_cause"] = enrichment.root_cause
        row["fix_description"] = enrichment.fix_description
        row["severity"] = enrichment.severity
        row["bug_pattern"] = enrichment.bug_pattern
        row["affected_component"] = enrichment.affected_component
        row["confidence_score"] = enrichment.confidence_score

        batch_buffer.append(row)
        completed_indices.add(idx)
        stats["processed"] += 1

        if len(batch_buffer) >= batch_size or idx == records_to_process[-1]:
            batch_df = pd.DataFrame(batch_buffer)
            # Write/append to CSV
            batch_df.to_csv(
                output_file,
                mode="a" if output_exists else "w",
                header=not output_exists,
                index=False
            )
            output_exists = True
            batch_buffer.clear()
            save_checkpoint(checkpoint_file, completed_indices, stats)

    print(f"\n========================================================")
    print(f"ENRICHMENT COMPLETE!")
    print(f"Processed: {stats['processed']} records.")
    print(f"Enriched dataset written to: {output_file}")
    print(f"========================================================\n")


if __name__ == "__main__":
    main()
