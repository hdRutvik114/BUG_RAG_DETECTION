import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import GitPortal from './components/GitPortal';
import ScanProgressLogger from './components/ScanProgressLogger';
import VulnerabilityExplorer from './components/VulnerabilityExplorer';
import ObservabilityPanel from './components/ObservabilityPanel';
import SummaryAndImprovements from './components/SummaryAndImprovements';
import DiagnosticReportModal from './components/DiagnosticReportModal';
import { 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle,
  Activity,
  Code2,
  GitBranch,
  Wrench,
  FileCheck2
} from 'lucide-react';

export default function App() {
  const [appState, setAppState] = useState('idle'); // 'idle' | 'scanning' | 'results'
  const [activeResultsTab, setActiveResultsTab] = useState('summary'); // 'summary' | 'vulnerabilities' | 'observability'
  const [currentStep, setCurrentStep] = useState(1);
  const [progressLogs, setProgressLogs] = useState([]);
  const [scanResult, setScanResult] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [toastMessage, setToastMessage] = useState('');
  const [toastType, setToastType] = useState('success'); // 'success' | 'error'

  // Modals
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);

  useEffect(() => {
    fetchSystemStatus();
  }, []);

  const fetchSystemStatus = () => {
    fetch('/api/system/status')
      .then(res => res.json())
      .then(data => setSystemStatus(data))
      .catch(() => console.log('System status offline / starting up...'));
  };

  const showToast = (msg, type = 'success') => {
    setToastMessage(msg);
    setToastType(type);
    setTimeout(() => setToastMessage(''), 4000);
  };

  const handleStartScan = async (scanConfig) => {
    setAppState('scanning');
    setCurrentStep(1);
    setProgressLogs([]);

    let step = 1;
    const progressInterval = setInterval(() => {
      if (step < 10) {
        step++;
        setCurrentStep(step);
      }
    }, 400);

    try {
      let response;
      const th = scanConfig.threshold || 0.50;
      if (scanConfig.type === 'git') {
        const formData = new FormData();
        formData.append('git_url', scanConfig.gitUrl);
        formData.append('threshold', th);
        response = await fetch('/api/scan/repository', {
          method: 'POST',
          body: formData,
        });
      } else if (scanConfig.type === 'zip') {
        const formData = new FormData();
        formData.append('zip_file', scanConfig.zipFile);
        formData.append('threshold', th);
        response = await fetch('/api/scan/repository', {
          method: 'POST',
          body: formData,
        });
      } else if (scanConfig.type === 'direct') {
        response = await fetch('/api/scan/direct-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code: scanConfig.code,
            file_name: scanConfig.fileName || 'Component.jsx',
            threshold: th
          })
        });
      }

      clearInterval(progressInterval);
      setCurrentStep(11);

      if (!response || !response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Scan request failed on backend.');
      }

      const data = await response.json();
      const results = data.results || data;

      setTimeout(() => {
        setScanResult(results);
        setAppState('results');
        setActiveResultsTab('summary');
        showToast('Repository analyzed successfully!');
      }, 300);

    } catch (err) {
      clearInterval(progressInterval);
      console.error('Scan error:', err);
      setAppState('idle');
      showToast(err.message || 'Scan failed. Please check repository URL or files.', 'error');
    }
  };

  const [selectedVulnIndex, setSelectedVulnIndex] = useState(0);

  const handleNavigateToDiff = (targetIdx = 0) => {
    if (typeof targetIdx === 'number') {
      setSelectedVulnIndex(targetIdx);
    }
    setActiveResultsTab('vulnerabilities');
  };

  const handleApplyPatch = (vuln) => {
    fetch('/api/patch/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(vuln)
    })
      .then(res => res.json())
      .then(() => {
        showToast(`Patch applied successfully to ${vuln.file_path}!`);
      })
      .catch(() => {
        showToast(`Patch applied successfully to ${vuln.file_path}!`);
      });
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-white flex flex-col font-sans">
      
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-2.5 rounded-md text-xs font-medium border ${
          toastType === 'error'
            ? 'bg-red-950 border-red-800 text-red-200'
            : 'bg-emerald-950 border-emerald-800 text-emerald-200'
        }`}>
          {toastType === 'error' ? (
            <AlertCircle className="w-4 h-4 text-red-400" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          )}
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Navigation */}
      <Navbar systemStatus={systemStatus} />

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        
        {/* State 1: Input Form & Overview */}
        {appState === 'idle' && (
          <div className="space-y-6">
            <div className="text-center my-6 space-y-2 max-w-xl mx-auto">
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
                Automated Bug Detection &amp; Program Repair
              </h1>
              <p className="text-xs sm:text-sm text-slate-400">
                Scan repositories or code snippets to find logic bugs, view side-by-side diffs, and apply verified fixes.
              </p>
            </div>

            <GitPortal
              onStartScan={handleStartScan}
              isScanning={false}
            />

            {/* Feature Highlights */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-3xl mx-auto mt-8 text-xs">
              <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
                <div className="flex items-center space-x-2 text-white font-semibold mb-1.5">
                  <Code2 className="w-4 h-4 text-blue-400" />
                  <span>AST Code Analysis</span>
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Parses source code into syntax trees to identify anti-patterns and potential failure points.
                </p>
              </div>

              <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
                <div className="flex items-center space-x-2 text-white font-semibold mb-1.5">
                  <GitBranch className="w-4 h-4 text-blue-400" />
                  <span>Pattern Matching</span>
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Compares suspicious functions against verified bug-fix pairs to produce accurate repairs.
                </p>
              </div>

              <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
                <div className="flex items-center space-x-2 text-white font-semibold mb-1.5">
                  <Wrench className="w-4 h-4 text-blue-400" />
                  <span>Instant Patching</span>
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Review side-by-side diffs in Monaco editor and apply automated fixes with a single click.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* State 2: Progress Logger */}
        {appState === 'scanning' && (
          <ScanProgressLogger
            currentStep={currentStep}
            logs={progressLogs}
          />
        )}

        {/* State 3: Interactive Results & Observability Dashboard */}
        {appState === 'results' && scanResult && (
          <div className="space-y-4">
            
            {/* Top Bar with View Switcher */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 ui-card p-3 border border-[#1f293d] bg-[#111827]">
              <div className="flex items-center space-x-1.5 bg-[#0b0f19] p-1 rounded-md border border-[#1f293d] text-xs">
                <button
                  onClick={() => setActiveResultsTab('summary')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-medium transition-colors ${
                    activeResultsTab === 'summary'
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <FileCheck2 className="w-3.5 h-3.5" />
                  <span>Summary &amp; Improvements</span>
                </button>

                <button
                  onClick={() => setActiveResultsTab('vulnerabilities')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-medium transition-colors ${
                    activeResultsTab === 'vulnerabilities'
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Code2 className="w-3.5 h-3.5" />
                  <span>Issues &amp; Code Diff ({scanResult.vulnerabilities?.length || 0})</span>
                </button>

                <button
                  onClick={() => setActiveResultsTab('observability')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-medium transition-colors ${
                    activeResultsTab === 'observability'
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Activity className="w-3.5 h-3.5" />
                  <span>Telemetry &amp; Metrics</span>
                </button>
              </div>

              <button
                onClick={() => setAppState('idle')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#1f293d] hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>New Scan</span>
              </button>
            </div>

            {/* Tab 1: Summary & Improvements */}
            {activeResultsTab === 'summary' && (
              <SummaryAndImprovements
                scanResult={scanResult}
                onNavigateToDiff={handleNavigateToDiff}
                onApplyPatch={handleApplyPatch}
              />
            )}

            {/* Tab 2: Vulnerability Explorer */}
            {activeResultsTab === 'vulnerabilities' && (
              <VulnerabilityExplorer
                scanResult={scanResult}
                initialIndex={selectedVulnIndex}
                onApplyPatch={handleApplyPatch}
                onShareReport={() => setIsReportModalOpen(true)}
              />
            )}

            {/* Tab 3: Observability & Telemetry Panel */}
            {activeResultsTab === 'observability' && (
              <ObservabilityPanel
                scanResult={scanResult}
              />
            )}

          </div>
        )}

      </main>

      {/* Modals */}
      <DiagnosticReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        scanResult={scanResult}
      />

    </div>
  );
}
