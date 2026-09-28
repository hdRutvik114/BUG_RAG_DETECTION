/**
 * githubFetcher.js
 * Fetches the source file tree and file contents from a public GitHub repo
 * using the GitHub REST API (no git clone required).
 */

const axios = require('axios');

const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';

function makeHeaders() {
  const headers = { Accept: 'application/vnd.github.v3+json' };
  if (GITHUB_TOKEN) headers['Authorization'] = `token ${GITHUB_TOKEN}`;
  return headers;
}

/**
 * Parse a GitHub URL into { owner, repo }
 * Handles:
 *   https://github.com/user/repo
 *   https://github.com/user/repo.git
 *   https://github.com/user/repo/tree/branch
 */
function parseGithubUrl(url) {
  const cleaned = url.trim().replace(/\.git$/, '').replace(/\/$/, '');
  const match = cleaned.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) throw new Error(`Invalid GitHub URL: ${url}`);
  return { owner: match[1], repo: match[2] };
}

/**
 * Get the default branch of a repository.
 */
async function getDefaultBranch(owner, repo) {
  const url = `https://api.github.com/repos/${owner}/${repo}`;
  const { data } = await axios.get(url, { headers: makeHeaders() });
  return data.default_branch || 'main';
}

/**
 * Fetch the full recursive file tree of a repo.
 * @returns {Array<{path, type, sha, size, url}>}
 */
async function fetchFileTree(owner, repo, branch) {
  const url = `https://api.github.com/repos/${owner}/${repo}/git/trees/${branch}?recursive=1`;
  const { data } = await axios.get(url, { headers: makeHeaders() });

  if (data.truncated) {
    console.warn('[GitHub] File tree was truncated (>100k files) — large monorepo?');
  }

  return (data.tree || []).filter(item => item.type === 'blob');
}

/**
 * Fetch the decoded content of a single file.
 * @returns {string} decoded file content
 */
async function fetchFileContent(owner, repo, filePath) {
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(filePath)}`;
  const { data } = await axios.get(url, { headers: makeHeaders() });
  if (data.encoding === 'base64') {
    return Buffer.from(data.content, 'base64').toString('utf8');
  }
  return data.content || '';
}

/**
 * Main entry: given a GitHub URL and a filter function, fetch all relevant files.
 * @param {string} githubUrl
 * @param {function} filterFn - (path: string) => boolean
 * @param {number} maxFiles - safety cap
 * @returns {Array<{path, content, size}>}
 */
async function fetchGithubRepo(githubUrl, filterFn, maxFiles = 300) {
  const { owner, repo } = parseGithubUrl(githubUrl);
  console.log(`[GitHub] Fetching: ${owner}/${repo}`);

  const branch = await getDefaultBranch(owner, repo);
  console.log(`[GitHub] Default branch: ${branch}`);

  const tree = await fetchFileTree(owner, repo, branch);
  console.log(`[GitHub] Total files in tree: ${tree.length}`);

  const relevant = tree.filter(f => filterFn(f.path)).slice(0, maxFiles);
  console.log(`[GitHub] Filtered to ${relevant.length} relevant files`);

  // Fetch file contents in batches of 10 (rate-limit friendly)
  const results = [];
  const BATCH_SIZE = 10;

  for (let i = 0; i < relevant.length; i += BATCH_SIZE) {
    const batch = relevant.slice(i, i + BATCH_SIZE);
    const fetched = await Promise.all(
      batch.map(async (f) => {
        try {
          const content = await fetchFileContent(owner, repo, f.path);
          return { path: f.path, content, size: f.size || 0 };
        } catch (err) {
          console.warn(`[GitHub] Failed to fetch ${f.path}: ${err.message}`);
          return null;
        }
      })
    );
    results.push(...fetched.filter(Boolean));
  }

  return results;
}

module.exports = { fetchGithubRepo, parseGithubUrl };
