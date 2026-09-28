/**
 * analyzeGithub.js — Route handler for POST /api/analyze/github
 */

const { fetchGithubRepo } = require('../githubFetcher');
const { shouldIncludeFile, filterFiles } = require('../fileFilter');
const { classifyProject } = require('../projectClassifier');
const { runEslint } = require('../engines/eslintRunner');
const { runTsc } = require('../engines/tscRunner');
const { runNpmAudit } = require('../engines/npmAuditRunner');
const { runSemgrep } = require('../engines/semgrepRunner');
const { buildReport } = require('../reportBuilder');

async function analyzeGithub(req, res) {
  const { url } = req.body;

  if (!url || !url.includes('github.com')) {
    return res.status(400).json({ error: 'Invalid or missing GitHub URL' });
  }

  try {
    console.log(`\n[MERN Shield] Analyzing GitHub repo: ${url}`);

    // 1. Fetch all source files from GitHub
    const rawFiles = await fetchGithubRepo(url, shouldIncludeFile, 300);

    // Also fetch package.json for npm audit (not filtered by shouldIncludeFile)
    let pkgFiles = [];
    try {
      const { parseGithubUrl } = require('../githubFetcher');
      const { owner, repo } = parseGithubUrl(url);
      const axios = require('axios');
      const headers = process.env.GITHUB_TOKEN
        ? { Authorization: `token ${process.env.GITHUB_TOKEN}`, Accept: 'application/vnd.github.v3+json' }
        : { Accept: 'application/vnd.github.v3+json' };
      const pkgRes = await axios.get(`https://api.github.com/repos/${owner}/${repo}/contents/package.json`, { headers });
      if (pkgRes.data?.content) {
        pkgFiles.push({
          path: 'package.json',
          content: Buffer.from(pkgRes.data.content, 'base64').toString('utf8'),
        });
      }
    } catch {}

    const allFiles = [...rawFiles, ...pkgFiles];

    return runAnalysis(allFiles, res);
  } catch (err) {
    console.error('[GitHub Route] Error:', err.message);
    const msg = err.response?.status === 404 ? 'Repository not found or is private' : err.message;
    return res.status(500).json({ error: msg });
  }
}

async function runAnalysis(allFiles, res) {
  // 2. Filter and classify files
  const filteredFiles = filterFiles(allFiles);
  const projectInfo = classifyProject(allFiles);

  console.log(`[Analysis] ${filteredFiles.length} source files | Type: ${projectInfo.type} | Frameworks: ${projectInfo.frameworks.join(', ')}`);

  // 3. Run all 4 engines in parallel
  const hasReact = projectInfo.frameworks.includes('react');
  const [eslintIssues, tscIssues, npmAuditIssues, semgrepResult] = await Promise.all([
    runEslint(filteredFiles, projectInfo.hasTypeScript, hasReact),
    runTsc(filteredFiles),
    runNpmAudit(allFiles),
    runSemgrep(filteredFiles),
  ]);

  console.log(`[Analysis] Issues — ESLint: ${eslintIssues.length} | TSC: ${tscIssues.length} | npm audit: ${npmAuditIssues.length} | Semgrep: ${(semgrepResult.issues || []).length}`);

  // 4. Build unified report
  const report = buildReport({
    files: filteredFiles,
    projectInfo,
    eslintIssues,
    tscIssues,
    npmAuditIssues,
    semgrepResult,
  });

  return res.json(report);
}

module.exports = { analyzeGithub, runAnalysis };
