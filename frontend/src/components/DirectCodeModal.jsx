import React, { useState } from 'react';
import { X, Play, Code2, Terminal, Sparkles, FileCode, CheckCircle2 } from 'lucide-react';

const SAMPLE_SNIPPETS = [
  {
    name: "Redux State Mutation",
    code: `const Blogs = () => {
  const posts = useSelector((state) => state.postsReducer);
  const dispatch = useDispatch();

  useEffect(() => {
    dispatch(fetchPostsApi());
    window.scrollTo({ top: 0 });
  }, []);

  return (
    <div className="mt-32 md:mt-40">
      <div className="flex gap-3 ml-5 md:ml-0 mb-6">
        <h2 className="text-2xl md:text-4xl">Latest Blogs</h2>
        <div className="border-b-2 mb-3 border-secondaryColor hr-blog" />
      </div>
      {posts.map((post) => (
        <BlogCard key={post.id} post={post} />
      ))}
    </div>
  );
};`
  },
  {
    name: "Async Token Handling",
    code: `async function fetchUserProfile(userId) {
  const response = fetch('/api/user/' + userId);
  const data = response.json();
  if (data.status === 'error') {
    throw new Error(data.message);
  }
  return data.profile;
}`
  },
  {
    name: "Boundary Array Slice",
    code: `function getTopRankings(scores, limit) {
  return scores.sort((a, b) => b.score - a.score).slice(0, limit);
}`
  }
];

export default function DirectCodeModal({ isOpen, onClose, onRunDirectScan }) {
  const [code, setCode] = useState(SAMPLE_SNIPPETS[0].code);
  const [fileName, setFileName] = useState('Blogs.jsx');

  if (!isOpen) return null;

  const handleScan = () => {
    if (!code.trim()) return;
    onRunDirectScan(code, fileName);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-3xl ui-card border border-slate-800/90 shadow-2xl overflow-hidden flex flex-col max-h-[88vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-slate-800/80 flex items-center justify-between bg-[#070c17]/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-cyan-950/60 text-cyan-400 border border-cyan-800/50 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                Code Snippet Analysis
              </h3>
              <p className="text-xs text-slate-400">Paste or test standalone JavaScript / TypeScript functions</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/80 transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1 bg-[#090e1a]/95">
          
          {/* Preset Buttons */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <span className="text-xs text-slate-400 font-semibold flex-shrink-0 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-cyan-400" /> Templates:
            </span>
            {SAMPLE_SNIPPETS.map((s, idx) => (
              <button
                key={idx}
                onClick={() => setCode(s.code)}
                className="px-3 py-1.5 rounded-lg bg-[#030712] hover:bg-cyan-950/40 border border-slate-800 hover:border-cyan-800/60 text-xs text-slate-300 hover:text-cyan-300 font-medium transition-all whitespace-nowrap"
              >
                {s.name}
              </button>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300">
                Function Code Snippet
              </label>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-mono">Filename:</span>
                <input
                  type="text"
                  value={fileName}
                  onChange={(e) => setFileName(e.target.value)}
                  className="px-3 py-1 bg-[#030712] border border-slate-800 rounded-lg text-xs text-cyan-300 font-mono focus:outline-none focus:border-cyan-500/80"
                />
              </div>
            </div>
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              rows={12}
              placeholder="Paste JavaScript/TypeScript function here..."
              className="w-full p-4 bg-[#030712] border border-slate-800 rounded-xl text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500/80 leading-relaxed shadow-inner"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800/80 bg-[#070c17]/90 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            Automated AST parsing and defect detection
          </span>
          <button
            onClick={handleScan}
            disabled={!code.trim()}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-white" />
            <span>Analyze Snippet</span>
          </button>
        </div>

      </div>
    </div>
  );
}
