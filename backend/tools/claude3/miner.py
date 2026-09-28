import base64
import csv
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import requests
from dotenv import load_dotenv
from unidiff import PatchSet

csv.field_size_limit(sys.maxsize)

from ast_vectorizer import extract_ast_vector_with_tier, is_reliable_tier
from comment_stripper import strip_js_comments
from function_extractor import extract_enclosing_function
from gemini_key_manager import GeminiKeyManager
from llm_providers import APPROVED_BUG_TYPES as LLM_APPROVED_BUG_TYPES

WORKDIR = Path(__file__).resolve().parent
ENV_PATH = WORKDIR / ".env"
DATASET_PATH = WORKDIR / "dataset_enriched_v3.csv"  # new schema -> new file, don't silently append to v2

load_dotenv(ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("miner")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# --- Gemini semantic-validation config --------------------------------------
# Regex/AST below are candidate generators only. The final bug_type always
# comes from Gemini reading the complete buggy/fixed functions (see spec).
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


def _load_gemini_keys() -> List[Tuple[str, str]]:
    """Loads OPENROUTER_API_KEY_1..N (preferred) or a single OPENROUTER_API_KEY
    or GEMINI_API_KEY_1..N from env.  All non-empty keys are returned so that
    GeminiKeyManager can fall back to the next one on HTTP 429."""
    # --- OpenRouter numbered keys (OPENROUTER_API_KEY_1 / _2 / _3 / ...) ---
    or_keys: List[Tuple[str, str]] = []
    i = 1
    while True:
        val = os.environ.get(f"OPENROUTER_API_KEY_{i}", "").strip()
        if not val:
            break
        or_keys.append((f"openrouter_key_{i}", val))
        i += 1
    if or_keys:
        return or_keys

    # --- Legacy single OpenRouter key (backward-compat) ---------------------
    single_or = (os.environ.get("OPENROUTER_API_KEY", "") or
                 os.environ.get("nemo", "")).strip()
    if single_or:
        return [("openrouter_key_1", single_or)]

    # --- Gemini numbered keys -----------------------------------------------
    keys: List[Tuple[str, str]] = []
    i = 1
    while True:
        val = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if not val:
            break
        keys.append((f"key_{i}", val))
        i += 1
    if not keys:
        single = os.environ.get("GEMINI_API_KEY", "").strip()
        if single:
            keys.append(("key_1", single))
    return keys


GEMINI_API_KEYS = _load_gemini_keys()
USE_LLM_JUDGE = bool(GEMINI_API_KEYS)

GEMINI_REQUEST_DELAY_SECONDS = float(os.environ.get("GEMINI_REQUEST_DELAY_SECONDS", "6"))
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "2"))
GEMINI_RETRY_DELAY_SECONDS = float(os.environ.get("GEMINI_RETRY_DELAY_SECONDS", "30"))
GEMINI_ALL_KEYS_COOLDOWN_SECONDS = float(os.environ.get("GEMINI_ALL_KEYS_COOLDOWN_SECONDS", "300"))
GEMINI_MIN_CONFIDENCE = float(os.environ.get("GEMINI_MIN_CONFIDENCE", "0.80"))
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "30"))

TARGET_VALIDATED_SAMPLES = int(os.environ.get("TARGET_VALIDATED_SAMPLES", "100"))

LLM_JUDGE_MAX_CANDIDATES = 4  # top-N near-tied regex categories sent to Gemini as candidates

_key_manager: Optional[GeminiKeyManager] = None
if USE_LLM_JUDGE:
    _key_manager = GeminiKeyManager(GEMINI_API_KEYS, GEMINI_MODEL, timeout=GEMINI_TIMEOUT_SECONDS)

BLACK_LISTED_ORGS: Set[str] = {
    "facebook", "google", "microsoft", "nestjs", "expressjs", "vercel",
    "reduxjs", "nodejs", "vuejs", "angular", "mongodb", "prisma",
    "sequelize", "typeorm", "axios", "fastify", "koa", "strapi", "helmet",
    "twitter", "netflix", "airbnb", "uber", "aws", "gcp",
}

APPROVED_BUG_TYPES: List[str] = list(LLM_APPROVED_BUG_TYPES)

# Realistic caps based on natural frequency in MERN repos (derived from actual mined data).
# Common bugs get higher caps; rare ones get a minimum of 20. Total ≈ 1010.
CATEGORY_CAPS: Dict[str, int] = {
    "state_management":         280,   # 27.5% — React hooks/Redux most common
    "logic_error":              250,   # 25.0% — very broad category
    "null_pointer":             160,   # 15.8% — ubiquitous in JS
    "async_error":               90,   #  9.2% — promises/await bugs
    "exception_handling":        70,   #  6.7% — try/catch issues
    "type_error":                50,   #  5.0% — JS type coercion
    "input_validation":          30,   #  3.3% — joi/zod/express-validator
    "api_misuse":                20,   #  2.5% — res.status misuse etc.
    "security_vulnerability":    20,   #  1.7% — floor: important even if rare
    "performance_issue":         20,   #  1.7% — floor
    "off_by_one":                20,   #  1.7% — floor
    "resource_leak":             20,   #  0.0% — floor: real category
}

FROZEN_CATEGORIES: Set[str] = set()

