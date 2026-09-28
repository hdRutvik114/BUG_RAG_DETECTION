import json
import logging
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger("ast_vectorizer")

NODE_TYPES: List[str] = [
    "Program", "Identifier", "StringLiteral", "NumericLiteral", "BooleanLiteral", "NullLiteral",
    "RegExpLiteral", "TemplateLiteral", "TemplateElement", "BigIntLiteral", "ArrayExpression",
    "ObjectExpression", "ObjectProperty", "ObjectMethod", "FunctionExpression", "ArrowFunctionExpression",
    "ClassExpression", "NewExpression", "CallExpression", "MemberExpression", "OptionalMemberExpression",
    "OptionalCallExpression", "UnaryExpression", "UpdateExpression", "BinaryExpression", "LogicalExpression",
    "ConditionalExpression", "AssignmentExpression", "SequenceExpression", "ThisExpression", "Super",
    "MetaProperty", "YieldExpression", "AwaitExpression", "ImportExpression", "ChainExpression",
    "SpreadElement", "RestElement", "ExpressionStatement", "BlockStatement", "EmptyStatement",
    "DebuggerStatement", "WithStatement", "ReturnStatement", "LabeledStatement", "BreakStatement",
    "ContinueStatement", "IfStatement", "SwitchStatement", "SwitchCase", "ThrowStatement",
    "TryStatement", "CatchClause", "WhileStatement", "DoWhileStatement", "ForStatement",
    "ForInStatement", "ForOfStatement", "FunctionDeclaration", "VariableDeclaration", "VariableDeclarator",
    "ClassDeclaration", "ClassBody", "ClassMethod", "ClassPrivateMethod", "ClassProperty",
    "ClassPrivateProperty", "ClassAccessorProperty", "StaticBlock", "ImportDeclaration", "ImportSpecifier",
    "ImportDefaultSpecifier", "ImportNamespaceSpecifier", "ExportNamedDeclaration", "ExportDefaultDeclaration",
    "ExportAllDeclaration", "ExportSpecifier", "JSXElement", "JSXFragment", "JSXAttribute",
    "JSXText", "JSXExpressionContainer", "JSXSpreadChild", "JSXOpeningElement", "JSXClosingElement",
    "JSXIdentifier", "JSXMemberExpression", "TSTypeAnnotation", "TSTypeParameterInstantiation",
    "TSAsExpression", "TSTypeAssertion", "TSNonNullExpression", "TSParameterProperty", "TSDeclareFunction",
    "TSInterfaceDeclaration", "TSTypeAliasDeclaration", "TSEnumDeclaration", "TSModuleDeclaration",
    "TSSatisfiesExpression", "Decorator", "PrivateName", "ParenthesizedExpression", "TaggedTemplateExpression",
    "Directive", "DirectiveLiteral",
]

NODE_INDEX = {t: i for i, t in enumerate(NODE_TYPES)}
BAG_DIM = len(NODE_TYPES)
STRUCT_DIM = 15
VECTOR_DIM = BAG_DIM + STRUCT_DIM

WORKDIR = Path(__file__).resolve().parent
PARSER_SCRIPT_PATH = WORKDIR / "js_ast_parser.js"
PARSE_TIMEOUT_SECONDS = 10


def _python_fallback_counts(code: str) -> Dict[str, int]:
    counts = {"Program": 1}
    def add(type_name, n=1):
        counts[type_name] = counts.get(type_name, 0) + n

    if re.search(r"\bfunction\b|\=\>", code): add("FunctionDeclaration", len(re.findall(r"\bfunction\b", code)))
    if re.search(r"\bclass\b", code): add("ClassDeclaration", len(re.findall(r"\bclass\b", code)))
    if re.search(r"\bif\b", code): add("IfStatement", len(re.findall(r"\bif\b", code)))
    if re.search(r"\bfor\b|\bwhile\b", code): add("ForStatement", len(re.findall(r"\bfor\b|\bwhile\b", code)))
    if re.search(r"\btry\b", code): add("TryStatement", len(re.findall(r"\btry\b", code)))
    if re.search(r"\bcatch\b", code): add("CatchClause", len(re.findall(r"\bcatch\b", code)))
    if re.search(r"\breturn\b", code): add("ReturnStatement", len(re.findall(r"\breturn\b", code)))
    if re.search(r"\bimport\b", code): add("ImportDeclaration", len(re.findall(r"\bimport\b", code)))
    if re.search(r"\bexport\b", code): add("ExportNamedDeclaration", len(re.findall(r"\bexport\b", code)))
    if re.search(r"\bawait\b", code): add("AwaitExpression", len(re.findall(r"\bawait\b", code)))
    if re.search(r"\bthrow\b", code): add("ThrowStatement", len(re.findall(r"\bthrow\b", code)))
    if re.search(r"\bswitch\b", code): add("SwitchStatement", len(re.findall(r"\bswitch\b", code)))
    if re.search(r"\bcase\b", code): add("SwitchCase", len(re.findall(r"\bcase\b", code)))

    idents = len(re.findall(r"\b[a-zA-Z_$][a-zA-Z0-9_$]*\b", code))
    if idents > 0: add("Identifier", idents)
    strings = len(re.findall(r"""['"`](?:\\.|[^\n'"`])*['"`]""", code))
    if strings > 0: add("StringLiteral", strings)
    numbers = len(re.findall(r"\b\d+(\.\d+)?\b", code))
    if numbers > 0: add("NumericLiteral", numbers)

    return counts


