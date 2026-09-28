/**
 * analyzeFolder.js — Route handler for POST /api/analyze/folder
 * Receives an array of {path, content} from the frontend folder drag-drop.
 */

const { filterFiles } = require('../fileFilter');
const { runAnalysis } = require('./analyzeGithub');

async function analyzeFolder(req, res) {
  const { files } = req.body;

  if (!files || !Array.isArray(files) || files.length === 0) {
    return res.status(400).json({ error: 'No files provided' });
  }

  console.log(`\n[MERN Shield] Analyzing uploaded folder: ${files.length} files received`);

  try {
    return await runAnalysis(files, res);
  } catch (err) {
    console.error('[Folder Route] Error:', err.message);
    return res.status(500).json({ error: err.message });
  }
}

module.exports = { analyzeFolder };