COMMIT_INCLUDE_KEYWORDS = [
    r"\bfix(es|ed)?\b", r"\bbug(fix)?\b", r"\bpatch\b", r"\bhotfix\b", r"\bresolve(d)?\b",
    r"\bissue\b", r"\berror\b", r"\bcrash\b", r"\bexception\b", r"\bvalidation\b",
    r"\bsanitize\b", r"\bsecurity\b", r"\bprevent\b", r"\bhandle\b", r"\bmissing\b",
    r"\bundefined\b", r"\bnull\b", r"\bpromise\b", r"\bawait\b", r"\bleak\b",
    r"\bbounds\b", r"\brace\b", r"\basync\b",
]

COMMIT_EXCLUDE_KEYWORDS = [
    r"\bdocs?\b", r"\breadme\b", r"\blicense\b", r"\bformat\b", r"\bprettier\b",
    r"\beslint\b", r"\blint\b", r"\bstyle\b", r"\brefactor\b", r"\brename\b",
    r"\bmerge\b", r"\brelease\b", r"\bversion\b", r"\bdependency\b", r"\bpackage\b",
    r"\bnpm\b", r"\byarn\b", r"\bpnpm\b", r"\blockfile\b", r"\bci\b", r"\bworkflow\b",
]

VALID_FILE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

# Gemini fields replace confidence_score/label_source as the authoritative
# label. match_margin/label_source are kept for continuity with the old
# schema and to show what candidates the regex stage handed to Gemini.
CSV_FIELDNAMES = [
    "repository", "commit_hash", "file_path", "language", "bug_type",
    "original_commit_message", "buggy_code", "fixed_code",
    "buggy_ast_vector", "fixed_ast_vector", "ast_tier", "bug_description", "root_cause",
    "fix_description", "severity", "bug_pattern", "affected_component",
    "confidence_score", "match_margin", "label_source",
    "gemini_model", "gemini_confidence", "gemini_reason",
    "gemini_validation_status", "gemini_api_key_slot", "gemini_attempts",
]

CONTEXT_LINES = 4


