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

# Ensure field size limits don't break large diff parsing
csv.field_size_limit(sys.maxsize)

from ast_vectorizer import extract_ast_vector

WORKDIR = Path(__file__).resolve().parent
ENV_PATH = WORKDIR / ".env"
DATASET_PATH = WORKDIR / "dataset_enriched.csv"

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

BLACK_LISTED_ORGS: Set[str] = {
    "facebook", "google", "microsoft", "nestjs", "expressjs", "vercel",
    "reduxjs", "nodejs", "vuejs", "angular", "mongodb", "prisma",
    "sequelize", "typeorm", "axios", "fastify", "koa", "strapi", "helmet",
    "twitter", "netflix", "airbnb", "uber", "aws", "gcp",
}

APPROVED_BUG_TYPES: List[str] = [
    "async_error", "null_pointer", "logic_error", "type_error", "api_misuse",
    "security_vulnerability", "off_by_one", "exception_handling", "resource_leak",
    "performance_issue", "input_validation", "state_management",
]

CATEGORY_CAPS: Dict[str, int] = {
    # Targets set to collect ~1,000 new records on top of the existing 1,985.
    # Allocation is weighted by real-world bug frequency:
    #   high-frequency types get +80–100, mid-tier +40–70, rare types +20–40.
    "logic_error":              310,   # +100  most common real-world bug
    "null_pointer":             226,   # +100  very common in JS/TS
    "async_error":              227,   # +90   widespread in Node/React
    "type_error":               197,   # +90   common in TS migrations
    "security_vulnerability":   192,   # +80   high value for dataset quality
    "exception_handling":       254,   # +70
    "state_management":         299,   # +60
    "input_validation":         278,   # +60
    "off_by_one":               263,   # +50
    "api_misuse":               241,   # +40
    "performance_issue":        176,   # +40
    "resource_leak":            122,   # +20   hardest to find in the wild
}

# FROZEN_CATEGORIES: Set[str] = {
#     "null_pointer", "security_vulnerability", "async_error", "type_error", "logic_error",
# }
# NEW
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

CSV_FIELDNAMES = [
    "repository", "commit_hash", "file_path", "language", "bug_type",
    "original_commit_message", "buggy_code", "fixed_code",
    "buggy_ast_vector", "fixed_ast_vector", "bug_description", "root_cause",
    "fix_description", "severity", "bug_pattern", "affected_component",
    "confidence_score",
]

CONTEXT_LINES = 4


