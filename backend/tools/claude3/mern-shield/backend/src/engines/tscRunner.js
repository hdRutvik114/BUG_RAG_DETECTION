/**
 * tscRunner.js
 * Runs TypeScript type checking on source files using a temp directory.
 * Gracefully skips if no .ts/.tsx files are present.
 */

const { execSync } = require('child_process');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

/**
 * Run TypeScript compiler (tsc) type checking on provided files.
 * @param {Array<{path, content}>} files
 * @returns {Array<{file, line, column, message, code, engine, severity, category}>}
 */
async function runTsc(files) {
  const tsFiles = files.filter(f => /\.(ts|tsx)$/.test(f.path));

  if (tsFiles.length === 0) {
    return []; // No TypeScript files — skip silently
  }

  const tmpDir = path.join(os.tmpdir(), `mern-shield-tsc-${Date.now()}`);
  const issues = [];

  try {
    await fs.ensureDir(tmpDir);

    // Write files to temp directory preserving structure
    for (const file of files) {
      const destPath = path.join(tmpDir, file.path);
      await fs.ensureDir(path.dirname(destPath));
      await fs.writeFile(destPath, file.content || '', 'utf8');
    }

    // Write a minimal tsconfig.json
    const tsconfig = {
      compilerOptions: {
        target: 'ES2020',
        module: 'ESNext',
        moduleResolution: 'bundler',
        jsx: 'react-jsx',
        strict: false,          // Don't be too strict — just find real errors
        noEmit: true,
        allowJs: true,
        checkJs: false,
        esModuleInterop: true,
        skipLibCheck: true,
        allowSyntheticDefaultImports: true,
        noUnusedLocals: true,
        noUnusedParameters: false,
        strictNullChecks: true,
      },
      include: ['**/*.ts', '**/*.tsx'],
      exclude: ['node_modules'],
    };
    await fs.writeJson(path.join(tmpDir, 'tsconfig.json'), tsconfig, { spaces: 2 });

    // Run tsc
    let output = '';
    try {
      execSync('npx tsc --noEmit', { cwd: tmpDir, stdio: 'pipe' });
    } catch (err) {
      output = (err.stdout || '').toString() + (err.stderr || '').toString();
    }

    // Parse tsc output: format is "path(line,col): error TS1234: message"
    const lines = output.split('\n');
    for (const line of lines) {
      const match = line.match(/^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+TS(\d+):\s+(.+)$/);
      if (match) {
        // Make path relative to project root (strip tmpDir prefix)
        const rawPath = match[1].replace(tmpDir + path.sep, '').replace(tmpDir + '/', '');
        issues.push({
          file: rawPath.replace(/\\/g, '/'),
          line: parseInt(match[2], 10),
          column: parseInt(match[3], 10),
          severity: match[4],
          code: `TS${match[5]}`,
          message: match[6].trim(),
          engine: 'typescript',
          category: 'type',
        });
      }
    }
  } catch (err) {
    console.warn('[TSC] Engine error:', err.message);
  } finally {
    // Clean up temp dir
    try { await fs.remove(tmpDir); } catch {}
  }

  return issues;
}

module.exports = { runTsc };
