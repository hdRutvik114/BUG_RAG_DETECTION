/**
 * eslintRunner.js
 * Runs ESLint programmatically on provided source files using the Node.js API.
 * No CLI invocation needed — uses the ESLint class directly.
 */

const { ESLint } = require('eslint');

/**
 * Build ESLint configuration based on detected project features.
 */
function buildEslintConfig(hasTypeScript, hasReact) {
  const plugins = [];
  const extendsArr = ['eslint:recommended'];
  const parser = hasTypeScript ? '@typescript-eslint/parser' : undefined;
  const parserOptions = {
    ecmaVersion: 2022,
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  };

  if (hasReact) {
    plugins.push('react', 'react-hooks');
    extendsArr.push('plugin:react/recommended', 'plugin:react-hooks/recommended');
  }

  if (hasTypeScript) {
    plugins.push('@typescript-eslint');
    extendsArr.push('plugin:@typescript-eslint/recommended');
  }

  return {
    useEslintrc: false,
    overrideConfig: {
      parser,
      parserOptions,
      plugins,
      extends: extendsArr,
      rules: {
        // Catch common MERN bugs
        'no-unused-vars': 'warn',
        'no-undef': 'error',
        'no-unreachable': 'error',
        'no-constant-condition': 'warn',
        'no-async-promise-executor': 'error',
        'no-await-in-loop': 'warn',
        'require-await': 'warn',
        'no-return-await': 'warn',
        'no-promise-executor-return': 'error',
        'no-unsafe-finally': 'error',
        'eqeqeq': ['warn', 'smart'],
        'no-eval': 'error',
        'no-implied-eval': 'error',
        'no-new-func': 'error',
        // React specific
        ...(hasReact ? {
          'react/prop-types': 'off',
          'react/react-in-jsx-scope': 'off',
          'react-hooks/rules-of-hooks': 'error',
          'react-hooks/exhaustive-deps': 'warn',
        } : {}),
      },
      env: {
        browser: true,
        node: true,
        es2022: true,
      },
      settings: hasReact ? { react: { version: 'detect' } } : {},
    },
  };
}

/**
 * Run ESLint on an array of source files.
 * @param {Array<{path, content}>} files
 * @param {boolean} hasTypeScript
 * @param {boolean} hasReact
 * @returns {Array<{file, line, column, severity, ruleId, message, engine}>}
 */
async function runEslint(files, hasTypeScript = false, hasReact = true) {
  const issues = [];

  try {
    const config = buildEslintConfig(hasTypeScript, hasReact);
    const eslint = new ESLint(config);

    for (const file of files) {
      try {
        // Skip if no content or very small file
        if (!file.content || file.content.trim().length < 10) continue;

        const results = await eslint.lintText(file.content, {
          filePath: file.path,
          warnIgnored: false,
        });

        for (const result of results) {
          for (const msg of result.messages) {
            issues.push({
              file: file.path,
              line: msg.line || 1,
              column: msg.column || 1,
              endLine: msg.endLine || msg.line || 1,
              severity: msg.severity === 2 ? 'error' : 'warning',
              ruleId: msg.ruleId || 'unknown',
              message: msg.message,
              engine: 'eslint',
              category: categoriseEslintRule(msg.ruleId),
            });
          }
        }
      } catch (fileErr) {
        // Skip unparseable files silently
      }
    }
  } catch (err) {
    console.warn('[ESLint] Engine error:', err.message);
  }

  return issues;
}

/**
 * Map an ESLint rule ID to a high-level category.
 */
function categoriseEslintRule(ruleId) {
  if (!ruleId) return 'logic';
  if (ruleId.includes('security') || ruleId.includes('eval') || ruleId.includes('injection')) return 'security';
  if (ruleId.includes('hook') || ruleId.includes('react')) return 'react';
  if (ruleId.includes('async') || ruleId.includes('await') || ruleId.includes('promise')) return 'async';
  if (ruleId.includes('typescript') || ruleId.includes('type')) return 'type';
  return 'logic';
}

module.exports = { runEslint };
