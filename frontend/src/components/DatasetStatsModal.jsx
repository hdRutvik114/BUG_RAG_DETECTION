import React, { useState, useEffect } from 'react';
import { X, Layers, Database, GitCommit, Search, Shield, PieChart, ArrowRight, ExternalLink } from 'lucide-react';

export default function DatasetStatsModal({ isOpen, onClose }) {
  const [stats, setStats] = useState(null);
  const [samples, setSamples] = useState([]);
  const [selectedBugType, setSelectedBugType] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);

    Promise.all([
      fetch('/api/dataset/stats').then(res => res.json()),
      fetch('/api/dataset/samples?limit=30').then(res => res.json())
    ])
      .then(([statsData, samplesData]) => {
        setStats(statsData);
        setSamples(samplesData.samples || []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error loading dataset stats:", err);
        setLoading(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  const filteredSamples = samples.filter(s => {
    const matchesType = selectedBugType === 'all' || s.bug_type?.toLowerCase() === selectedBugType.toLowerCase();
    const matchesSearch = !searchQuery || 
      s.commit_message?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.project_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.bug_type?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesType && matchesSearch;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-4xl ui-card border border-slate-800/90 shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800/80 flex items-center justify-between bg-[#070c17]/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-cyan-950/60 text-cyan-400 border border-cyan-800/50 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Bug-Fix Benchmark Dataset
                <span className="text-xs px-2.5 py-0.5 rounded-full font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                  478 Verified Pairs
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Mined historical bug-fix pairs used for pattern matching and repair synthesis.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/80 transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 bg-[#090e1a]/95">
          
          {/* Key Metrics Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <div className="text-xs text-slate-400 font-medium">Total Indexed Pairs</div>
              <div className="text-xl font-extrabold text-white mt-1 font-mono">{stats?.total_pairs || 478}</div>
              <div className="text-[11px] text-slate-500 mt-0.5">Buggy &amp; Fixed Code</div>
            </div>

            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <div className="text-xs text-slate-400 font-medium">AST Vector Dimensions</div>
              <div className="text-xl font-extrabold text-cyan-400 mt-1 font-mono">120-D</div>
              <div className="text-[11px] text-slate-500 mt-0.5">Structural Geometry</div>
            </div>

            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <div className="text-xs text-slate-400 font-medium">Boundary Check Fixes</div>
              <div className="text-xl font-extrabold text-emerald-400 mt-1 font-mono">
                {stats?.delta_metrics?.total_boundary_check_fixes || 312}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">Defensive Guard Fixes</div>
            </div>

            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <div className="text-xs text-slate-400 font-medium">Async / Await Fixes</div>
              <div className="text-xl font-extrabold text-amber-400 mt-1 font-mono">
                {stats?.delta_metrics?.total_async_await_fixes || 148}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">Promise Timing Fixes</div>
            </div>
          </div>

          {/* Bug Types & Severity Distribution */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
                <PieChart className="w-4 h-4 text-cyan-400" />
                <span>Bug Types Distribution</span>
              </h4>
              <div className="space-y-2">
                {stats?.bug_types && Object.entries(stats.bug_types).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-xs font-medium">
                    <span className="text-slate-300">{type}</span>
                    <span className="font-mono font-bold text-cyan-300 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/60">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#030712] border border-slate-800">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
                <Shield className="w-4 h-4 text-emerald-400" />
                <span>Severity Classifications</span>
              </h4>
              <div className="space-y-2">
                {stats?.severities && Object.entries(stats.severities).map(([sev, count]) => (
                  <div key={sev} className="flex items-center justify-between text-xs font-medium">
                    <span className="text-slate-300">{sev}</span>
                    <span className="font-mono font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Search & Filter Historical Samples Table */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <h4 className="text-xs font-bold text-white flex items-center gap-2">
                <GitCommit className="w-4 h-4 text-cyan-400" />
                <span>Historical Bug-Fix Samples</span>
              </h4>
              <div className="relative w-full sm:w-64">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search commits or repo..."
                  className="w-full pl-8 pr-3 py-1.5 bg-[#030712] border border-slate-800 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500/80"
                />
              </div>
            </div>

            {/* Table */}
            <div className="rounded-xl border border-slate-800 overflow-hidden bg-[#030712]">
              <div className="max-h-60 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#070c17] text-slate-400 font-mono text-[10px] uppercase sticky top-0 border-b border-slate-800">
                    <tr>
                      <th className="p-3">ID</th>
                      <th className="p-3">Repository</th>
                      <th className="p-3">Bug Category</th>
                      <th className="p-3">Severity</th>
                      <th className="p-3">Structural Fix</th>
                      <th className="p-3">Commit Message</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300 font-medium">
                    {filteredSamples.map((s) => (
                      <tr key={s.pair_id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="p-3 font-mono text-cyan-400 font-bold">#{s.pair_id}</td>
                        <td className="p-3 truncate max-w-[120px] font-mono text-slate-400">{s.project_name}</td>
                        <td className="p-3">{s.bug_type}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            s.severity === 'Critical' ? 'bg-red-950 text-red-300 border border-red-800' : 'bg-amber-950 text-amber-300 border border-amber-800'
                          }`}>
                            {s.severity}
                          </span>
                        </td>
                        <td className="p-3 font-mono text-[11px] text-slate-400">
                          {`+${s.delta_signature?.added_boundary_check || 0} guard, +${s.delta_signature?.added_await || 0} await`}
                        </td>
                        <td className="p-3 truncate max-w-[200px] text-slate-400">{s.commit_message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800/80 bg-[#070c17]/90 flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 text-xs font-semibold border border-slate-700/80 transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
