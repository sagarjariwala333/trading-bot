import { useState, useRef, useEffect, useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardAction, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export default function LogsPanel({ logs = [] }) {
  const containerRef = useRef(null);
  const [activeCategory, setActiveCategory] = useState('ALL');
  const [activeLevel, setActiveLevel] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [isPaused, setIsPaused] = useState(false);

  // Auto-scroll to bottom unless auto-scroll is paused
  useEffect(() => {
    if (!isPaused && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, isPaused]);

  // Categorize log line helper
  const getLogCategory = (logStr) => {
    const s = String(logStr).toUpperCase();
    if (s.includes('ERROR') || s.includes('EXCEPTION') || s.includes('CRITICAL') || s.includes('FAILED') || s.includes('-2021') || s.includes('-2013')) return 'ERRORS';
    if (s.includes('ORDER') || s.includes('FILLED') || s.includes('TRADE') || s.includes('STOP LOSS') || s.includes('TAKE PROFIT') || s.includes('TP_LEVEL') || s.includes('SL_PRICE')) return 'TRADES';
    if (s.includes('ALMA') || s.includes('RSI') || s.includes('SIGNAL') || s.includes('INDICATOR') || s.includes('KLINE') || s.includes('CANDLE') || s.includes('TREND')) return 'STRATEGY';
    if (s.includes('BINANCE') || s.includes('REST') || s.includes('WEIGHT') || s.includes('FUTURES_')) return 'EXCHANGE';
    return 'SYSTEM';
  };

  // Filtered log items based on selected category, level, and search keyword
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      const logStr = typeof log === 'string' ? log : (log.message || JSON.stringify(log));
      const logUpper = logStr.toUpperCase();

      // Category Filter
      if (activeCategory !== 'ALL') {
        const cat = getLogCategory(logStr);
        if (activeCategory === 'ERRORS' && cat !== 'ERRORS' && !logUpper.includes('WARNING') && !logUpper.includes('⚠️')) return false;
        if (activeCategory !== 'ERRORS' && cat !== activeCategory) return false;
      }

      // Level Filter
      if (activeLevel !== 'ALL') {
        if (activeLevel === 'ERROR' && !logUpper.includes('ERROR') && !logUpper.includes('EXCEPTION')) return false;
        if (activeLevel === 'WARNING' && !logUpper.includes('WARN') && !logUpper.includes('⚠️')) return false;
        if (activeLevel === 'INFO' && (logUpper.includes('ERROR') || logUpper.includes('WARN'))) return false;
      }

      // Search Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        if (!logStr.toLowerCase().includes(q)) return false;
      }

      return true;
    });
  }, [logs, activeCategory, activeLevel, searchQuery]);

  // Export logs to .txt file
  const handleExportLogs = () => {
    const content = filteredLogs.map(l => typeof l === 'string' ? l : `${l.timestamp || ''} [${l.level || 'INFO'}] ${l.message}`).join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bot_logs_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30 flex flex-col">
      
      {/* Header */}
      <CardHeader className="px-6 py-4 border-b border-slate-200 dark:border-white/[0.05] flex flex-col gap-3">
        <div className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            🪵 Live Process Log Explorer
            {isPaused && (
              <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 text-[10px]">
                ⏸ Auto-Scroll Paused
              </Badge>
            )}
          </CardTitle>
          <CardAction className="flex items-center gap-2">
            <Button
              size="xs"
              variant="outline"
              onClick={() => setIsPaused(!isPaused)}
              className={cn(
                "text-xs px-2.5 py-1 h-auto rounded border transition-colors",
                isPaused
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  : "bg-slate-800/60 text-slate-300 border-white/[0.08] hover:bg-slate-700"
              )}
            >
              {isPaused ? '▶ Resume Scroll' : '⏸ Pause Scroll'}
            </Button>

            <Button
              size="xs"
              variant="outline"
              onClick={handleExportLogs}
              className="text-xs px-2.5 py-1 h-auto rounded border border-white/[0.08] bg-slate-800/60 text-slate-300 hover:bg-slate-700"
              title="Download visible logs as .txt file"
            >
              📥 Export Logs
            </Button>

            <Badge variant="outline" className="text-slate-400 border-white/[0.06] bg-slate-900/60 text-[11px]">
              {filteredLogs.length} / {logs.length} lines
            </Badge>
          </CardAction>
        </div>

        {/* Category Tabs */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {[
            { id: 'ALL', label: 'All Events' },
            { id: 'TRADES', label: '🎯 Trades & Risk' },
            { id: 'STRATEGY', label: '📊 Indicators & Signals' },
            { id: 'EXCHANGE', label: '🔌 Exchange API' },
            { id: 'SYSTEM', label: '⚙️ System & DB' },
            { id: 'ERRORS', label: '⚠️ Errors & Warns' }
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={cn(
                "px-2.5 py-1 rounded text-xs font-semibold transition-all",
                activeCategory === cat.id
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-slate-900/40 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-white/[0.03]"
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search Bar & Level Selector */}
        <div className="flex items-center gap-3 pt-1">
          <Input
            placeholder="🔍 Search log keywords (e.g. BTCUSDT, Stop Loss, -2021)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 bg-slate-950/80 border-slate-200 dark:border-white/[0.08] text-xs text-slate-200"
          />
          
          <select
            value={activeLevel}
            onChange={(e) => setActiveLevel(e.target.value)}
            className="h-8 bg-slate-950/80 border border-slate-200 dark:border-white/[0.08] text-xs text-slate-300 rounded px-2 shrink-0"
          >
            <option value="ALL">All Levels</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
      </CardHeader>

      {/* Terminal View Container */}
      <CardContent className="p-0 flex-1">
        <div
          ref={containerRef}
          className="h-[420px] overflow-y-auto p-5 bg-slate-950 dark:bg-[#02050e] text-[12.5px] leading-relaxed flex flex-col gap-1"
          style={{ fontFamily: "'JetBrains Mono', monospace", scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.1) transparent' }}
        >
          {filteredLogs.length === 0 ? (
            <div className="text-slate-500 italic py-6 text-center">
              {logs.length === 0 ? 'Connecting to live WebSocket stream — waiting for log records…' : 'No logs match the selected category or search query.'}
            </div>
          ) : (
            filteredLogs.map((log, idx) => {
              const logStr = typeof log === 'string' ? log : (log.message || JSON.stringify(log));
              const isErr  = logStr.includes('ERROR')   || logStr.includes('Exception') || logStr.includes('CRITICAL');
              const isWarn = logStr.includes('WARNING')  || logStr.includes('⚠️');
              const isTrade = logStr.includes('ORDER') || logStr.includes('FILLED') || logStr.includes('TRADE') || logStr.includes('STOP LOSS');
              const isSignal = logStr.includes('ALMA') || logStr.includes('RSI') || logStr.includes('SIGNAL');

              return (
                <div
                  key={idx}
                  className={cn(
                    'py-1 px-2 rounded border-b border-white/[0.02] break-all flex items-start gap-2 font-mono transition-colors hover:bg-white/[0.02]',
                    isErr ? 'text-red-400 bg-red-500/5' :
                    isWarn ? 'text-amber-400 bg-amber-500/5' :
                    isTrade ? 'text-emerald-400 bg-emerald-500/5' :
                    isSignal ? 'text-cyan-400' : 'text-slate-300'
                  )}
                >
                  {/* Category icon indicator */}
                  <span className="shrink-0 text-[10px] select-none opacity-80 pt-0.5">
                    {isErr ? '🛑' : isWarn ? '⚠️' : isTrade ? '🎯' : isSignal ? '📊' : 'ℹ️'}
                  </span>
                  
                  {/* Log Message */}
                  <span className="flex-1">{logStr}</span>
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}