class CategoryBalancer:
    def __init__(self, cap_per_category: int, dataset_path: Path):
        self.cap_per_category = cap_per_category
        self.counts: Dict[str, int] = {bt: 0 for bt in APPROVED_BUG_TYPES}
        self.existing_commits: Set[str] = set()
        self.repo_counts: Dict[str, int] = {}
        self._load_existing(dataset_path)

    def _load_existing(self, dataset_path: Path) -> None:
        if not dataset_path.exists():
            return
        try:
            with open(dataset_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bug_type = row.get("bug_type", "")
                    if bug_type in self.counts:
                        self.counts[bug_type] += 1
                    repo = row.get("repository", "")
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
        return sorted(
            APPROVED_BUG_TYPES,
            key=lambda bt: self.remaining_for(bt),
            reverse=True,
        )


def is_valid_commit_msg(msg: str) -> bool:
    msg_lower = msg.lower()
    if any(re.search(pat, msg_lower) for pat in COMMIT_EXCLUDE_KEYWORDS):
        return False
    return any(re.search(pat, msg_lower) for pat in COMMIT_INCLUDE_KEYWORDS)


_CATEGORY_RULES: Dict[str, List[re.Pattern]] = {
    "async_error": [
        re.compile(r"\bawait\b"),
        re.compile(r"\.then\s*\("),
        re.compile(r"\bpromise\b", re.I),
        re.compile(r"\basync\s+function\b"),
    ],
    "exception_handling": [
        re.compile(r"\btry\s*\{"),
        re.compile(r"\bcatch\s*\("),
        re.compile(r"\bthrow\b"),
        re.compile(r"\bfinally\s*\{"),
    ],
    "null_pointer": [
        re.compile(r"\?\."),
        re.compile(r"!=\s*null"),
        re.compile(r"!==\s*null"),
        re.compile(r"!=\s*undefined"),
        re.compile(r"!==\s*undefined"),
        re.compile(r"\?\?"),
        re.compile(r"if\s*\(![a-zA-Z0-9_$.]+\)"),
    ],
    "state_management": [
        re.compile(r"\buseeffect\b", re.I),
        re.compile(r"\busestate\b", re.I),
        re.compile(r"\busememo\b", re.I),
        re.compile(r"\busecallback\b", re.I),
        re.compile(r"\bdispatch\b", re.I),
        re.compile(r"\bsetstate\b", re.I),
        re.compile(r"\breducer\b", re.I),
        re.compile(r"\bzustand\b", re.I),
        re.compile(r"\bmobx\b", re.I),
        re.compile(r"\brecoil\b", re.I),
    ],
    "security_vulnerability": [
        re.compile(r"\bsanitize\b", re.I),
        re.compile(r"\bescape\b", re.I),
        re.compile(r"\bhelmet\b", re.I),
        re.compile(r"\bcors\b", re.I),
        re.compile(r"\bjwt\b", re.I),
        re.compile(r"\bbcrypt\b", re.I),
        re.compile(r"\bauth\b", re.I),
        re.compile(r"\bhash\b", re.I),
        re.compile(r"\bxss\b", re.I),
        re.compile(r"\bsql\s*inject", re.I),
    ],
    "input_validation": [
        re.compile(r"\bvalidator\b", re.I),
        re.compile(r"\bisvalid\b", re.I),
        re.compile(r"\btypeof\b"),
        re.compile(r"\breq\.body\b"),
        re.compile(r"\breq\.params\b"),
        re.compile(r"\breq\.query\b"),
        re.compile(r"\bjoi\.\w+"),
        re.compile(r"\btrim\s*\("),
        re.compile(r"\bschema\b", re.I),
        re.compile(r"\bzod\b", re.I),
        re.compile(r"\byup\.\w+"),
        re.compile(r"\bz\.\w+\("),
    ],
    "type_error": [
        re.compile(r"\bobjectid\b", re.I),
        re.compile(r"\bparseint\b"),
        re.compile(r"\bparsefloat\b"),
        re.compile(r"\bas\s+[A-Z][a-zA-Z0-9_]*"),
        re.compile(r":\s*(string|number|boolean)\b"),
        re.compile(r"\btoString\s*\("),
        re.compile(r"\bNumber\s*\("),
        re.compile(r"\bString\s*\("),
    ],
    "resource_leak": [
        re.compile(r"\bclose\s*\("),
        re.compile(r"\bdestroy\s*\("),
        re.compile(r"\bdisconnect\s*\("),
        re.compile(r"\bunsubscribe\s*\("),
        re.compile(r"\bclearinterval\s*\(", re.I),
        re.compile(r"\bcleartimeout\s*\(", re.I),
        re.compile(r"\bremoveeventlistener\b", re.I),
        re.compile(r"\bfinally\s*\{.*(close|destroy|disconnect)", re.I | re.S),
        re.compile(r"\bredis\b", re.I),
        re.compile(r"\bconnection\s*pool\b", re.I),
        re.compile(r"\bsocket\.io\b", re.I),
        re.compile(r"\bws\.close\b", re.I),
    ],
    "off_by_one": [
        re.compile(r"[<>]=?\s*\w+\.length"),
        re.compile(r"\bfor\s*\([^)]*[<>]=?"),
        re.compile(r"\+\+|--"),
        re.compile(r"\bslice\s*\("),
        re.compile(r"\bsubstring\s*\("),
        re.compile(r"\[\s*i\s*[-+]\s*1\s*\]"),
        re.compile(r"\bpage\s*\*\s*limit\b", re.I),
        re.compile(r"\boffset\b", re.I),
    ],
    "performance_issue": [
        re.compile(r"\busememo\b", re.I),
        re.compile(r"\busecallback\b", re.I),
        re.compile(r"\bmemo\s*\("),
        re.compile(r"\bdebounce\b", re.I),
        re.compile(r"\bthrottle\b", re.I),
        re.compile(r"\bcache\b", re.I),
        re.compile(r"\bindex(ed)?\b.*\bmongo|\.index\s*\(", re.I),
        re.compile(r"\bO\(n", re.I),
        re.compile(r"\blazy\b", re.I),
        re.compile(r"\bReact\.lazy\b"),
    ],
    "api_misuse": [
        re.compile(r"\boptions\b", re.I),
        re.compile(r"\bconfig\b", re.I),
        re.compile(r"\bheaders\b", re.I),
        re.compile(r"\bmethod:\s*['\"]"),
        re.compile(r"\bres\.status\s*\("),
        re.compile(r"\bres\.send\s*\("),
        re.compile(r"\bres\.json\s*\("),
        re.compile(r"\baxios\.\w+\("),
        re.compile(r"\bgraphql\b", re.I),
    ],
    "logic_error": [
        re.compile(r"&&|\|\|"),
        re.compile(r"===?|!==?"),
        re.compile(r"\bif\s*\("),
        re.compile(r"\belse\b"),
    ],
}

_CATEGORY_META: Dict[str, Tuple[str, str, str, str]] = {
    "async_error": (
        "Missing or incorrect handling of an asynchronous operation.",
        "Asynchronous function executed without properly waiting for promise resolution.",
        "Added/corrected await or promise-chain handling.",
        "Async Handling Error",
    ),
    "exception_handling": (
        "Missing or incomplete error handling around a risky operation.",
        "Unhandled runtime exception during execution.",
        "Wrapped risky operation in try/catch or added throw/finally handling.",
        "Missing Exception Guard",
    ),
    "null_pointer": (
        "Missing null/undefined check before property access.",
        "Dereferencing potentially null or undefined value.",
        "Added null guard check / optional chaining / nullish coalescing.",
        "Missing Null Check",
    ),
    "state_management": (
        "Incorrect React state update or hook dependency.",
        "Stale state closure or improper state mutation.",
        "Updated React state setter / hook dependencies.",
        "React State Error",
    ),
    "security_vulnerability": (
        "Security vulnerability in request handling or auth.",
        "Potential unauthorized access or injection vulnerability.",
        "Applied sanitization, CORS, or authorization check.",
        "Security Vulnerability",
    ),
    "input_validation": (
        "Missing input validation on payload or parameters.",
        "Invalid or un-sanitized user input processed by system.",
        "Added input boundary/schema check.",
        "Missing Input Validation",
    ),
    "type_error": (
        "Mismatched type or unsafe type conversion.",
        "Type mismatch or implicit coercion failure.",
        "Added explicit type check or type conversion.",
        "Unsafe Type Conversion",
    ),
    "resource_leak": (
        "Unclosed resource connection or event listener.",
        "Resource leak due to unreleased socket/timer/connection.",
        "Properly closed resource connection / cleared timer.",
        "Resource Leak",
    ),
    "off_by_one": (
        "Off-by-one boundary comparison error.",
        "Incorrect loop bound or index comparison.",
        "Adjusted boundary index comparison operator.",
        "Off By One Error",
    ),
    "performance_issue": (
        "Sub-optimal computation or un-memoized re-render.",
        "Performance degradation during heavy calculation.",
        "Applied memoization / optimization.",
        "Performance Bottleneck",
    ),
    "api_misuse": (
        "Incorrect API method signature or invalid parameters.",
        "Misused library method arguments or options.",
        "Corrected method invocation argument signature.",
        "API Misuse",
    ),
    "logic_error": (
        "Flawed condition or business logic calculation.",
        "Incorrect algorithm logic flow.",
        "Updated logical conditional expressions.",
        "Logic Error",
    ),
}


def classify_bug_heuristically(
    diff: str,
    buggy: str,
    fixed: str,
    msg: str,
    balancer: Optional[CategoryBalancer] = None,
) -> Tuple[str, str, str, str, str]:
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

    if not scores:
        best_category = "logic_error"
    else:
        top_score = max(scores.values())
        tied = [c for c, s in scores.items() if s == top_score]
        if len(tied) == 1 or balancer is None:
            best_category = tied[0]
        else:
            best_category = max(tied, key=lambda c: balancer.remaining_for(c))

    b_desc, r_cause, f_desc, b_pattern = _CATEGORY_META[best_category]
    return best_category, b_desc, r_cause, f_desc, b_pattern


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


def extract_symmetrical_hunks(patch_text: str, context_lines: int = CONTEXT_LINES) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
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

            pairs.append((buggy_snippet, fixed_snippet))

    return pairs


def build_records_for_commit(
    repo: str,
    commit_sha: str,
    msg: str,
    commit_data: Dict[str, Any],
    balancer: CategoryBalancer,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    files = commit_data.get("files", [])

    for f in files:
        if balancer.all_categories_full():
            break

        filename = f.get("filename", "")
        ext = Path(filename).suffix.lower()
        if ext not in VALID_FILE_EXTENSIONS:
            continue

        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        changes = additions + deletions
        if not (1 <= changes <= 25):
            continue

        patch = f.get("patch", "")
        if not patch:
            continue

        hunk_pairs = extract_symmetrical_hunks(patch)
        if not hunk_pairs:
            continue

        for buggy_code, fixed_code in hunk_pairs:
            try:
                ast_buggy = extract_ast_vector(buggy_code, filename)
                ast_fixed = extract_ast_vector(fixed_code, filename)
            except Exception as exc:
                logger.warning("AST extraction failed for %s/%s (%s): %s", repo, commit_sha, filename, exc)
                continue

            if np.all(ast_buggy == 0) or np.all(ast_fixed == 0):
                continue

            b_type, b_desc, r_cause, f_desc, b_pattern = classify_bug_heuristically(
                patch, buggy_code, fixed_code, msg, balancer=balancer
            )

            if b_type not in APPROVED_BUG_TYPES:
                continue

            if balancer.is_category_full(b_type):
                continue

            lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"

            record = {
                "repository": repo,
                "commit_hash": commit_sha,
                "file_path": filename,
                "language": lang,
                "bug_type": b_type,
                "original_commit_message": msg.strip().replace("\n", " ")[:300],
                "buggy_code": buggy_code,
                "fixed_code": fixed_code,
                "buggy_ast_vector": json.dumps([round(float(x), 8) for x in ast_buggy]),
                "fixed_ast_vector": json.dumps([round(float(x), 8) for x in ast_fixed]),
                "bug_description": b_desc,
                "root_cause": r_cause,
                "fix_description": f_desc,
                "severity": "medium",
                "bug_pattern": b_pattern,
                "affected_component": "backend" if ("server" in filename or "api" in filename) else "frontend",
                "confidence_score": 0.88,
            }
            records.append(record)

    return records


class DatasetWriter:
    def __init__(self, path: Path, fieldnames: List[str]):
        self.path = path
        self.fieldnames = fieldnames
        file_exists = path.exists() and path.stat().st_size > 0
        self._fh = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._fh,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
        )
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
        "topic:winston", "topic:logging", "topic:exception-handling",
    ],
    "off_by_one": [
        "topic:pagination", "topic:array", "topic:infinite-scroll",
        "topic:slicing", "topic:pagination-component",
    ],
    "state_management": [
        "topic:redux", "topic:react-hooks", "topic:context-api",
        "topic:zustand", "topic:mobx", "topic:recoil", "topic:state-management",
    ],
    "api_misuse": [
        "topic:rest-api", "topic:api", "topic:axios", "topic:fetch-api",
        "topic:graphql", "topic:api-client",
    ],
    "input_validation": [
        "topic:express-validator", "topic:joi", "topic:zod", "topic:yup",
        "topic:form-validation", "topic:form",
    ],
    "performance_issue": [
        "topic:performance", "topic:optimization", "topic:memoization",
        "topic:lazy-loading", "topic:caching",
    ],
    "resource_leak": [
        "topic:websocket", "topic:socket-io", "topic:database",
        "topic:redis", "topic:connection-pool", "topic:event-emitter",
        "topic:mongoose",
    ],
    "type_error": ["topic:typescript"],
    "security_vulnerability": ["topic:security", "topic:authentication"],
}

