/**
 * functionChunker.js
 * Splits a JS/TS source file into individual function chunks using
 * regex + brace-matching heuristics (no Babel dependency).
 *
 * For each function found it returns:
 *   { name, startLine, endLine, lines, code, type }
 */

const FUNCTION_SIGNATURES = [
  // export default function Foo(...) {
  // export async function foo(...) {
  // function foo(...) {
  {
    regex: /^[ \t]*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/,
    nameGroup: 4,
  },
  // const Foo = async (...) => {
  // export const foo = (...) => {
  {
    regex: /^[ \t]*(export\s+)?(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(async\s+)?(\([^)]*\)|[A-Za-z_$][\w$]*)\s*(:\s*[^=]+)?\s*=>/,
    nameGroup: 3,
  },
  // const foo = function(...) {
  {
    regex: /^[ \t]*(export\s+)?(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(async\s+)?function\s*\*?\s*\(/,
    nameGroup: 3,
  },
  // class method: methodName(...) {  or  async methodName(...) {
  {
    regex: /^[ \t]*(public\s+|private\s+|protected\s+|static\s+|async\s+|\*\s*)*(?!if\b|for\b|while\b|switch\b|catch\b|function\b|return\b|class\b)([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(:\s*[^{]+)?\{/,
    nameGroup: 2,
  },
];

/**
 * Classify function type based on name and file role.
 * @param {string} name
 * @param {string} fileRole
 */
function classifyFunctionType(name, fileRole) {
  if (!name) return 'anonymous';
  const lower = name.toLowerCase();
  // React hooks start with 'use' + uppercase
  if (/^use[A-Z]/.test(name)) return 'hook';
  // React components start with uppercase
  if (/^[A-Z]/.test(name)) return 'component';
  // Common backend patterns
  if (['get', 'post', 'put', 'patch', 'delete', 'handle'].some(p => lower.startsWith(p))) {
    if (fileRole === 'route' || fileRole === 'controller') return fileRole;
  }
  if (fileRole === 'model') return 'model';
  if (fileRole === 'middleware') return 'middleware';
  return 'utility';
}

/**
 * Find the index of the matching closing brace, starting right after the opening brace.
 * @param {string} source - full source string
 * @param {number} openBraceIdx - index of the '{' character
 * @returns {number} index of matching '}', or -1 if not found
 */
function findMatchingBrace(source, openBraceIdx) {
  let depth = 0;
  let inString = false;
  let stringChar = '';
  let inTemplate = false;
  let templateDepth = 0;
  let i = openBraceIdx;
  const n = source.length;

  while (i < n) {
    const ch = source[i];

    // Handle string literals
    if (!inString && !inTemplate && (ch === '"' || ch === "'")) {
      inString = true;
      stringChar = ch;
      i++;
      continue;
    }
    if (inString) {
      if (ch === '\\') { i += 2; continue; }
      if (ch === stringChar) inString = false;
      i++;
      continue;
    }

    // Handle template literals
    if (!inTemplate && ch === '`') {
      inTemplate = true;
      templateDepth = depth;
      i++;
      continue;
    }
    if (inTemplate) {
      if (ch === '\\') { i += 2; continue; }
      if (ch === '`') { inTemplate = false; }
      i++;
      continue;
    }

    // Handle line comments
    if (ch === '/' && source[i + 1] === '/') {
      const nl = source.indexOf('\n', i);
      i = nl === -1 ? n : nl + 1;
      continue;
    }

    // Handle block comments
    if (ch === '/' && source[i + 1] === '*') {
      const end = source.indexOf('*/', i + 2);
      i = end === -1 ? n : end + 2;
      continue;
    }

    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return i;
    }

    i++;
  }

  return -1;
}

/**
 * Extract all functions from source code.
 * @param {string} source - raw source code string
 * @param {string} fileRole - role from fileFilter.js
 * @returns {Array<{name, startLine, endLine, lines, code, type}>}
 */
function chunkFunctions(source, fileRole = 'unknown') {
  const sourceLines = source.split('\n');
  const chunks = [];
  const usedLines = new Set();

  for (let lineIdx = 0; lineIdx < sourceLines.length; lineIdx++) {
    if (usedLines.has(lineIdx)) continue;

    const line = sourceLines[lineIdx];

    for (const sig of FUNCTION_SIGNATURES) {
      const match = sig.regex.exec(line);
      if (!match) continue;

      const funcName = match[sig.nameGroup] || 'anonymous';

      // Find opening brace — may be on same or next line
      let braceLineIdx = lineIdx;
      let braceCharIdx = -1;

      // Look for '{' starting from this line, scanning up to 5 lines ahead
      const searchWindow = sourceLines.slice(lineIdx, lineIdx + 5).join('\n');
      const openBraceRelIdx = searchWindow.indexOf('{');
      if (openBraceRelIdx === -1) break;

      // Convert relative position to absolute source index
      const linesUpToThis = sourceLines.slice(0, lineIdx).join('\n');
      const absoluteStart = linesUpToThis.length + (lineIdx > 0 ? 1 : 0); // +1 for \n
      const openBraceAbsIdx = absoluteStart + openBraceRelIdx;

      const closeBraceAbsIdx = findMatchingBrace(source, openBraceAbsIdx);
      if (closeBraceAbsIdx === -1) break;

      const funcCode = source.slice(openBraceAbsIdx - openBraceRelIdx + (lineIdx > 0 ? 0 : 0), closeBraceAbsIdx + 1);
      const extractedCode = sourceLines.slice(lineIdx).join('\n').slice(0, closeBraceAbsIdx - openBraceAbsIdx + openBraceRelIdx + 1);

      // Count end line
      const codeUpToClose = source.slice(0, closeBraceAbsIdx + 1);
      const endLineIdx = (codeUpToClose.match(/\n/g) || []).length;

      // Don't add duplicates or very tiny chunks (< 3 lines)
      const lineCount = endLineIdx - lineIdx + 1;
      if (lineCount < 2) break;

      // Mark these lines as used so we don't double-extract
      for (let l = lineIdx; l <= endLineIdx; l++) usedLines.add(l);

      chunks.push({
        name: funcName,
        startLine: lineIdx + 1,  // 1-indexed
        endLine: endLineIdx + 1,
        lines: lineCount,
        code: sourceLines.slice(lineIdx, endLineIdx + 1).join('\n'),
        type: classifyFunctionType(funcName, fileRole),
      });

      break; // Only match one signature per line
    }
  }

  return chunks;
}

module.exports = { chunkFunctions };