class CategoryBalancer:
    def __init__(self, cap_per_category: int, dataset_path: Path,
                 exclude_blacklisted_repos: bool = True):
        self.cap_per_category = cap_per_category
        self.counts: Dict[str, int] = {bt: 0 for bt in APPROVED_BUG_TYPES}
        self.existing_commits: Set[str] = set()
        self.repo_counts: Dict[str, int] = {}
        self.exclude_blacklisted_repos = exclude_blacklisted_repos
        self._load_existing(dataset_path)

    def _load_existing(self, dataset_path: Path) -> None:
        if not dataset_path.exists():
            return
        try:
            with open(dataset_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    repo = row.get("repository", "")
                    owner = repo.split("/")[0].lower() if repo else ""
                    if self.exclude_blacklisted_repos and owner in BLACK_LISTED_ORGS:
                        continue
                    bug_type = row.get("bug_type", "")
                    if bug_type in self.counts:
                        self.counts[bug_type] += 1
                    if repo:
                        self.repo_counts[repo] = self.repo_counts.get(repo, 0) + 1
                    commit_hash = row.get("commit_hash", "")
                    if commit_hash:
                        self.existing_commits.add(commit_hash)
        except (OSError, csv.Error) as exc:
            logger.error("Failed to load existing dataset for balancing: %s", exc)

    def cap_for(self, bug_type: str) -> int:
        return CATEGORY_CAPS.get(bug_type, self.cap_per_category)

    def remaining_for(self, bug_type: str) -> int:
        if bug_type in FROZEN_CATEGORIES:
            return 0
        return max(0, self.cap_for(bug_type) - self.counts.get(bug_type, 0))

    def is_category_full(self, bug_type: str) -> bool:
        if bug_type in FROZEN_CATEGORIES:
            return True
        return self.counts.get(bug_type, 0) >= self.cap_for(bug_type)

    def all_categories_full(self) -> bool:
        return all(self.is_category_full(bt) for bt in APPROVED_BUG_TYPES)

    def register(self, bug_type: str, repository: str) -> None:
        self.counts[bug_type] = self.counts.get(bug_type, 0) + 1
        self.repo_counts[repository] = self.repo_counts.get(repository, 0) + 1

    def remaining_categories(self) -> List[str]:
        return [bt for bt in APPROVED_BUG_TYPES if not self.is_category_full(bt)]

    def categories_by_need(self) -> List[str]:
        return sorted(APPROVED_BUG_TYPES, key=lambda bt: self.remaining_for(bt), reverse=True)


def is_valid_commit_msg(msg: str) -> bool:
    msg_lower = msg.lower()
    if any(re.search(pat, msg_lower) for pat in COMMIT_EXCLUDE_KEYWORDS):
        return False
    return any(re.search(pat, msg_lower) for pat in COMMIT_INCLUDE_KEYWORDS)


# ---------------------------------------------------------------------------
# Candidate generation ONLY. This is deliberately narrow/imperfect - its job
# is to cut down which commits are worth an (expensive, rate-limited) Gemini
# call, and to hand Gemini a short list of plausible categories instead of
# all 12. It must never be treated as the final label (spec section 1).
# ---------------------------------------------------------------------------
_CATEGORY_RULES: Dict[str, List[re.Pattern]] = {
    "async_error": [
        re.compile(r"\bawait\b"), re.compile(r"\.then\s*\("),
        re.compile(r"\bnew Promise\s*\(", re.I), re.compile(r"\basync\s+function\b"),
        re.compile(r"\basync\s*\("), re.compile(r"\.catch\s*\("),
    ],
    "exception_handling": [
        re.compile(r"\btry\s*\{"), re.compile(r"\bcatch\s*\("),
        re.compile(r"\bthrow\b"), re.compile(r"\bfinally\s*\{"),
    ],
    "null_pointer": [
        re.compile(r"\?\."), re.compile(r"!=\s*null"), re.compile(r"!==\s*null"),
        re.compile(r"!=\s*undefined"), re.compile(r"!==\s*undefined"), re.compile(r"\?\?"),
        re.compile(r"if\s*\(![a-zA-Z0-9_$.]+\)"),
    ],
    "state_management": [
        re.compile(r"\buseeffect\b", re.I), re.compile(r"\busestate\b", re.I),
        re.compile(r"\busememo\b", re.I), re.compile(r"\busecallback\b", re.I),
        re.compile(r"\bdispatch\s*\(", re.I), re.compile(r"\bsetstate\s*\(", re.I),
        re.compile(r"\bcreateslice\b|\bcombine reducers\b|\breducer\s*\(", re.I),
        re.compile(r"\bzustand\b", re.I), re.compile(r"\bmobx\b|\bobservable\b|\baction\s*\(", re.I),
        re.compile(r"\brecoil\b", re.I),
    ],
    "security_vulnerability": [
        re.compile(r"\bsanitize\b", re.I), re.compile(r"\bescape(html)?\s*\(", re.I),
        re.compile(r"\bhelmet\b", re.I), re.compile(r"\bcors\s*\(", re.I),
        re.compile(r"\bjwt\.\w+\(|\bverify\s*\(.*token", re.I),
        re.compile(r"\bbcrypt\.\w+\(", re.I), re.compile(r"\bxss\b", re.I),
        re.compile(r"\bsql\s*inject", re.I), re.compile(r"\bnosql\s*inject", re.I),
        re.compile(r"req\.(body|params|query)[^\n]{0,80}(find|query|exec|\$where|eval)", re.I),
    ],
    "input_validation": [
        re.compile(r"\bvalidator\.\w+\(", re.I), re.compile(r"\bisvalid\w*\s*\(", re.I),
        re.compile(r"\bjoi\.\w+\(.*\)\.validate", re.I),
        re.compile(r"\bschema\.(parse|safeParse|validate)\s*\(", re.I),
        re.compile(r"\bzod\b.*\bparse\b", re.I), re.compile(r"\byup\.\w+\(.*\)\.validate", re.I),
        re.compile(r"\bz\.\w+\(\).*\.parse\(", re.I),
        re.compile(r"if\s*\(\s*!req\.(body|params|query)", re.I),
    ],
    "type_error": [
        re.compile(r"\bobjectid\b", re.I), re.compile(r"\bparseint\s*\("),
        re.compile(r"\bparsefloat\s*\("), re.compile(r"\bas\s+[A-Z][a-zA-Z0-9_]*"),
        re.compile(r":\s*(string|number|boolean)\b"), re.compile(r"\.toString\s*\("),
        re.compile(r"\bNumber\s*\("), re.compile(r"\btypeof\s+\w+\s*[=!]=="),
    ],
    "resource_leak": [
        re.compile(r"\.close\s*\("), re.compile(r"\.destroy\s*\("),
        re.compile(r"\.disconnect\s*\("), re.compile(r"\.unsubscribe\s*\("),
        re.compile(r"\bclearinterval\s*\(", re.I), re.compile(r"\bcleartimeout\s*\(", re.I),
        re.compile(r"\bremoveeventlistener\s*\(", re.I),
        re.compile(r"\bfinally\s*\{[^}]*(close|destroy|disconnect)", re.I | re.S),
        re.compile(r"\bredis\b.*(client|connection)", re.I),
        re.compile(r"\bpool\.(getConnection|end)\s*\(", re.I),
        re.compile(r"\bws\.close\s*\(", re.I), re.compile(r"MongoClient\.connect\s*\(", re.I),
    ],
    "off_by_one": [
        re.compile(r"[<>]=?\s*\w+\.length"), re.compile(r"\.slice\s*\("),
        re.compile(r"\.substring\s*\("), re.compile(r"\[\s*i\s*[-+]\s*1\s*\]"),
        re.compile(r"\bpage\s*\*\s*(limit|pagesize|page_size)\b", re.I),
        re.compile(r"\boffset\s*[-+]\s*1\b", re.I),
        re.compile(r"for\s*\([^;]*;\s*\w+\s*<=\s*\w+\.length"),
    ],
    "performance_issue": [
        re.compile(r"\busememo\s*\(", re.I), re.compile(r"\busecallback\s*\(", re.I),
        re.compile(r"\breact\.memo\s*\(", re.I), re.compile(r"\bdebounce\s*\(", re.I),
        re.compile(r"\bthrottle\s*\(", re.I), re.compile(r"\.createIndex\s*\(", re.I),
        re.compile(r"\bReact\.lazy\s*\("),
        re.compile(r"\bfor\s*\([^)]*\)\s*\{[^}]*\bfor\s*\(", re.S),
    ],
    "api_misuse": [
        re.compile(r"\bres\.status\s*\(\d+\)\.send\s*\("),
        re.compile(r"\bres\.status\s*\(\d+\)\.json\s*\("),
        re.compile(r"\baxios\.(get|post|put|delete|patch)\s*\("),
        re.compile(r"\bfetch\s*\([^)]*\{\s*method"), re.compile(r"\bgraphql`", re.I),
    ],
    "logic_error": [
        re.compile(r"(===?|!==?)\s*(true|false|null|undefined|\d+)"),
        re.compile(r"\bif\s*\([^)]*(&&|\|\|)[^)]*\)"),
    ],
}


_STRONG_FIX_SIGNALS = [
    # Guards, conditionals, and null/undefined checks
    re.compile(r"\bif\s*\(", re.I), re.compile(r"\?\?|\?\.|!==?|===?"),
    re.compile(r"\b(null|undefined)\b", re.I),
    # Async & Error handling
    re.compile(r"\b(async|await|try|catch|throw|finally)\b", re.I),
    # Validation & Sanitization
    re.compile(r"\b(validate|validator|sanitize|schema|parse|check|isvalid)\b", re.I),
    # Boundaries & Slicing
    re.compile(r"\.length\b|\[\s*\w+\s*[-+]\s*1\s*\]|\.slice|\.substring"),
    # Resource cleanup
    re.compile(r"\b(close|destroy|unsubscribe|clearTimeout|clearInterval)\b", re.I),
    # Logic, State, and Control flow
    re.compile(r"\b(return|dispatch|setState|useState|useEffect)\b", re.I),
]


def _score_categories(diff: str, buggy: str, fixed: str, msg: str) -> Dict[str, int]:
    haystack = f"{diff}\n{fixed}\n{msg}"
    scores: Dict[str, int] = {}
    for category, patterns in _CATEGORY_RULES.items():
        score = 0
        for pat in patterns:
            if pat.search(haystack):
                score += 1
            if pat.search(fixed) and not pat.search(buggy):
                score += 2
        if score > 0:
            scores[category] = score
    return scores


def _has_meaningful_code_diff(buggy: str, fixed: str) -> bool:
    """Returns False if buggy and fixed snippets are identical after stripping
    whitespace, newlines, and semicolons."""
    b_norm = re.sub(r"[\s;]", "", buggy)
    f_norm = re.sub(r"[\s;]", "", fixed)
    return b_norm != f_norm


def candidate_categories(diff: str, buggy: str, fixed: str, msg: str) -> Tuple[List[str], int]:
    """Returns (ranked candidate categories to hand Gemini/LLM, top_score_margin).
    Empty list means the regex stage found nothing worth spending an LLM
    call on - this candidate is filtered out entirely to save API quota."""
    # 1. Quick check: snippets must not be identical after whitespace normalization
    if not _has_meaningful_code_diff(buggy, fixed):
        return [], 0

    # 2. Require at least one strong bug-fix signal in the patch, diff, or commit message
    haystack = f"{diff}\n{fixed}\n{msg}"
    if not any(pat.search(haystack) for pat in _STRONG_FIX_SIGNALS):
        return [], 0

    scores = _score_categories(diff, buggy, fixed, msg)
    if not scores:
        return [], 0

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_score = ranked[0][1]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    margin = top_score - runner_up
    return [c for c, _ in ranked[:LLM_JUDGE_MAX_CANDIDATES]], margin


def search_github_repositories(query: str, page: int = 1, max_repos: int = 30) -> List[Dict[str, Any]]:
    time.sleep(2.0)
    url = (
        f"https://api.github.com/search/repositories?q={query}+stars:>=5+language:javascript"
        f"&sort=updated&order=desc&per_page={max_repos}&page={page}"
    )
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            items = res.json().get("items", [])
            valid_repos = []
            for r in items:
                owner = r.get("owner", {}).get("login", "").lower()
                if owner in BLACK_LISTED_ORGS:
                    continue
                valid_repos.append(r)
            return valid_repos
        if res.status_code == 403:
            logger.warning("GitHub API rate limit reached. Waiting 30s...")
            time.sleep(30)
        else:
            logger.warning("GitHub search returned status %s for query %s", res.status_code, query)
    except requests.RequestException as exc:
        logger.error("GitHub search failed for query %s: %s", query, exc)
    return []


def get_repo_fix_commits(repo_full_name: str, max_commits: int = 5) -> List[Dict[str, Any]]:
    time.sleep(0.2)
    url = f"https://api.github.com/repos/{repo_full_name}/commits?per_page=30"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            commits = res.json()
            fix_commits = []
            for c in commits:
                msg = c.get("commit", {}).get("message", "")
                if is_valid_commit_msg(msg):
                    fix_commits.append(c)
                    if len(fix_commits) >= max_commits:
                        break
            return fix_commits
        logger.warning("Failed to list commits for %s: status %s", repo_full_name, res.status_code)
    except requests.RequestException as exc:
        logger.error("Failed to fetch commits for %s: %s", repo_full_name, exc)
    return []


def fetch_commit_patch(repo: str, commit_sha: str) -> Optional[Dict[str, Any]]:
    time.sleep(0.2)
    url = f"https://api.github.com/repos/{repo}/commits/{commit_sha}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            logger.warning("Failed to fetch commit %s/%s: status %s", repo, commit_sha, res.status_code)
            return None
        return res.json()
    except requests.RequestException as exc:
        logger.error("Failed to fetch commit %s/%s: %s", repo, commit_sha, exc)
        return None


def fetch_file_content_at_ref(repo: str, path: str, ref: str) -> Optional[str]:
    """Full file content at a given commit ref, via the contents API. Used
    to get the COMPLETE source (not just the hunk) so the complete enclosing
    function can be extracted."""
    time.sleep(0.2)
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        res = requests.get(url, headers=HEADERS, params={"ref": ref}, timeout=10)
        if res.status_code != 200:
            logger.warning("Failed to fetch file %s@%s in %s: status %s", path, ref, repo, res.status_code)
            return None
        data = res.json()
        if data.get("encoding") != "base64" or "content" not in data:
            return None
        raw = base64.b64decode(data["content"])
        return raw.decode("utf-8", errors="replace")
    except (requests.RequestException, ValueError) as exc:
        logger.error("Failed to fetch/decode file %s@%s in %s: %s", path, ref, repo, exc)
        return None


def extract_symmetrical_hunks(patch_text: str, context_lines: int = CONTEXT_LINES) -> List[Dict[str, Any]]:
    """Same hunk-pair extraction as before, but now also returns each hunk's
    source/target line ranges so the complete enclosing function can be
    located in the full before/after file content."""
    pairs: List[Dict[str, Any]] = []
    try:
        diff_wrapper = "--- a/file\n+++ b/file\n" + patch_text
        patch_set = PatchSet(diff_wrapper)
    except Exception as exc:
        logger.warning("Failed to parse patch with unidiff: %s", exc)
        return pairs

    for patched_file in patch_set:
        for hunk in patched_file:
            hunk_lines = list(hunk)
            buggy_lines: List[str] = []
            fixed_lines: List[str] = []

            leading_context: List[str] = []
            for line in hunk_lines:
                if line.is_context:
                    leading_context.append(line.value.rstrip("\n"))
                else:
                    break
            leading_context = leading_context[-context_lines:]

            trailing_context: List[str] = []
            for line in reversed(hunk_lines):
                if line.is_context:
                    trailing_context.insert(0, line.value.rstrip("\n"))
                else:
                    break
            trailing_context = trailing_context[:context_lines]

            change_started = False
            change_ended = False
            for line in hunk_lines:
                text = line.value.rstrip("\n")
                if line.is_context:
                    if change_started:
                        change_ended = True
                    continue
                change_started = True
                if change_ended:
                    continue
                if line.is_removed:
                    buggy_lines.append(text)
                elif line.is_added:
                    fixed_lines.append(text)

            if not buggy_lines and not fixed_lines:
                continue

            buggy_snippet = "\n".join(leading_context + buggy_lines + trailing_context).strip()
            fixed_snippet = "\n".join(leading_context + fixed_lines + trailing_context).strip()

            if not buggy_snippet or not fixed_snippet or buggy_snippet == fixed_snippet:
                continue

            pairs.append({
                "buggy_snippet": buggy_snippet,
                "fixed_snippet": fixed_snippet,
                "source_start": hunk.source_start,
                "source_length": hunk.source_length,
                "target_start": hunk.target_start,
                "target_length": hunk.target_length,
            })

    return pairs


_BASE_SEVERITY: Dict[str, str] = {
    "security_vulnerability": "high", "resource_leak": "medium", "async_error": "medium",
    "null_pointer": "medium", "exception_handling": "medium", "type_error": "low",
    "logic_error": "medium", "off_by_one": "medium", "input_validation": "medium",
    "state_management": "low", "performance_issue": "low", "api_misuse": "low",
}


def build_records_for_commit(
    repo: str,
    commit_sha: str,
    msg: str,
    commit_data: Dict[str, Any],
    balancer: "CategoryBalancer",
    remaining_target: int,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Returns (validated_records, gemini_calls_made, candidates_seen).
    Stops early once `remaining_target` validated records have been produced
    for this commit's files (the caller still tracks the run-wide total)."""
    records: List[Dict[str, Any]] = []
    gemini_calls = 0
    candidates_seen = 0
    seen_code_pairs: Set[Tuple[str, str]] = set()
    files = commit_data.get("files", [])
    parents = commit_data.get("parents", [])
    parent_sha = parents[0]["sha"] if parents else None

    if parent_sha is None:
        logger.info("Commit %s/%s has no parent (initial commit) - skipping.", repo, commit_sha)
        return records, gemini_calls, candidates_seen

    file_content_cache: Dict[Tuple[str, str], Optional[str]] = {}

    def get_file(path: str, ref: str) -> Optional[str]:
        key = (path, ref)
        if key not in file_content_cache:
            file_content_cache[key] = fetch_file_content_at_ref(repo, path, ref)
        return file_content_cache[key]

    for f in files:
        if len(records) >= remaining_target:
            break
        if balancer.all_categories_full():
            break

        filename = f.get("filename", "")
        ext = Path(filename).suffix.lower()
        if ext not in VALID_FILE_EXTENSIONS:
            continue

        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        changes = additions + deletions
        if not (1 <= changes <= 35):
            continue

        patch = f.get("patch", "")
        if not patch:
            continue

        hunks = extract_symmetrical_hunks(patch)
        if not hunks:
            continue

        buggy_file_src = get_file(filename, parent_sha)
        fixed_file_src = get_file(filename, commit_sha)

        for hunk in hunks:
            if len(records) >= remaining_target or balancer.all_categories_full():
                break

            buggy_snippet = hunk["buggy_snippet"]
            fixed_snippet = hunk["fixed_snippet"]

            logger.info("[Candidate]\nRepository: %s\nCommit: %s\nFile: %s", repo, commit_sha[:12], filename)

            # --- candidate filtering (regex) - cheap, reduces Gemini calls ---
            candidates, margin = candidate_categories(patch, buggy_snippet, fixed_snippet, msg)
            if not candidates:
                continue
            candidates_seen += 1

            # --- complete function extraction ---
            buggy_func = fixed_func = None
            if buggy_file_src is not None:
                src_start = hunk["source_start"] or 1
                src_end = src_start + max(hunk["source_length"] - 1, 0)
                found = extract_enclosing_function(buggy_file_src, src_start, src_end)
                if found:
                    buggy_func = found[0]
            if fixed_file_src is not None:
                tgt_start = hunk["target_start"] or 1
                tgt_end = tgt_start + max(hunk["target_length"] - 1, 0)
                found = extract_enclosing_function(fixed_file_src, tgt_start, tgt_end)
                if found:
                    fixed_func = found[0]

            if not buggy_func or not fixed_func:
                logger.info(
                    "[Function Extraction]\nCould not confidently extract complete enclosing "
                    "function for %s @ %s - marking insufficient_context, not counted toward target.",
                    filename, commit_sha[:12],
                )
                continue  # do not manufacture a function from fragments; don't count toward target

            # --- comment removal (mandatory before sending to Gemini) ---
            buggy_clean = strip_js_comments(buggy_func)
            fixed_clean = strip_js_comments(fixed_func)

            if not _has_meaningful_code_diff(buggy_clean, fixed_clean):
                logger.info("[Extraction]\nBuggy and fixed enclosing functions are identical after comment stripping — skipping.")
                continue

            # --- deduplicate identical function pairs within commit ---
            pair_key = (buggy_clean, fixed_clean)
            if pair_key in seen_code_pairs:
                continue
            seen_code_pairs.add(pair_key)

            # --- AST vectors (structural signal, kept alongside semantics) ---
            try:
                ast_buggy, tier_buggy = extract_ast_vector_with_tier(buggy_clean, filename)
                ast_fixed, tier_fixed = extract_ast_vector_with_tier(fixed_clean, filename)
            except Exception as exc:
                logger.warning("AST extraction failed for %s/%s (%s): %s", repo, commit_sha, filename, exc)
                continue

            if np.all(ast_buggy == 0) or np.all(ast_fixed == 0):
                continue

            ast_tier = tier_buggy if is_reliable_tier(tier_buggy) else tier_fixed
            reliable = is_reliable_tier(tier_buggy) and is_reliable_tier(tier_fixed)
            if not reliable:
                ast_tier = f"unreliable:{tier_buggy}|{tier_fixed}"

            if not USE_LLM_JUDGE or _key_manager is None:
                logger.info("Gemini not configured (no API key) - discarding candidate, cannot semantically validate.")
                continue

            # --- Gemini semantic validation (the ONLY source of the final label) ---
            gemini_calls += 1
            result, key_slot, attempts = _key_manager.classify(
                buggy_code=buggy_clean,
                fixed_code=fixed_clean,
                diff=patch,
                commit_message=msg,
                candidates=candidates,
                max_retries=GEMINI_MAX_RETRIES,
                retry_delay_seconds=GEMINI_RETRY_DELAY_SECONDS,
                all_keys_cooldown_seconds=GEMINI_ALL_KEYS_COOLDOWN_SECONDS,
                request_delay_seconds=GEMINI_REQUEST_DELAY_SECONDS,
            )

            if result is None:
                continue  # all keys exhausted for this candidate; cooldown already applied

            if result.decision != "accept" or result.bug_type is None:
                logger.info("[Gemini]\nRejected (decision=%s) - not counted toward target.", result.decision)
                continue

            if result.confidence < GEMINI_MIN_CONFIDENCE:
                logger.info(
                    "[Gemini]\nConfidence %.2f below threshold %.2f - discarding.",
                    result.confidence, GEMINI_MIN_CONFIDENCE,
                )
                continue

            b_type = result.bug_type
            if b_type not in APPROVED_BUG_TYPES:
                continue
            if balancer.is_category_full(b_type):
                logger.info("[Balancer]\n%s is at cap - rejecting for current dataset target.", b_type)
                continue

            lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"
            severity = result.severity or _BASE_SEVERITY.get(b_type, "medium")
            bug_pattern = (result.evidence[0] if result.evidence else b_type.replace("_", " ").title())[:120]

            record = {
                "repository": repo,
                "commit_hash": commit_sha,
                "file_path": filename,
                "language": lang,
                "bug_type": b_type,
                "original_commit_message": msg.strip().replace("\n", " ")[:300],
                "buggy_code": buggy_clean,
                "fixed_code": fixed_clean,
                "buggy_ast_vector": json.dumps([round(float(x), 8) for x in ast_buggy]),
                "fixed_ast_vector": json.dumps([round(float(x), 8) for x in ast_fixed]),
                "ast_tier": ast_tier,
                "bug_description": result.bug_description,
                "root_cause": result.root_cause,
                "fix_description": result.fix_description,
                "severity": severity,
                "bug_pattern": bug_pattern,
                "affected_component": "backend" if ("server" in filename or "api" in filename) else "frontend",
                "confidence_score": round(result.confidence, 2),
                "match_margin": margin,
                "label_source": "gemini_semantic",
                "gemini_model": result.model,
                "gemini_confidence": round(result.confidence, 2),
                "gemini_reason": "; ".join(result.evidence)[:500] if result.evidence else "",
                "gemini_validation_status": "validated",
                "gemini_api_key_slot": key_slot or "",
                "gemini_attempts": attempts,
            }
            records.append(record)

    return records, gemini_calls, candidates_seen


class DatasetWriter:
    def __init__(self, path: Path, fieldnames: List[str]):
        self.path = path
        self.fieldnames = fieldnames
        file_exists = path.exists() and path.stat().st_size > 0
        self._fh = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        if not file_exists:
            self._writer.writeheader()
            self._fh.flush()

    def write(self, record: Dict[str, Any]) -> None:
        self._writer.writerow(record)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


_CATEGORY_TOPIC_HINTS: Dict[str, List[str]] = {
    "exception_handling": [
        "topic:error-handling", "topic:try-catch", "topic:sentry",
        "topic:winston", "topic:logging", "topic:exception-handling", "topic:bunyan", "topic:pino",
    ],
    "off_by_one": [
        "topic:pagination", "topic:array", "topic:infinite-scroll",
        "topic:slicing", "topic:pagination-component", "topic:table",
        "topic:datatable", "topic:carousel", "topic:virtual-list",
    ],
    "state_management": [
        "topic:redux", "topic:react-hooks", "topic:context-api",
        "topic:zustand", "topic:mobx", "topic:recoil", "topic:state-management",
        "topic:jotai", "topic:valtio", "topic:pinia",
    ],
    "api_misuse": [
        "topic:rest-api", "topic:api", "topic:axios", "topic:fetch-api",
        "topic:graphql", "topic:api-client", "topic:trpc", "topic:supertest", "topic:swr", "topic:react-query",
    ],
    "input_validation": [
        "topic:express-validator", "topic:joi", "topic:zod", "topic:yup",
        "topic:form-validation", "topic:form", "topic:react-hook-form", "topic:formik", "topic:valibot",
    ],
    "performance_issue": [
        "topic:performance", "topic:optimization", "topic:memoization",
        "topic:lazy-loading", "topic:caching", "topic:debounce", "topic:throttle", "topic:virtualization",
    ],
    "resource_leak": [
        "topic:websocket", "topic:socket-io", "topic:database",
        "topic:redis", "topic:connection-pool", "topic:event-emitter",
        "topic:mongoose", "topic:knex", "topic:typeorm", "topic:prisma", "topic:pg", "topic:mysql",
    ],
    "type_error": [
        "topic:typescript", "topic:type-checking", "topic:types", "topic:type-definitions",
    ],
    "security_vulnerability": [
        "topic:security", "topic:authentication", "topic:jwt", "topic:oauth",
        "topic:passport", "topic:authorization", "topic:cors", "topic:helmet", "topic:xss", "topic:sanitization",
    ],
    "async_error": [
        "topic:async", "topic:promises", "topic:async-await", "topic:rxjs", "topic:concurrency",
    ],
}

_GENERIC_TOPICS = [
    "topic:mern", "topic:express", "topic:react", "topic:nodejs", "topic:mongodb",
    "topic:nextjs", "topic:typescript", "topic:nest", "topic:fastify", "topic:gatsby",
    "topic:remix", "topic:koa", "topic:vue", "topic:nuxt", "topic:svelte", "topic:fullstack",
]


def build_search_queries(balancer: CategoryBalancer) -> List[str]:
    queries: List[str] = []
    seen: Set[str] = set()
    for category in balancer.categories_by_need():
        if balancer.is_category_full(category):
            continue
        for topic in _CATEGORY_TOPIC_HINTS.get(category, []):
            if topic not in seen:
                seen.add(topic)
                queries.append(topic)
    for topic in _GENERIC_TOPICS:
        if topic not in seen:
            seen.add(topic)
            queries.append(topic)
    return queries


def run_miner(
    cap_per_category: int = 100,
    max_per_repo: int = 2,
    pages_per_topic: int = 2,
    dataset_path: Optional[Path] = None,
    target_validated_samples: Optional[int] = None,
) -> None:
    if dataset_path is None:
        dataset_path = DATASET_PATH
    target = target_validated_samples if target_validated_samples is not None else TARGET_VALIDATED_SAMPLES

    logger.info("=" * 60)
    logger.info("STARTING CLASS-BALANCED MERN BUG MINER (v3 - Gemini semantic validation)")
    logger.info("Cap per category: %s | Max per repo: %s | Target file: %s", cap_per_category, max_per_repo, dataset_path.name)
    logger.info("Frozen (majority) categories: %s", sorted(FROZEN_CATEGORIES))
    logger.info("Target validated samples this run: %s", target)
    if USE_LLM_JUDGE:
        logger.info("Gemini semantic validation ENABLED (model: %s, %d key(s) loaded)", GEMINI_MODEL, len(GEMINI_API_KEYS))
        logger.info("Min confidence: %s | Request delay: %ss | Max retries: %s | Retry delay: %ss | All-keys cooldown: %ss",
                     GEMINI_MIN_CONFIDENCE, GEMINI_REQUEST_DELAY_SECONDS, GEMINI_MAX_RETRIES,
                     GEMINI_RETRY_DELAY_SECONDS, GEMINI_ALL_KEYS_COOLDOWN_SECONDS)
    else:
        logger.info("Gemini semantic validation DISABLED (no GEMINI_API_KEY_1.. or GEMINI_API_KEY set) - "
                     "no records can be validated; nothing will be written.")
    logger.info("=" * 60)

    balancer = CategoryBalancer(cap_per_category, dataset_path)
    writer = DatasetWriter(dataset_path, CSV_FIELDNAMES)

    logger.info("Existing category distribution: %s", balancer.counts)

    total_validated = 0
    total_candidates_seen = 0
    total_gemini_calls = 0
    unique_repos_mined: Set[str] = set()

    try:
        search_topics = build_search_queries(balancer)

        for topic in search_topics:
            if balancer.all_categories_full() or total_validated >= target:
                logger.info("Stopping: %s", "all categories full" if balancer.all_categories_full() else "target reached")
                break

            logger.info("Searching topic: %s | remaining need: %s | validated so far: %s/%s",
                        topic, {bt: balancer.remaining_for(bt) for bt in balancer.remaining_categories()},
                        total_validated, target)
            sys.stdout.flush()

            for page in range(1, pages_per_topic + 1):
                if balancer.all_categories_full() or total_validated >= target:
                    break

                repos = search_github_repositories(topic, page=page, max_repos=20)

                for idx, r in enumerate(repos, 1):
                    if balancer.all_categories_full() or total_validated >= target:
                        break

                    repo_name = r.get("full_name", "")
                    if not repo_name:
                        continue
                    if balancer.repo_counts.get(repo_name, 0) >= max_per_repo:
                        continue

                    logger.info("  [%d/%d] Scanning repo: %s ...", idx, len(repos), repo_name)
                    sys.stdout.flush()

                    commits = get_repo_fix_commits(repo_name, max_commits=5)

                    for c in commits:
                        if balancer.repo_counts.get(repo_name, 0) >= max_per_repo:
                            break
                        if balancer.all_categories_full() or total_validated >= target:
                            break

                        sha = c.get("sha", "")
                        if not sha or sha in balancer.existing_commits:
                            continue

                        msg = c.get("commit", {}).get("message", "")
                        commit_data = fetch_commit_patch(repo_name, sha)
                        if commit_data is None:
                            continue

                        remaining = target - total_validated
                        records, gemini_calls, candidates_seen = build_records_for_commit(
                            repo_name, sha, msg, commit_data, balancer, remaining,
                        )
                        total_gemini_calls += gemini_calls
                        total_candidates_seen += candidates_seen

                        balancer.existing_commits.add(sha)
                        if not records:
                            continue

                        for record in records:
                            bug_type = record["bug_type"]
                            if balancer.is_category_full(bug_type):
                                continue
                            if balancer.repo_counts.get(repo_name, 0) >= max_per_repo:
                                break
                            if total_validated >= target:
                                break

                            writer.write(record)
                            balancer.register(bug_type, repo_name)
                            total_validated += 1
                            unique_repos_mined.add(repo_name)

                            logger.info(
                                "[Dataset]\nValidated sample saved.\nRepo: %s | Type: %s | Gemini conf: %s | "
                                "Key: %s | Progress: %s/%s | Class total: %s/%s",
                                repo_name, bug_type, record["gemini_confidence"], record["gemini_api_key_slot"],
                                total_validated, target, balancer.counts[bug_type], balancer.cap_for(bug_type),
                            )

    except KeyboardInterrupt:
        logger.info("Mining interrupted by user.")
    finally:
        writer.close()
        logger.info("=" * 60)
        logger.info("MINING SESSION SUMMARY")
        logger.info("Validated records added: %s / target %s", total_validated, target)
        logger.info("Candidates handed to Gemini: %s | Gemini calls made: %s", total_candidates_seen, total_gemini_calls)
        logger.info("Unique repos processed: %s", len(unique_repos_mined))
        logger.info("Final Category Distribution: %s", balancer.counts)
        logger.info("=" * 60)


if __name__ == "__main__":
    run_miner(
        cap_per_category=150,    # fallback only; CATEGORY_CAPS takes priority
        max_per_repo=4,
        pages_per_topic=10,
    )
