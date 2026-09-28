import re
import numpy as np
from typing import List

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
    "Directive", "DirectiveLiteral"
]

NODE_INDEX = {t: i for i, t in enumerate(NODE_TYPES)}
BAG_DIM = len(NODE_TYPES)
STRUCT_DIM = 15
VECTOR_DIM = BAG_DIM + STRUCT_DIM


def extract_ast_vector(code: str) -> np.ndarray:
    bag = [0] * BAG_DIM
    if not isinstance(code, str) or not code.strip():
        return np.zeros(VECTOR_DIM, dtype=np.float64)

    lines = code.split("\n")
    max_depth = max([len(line) - len(line.lstrip()) for line in lines]) // 2 + 1 if lines else 1
    avg_depth = max_depth / 2.0

    seen_types = set()
    node_count = 0

    def add_node(type_name: str, count: int = 1):
        nonlocal node_count
        node_count += count
        seen_types.add(type_name)
        idx = NODE_INDEX.get(type_name)
        if idx is not None:
            bag[idx] += count

    add_node("Program")
    add_node("BlockStatement", max(1, len(lines)))

    # Node pattern recognizers
    fn_declarations = len(re.findall(r"\bfunction\b", code))
    arrow_functions = len(re.findall(r"=>", code))
    class_declarations = len(re.findall(r"\bclass\b", code))
    if_statements = len(re.findall(r"\bif\b", code))
    return_statements = len(re.findall(r"\breturn\b", code))
    await_expressions = len(re.findall(r"\bawait\b", code))
    try_statements = len(re.findall(r"\btry\b", code))
    catch_clauses = len(re.findall(r"\bcatch\b", code))
    for_statements = len(re.findall(r"\bfor\b", code))
    while_statements = len(re.findall(r"\bwhile\b", code))
    
    string_literals = len(re.findall(r"(['\"])(.*?)\1|`(.*?)`", code))
    number_literals = len(re.findall(r"\b\d+(\.\d+)?\b", code))
    boolean_literals = len(re.findall(r"\b(true|false)\b", code))
    null_literals = len(re.findall(r"\bnull\b", code))
    
    binary_expressions = len(re.findall(r"===|!==|==|!=|&&|\|\||<=|>=|<|>", code))
    unary_expressions = len(re.findall(r"typeof|instanceof|!|\+\+|--", code))
    call_expressions = len(re.findall(r"\b[a-zA-Z0-9_$]+\s*\(", code))
    member_expressions = len(re.findall(r"\?\.|[a-zA-Z0-9_$]+\.[a-zA-Z0-9_$]+", code))
    optional_chaining = len(re.findall(r"\?\.", code))
    type_assertions = len(re.findall(r"\bas\s+[a-zA-Z0-9_$]+", code))

    add_node("FunctionDeclaration", fn_declarations)
    add_node("ArrowFunctionExpression", arrow_functions)
    add_node("ClassDeclaration", class_declarations)
    add_node("IfStatement", if_statements)
    add_node("ReturnStatement", return_statements)
    add_node("AwaitExpression", await_expressions)
    add_node("TryStatement", try_statements)
    add_node("CatchClause", catch_clauses)
    add_node("ForStatement", for_statements)
    add_node("WhileStatement", while_statements)
    add_node("StringLiteral", string_literals)
    add_node("NumericLiteral", number_literals)
    add_node("BooleanLiteral", boolean_literals)
    add_node("NullLiteral", null_literals)
    add_node("BinaryExpression", binary_expressions)
    add_node("UnaryExpression", unary_expressions)
    add_node("CallExpression", call_expressions)
    add_node("MemberExpression", member_expressions)
    add_node("OptionalMemberExpression", optional_chaining)
    add_node("TSAsExpression", type_assertions)

    fn_count = fn_declarations
    arrow_count = arrow_functions
    class_count = class_declarations
    string_lit = string_literals
    number_lit = number_literals
    bool_lit = boolean_literals
    null_lit = null_literals
    binary_count = binary_expressions
    unary_count = unary_expressions
    call_count = call_expressions
    member_count = member_expressions

    structural = [
        float(node_count),
        float(max_depth),
        float(avg_depth),
        float(len(seen_types)),
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
        float(member_count)
    ]

    raw = np.array(bag + structural, dtype=np.float64)
    total_sum = np.sum(raw)
    if total_sum > 0:
        return raw / total_sum
    return raw
