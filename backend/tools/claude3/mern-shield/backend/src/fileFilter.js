/**
 * fileFilter.js
 * Decides which files from a project tree are worth analysing.
 * Returns only source JS/TS files, ignoring generated/tool/config files.
 */

const VALID_EXTENSIONS = new Set(['.js', '.jsx', '.ts', '.tsx']);

// Folder segments that disqualify a file from analysis
const IGNORE_DIRS = new Set([
  'node_modules', 'build', 'dist', '.git', '.next', 'out',
  'coverage', '.cache', '__pycache__', 'public', 'static',
  '.vscode', '.idea', 'tmp', 'temp', 'vendor',
]);

// Filename substrings/patterns that disqualify a file
const IGNORE_PATTERNS = [
  /\.test\.(js|jsx|ts|tsx)$/i,
  /\.spec\.(js|jsx|ts|tsx)$/i,
  /\.min\.js$/i,
  /\.d\.ts$/i,
  /setupTests/i,
  /reportWebVitals/i,
  /serviceWorker/i,
  /sw\.js$/i,
  /polyfill/i,
  /webpack\.config/i,
  /babel\.config/i,
  /jest\.config/i,
  /vite\.config/i,
  /rollup\.config/i,
  /\.stories\./i,
];

// Priority source directories — files in these are always candidates
const PRIORITY_DIRS = new Set([
  'src', 'components', 'pages', 'hooks', 'utils', 'helpers',
  'controllers', 'routes', 'models', 'middleware', 'services',
  'api', 'lib', 'context', 'store', 'redux', 'slices', 'config',
  'server', 'app', 'features', 'views',
]);

/**
 * Given a relative file path, return true if it should be analysed.
 * @param {string} filePath - e.g. "frontend/src/pages/Login.jsx"
 */
function shouldIncludeFile(filePath) {
  const normalised = filePath.replace(/\\/g, '/');
  const parts = normalised.split('/');
  const filename = parts[parts.length - 1];
  const ext = '.' + filename.split('.').pop();

  // Must have a valid JS/TS extension
  if (!VALID_EXTENSIONS.has(ext)) return false;

  // Check each directory segment
  for (const part of parts.slice(0, -1)) {
    if (IGNORE_DIRS.has(part.toLowerCase())) return false;
  }

  // Check filename against ignore patterns
  for (const pattern of IGNORE_PATTERNS) {
    if (pattern.test(filename)) return false;
  }

  return true;
}

/**
 * Determine the role/category of a file based on its path.
 * @param {string} filePath
 * @returns {'component'|'hook'|'route'|'controller'|'model'|'middleware'|'utility'|'store'|'config'|'entry'|'unknown'}
 */
function classifyFileRole(filePath) {
  const lower = filePath.toLowerCase().replace(/\\/g, '/');

  if (/\/hooks?\//i.test(lower) || /use[A-Z]/.test(filePath)) return 'hook';
  if (/\/controllers?\//i.test(lower)) return 'controller';
  if (/\/routes?\//i.test(lower)) return 'route';
  if (/\/models?\//i.test(lower)) return 'model';
  if (/\/middleware\//i.test(lower)) return 'middleware';
  if (/\/(store|redux|slices?|context)\//i.test(lower)) return 'store';
  if (/\/(config|settings)\//i.test(lower)) return 'config';
  if (/\/(components?|ui|views?|pages?)\//i.test(lower)) return 'component';
  if (/\/(utils?|helpers?|lib|services?|api)\//i.test(lower)) return 'utility';
  if (/\/(index|main|app)\.(js|jsx|ts|tsx)$/i.test(lower)) return 'entry';

  return 'unknown';
}

/**
 * Filter an array of file paths and return only the relevant ones with metadata.
 * @param {Array<{path: string, content?: string, size?: number}>} files
 * @returns {Array<{path: string, role: string, content?: string}>}
 */
function filterFiles(files) {
  return files
    .filter(f => shouldIncludeFile(f.path))
    .map(f => ({
      ...f,
      role: classifyFileRole(f.path),
    }));
}

module.exports = { shouldIncludeFile, classifyFileRole, filterFiles };
