const parser = require("@babel/parser");

function collectPlugins(filename) {
  const isTypescript = /\.tsx?$/.test(filename);
  const isJsx = /\.[jt]sx$/.test(filename) || !isTypescript;

  const plugins = [
    "classProperties",
    "classPrivateProperties",
    "classPrivateMethods",
    "classStaticBlock",
    "objectRestSpread",
    "optionalChaining",
    "nullishCoalescingOperator",
    ["decorators", { legacy: true }],
    "dynamicImport",
    "exportDefaultFrom",
    "exportNamespaceFrom",
    "topLevelAwait",
    "logicalAssignment",
    "numericSeparator",
    "bigInt",
    "throwExpressions",
    "optionalCatchBinding",
    "importAttributes",
  ];

  if (isJsx) {
    plugins.push("jsx");
  }
  if (isTypescript) {
    plugins.push("typescript");
  }

  return plugins;
}

function parseDirect(code, filename) {
  const plugins = collectPlugins(filename);
  return parser.parse(code, {
    sourceType: "module",
    allowReturnOutsideFunction: true,
    allowAwaitOutsideFunction: true,
    allowImportExportEverywhere: true,
    allowSuperOutsideMethod: true,
    allowUndeclaredExports: true,
    errorRecovery: true,
    plugins,
  });
}

function walk(node, depth, state) {
  if (!node || typeof node.type !== "string") {
    return;
  }

  if (
    node.name === "__dummy__" ||
    node.name === "__DummyClass__" ||
    node.name === "__dummyFn__" ||
    node.name === "__dummyObj__"
  ) {
    return;
  }

  state.totalNodes += 1;
  state.sumDepth += depth;
  if (depth > state.maxDepth) {
    state.maxDepth = depth;
  }
  state.counts[node.type] = (state.counts[node.type] || 0) + 1;

  for (const key of Object.keys(node)) {
    if (
      key === "loc" ||
      key === "start" ||
      key === "end" ||
      key === "range" ||
      key === "extra" ||
      key === "leadingComments" ||
      key === "trailingComments" ||
      key === "innerComments"
    ) {
      continue;
    }
    const value = node[key];
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item && typeof item.type === "string") {
          walk(item, depth + 1, state);
        }
      }
    } else if (value && typeof value.type === "string") {
      walk(value, depth + 1, state);
    }
  }
}

function balanceBraces(code) {
  let openBraces = 0;
  let closeBraces = 0;
  for (const char of code) {
    if (char === "{") openBraces++;
    else if (char === "}") closeBraces++;
  }
  let repaired = code;
  if (openBraces > closeBraces) {
    repaired += "\n" + "}".repeat(openBraces - closeBraces);
  } else if (closeBraces > openBraces) {
    repaired = "{".repeat(closeBraces - openBraces) + "\n" + repaired;
  }
  return repaired;
}

