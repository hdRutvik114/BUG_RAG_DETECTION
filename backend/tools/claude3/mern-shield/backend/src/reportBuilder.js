/**
 * reportBuilder.js
 * Merges results from all 4 engines into a single unified analysis report.
 */

const { chunkFunctions } = require('./functionChunker');

/**
 * Build the unified report from all analysis inputs.
 */
function buildReport({ files, projectInfo, eslintIssues, tscIssues, npmAuditIssues, semgrepResult }) {
  const allIssues = [
    ...eslintIssues,
    ...tscIssues,
    ...npmAuditIssues,
    ...(semgrepResult.issues || []),
  ];

  // Build per-file structure with functions and issues
  const fileMap = {};

  for (const file of files) {
    const functions = chunkFunctions(file.content || '', file.role);
    fileMap[file.path] = {
      path: file.path,
      role: file.role,
      lines: (file.content || '').split('\n').length,
      functions,
      issues: [],
      issueCount: 0,
    };
  }

  // Attach issues to their files
  for (const issue of allIssues) {
    const filePath = issue.file;
    if (fileMap[filePath]) {
      fileMap[filePath].issues.push(issue);
      fileMap[filePath].issueCount++;
    } else {
      // File not in filtered set (e.g. package.json for npm audit) — add minimal entry
      if (!fileMap[filePath]) {
        fileMap[filePath] = {
          path: filePath,
          role: 'config',
          lines: 0,
          functions: [],
          issues: [issue],
          issueCount: 1,
        };
      }
    }
  }

  // Sort files: most issues first
  const sortedFiles = Object.values(fileMap).sort((a, b) => b.issueCount - a.issueCount);

  // Summary statistics
  const bySeverity = { error: 0, warning: 0, info: 0 };
  const byEngine = { eslint: 0, typescript: 0, 'npm-audit': 0, semgrep: 0 };
  const byCategory = { security: 0, logic: 0, type: 0, dependency: 0, react: 0, async: 0, unknown: 0 };

  for (const issue of allIssues) {
    bySeverity[issue.severity] = (bySeverity[issue.severity] || 0) + 1;
    byEngine[issue.engine] = (byEngine[issue.engine] || 0) + 1;
    byCategory[issue.category] = (byCategory[issue.category] || 0) + 1;
  }

  const totalFunctions = Object.values(fileMap).reduce((sum, f) => sum + f.functions.length, 0);

  // Function type distribution
  const functionTypes = {};
  for (const file of Object.values(fileMap)) {
    for (const fn of file.functions) {
      functionTypes[fn.type] = (functionTypes[fn.type] || 0) + 1;
    }
  }

  return {
    project: {
      type: projectInfo.type,
      frameworks: projectInfo.frameworks,
      hasTypeScript: projectInfo.hasTypeScript,
      hasFrontend: projectInfo.hasFrontend,
      hasBackend: projectInfo.hasBackend,
      totalFiles: files.length,
      totalFunctions,
    },
    engines: {
      eslint: { status: 'completed', issueCount: eslintIssues.length },
      typescript: {
        status: projectInfo.hasTypeScript ? 'completed' : 'skipped',
        reason: projectInfo.hasTypeScript ? null : 'No .ts/.tsx files found',
        issueCount: tscIssues.length,
      },
      'npm-audit': {
        status: npmAuditIssues.length >= 0 ? 'completed' : 'skipped',
        issueCount: npmAuditIssues.length,
      },
      semgrep: {
        status: semgrepResult.skipped ? 'skipped' : 'completed',
        reason: semgrepResult.reason || null,
        issueCount: (semgrepResult.issues || []).length,
      },
    },
    summary: {
      totalIssues: allIssues.length,
      bySeverity,
      byEngine,
      byCategory,
      functionTypes,
    },
    files: sortedFiles,
  };
}

module.exports = { buildReport };
