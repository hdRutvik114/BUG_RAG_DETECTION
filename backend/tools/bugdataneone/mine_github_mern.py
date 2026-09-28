import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from ast_vectorizer import extract_ast_vector

WORKDIR = Path(__file__).resolve().parent
ENV_PATH = WORKDIR / ".env"
DATASET_PATH = WORKDIR / "dataset_enriched.csv"
if not DATASET_PATH.exists():
    DATASET_PATH = WORKDIR / "dataset.csv"

load_dotenv(ENV_PATH)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# Blacklisted framework, library, and enterprise organization usernames
BLACK_LISTED_ORGS: Set[str] = {
    "facebook", "google", "microsoft", "nestjs", "expressjs", "vercel",
    "reduxjs", "nodejs", "vuejs", "angular", "mongodb", "prisma",
    "sequelize", "typeorm", "axios", "fastify", "koa", "strapi", "helmet",
    "twitter", "netflix", "airbnb", "uber", "aws", "gcp"
}

APPROVED_BUG_TYPES = [
    "async_error", "null_pointer", "logic_error", "type_error", "api_misuse",
    "security_vulnerability", "off_by_one", "exception_handling", "resource_leak",
    "performance_issue", "input_validation", "state_management"
]

COMMIT_INCLUDE_KEYWORDS = [
    r"\bfix(es|ed)?\b", r"\bbug(fix)?\b", r"\bpatch\b", r"\bhotfix\b", r"\bresolve(d)?\b",
    r"\bissue\b", r"\berror\b", r"\bcrash\b", r"\bexception\b", r"\bvalidation\b",
    r"\bsanitize\b", r"\bsecurity\b", r"\bprevent\b", r"\bhandle\b", r"\bmissing\b",
    r"\bundefined\b", r"\bnull\b", r"\bpromise\b", r"\bawait\b", r"\bleak\b",
    r"\bbounds\b", r"\brace\b", r"\basync\b"
]

COMMIT_EXCLUDE_KEYWORDS = [
    r"\bdocs?\b", r"\breadme\b", r"\blicense\b", r"\bformat\b", r"\bprettier\b",
    r"\beslint\b", r"\blint\b", r"\bstyle\b", r"\brefactor\b", r"\brename\b",
    r"\bmerge\b", r"\brelease\b", r"\bversion\b", r"\bdependency\b", r"\bpackage\b",
    r"\bnpm\b", r"\byarn\b", r"\bpnpm\b", r"\blockfile\b", r"\bci\b", r"\bworkflow\b"
]

VALID_FILE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


def is_valid_commit_msg(msg: str) -> bool:
    msg_lower = msg.lower()
    if any(re.search(pat, msg_lower) for pat in COMMIT_EXCLUDE_KEYWORDS):
        return False
    return any(re.search(pat, msg_lower) for pat in COMMIT_INCLUDE_KEYWORDS)


