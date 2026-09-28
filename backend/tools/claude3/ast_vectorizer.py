"""
AST vectorizer for JS/TS code snippets.

Calls js_ast_parser.js (a subprocess) with the code via stdin/stdout JSON,
then maps the returned node-type count dict to a fixed 64-dimensional numpy
vector.

Tier semantics (mirrors js_ast_parser.js):
  tier_1_direct         – parsed as-is by Babel; highest quality
  tier_2_*              – parsed after a wrapper/brace-balancing pass; usable
  tier_3_fallback*      – pure regex token counts (Babel unavailable);
                          structurally weaker but non-zero and consistent

is_reliable_tier() returns True for tier_1 and tier_2, False for tier_3.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger("ast_vectorizer")

# ---------------------------------------------------------------------------
# The 64 AST node-type slots. Order is fixed — do NOT reorder.
# Any node type returned by the JS parser that isn't in this list is ignored.
# Any slot not present in a result is zero.
# ---------------------------------------------------------------------------
_AST_SLOTS = [
    # Declarations
    "FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression",
    "ClassDeclaration", "ClassExpression", "ClassMethod", "ClassProperty",
    "VariableDeclaration", "VariableDeclarator",
    # Statements
    "ExpressionStatement", "ReturnStatement", "IfStatement",
    "ForStatement", "ForInStatement", "ForOfStatement",
    "WhileStatement", "DoWhileStatement",
    "SwitchStatement", "SwitchCase",
    "TryStatement", "CatchClause",
    "ThrowStatement", "BreakStatement", "ContinueStatement",
    "BlockStatement", "LabeledStatement",
    # Expressions
    "CallExpression", "NewExpression", "MemberExpression",
    "AssignmentExpression", "BinaryExpression", "LogicalExpression",
    "UnaryExpression", "UpdateExpression", "ConditionalExpression",
    "SequenceExpression", "SpreadElement", "YieldExpression",
    "AwaitExpression", "TaggedTemplateExpression", "TemplateLiteral",
    "ObjectExpression", "ArrayExpression",
    # Patterns / destructuring
    "ObjectPattern", "ArrayPattern", "AssignmentPattern",
    "RestElement",
    # Identifiers / literals
    "Identifier", "StringLiteral", "NumericLiteral", "BooleanLiteral",
    "NullLiteral", "RegExpLiteral",
    # Imports / exports
    "ImportDeclaration", "ExportNamedDeclaration", "ExportDefaultDeclaration",
    "ExportAllDeclaration",
    # Misc
    "Program",
    # Padding to reach 64 slots
    "_pad_58", "_pad_59", "_pad_60", "_pad_61", "_pad_62", "_pad_63",
]

assert len(_AST_SLOTS) == 64, f"Expected 64 AST slots, got {len(_AST_SLOTS)}"

_SLOT_INDEX = {name: idx for idx, name in enumerate(_AST_SLOTS)}

# Path to the JS parser script (sibling file)
_JS_PARSER_PATH = Path(__file__).resolve().parent / "js_ast_parser.js"

# Timeout for the Node subprocess (seconds)
_NODE_TIMEOUT = 10


def _run_js_parser(code: str, filename: str) -> Optional[dict]:
    """Run js_ast_parser.js as a subprocess and return the parsed JSON result,
    or None on any failure."""
    if not _JS_PARSER_PATH.exists():
        logger.warning("js_ast_parser.js not found at %s", _JS_PARSER_PATH)
        return None
    try:
        payload = json.dumps({"code": code, "filename": filename})
        result = subprocess.run(
            ["node", str(_JS_PARSER_PATH)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_NODE_TIMEOUT,
            cwd=str(_JS_PARSER_PATH.parent),
        )
        if result.returncode != 0 and not result.stdout.strip():
            logger.debug(
                "js_ast_parser.js stderr: %s", result.stderr[:200] if result.stderr else "(empty)"
            )
            return None
        raw = result.stdout.strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        if "error" in parsed:
            logger.debug("js_ast_parser returned error: %s", parsed.get("message", parsed["error"]))
            return None
        return parsed
    except subprocess.TimeoutExpired:
        logger.warning("js_ast_parser.js timed out for filename=%s", filename)
        return None
    except (json.JSONDecodeError, OSError, FileNotFoundError) as exc:
        logger.debug("js_ast_parser.js call failed: %s", exc)
        return None


def _python_fallback_counts(code: str) -> dict:
    """Pure-Python regex token counter, used when Node.js is unavailable.
    Mirrors the logic in fallbackTokenCounts() in js_ast_parser.js so that
    the resulting tier ('tier_3_fallback_py') is clearly labelled as a
    non-AST approximation."""
    import re
    counts: dict = {"Program": 1}

    def add(key: str, n: int = 1) -> None:
        counts[key] = counts.get(key, 0) + n

    if re.search(r'\bfunction\b|=>', code):
        m = re.findall(r'\bfunction\b', code)
        add("FunctionDeclaration", len(m) if m else 1)
    if re.search(r'=>', code):
        m = re.findall(r'=>', code)
        add("ArrowFunctionExpression", len(m))
    if re.search(r'\bclass\b', code):
        m = re.findall(r'\bclass\b', code)
        add("ClassDeclaration", len(m))
    if re.search(r'\bif\b', code):
        m = re.findall(r'\bif\b', code)
        add("IfStatement", len(m))
    if re.search(r'\bfor\b|\bwhile\b', code):
        m = re.findall(r'\bfor\b|\bwhile\b', code)
        add("ForStatement", len(m))
    if re.search(r'\btry\b', code):
        m = re.findall(r'\btry\b', code)
        add("TryStatement", len(m))
    if re.search(r'\bcatch\b', code):
        m = re.findall(r'\bcatch\b', code)
        add("CatchClause", len(m))
    if re.search(r'\breturn\b', code):
        m = re.findall(r'\breturn\b', code)
        add("ReturnStatement", len(m))
    if re.search(r'\bimport\b', code):
        m = re.findall(r'\bimport\b', code)
        add("ImportDeclaration", len(m))
    if re.search(r'\bexport\b', code):
        m = re.findall(r'\bexport\b', code)
        add("ExportNamedDeclaration", len(m))
    if re.search(r'\bawait\b', code):
        m = re.findall(r'\bawait\b', code)
        add("AwaitExpression", len(m))
    if re.search(r'\bthrow\b', code):
        m = re.findall(r'\bthrow\b', code)
        add("ThrowStatement", len(m))
    if re.search(r'\bswitch\b', code):
        m = re.findall(r'\bswitch\b', code)
        add("SwitchStatement", len(m))
    if re.search(r'\bcase\b', code):
        m = re.findall(r'\bcase\b', code)
        add("SwitchCase", len(m))
    idents = re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', code)
    if idents:
        add("Identifier", len(idents))
    strings = re.findall(r"['\"`](?:\\.|[^'\"\`\n])*['\"`]", code)
    if strings:
        add("StringLiteral", len(strings))
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', code)
    if numbers:
        add("NumericLiteral", len(numbers))
    return counts


def _counts_to_vector(counts: dict, total_nodes: int, max_depth: int, sum_depth: int) -> np.ndarray:
    """Convert AST node-type counts + summary stats to a 64-dimensional float32 vector.

    Slots 0..61 → raw counts for the corresponding AST node type.
    Slot 62 → log1p(total_nodes) — overall size signal.
    Slot 63 → max_depth / 30.0 (clamped) — structural depth signal.
    (Overrides the _pad_62/_pad_63 placeholder names.)
    """
    vec = np.zeros(64, dtype=np.float32)
    for node_type, count in counts.items():
        idx = _SLOT_INDEX.get(node_type)
        if idx is not None and idx < 62:
            vec[idx] = float(count)
    # Slot 62: size signal
    vec[62] = float(np.log1p(max(total_nodes, 0)))
    # Slot 63: depth signal
    vec[63] = float(min(max_depth, 30)) / 30.0
    # L2-normalise so vectors from functions of very different sizes are
    # comparable; guard against the all-zero edge case.
    norm = np.linalg.norm(vec)
    if norm > 0.0:
        vec = vec / norm
    return vec


def extract_ast_vector_with_tier(code: str, filename: str) -> Tuple[np.ndarray, str]:
    """Main public entry point consumed by miner.py.

    Args:
        code:     JS/TS source code (comments already stripped).
        filename: Original filename (e.g. 'src/utils.ts') — used by the JS
                  parser to select the correct Babel plugins (JSX/TypeScript).

    Returns:
        (vector, tier)
        vector: 64-dimensional float32 numpy array (L2-normalised).
        tier:   string label indicating parsing quality:
                'tier_1_direct', 'tier_2_*', 'tier_3_fallback',
                'tier_3_fallback_py' (Python fallback if Node unavailable).
    """
    # 1. Try Node.js JS parser
    result = _run_js_parser(code, filename)
    if result is not None:
        counts = result.get("counts", {})
        total_nodes = int(result.get("totalNodes", 1))
        max_depth = int(result.get("maxDepth", 1))
        sum_depth = int(result.get("sumDepth", 0))
        tier = str(result.get("tier", "tier_3_fallback"))
        vec = _counts_to_vector(counts, total_nodes, max_depth, sum_depth)
        return vec, tier

    # 2. Python fallback (Node.js unavailable)
    counts = _python_fallback_counts(code)
    total_nodes = sum(counts.values())
    vec = _counts_to_vector(counts, total_nodes, max_depth=2, sum_depth=total_nodes * 2)
    return vec, "tier_3_fallback_py"


def is_reliable_tier(tier: str) -> bool:
    """Returns True for tier_1 and tier_2 (real Babel AST), False for tier_3
    (regex fallback or Python fallback). Used by miner.py to set the
    `ast_tier` field and to flag samples whose AST quality is lower."""
    if not tier:
        return False
    return tier.startswith("tier_1") or tier.startswith("tier_2")