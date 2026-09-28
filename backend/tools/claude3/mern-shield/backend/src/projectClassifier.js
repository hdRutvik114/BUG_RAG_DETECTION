/**
 * projectClassifier.js
 * Detects project type, structure, and libraries from file paths and package.json content.
 */

const FRAMEWORK_SIGNATURES = {
  react:        { files: [/\.jsx$/i, /\.tsx$/i], deps: ['react', 'react-dom'] },
  redux:        { files: [], deps: ['redux', '@reduxjs/toolkit', 'react-redux'] },
  reactQuery:   { files: [], deps: ['@tanstack/react-query', 'react-query'] },
  mongoose:     { files: [], deps: ['mongoose'] },
  express:      { files: [], deps: ['express'] },
  next:         { files: [/\/pages\//i, /\/app\//i], deps: ['next'] },
  vite:         { files: [/vite\.config/i], deps: ['vite'] },
  typescript:   { files: [/\.tsx?$/], deps: ['typescript'] },
  tailwind:     { files: [], deps: ['tailwindcss'] },
  axios:        { files: [], deps: ['axios'] },
  jwt:          { files: [], deps: ['jsonwebtoken'] },
  bcrypt:       { files: [], deps: ['bcrypt', 'bcryptjs'] },
  socket:       { files: [], deps: ['socket.io', 'socket.io-client'] },
  zustand:      { files: [], deps: ['zustand'] },
  prisma:       { files: [], deps: ['prisma', '@prisma/client'] },
};

/**
 * Detect project structure type from file paths.
 * @param {string[]} filePaths
 * @returns {'fullstack-monorepo'|'react-only'|'express-only'|'next-js'|'unknown'}
 */
function detectStructureType(filePaths) {
  const hasFrontend = filePaths.some(p => /^frontend\//i.test(p) || /^client\//i.test(p));
  const hasBackend = filePaths.some(p => /^backend\//i.test(p) || /^server\//i.test(p));
  const hasNext = filePaths.some(p => /\/pages\//i.test(p) || /\/app\/page\./i.test(p));
  const hasReact = filePaths.some(p => /\.jsx?$/i.test(p) && /\/(components?|pages?|src)\//i.test(p));
  const hasExpress = filePaths.some(p => /\/(routes?|controllers?|middleware)\//i.test(p));

  if (hasFrontend && hasBackend) return 'fullstack-monorepo';
  if (hasNext) return 'next-js';
  if (hasReact && hasExpress) return 'fullstack-single';
  if (hasReact) return 'react-only';
  if (hasExpress) return 'express-only';
  return 'unknown';
}

/**
 * Parse package.json content to get all declared dependencies.
 * @param {string} packageJsonContent
 * @returns {string[]} flat list of dependency names
 */
function parseDependencies(packageJsonContent) {
  try {
    const pkg = JSON.parse(packageJsonContent);
    return [
      ...Object.keys(pkg.dependencies || {}),
      ...Object.keys(pkg.devDependencies || {}),
    ];
  } catch {
    return [];
  }
}

/**
 * Detect which frameworks/libraries are used.
 * @param {string[]} filePaths
 * @param {string[]} declaredDeps
 * @returns {string[]}
 */
function detectFrameworks(filePaths, declaredDeps) {
  const detected = [];
  const depsSet = new Set(declaredDeps.map(d => d.toLowerCase()));

  for (const [name, sig] of Object.entries(FRAMEWORK_SIGNATURES)) {
    const matchesDep = sig.deps.some(d => depsSet.has(d.toLowerCase()));
    const matchesFile = sig.files.some(pattern => filePaths.some(p => pattern.test(p)));
    if (matchesDep || matchesFile) detected.push(name);
  }

  return detected;
}

/**
 * Main classifier function.
 * @param {Array<{path, content}>} files
 * @returns {{ type, frameworks, hasFrontend, hasBackend, hasTypeScript, packageJson }}
 */
function classifyProject(files) {
  const filePaths = files.map(f => f.path);

  // Find package.json files (skip nested ones inside node_modules)
  const pkgFile = files.find(f =>
    /^package\.json$/i.test(f.path) ||
    /^(frontend|backend|client|server)\/package\.json$/i.test(f.path)
  );

  const declaredDeps = pkgFile ? parseDependencies(pkgFile.content || '') : [];
  const frameworks = detectFrameworks(filePaths, declaredDeps);
  const type = detectStructureType(filePaths);

  const hasTypeScript = filePaths.some(p => /\.(ts|tsx)$/.test(p));
  const hasFrontend = filePaths.some(p => /^(frontend|client)\//i.test(p));
  const hasBackend = filePaths.some(p => /^(backend|server)\//i.test(p));

  return {
    type,
    frameworks,
    hasTypeScript,
    hasFrontend,
    hasBackend,
    declaredDeps,
  };
}

module.exports = { classifyProject };