def classify_bug_heuristically(diff: str, buggy: str, fixed: str, msg: str) -> Tuple[str, str, str, str, str]:
    """Classifies bug into one of 12 categories based on code diff analysis."""
    diff_lower = diff.lower()
    msg_lower = msg.lower()

    if "await" in fixed and "await" not in buggy:
        return "async_error", "Missing await on asynchronous promise call.", "Asynchronous function executed synchronously without waiting for promise resolution.", "Added await keyword before asynchronous call.", "Missing Await"

    if re.search(r"\b(try\s*\{|catch\s*\()", fixed) and not re.search(r"\b(try\s*\{|catch\s*\()", buggy):
        return "exception_handling", "Missing try/catch block for error handling.", "Unhandled runtime exception during execution.", "Wrapped risky operation in try/catch block.", "Missing Exception Guard"

    if re.search(r"(\?\.|!=\s*null|!==\s*null|!=\s*undefined|!==\s*undefined|\bif\s*\(![a-zA-Z0-9_$]+\))", fixed):
        return "null_pointer", "Missing null/undefined check before property access.", "Dereferencing potentially null or undefined object.", "Added null guard check / optional chaining.", "Missing Null Check"

    if re.search(r"(useeffect|usestate|usememo|usecallback|dispatch|setstate)", diff_lower):
        return "state_management", "Incorrect React state update or hook dependency.", "Stale state closure or improper state mutation.", "Updated React state setter / hook dependencies.", "React State Error"

    if re.search(r"(\bsanitize\b|\bescape\b|\bhelmet\b|\bcors\b|\bjwt\b|\bbcrypt\b|\bauth\b|\bhash\b)", diff_lower) or "security" in msg_lower:
        return "security_vulnerability", "Security vulnerability in request handling or auth.", "Potential unauthorized access or injection vulnerability.", "Applied sanitization, CORS, or authorization check.", "Security Vulnerability"

    if re.search(r"(\bvalidator\b|\bcheck\b|\bisvalid\b|\btypeof\b|\breq\.body\b|\breq\.params\b)", diff_lower) and "if" in fixed:
        return "input_validation", "Missing input validation on payload or parameters.", "Invalid or un-sanitized user input processed by system.", "Added input boundary check.", "Missing Input Validation"

    if re.search(r"(\bobjectid\b|\bparseint\b|\bparsefloat\b|\bstring\b|\bnumber\b|\bboolean\b|\bas\s+[a-zA-Z])", diff_lower):
        return "type_error", "Mismatched type or unsafe type conversion.", "Type mismatch or implicit coercion failure.", "Added explicit type check or type conversion.", "Unsafe Type Conversion"

    if re.search(r"(\bclose\b|\bdestroy\b|\bdisconnect\b|\bunsubscribe\b|\bclearinterval\b|\bcleartimeout\b)", fixed.lower()):
        return "resource_leak", "Unclosed resource connection or event listener.", "Resource leak due to unreleased socket/timer/connection.", "Properly closed resource connection / cleared timer.", "Resource Leak"

    if re.search(r"(<=|<|>=|>|\+\+|--|\.length)", diff_lower) and re.search(r"(\bfor\b|\bwhile\b|index|i\b)", diff_lower):
        return "off_by_one", "Off-by-one boundary comparison error.", "Incorrect loop bound comparison.", "Adjusted boundary index comparison operator.", "Off By One Error"

    if re.search(r"(usememo|usecallback|memo|debounce|throttle|cache|batch)", fixed.lower()):
        return "performance_issue", "Sub-optimal computation or un-memoized re-render.", "Performance degradation during heavy calculation.", "Applied memoization / optimization.", "Performance Bottleneck"

    if "options" in diff_lower or "config" in diff_lower or "params" in diff_lower or "headers" in diff_lower:
        return "api_misuse", "Incorrect API method signature or invalid parameters.", "Misused library method arguments or options.", "Corrected method invocation argument signature.", "API Misuse"

    return "logic_error", "Flawed condition or business logic calculation.", "Incorrect algorithm logic flow.", "Updated logical conditional expressions.", "Logic Error"


def search_github_repositories(query: str, page: int = 1, max_repos: int = 30) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/search/repositories?q={query}+stars:>=5+language:javascript&sort=updated&order=desc&per_page={max_repos}&page={page}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            items = res.json().get("items", [])
            valid_repos = []
            for r in items:
                owner = r.get("owner", {}).get("login", "").lower()
                repo_type = r.get("owner", {}).get("type", "")
                if owner in BLACK_LISTED_ORGS or repo_type == "Organization":
                    continue
                valid_repos.append(r)
            return valid_repos
        elif res.status_code == 403:
            print("[WARN] GitHub API rate limit reached. Waiting 30s...")
            time.sleep(30)
    except Exception as e:
        print(f"[ERROR] GitHub search failed: {e}")
    return []


def get_repo_fix_commits(repo_full_name: str, max_commits: int = 5) -> List[Dict[str, Any]]:
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
    except Exception as e:
        pass
    return []


def process_commit_diff(repo: str, commit_sha: str, msg: str) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/commits/{commit_sha}"
    extracted_records = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return []
        
        data = res.json()
        files = data.get("files", [])
        
        for f in files:
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

            raw_url = f.get("raw_url", "")
            if not raw_url:
                continue

            # Fetch fixed code content
            resp_fixed = requests.get(raw_url, headers=HEADERS, timeout=10)
            if resp_fixed.status_code != 200:
                continue
            fixed_code = resp_fixed.text.strip()

            # Construct approximate buggy code from patch reversal
            buggy_lines = []
            for line in patch.split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    continue
                elif line.startswith("-") and not line.startswith("---"):
                    buggy_lines.append(line[1:])
                elif not line.startswith("@@"):
                    buggy_lines.append(line)

            buggy_code = "\n".join(buggy_lines).strip()
            if not buggy_code or not fixed_code or buggy_code == fixed_code:
                continue

            # AST Verification
            ast_buggy = extract_ast_vector(buggy_code)
            ast_fixed = extract_ast_vector(fixed_code)

            if np.all(ast_buggy == 0) or np.all(ast_fixed == 0):
                continue

            # Classify bug into 12 taxonomy categories
            b_type, b_desc, r_cause, f_desc, b_pattern = classify_bug_heuristically(patch, buggy_code, fixed_code, msg)

            lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"

            rec = {
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
                "affected_component": "backend" if "server" in filename or "api" in filename else "frontend",
                "confidence_score": 0.88
            }
            extracted_records.append(rec)
    except Exception as e:
        pass
    return extracted_records


