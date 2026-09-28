/**
 * semgrepRunner.js
 * Runs Semgrep SAST security analysis on source files.
 * Gracefully skips if Semgrep is not installed on the system.
 */

const { execSync, spawnSync } = require('child_process');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

/**
 * Check if Semgrep is installed on the system.
 * @returns {boolean}
 */
function isSemgrepInstalled() {
  try {
    execSync('semgrep --version', { stdio: 'pipe' });
    return true;
  } catch {
    return false;
  }
}

/**
 * Run Semgrep on source files.
 * @param {Array<{path, content}>} files
 * @returns {{ issues: Array, skipped: boolean, reason?: string }}
 */
async function runSemgrep(files) {
  if (!isSemgrepInstalled()) {
    console.warn('[Semgrep] Not installed — skipping. Install with: pip install semgrep');
    return { issues: [], skipped: true, reason: 'Semgrep not installed. Run: pip install semgrep' };
  }

  const sourceFiles = files.filter(f => /\.(js|jsx|ts|tsx)$/.test(f.path));
  if (sourceFiles.length === 0) {
    return { issues: [], skipped: false };
  }

  const tmpDir = path.join(os.tmpdir(), `mern-shield-semgrep-${Date.now()}`);
  const issues = [];

  try {
    await fs.ensureDir(tmpDir);

    // Write source files to temp dir
    for (const file of sourceFiles) {
      const destPath = path.join(tmpDir, file.path);
      await fs.ensureDir(path.dirname(destPath));
      await fs.writeFile(destPath, file.content || '', 'utf8');
    }

    // Run semgrep with JS + React + security rule packs
    const result = spawnSync(
      'semgrep',
      [
        '--config', 'p/javascript',
        '--config', 'p/react',
        '--config', 'p/owasp-top-ten',
        '--json',
        '--quiet',
        tmpDir,
      ],
      { encoding: 'utf8', timeout: 60000 }
    );

    const output = result.stdout || '';
    if (!output.trim()) {
      return { issues: [], skipped: false };
    }

    let semgrepData;
    try {
      semgrepData = JSON.parse(output);
    } catch {
      return { issues: [], skipped: false };
    }

    for (const finding of (semgrepData.results || [])) {
      const filePath = finding.path.replace(tmpDir + path.sep, '').replace(tmpDir + '/', '').replace(/\\/g, '/');
      issues.push({
        file: filePath,
        line: finding.start?.line || 1,
        column: finding.start?.col || 1,
        endLine: finding.end?.line || finding.start?.line || 1,
        severity: mapSemgrepSeverity(finding.extra?.severity),
        ruleId: finding.check_id,
        message: finding.extra?.message || 'Security issue detected',
        engine: 'semgrep',
        category: 'security',
        metadata: finding.extra?.metadata || {},
      });
    }
  } catch (err) {
    console.warn('[Semgrep] Engine error:', err.message);
    return { issues: [], skipped: true, reason: err.message };
  } finally {
    try { await fs.remove(tmpDir); } catch {}
  }

  return { issues, skipped: false };
}

function mapSemgrepSeverity(sev) {
  if (!sev) return 'warning';
  const s = sev.toUpperCase();
  if (s === 'ERROR' || s === 'CRITICAL' || s === 'HIGH') return 'error';
  if (s === 'WARNING' || s === 'MEDIUM') return 'warning';
  return 'info';
}

module.exports = { runSemgrep, isSemgrepInstalled };
