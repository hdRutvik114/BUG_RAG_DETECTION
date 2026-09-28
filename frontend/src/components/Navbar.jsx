import React from 'react';
import { Bug, Activity, Shield, Wifi, WifiOff } from 'lucide-react';

export default function Navbar({ systemStatus }) {
  const isOnline = systemStatus?.status === 'online';

  return (
    <header className="sticky top-0 z-40 border-b border-[#1f293d] bg-[#0b0f19]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          
          {/* Logo */}
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30">
              <Bug className="w-4 h-4 text-blue-400" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-white tracking-tight">BugIdentifier</span>
              <span className="text-xs text-slate-400">Code-RAG Engine</span>
            </div>
          </div>

          {/* Status Pills */}
          <div className="flex items-center gap-2 text-xs">
            {/* Backend Status */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-medium ${
              isOnline
                ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400'
                : 'bg-red-950/40 border-red-800/60 text-red-400'
            }`}>
              {isOnline ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              <span>{isOnline ? 'API Online' : 'API Offline'}</span>
            </div>

            {/* DB Mode */}
            {systemStatus && (
              <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border bg-[#111827] border-[#1f293d] text-slate-300 font-medium">
                <Shield className="w-3.5 h-3.5 text-slate-400" />
                <span className="capitalize">{systemStatus.db_mode || 'local'}</span>
              </div>
            )}

            {/* LLM */}
            {systemStatus?.llm_provider && (
              <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md border bg-[#111827] border-[#1f293d] text-slate-300 font-medium">
                <Activity className="w-3.5 h-3.5 text-slate-400" />
                <span className="capitalize">{systemStatus.llm_provider}</span>
              </div>
            )}
          </div>

        </div>
      </div>
    </header>
  );
}
