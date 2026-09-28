import React, { useState, useEffect } from 'react';
import { GitBranch, Upload, Code2, Zap, AlertCircle, ChevronDown } from 'lucide-react';
import DirectCodeModal from './DirectCodeModal';

const SCAN_MODES = [
  { id: 'git',    label: 'GitHub URL',     icon: GitBranch },
  { id: 'zip',    label: 'Upload ZIP',     icon: Upload    },
  { id: 'direct', label: 'Code Snippet',   icon: Code2     },
];

const THRESHOLD_OPTIONS = [
  { value: 0.30, label: '0.30 — Sensitive (more results)' },
  { value: 0.50, label: '0.50 — Balanced (recommended)' },
  { value: 0.70, label: '0.70 — Strict (fewer results)' },
  { value: 0.80, label: '0.80 — High Confidence' },
];

export default function GitPortal({ onStartScan, isScanning }) {
  const [mode, setMode] = useState('git');
  const [gitUrl, setGitUrl] = useState('');
  const [zipFile, setZipFile] = useState(null);
  const [threshold, setThreshold] = useState(0.50);
  const [suggestions, setSuggestions] = useState([]);
  const [error, setError] = useState('');
  const [isDirectModalOpen, setIsDirectModalOpen] = useState(false);

  useEffect(() => {
    fetch('/api/dataset/suggestions')
      .then(r => r.json())
      .then(d => setSuggestions(d.suggestions || []))
      .catch(() => {});
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (mode === 'git') {
      if (!gitUrl.trim()) { setError('Please enter a GitHub repository URL.'); return; }
      if (!gitUrl.startsWith('http')) { setError('Please enter a valid URL starting with http.'); return; }
      onStartScan({ type: 'git', gitUrl: gitUrl.trim(), threshold });
    } else if (mode === 'zip') {
      if (!zipFile) { setError('Please select a ZIP file.'); return; }
      onStartScan({ type: 'zip', zipFile, threshold });
    }
  };

  const handleDirectScan = (code, fileName) => {
    onStartScan({ type: 'direct', code, fileName, threshold });
  };

  return (
    <>
      <div className="max-w-2xl mx-auto">
        <div className="ui-card overflow-hidden border border-[#1f293d] bg-[#111827]">
          
          {/* Mode Tabs */}
          <div className="flex border-b border-[#1f293d] bg-[#0b0f19]">
            {SCAN_MODES.map((m) => {
              const Icon = m.icon;
              const isActive = mode === m.id;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => { setMode(m.id); setError(''); if (m.id === 'direct') setIsDirectModalOpen(true); }}
                  className={`flex-1 flex items-center justify-center gap-2 py-3 px-4 text-xs font-medium transition-colors border-b-2 ${
                    isActive
                      ? 'border-blue-500 text-white bg-[#111827]'
                      : 'border-transparent text-slate-400 hover:text-white'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {m.label}
                </button>
              );
            })}
          </div>

          {/* Form Body */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4">

            {/* Git URL Input */}
            {mode === 'git' && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white">
                  GitHub Repository URL <span className="text-red-400">*</span>
                </label>
                <input
                  type="url"
                  value={gitUrl}
                  onChange={e => setGitUrl(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  className="w-full px-3.5 py-2.5 bg-[#0b0f19] border border-[#1f293d] rounded-md text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                {/* Sample Repos */}
                {suggestions.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className="text-[11px] text-slate-400">Sample Repos:</span>
                    {suggestions.slice(0, 3).map((s, i) => {
                      const urlStr = typeof s === 'string' ? s : (s?.url || s?.name || '');
                      const labelStr = typeof s === 'string' 
                        ? s.replace('https://github.com/', '') 
                        : (s?.name || s?.url || 'repo').replace('https://github.com/', '');
                      return (
                        <button
                          key={i}
                          type="button"
                          onClick={() => setGitUrl(urlStr)}
                          className="text-[11px] px-2 py-0.5 rounded bg-[#1f293d] hover:bg-slate-700 text-slate-200 border border-slate-700 transition font-mono truncate max-w-[200px]"
                        >
                          {labelStr}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ZIP Upload */}
            {mode === 'zip' && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white">
                  ZIP Archive <span className="text-red-400">*</span>
                </label>
                <label className="flex flex-col items-center justify-center w-full h-28 border-2 border-dashed border-[#1f293d] rounded-md cursor-pointer bg-[#0b0f19] hover:border-blue-500 transition-colors">
                  <div className="flex flex-col items-center gap-1 text-slate-400">
                    <Upload className="w-5 h-5 text-slate-300" />
                    <span className="text-xs text-white">
                      {zipFile ? zipFile.name : 'Select or drop ZIP file here'}
                    </span>
                    <span className="text-[11px] text-slate-400">.zip files containing source code</span>
                  </div>
                  <input
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={e => setZipFile(e.target.files?.[0] || null)}
                  />
                </label>
              </div>
            )}

            {/* Direct Code mode */}
            {mode === 'direct' && (
              <div className="flex flex-col items-center justify-center py-6 text-slate-400 gap-3 bg-[#0b0f19] rounded-md border border-[#1f293d]">
                <Code2 className="w-7 h-7 text-blue-400" />
                <p className="text-xs text-white">Analyze JavaScript or TypeScript code snippets.</p>
                <button
                  type="button"
                  onClick={() => setIsDirectModalOpen(true)}
                  className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
                >
                  Open Code Editor
                </button>
              </div>
            )}

            {/* Threshold Selector */}
            {mode !== 'direct' && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white">
                  Detection Sensitivity
                </label>
                <div className="relative">
                  <select
                    value={threshold}
                    onChange={e => setThreshold(parseFloat(e.target.value))}
                    className="w-full appearance-none px-3.5 py-2.5 bg-[#0b0f19] border border-[#1f293d] rounded-md text-xs text-white focus:outline-none focus:border-blue-500 transition-colors pr-8 cursor-pointer"
                  >
                    {THRESHOLD_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value} className="bg-[#111827] text-white">{opt.label}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-950/40 border border-red-800/60 px-3 py-2 rounded-md">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Submit */}
            {mode !== 'direct' && (
              <div className="flex justify-end pt-1">
                <button
                  type="submit"
                  disabled={isScanning}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                >
                  <Zap className="w-4 h-4" />
                  Analyze Repository
                </button>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* Direct Code Modal */}
      <DirectCodeModal
        isOpen={isDirectModalOpen}
        onClose={() => { setIsDirectModalOpen(false); setMode('git'); }}
        onRunDirectScan={handleDirectScan}
      />
    </>
  );
}