def run_miner(max_samples_target: int = 50, max_per_repo: int = 2):
    print("===========================================================")
    print(f" STARTING REPOSITORY-DIVERSE GITHUB BUG MINER")
    print(f" Strict Limit: Max {max_per_repo} samples per unique repository")
    print("===========================================================")
    
    if DATASET_PATH.exists():
        df_exist = pd.read_csv(DATASET_PATH)
        existing_commits = set(df_exist["commit_hash"].astype(str))
        # Count existing samples per repository
        repo_counts = df_exist["repository"].value_counts().to_dict()
    else:
        df_exist = pd.DataFrame()
        existing_commits = set()
        repo_counts = {}

    search_topics = [
        "topic:mern", "topic:react", "topic:express", "topic:nodejs",
        "topic:mongodb", "topic:nextjs", "topic:fullstack", "topic:ecommerce",
        "topic:admin-dashboard", "topic:crm", "topic:chat", "topic:auth",
        "topic:hospital-management", "topic:school-management", "topic:lms",
        "topic:expense-tracker", "topic:erp", "topic:task-manager", "topic:booking",
        "topic:social-media", "topic:saas", "topic:inventory", "topic:finance"
    ]

    new_records = []
    unique_repos_mined_this_run = set()

    for topic in search_topics:
        if len(new_records) >= max_samples_target:
            break

        print(f"\n[SEARCHING QUERY] {topic}")
        
        for page in range(1, 3):
            if len(new_records) >= max_samples_target:
                break

            repos = search_github_repositories(topic, page=page, max_repos=20)
            
            for r in repos:
                if len(new_records) >= max_samples_target:
                    break

                repo_name = r.get("full_name", "")
                
                # Enforce strict repository diversity: Skip if repo already reached max limit
                current_repo_samples = repo_counts.get(repo_name, 0)
                if current_repo_samples >= max_per_repo:
                    continue

                commits = get_repo_fix_commits(repo_name, max_commits=5)
                repo_added_in_commit = 0

                for c in commits:
                    if repo_counts.get(repo_name, 0) >= max_per_repo:
                        break

                    sha = c.get("sha", "")
                    if sha in existing_commits:
                        continue
                    
                    msg = c.get("commit", {}).get("message", "")
                    recs = process_commit_diff(repo_name, sha, msg)
                    
                    for rec in recs:
                        new_records.append(rec)
                        existing_commits.add(sha)
                        repo_counts[repo_name] = repo_counts.get(repo_name, 0) + 1
                        unique_repos_mined_this_run.add(repo_name)
                        repo_added_in_commit += 1

                        print(f"  [+ADDED ({repo_counts[repo_name]}/{max_per_repo})] Repo: {repo_name} | {rec['bug_type']} | {rec['file_path']} (Total new: {len(new_records)})")
                        
                        if repo_counts[repo_name] >= max_per_repo or len(new_records) >= max_samples_target:
                            break

    if new_records:
        df_new = pd.DataFrame(new_records)
        df_final = pd.concat([df_exist, df_new], ignore_index=True) if not df_exist.empty else df_new
        df_final.to_csv(DATASET_PATH, index=False)
        print(f"\n===========================================================")
        print(f"[SUCCESS] Extracted {len(new_records)} new bug-fix samples!")
        print(f"[REPOS] Mined across {len(unique_repos_mined_this_run)} UNIQUE repositories!")
        print(f"Updated total dataset size: {len(df_final)} rows.")
        print(f"===========================================================")
    else:
        print("\n[INFO] No new matching commits found from unvisited repositories.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mine public GitHub user repos with strict repository diversity")
    parser.add_argument("--count", type=int, default=50, help="Target number of new samples to mine")
    parser.add_argument("--max-per-repo", type=int, default=2, help="Strict maximum samples allowed per repository")
    args = parser.parse_args()
    
    run_miner(max_samples_target=args.count, max_per_repo=args.max_per_repo)
