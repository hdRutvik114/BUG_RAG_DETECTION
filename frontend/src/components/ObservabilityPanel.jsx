import React from 'react';
import { Activity, Clock, FileCode2, Bug, CheckCircle2, BarChart2, Cpu } from 'lucide-react';

function MetricCard({ icon: Icon, label, value }) {
  return (
    <div className="ui-card p-4 flex items-center gap-3 border border-[#1f293d] bg-[#111827]">
      <div className="p-2 rounded-md bg-[#0b0f19] border border-[#1f293d] text-slate-300">
        <Icon className="w-4 h-4 text-blue-400" />
      </div>
      <div>
        <div className="text-2xl font-bold text-white font-mono">{value ?? '—'}</div>
        <div className="text-xs text-slate-400 mt-0.5">{label}</div>
      </div>
    </div>
  );
}

export default function ObservabilityPanel({ scanResult }) {
  if (!scanResult) return null;

  const t = scanResult.telemetry || {};
  const sb = t.severity_breakdown || {};
  const topBugs = t.top_bug_types || [];
  const scanTime = scanResult.scan_timestamp
    ? new Date(scanResult.scan_timestamp * 1000).toLocaleString()
    : 'N/A';

  const detectionRate = t.functions_analyzed > 0
    ? ((t.bugs_detected / t.functions_analyzed) * 100).toFixed(1) + '%'
    : '0%';

  return (
    <div className="space-y-4 my-4">
      
      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard icon={FileCode2}    label="Files Scanned"       value={t.files_scanned ?? scanResult.files_scanned} />
        <MetricCard icon={Cpu}          label="Functions Analyzed"  value={t.functions_analyzed} />
        <MetricCard icon={Bug}          label="Bugs Detected"       value={t.bugs_detected} />
        <MetricCard icon={CheckCircle2} label="Clean Functions"     value={t.clean_functions} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Severity Breakdown */}
        <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
          <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#1f293d]">
            <BarChart2 className="w-4 h-4 text-slate-400" />
            <h3 className="text-sm font-semibold text-white">Severity Breakdown</h3>
          </div>
          <div className="space-y-3">
            {[
              { level: 'Critical', count: sb.Critical || 0, color: 'bg-red-500' },
              { level: 'Major',    count: sb.Major    || 0, color: 'bg-amber-500' },
              { level: 'Minor',    count: sb.Minor    || 0, color: 'bg-blue-500' },
            ].map(({ level, count, color }) => {
              const total = (sb.Critical || 0) + (sb.Major || 0) + (sb.Minor || 0);
              const pct = total > 0 ? (count / total) * 100 : 0;
              return (
                <div key={level} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-white font-medium">{level}</span>
                    <span className="text-slate-400 font-mono">{count} issues</span>
                  </div>
                  <div className="w-full bg-[#0b0f19] rounded-full h-2 overflow-hidden border border-[#1f293d]">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${color}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Scan Metadata + Top Bug Types */}
        <div className="space-y-4">
          {/* Scan Info */}
          <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
            <div className="flex items-center gap-2 mb-3 pb-2.5 border-b border-[#1f293d]">
              <Activity className="w-4 h-4 text-slate-400" />
              <h3 className="text-sm font-semibold text-white">Scan Telemetry Metadata</h3>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Source</span>
                <span className="text-white font-mono truncate max-w-[200px]">{scanResult.source || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Threshold Used</span>
                <span className="text-white font-mono font-semibold">{scanResult.threshold_used ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Detection Rate</span>
                <span className="text-emerald-400 font-semibold">{detectionRate}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Scan ID</span>
                <span className="text-slate-400 font-mono">{scanResult.scan_id || '—'}</span>
              </div>
              <div className="flex justify-between items-start">
                <span className="text-slate-400">Timestamp</span>
                <span className="text-slate-400 text-right">{scanTime}</span>
              </div>
            </div>
          </div>

          {/* Top Bug Types */}
          {topBugs.length > 0 && (
            <div className="ui-card p-4 border border-[#1f293d] bg-[#111827]">
              <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[#1f293d]">
                <Bug className="w-4 h-4 text-slate-400" />
                <h3 className="text-sm font-semibold text-white">Top Bug Types</h3>
              </div>
              <div className="space-y-1.5">
                {topBugs.map((bt, i) => (
                  <div key={i} className="flex justify-between items-center text-xs">
                    <span className="text-slate-300">{bt.type}</span>
                    <span className="px-2 py-0.5 rounded bg-[#0b0f19] border border-[#1f293d] text-white font-mono font-medium">
                      ×{bt.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
