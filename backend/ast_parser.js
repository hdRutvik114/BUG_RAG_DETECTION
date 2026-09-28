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

  state.nodes += 1;
  if (depth > state.maxDepth) {
    state.maxDepth = depth;
  }

  if (
    node.type === "IfStatement" ||
    node.type === "ForStatement" ||
    node.type === "ForInStatement" ||
    node.type === "ForOfStatement" ||
    node.type === "WhileStatement" ||
    node.type === "DoWhileStatement" ||
    node.type === "CatchClause" ||
    node.type === "ConditionalExpression" ||
    node.type === "LogicalExpression"
  ) {
    state.complexity += 1;
  }

  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "range" || key === "comments") {
      continue;
    }
    const val = node[key];
    if (Array.isArray(val)) {
      for (const item of val) {
        if (item && typeof item.type === "string") {
          walk(item, depth + 1, state);
        }
      }
    } else if (val && typeof val.type === "string") {
      walk(val, depth + 1, state);
    }
  }
}

function extractFunctions(code, filename) {
  let ast;
  try {
    ast = parseDirect(code, filename);
  } catch (err) {
    return [];
  }

  const results = [];
  const lines = code.split("\n");

  function processFunctionNode(node, name) {
    const startLine = node.loc ? node.loc.start.line : 1;
    const endLine = node.loc ? node.loc.end.line : lines.length;
    const fnCode = lines.slice(startLine - 1, endLine).join("\n");

    const state = { nodes: 0, maxDepth: 0, complexity: 1 };
    walk(node.body || node, 1, state);

    // Generate 64-D AST Vector
    const vector = new Array(64).fill(0);
    vector[0] = Math.min(state.nodes / 100, 1.0);
    vector[1] = Math.min(state.maxDepth / 20, 1.0);
    vector[2] = Math.min(state.complexity / 15, 1.0);
    vector[3] = (fnCode.match(/if\s*\(/g) || []).length / 10;
    vector[4] = (fnCode.match(/for\s*\(/g) || []).length / 5;
    vector[5] = (fnCode.match(/await\s+/g) || []).length / 5;
    vector[6] = (fnCode.match(/try\s*\{/g) || []).length / 5;

    results.append ? results.push({
      method_name: name || "anonymous",
      line_number_start: startLine,
      line_number_end: endLine,
      code: fnCode,
      ast_vector: vector,
      complexity: state.complexity,
      max_depth: state.maxDepth
    }) : results.push({
      method_name: name || "anonymous",
      line_number_start: startLine,
      line_number_end: endLine,
      code: fnCode,
      ast_vector: vector,
      complexity: state.complexity,
      max_depth: state.maxDepth
    });
  }

  function traverse(node) {
    if (!node || typeof node.type !== "string") return;

    if (
      node.type === "FunctionDeclaration" ||
      node.type === "FunctionExpression" ||
      node.type === "ArrowFunctionExpression"
    ) {
      let name = "anonymous";
      if (node.id && node.id.name) {
        name = node.id.name;
      }
      processFunctionNode(node, name);
    }

    for (const key of Object.keys(node)) {
      if (key === "loc" || key === "range" || key === "comments") continue;
      const val = node[key];
      if (Array.isArray(val)) {
        for (const item of val) {
          if (item && typeof item.type === "string") traverse(item);
        }
      } else if (val && typeof val.type === "string") {
        traverse(val);
      }
    }
  }

  traverse(ast);
  return results;
}

let inputData = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  inputData += chunk;
});

process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(inputData);
    const code = payload.code || "";
    const filepath = payload.filepath || "snippet.js";
    const funcs = extractFunctions(code, filepath);
    process.stdout.write(JSON.stringify(funcs));
  } catch (err) {
    process.stdout.write(JSON.stringify([]));
  }
});