_GENERIC_TOPICS = [
    "topic:mern", "topic:express", "topic:react", "topic:nodejs", "topic:mongodb",
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
) -> None:
    if dataset_path is None:
        dataset_path = DATASET_PATH

    logger.info("=" * 60)
    logger.info("STARTING CLASS-BALANCED MERN BUG MINER")
    logger.info("Cap per category: %s | Max per repo: %s | Target: %s", cap_per_category, max_per_repo, dataset_path.name)
    logger.info("Frozen (majority) categories: %s", sorted(FROZEN_CATEGORIES))
    logger.info("=" * 60)

    balancer = CategoryBalancer(cap_per_category, dataset_path)
    writer = DatasetWriter(dataset_path, CSV_FIELDNAMES)

    logger.info("Existing category distribution: %s", balancer.counts)

    total_written = 0
    unique_repos_mined: Set[str] = set()

    try:
        search_topics = build_search_queries(balancer)

        for topic in search_topics:
            if balancer.all_categories_full():
                logger.info("All categories reached cap. Stopping.")
                break

            logger.info("Searching topic: %s | remaining need: %s", topic, {
                bt: balancer.remaining_for(bt) for bt in balancer.remaining_categories()
            })
            sys.stdout.flush()

            for page in range(1, pages_per_topic + 1):
                if balancer.all_categories_full():
                    break

                repos = search_github_repositories(topic, page=page, max_repos=20)

                for idx, r in enumerate(repos, 1):
                    if balancer.all_categories_full():
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
                        if balancer.all_categories_full():
                            break

                        sha = c.get("sha", "")
                        if not sha or sha in balancer.existing_commits:
                            continue

                        msg = c.get("commit", {}).get("message", "")
                        commit_data = fetch_commit_patch(repo_name, sha)
                        if commit_data is None:
                            continue

                        records = build_records_for_commit(repo_name, sha, msg, commit_data, balancer)
                        if not records:
                            continue

                        balancer.existing_commits.add(sha)

                        for record in records:
                            bug_type = record["bug_type"]
                            if balancer.is_category_full(bug_type):
                                continue
                            if balancer.repo_counts.get(repo_name, 0) >= max_per_repo:
                                break

                            writer.write(record)
                            balancer.register(bug_type, repo_name)
                            total_written += 1
                            unique_repos_mined.add(repo_name)

                            logger.info(
                                "[+1 Record] Repo: %s | Type: %s | Total in class: %s/%s",
                                repo_name,
                                bug_type,
                                balancer.counts[bug_type],
                                balancer.cap_for(bug_type),
                            )

    except KeyboardInterrupt:
        logger.info("Mining interrupted by user.")
    finally:
        writer.close()
        logger.info("=" * 60)
        logger.info("MINING SESSION SUMMARY")
        logger.info("New records added: %s", total_written)
        logger.info("Unique repos processed: %s", len(unique_repos_mined))
        logger.info("Final Category Distribution: %s", balancer.counts)
        logger.info("=" * 60)


if __name__ == "__main__":
    run_miner(
        cap_per_category=150,
        max_per_repo=2,
        pages_per_topic=3,
    )