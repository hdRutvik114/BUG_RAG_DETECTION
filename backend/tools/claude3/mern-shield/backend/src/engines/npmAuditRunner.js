/**
 * npmAuditRunner.js
 * Runs npm audit on the project's package.json to find vulnerable dependencies.
 * Writes a temp package.json and runs `npm audit --json`.
 */

const { execSync } = require('child_process');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

/**
 * Run npm audit on a package.json content string.
 * @param {Array<{path, content}>} files - all project files (looks for package.json)
 * @returns {Array<{package, severity, title, url, engine, category, file, line}>}
 */
async function runNpmAudit(files) {
  // Find the root or closest package.json
  const pkgFile = files.find(f =>
    /^package\.json$/i.test(f.path) ||
    /^(frontend|backend|client|server)\/package\.json$/i.test(f.path)
  );

  if (!pkgFile || !pkgFile.content) {
    return []; // No package.json — skip
  }

  // Validate it's valid JSON with dependencies
  let pkg;
  try {
    pkg = JSON.parse(pkgFile.content);
  } catch {
    return [];
  }

  if (!pkg.dependencies && !pkg.devDependencies) {
    return []; // No dependencies declared
  }

  const tmpDir = path.join(os.tmpdir(), `mern-shield-audit-${Date.now()}`);
  const issues = [];

  try {
    await fs.ensureDir(tmpDir);

    // Write a minimal package.json with only dependencies (npm audit doesn't need the full pkg)
    const minPkg = {
      name: pkg.name || 'mern-shield-audit',
      version: pkg.version || '1.0.0',
      dependencies: pkg.dependencies || {},
      devDependencies: pkg.devDependencies || {},
    };
    await fs.writeJson(path.join(tmpDir, 'package.json'), minPkg, { spaces: 2 });

    // Create a minimal package-lock.json to prevent npm install being required
    // We use `npm audit --package-lock-only` which audits without installing
    let output = '';
    try {
      // First try to generate a lockfile then audit
      execSync('npm install --package-lock-only --ignore-scripts 2>&1', {
        cwd: tmpDir,
        stdio: 'pipe',
        timeout: 30000,
      });
      output = execSync('npm audit --json 2>&1', {
        cwd: tmpDir,
        stdio: 'pipe',
        timeout: 30000,
      }).toString();
    } catch (err) {
      output = (err.stdout || '').toString() || (err.stderr || '').toString();
    }

    if (!output || output.trim() === '') return [];

    let auditData;
    try {
      auditData = JSON.parse(output);
    } catch {
      return []; // Non-JSON output (likely an npm error)
    }

    // npm audit v7+ format uses auditData.vulnerabilities
    const vulns = auditData.vulnerabilities || {};
    for (const [pkgName, vuln] of Object.entries(vulns)) {
      const sev = vuln.severity || 'info';
      const via = vuln.via || [];
      const advisory = typeof via[0] === 'object' ? via[0] : null;

      issues.push({
        file: pkgFile.path,
        line: 1,
        engine: 'npm-audit',
        severity: sev === 'critical' || sev === 'high' ? 'error' : 'warning',
        category: 'dependency',
        package: pkgName,
        installedVersion: vuln.range || 'unknown',
        title: advisory?.title || `Vulnerability in ${pkgName}`,
        message: advisory?.title || `${pkgName} has a known ${sev} vulnerability`,
        url: advisory?.url || `https://www.npmjs.com/advisories`,
        cwe: advisory?.cwe || [],
        cvss: advisory?.cvss?.score || null,
        ruleId: `npm-audit/${sev}`,
      });
    }
  } catch (err) {
    console.warn('[npm audit] Engine error:', err.message);
  } finally {
    try { await fs.remove(tmpDir); } catch {}
  }

  return issues;
}

module.exports = { runNpmAudit };