function fallbackTokenCounts(code) {
  const counts = {};
  const add = (type, n = 1) => {
    counts[type] = (counts[type] || 0) + n;
  };

  counts["Program"] = 1;
  if (/\bfunction\b|\=\>/.test(code)) add("FunctionDeclaration", (code.match(/\bfunction\b/g) || []).length);
  if (/\bclass\b/.test(code)) add("ClassDeclaration", (code.match(/\bclass\b/g) || []).length);
  if (/\bif\b/.test(code)) add("IfStatement", (code.match(/\bif\b/g) || []).length);
  if (/\bfor\b|\bwhile\b/.test(code)) add("ForStatement", (code.match(/\bfor\b|\bwhile\b/g) || []).length);
  if (/\btry\b/.test(code)) add("TryStatement", (code.match(/\btry\b/g) || []).length);
  if (/\bcatch\b/.test(code)) add("CatchClause", (code.match(/\bcatch\b/g) || []).length);
  if (/\breturn\b/.test(code)) add("ReturnStatement", (code.match(/\breturn\b/g) || []).length);
  if (/\bimport\b/.test(code)) add("ImportDeclaration", (code.match(/\bimport\b/g) || []).length);
  if (/\bexport\b/.test(code)) add("ExportNamedDeclaration", (code.match(/\bexport\b/g) || []).length);
  if (/\bawait\b/.test(code)) add("AwaitExpression", (code.match(/\bawait\b/g) || []).length);
  if (/\bthrow\b/.test(code)) add("ThrowStatement", (code.match(/\bthrow\b/g) || []).length);
  if (/\bswitch\b/.test(code)) add("SwitchStatement", (code.match(/\bswitch\b/g) || []).length);
  if (/\bcase\b/.test(code)) add("SwitchCase", (code.match(/\bcase\b/g) || []).length);

  const idents = (code.match(/\b[a-zA-Z_$][a-zA-Z0-9_$]*\b/g) || []).length;
  if (idents > 0) add("Identifier", idents);

  const strings = (code.match(/['"`](?:\\.|[^\n'"`])*['"`]/g) || []).length;
  if (strings > 0) add("StringLiteral", strings);

  const numbers = (code.match(/\b\d+(\.\d+)?\b/g) || []).length;
  if (numbers > 0) add("NumericLiteral", numbers);

  return counts;
}

function parseAndCount(code, filename) {
  const wrappers = [
    { name: "tier_1_direct", fn: (c) => c },
    { name: "tier_2_balanced", fn: (c) => balanceBraces(c) },
    { name: "tier_2_class", fn: (c) => `class __DummyClass__ {\n${c}\n}` },
    { name: "tier_2_class_balanced", fn: (c) => `class __DummyClass__ {\n${balanceBraces(c)}\n}` },
    { name: "tier_2_function", fn: (c) => `async function* __dummyFn__() {\n${c}\n}` },
    { name: "tier_2_function_balanced", fn: (c) => `async function* __dummyFn__() {\n${balanceBraces(c)}\n}` },
    { name: "tier_2_switch", fn: (c) => `switch (__dummy__) {\n${c}\n}` },
    { name: "tier_2_switch_balanced", fn: (c) => `switch (__dummy__) {\n${balanceBraces(c)}\n}` },
    { name: "tier_2_if", fn: (c) => `if (true) {}\n${c}` },
    { name: "tier_2_try", fn: (c) => `try {}\n${c}` },
    { name: "tier_2_object", fn: (c) => `const __dummyObj__ = {\n${c}\n};` },
    { name: "tier_2_object_balanced", fn: (c) => `const __dummyObj__ = {\n${balanceBraces(c)}\n};` },
    { name: "tier_2_expression", fn: (c) => `(__dummy__ = (\n${c}\n));` },
  ];

  for (const wrapper of wrappers) {
    try {
      const wrappedCode = wrapper.fn(code);
      const ast = parseDirect(wrappedCode, filename);
      const state = { counts: {}, totalNodes: 0, maxDepth: 0, sumDepth: 0, tier: wrapper.name };
      walk(ast.program, 1, state);
      if (state.totalNodes > 0) {
        return state;
      }
    } catch (err) {
      // continue
    }
  }

  const counts = fallbackTokenCounts(code);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return {
    counts,
    totalNodes: total || 1,
    maxDepth: 2,
    sumDepth: (total || 1) * 2,
    tier: "tier_3_fallback",
  };
}

function main() {
  let input = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    input += chunk;
  });
  process.stdin.on("end", () => {
    let payload;
    try {
      payload = JSON.parse(input);
    } catch (err) {
      process.stdout.write(
        JSON.stringify({ error: "invalid_input", message: String(err.message || err) })
      );
      return;
    }

    const code = typeof payload.code === "string" ? payload.code : "";
    const filename = typeof payload.filename === "string" ? payload.filename : "snippet.tsx";

    if (!code.trim()) {
      process.stdout.write(JSON.stringify({ error: "empty_code" }));
      return;
    }

    try {
      const result = parseAndCount(code, filename);
      process.stdout.write(JSON.stringify(result));
    } catch (err) {
      const counts = fallbackTokenCounts(code);
      const total = Object.values(counts).reduce((a, b) => a + b, 0);
      process.stdout.write(
        JSON.stringify({
          counts,
          totalNodes: total || 1,
          maxDepth: 2,
          sumDepth: (total || 1) * 2,
          tier: "tier_3_fallback_emergency",
        })
      );
    }
  });
}

main();