def _invoke_node_parser(code: str, filename: str) -> Dict[str, Any]:
    payload = json.dumps({"code": code, "filename": filename})

    try:
        result = subprocess.run(
            ["node", str(PARSER_SCRIPT_PATH)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=PARSE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"tier": "timeout"}
    except (OSError, FileNotFoundError):
        return {"tier": "exec_error"}

    if result.returncode != 0:
        return {"tier": "exit_error"}

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"tier": "json_error"}

    if "error" in parsed:
        return {"tier": "parse_error"}

    return parsed


@lru_cache(maxsize=1024)
def _cached_extract_with_tier(code_hash: int, code: str, filename: str) -> Tuple[Tuple[float, ...], str]:
    parsed = _invoke_node_parser(code, filename)
    counts: Dict[str, int] = parsed.get("counts", {})
    total_nodes: int = parsed.get("totalNodes", 0)
    max_depth: int = parsed.get("maxDepth", 0)
    sum_depth: int = parsed.get("sumDepth", 0)
    tier: str = parsed.get("tier", "unknown")

    if not counts or total_nodes == 0:
        counts = _python_fallback_counts(code)
        total_nodes = sum(counts.values()) or 1
        max_depth = 2
        sum_depth = total_nodes * 2
        tier = "tier_3_python_fallback"

    bag = [0.0] * BAG_DIM
    for node_type, count in counts.items():
        idx = NODE_INDEX.get(node_type)
        if idx is not None:
            bag[idx] = float(count)

    avg_depth = (sum_depth / total_nodes) if total_nodes else 0.0
    seen_types = float(len(counts))

    fn_count = counts.get("FunctionDeclaration", 0) + counts.get("FunctionExpression", 0)
    arrow_count = counts.get("ArrowFunctionExpression", 0)
    class_count = counts.get("ClassDeclaration", 0) + counts.get("ClassExpression", 0)
    string_lit = counts.get("StringLiteral", 0) + counts.get("TemplateElement", 0)
    number_lit = counts.get("NumericLiteral", 0)
    bool_lit = counts.get("BooleanLiteral", 0)
    null_lit = counts.get("NullLiteral", 0)
    binary_count = counts.get("BinaryExpression", 0) + counts.get("LogicalExpression", 0)
    unary_count = counts.get("UnaryExpression", 0) + counts.get("UpdateExpression", 0)
    call_count = (
        counts.get("CallExpression", 0)
        + counts.get("OptionalCallExpression", 0)
        + counts.get("NewExpression", 0)
    )
    member_count = counts.get("MemberExpression", 0) + counts.get("OptionalMemberExpression", 0)

    structural = [
        float(total_nodes),
        float(max_depth),
        float(avg_depth),
        seen_types,
        float(fn_count),
        float(arrow_count),
        float(class_count),
        float(string_lit),
        float(number_lit),
        float(bool_lit),
        float(null_lit),
        float(binary_count),
        float(unary_count),
        float(call_count),
        float(member_count),
    ]

    raw = np.array(bag + structural, dtype=np.float64)
    total_sum = np.sum(raw)
    if total_sum > 0:
        return tuple(raw / total_sum), tier
    return tuple(raw), tier


def extract_ast_vector_with_tier(code: str, filename: str = "snippet.tsx") -> Tuple[np.ndarray, str]:
    if not isinstance(code, str) or not code.strip():
        return np.zeros(VECTOR_DIM, dtype=np.float64), "empty"

    vec_tuple, tier = _cached_extract_with_tier(hash(code), code, filename)
    return np.array(vec_tuple, dtype=np.float64), tier


def extract_ast_vector(code: str, filename: str = "snippet.tsx") -> np.ndarray:
    vec, _ = extract_ast_vector_with_tier(code, filename)
    return vec