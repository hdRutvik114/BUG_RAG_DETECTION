require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { analyzeGithub } = require('./src/routes/analyzeGithub');
const { analyzeFolder } = require('./src/routes/analyzeFolder');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'MERN Shield Backend is running' });
});

// Analysis routes
app.post('/api/analyze/github', analyzeGithub);
app.post('/api/analyze/folder', analyzeFolder);

app.listen(PORT, () => {
  console.log(`\n🛡️  MERN Shield Backend running on http://localhost:${PORT}`);
  console.log(`   GitHub Token: ${process.env.GITHUB_TOKEN ? '✅ Configured (5000 req/hr)' : '⚠️  Not set (60 req/hr)'}`);
});
