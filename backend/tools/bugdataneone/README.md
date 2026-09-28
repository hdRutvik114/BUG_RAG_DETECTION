# Bug Dataset Enrichment Pipeline

A Python-based dataset enrichment and reclassification pipeline designed to enhance bug-fix datasets for training Machine Learning models for **Bug Detection**, **Bug Classification**, and **Severity Prediction**.

## Features

- **Automated Reclassification**: Corrects vague/inaccurate bug types (and eliminates overuse of `"other"`) into a 27-category taxonomy.
- **Rich Annotations**: Generates 8 new technical columns (`bug_type`, `bug_description`, `root_cause`, `fix_description`, `severity`, `bug_pattern`, `affected_component`, `confidence_score`).
- **Resilient API Key Failover**: Rotates through multiple Gemini API keys (`GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, etc.) when quota or rate limits (HTTP 429) are encountered.
- **Checkpointing & Resume**: Automatically saves progress to `checkpoint.json` after every batch. Can be stopped and resumed at any point without re-processing or losing data.
- **Schema Validation**: Guarantees JSON output compliance using Pydantic schemas with type enforcement and bounds checking.
- **Preserves Original Data**: Reads `dataset.csv` and outputs to `dataset_enriched.csv` without overwriting input files.

---

## Installation & Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API Keys**:
   Add your Gemini API key(s) to `.env`:
   ```env
   GEMINI_API_KEY_1=your_primary_api_key
   GEMINI_API_KEY_2=your_secondary_api_key
   ```

---

## Execution

### Run Full Pipeline
```bash
python enrich_dataset.py
```

### Run a Test Batch
```bash
python enrich_dataset.py --max-records 10
```

### Options & CLI Flags
| Flag | Description | Default |
|---|---|---|
| `--input` | Path to input dataset CSV | `dataset.csv` |
| `--output` | Path to output enriched CSV | `dataset_enriched.csv` |
| `--batch-size` | Number of records per batch save | `10` |
| `--max-records` | Limit processing count (for testing) | None (all) |
| `--reset-checkpoint` | Clear checkpoint & restart output file | False |

---

## Taxonomy & Output Columns

### Enriched Columns Appended:
1. `bug_type`: Corrected taxonomy category (`null_pointer`, `type_error`, `logic_error`, `async_error`, `security_vulnerability`, etc.)
2. `bug_description`: 20-60 words detailed technical description.
3. `root_cause`: Concise technical cause statement.
4. `fix_description`: Summary of code modification and fix impact.
5. `severity`: `low`, `medium`, `high`, or `critical`.
6. `bug_pattern`: Pattern name (e.g. `Missing Null Check`, `Missing Await`).
7. `affected_component`: Component classification (`backend`, `frontend`, `api`, `database`, `security`, etc.).
8. `confidence_score`: Float between `0.00` and `1.00`.
