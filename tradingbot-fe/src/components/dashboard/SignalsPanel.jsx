import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '../../services/api';

export default function SignalsPanel({ symbol, signals: wsSignals }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchSignalsData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getSignals(symbol, 100);
      setSignals(data.signals || []);
    } catch (err) {
      setError(err.message || 'Failed to load signals history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (wsSignals && wsSignals.length > 0) {
      setSignals(wsSignals);
    } else {
      fetchSignalsData();
    }
  }, [symbol, wsSignals]);

  return (
    <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30">
      <CardHeader className="flex flex-row items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/[0.05]">
        <div className="flex items-center gap-2">
          <div>
            <CardTitle>Strategy Decisions & Indicator Audit Trail</CardTitle>
            <CardDescription>Real-time WebSocket stream of candle technical indicators and decision rationale</CardDescription>
          </div>
          <Badge variant="outline" className="text-emerald-400 border-emerald-500/20 bg-emerald-500/10 text-[10px] gap-1">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            Live Socket Stream
          </Badge>
        </div>
        <Button size="sm" variant="outline" onClick={fetchSignalsData} disabled={loading} className="text-xs">
          {loading ? '↻ Refreshing...' : '↻ Refresh'}
        </Button>
      </CardHeader>
      <CardContent className="p-0 overflow-x-auto">
        {error && <div className="p-4 text-sm text-red-500">{error}</div>}
        {!loading && signals.length === 0 ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400 text-sm">
            No strategy decision records logged yet for {symbol}.
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100 dark:bg-slate-900/60 text-slate-500 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-200 dark:border-white/[0.05]">
              <tr>
                <th className="py-3 px-4">Candle Time</th>
                <th className="py-3 px-4">HA Close</th>
                <th className="py-3 px-4">ALMA (9)</th>
                <th className="py-3 px-4">RSI (14)</th>
                <th className="py-3 px-4">RSI SMA (14)</th>
                <th className="py-3 px-4">ATR (14)</th>
                <th className="py-3 px-4">ADX (14)</th>
                <th className="py-3 px-4">Trend SMA (50)</th>
                <th className="py-3 px-4">Signal</th>
                <th className="py-3 px-4">Decision Rationale</th>
                <th className="py-3 px-4">Executed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-white/[0.04]">
              {signals.map((s, idx) => (
                <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                  <td className="py-3 px-4 text-slate-500 font-mono">{s.candle_time}</td>
                  <td className="py-3 px-4 font-semibold text-slate-800 dark:text-slate-200">${s.ha_close ? s.ha_close.toFixed(2) : '--'}</td>
                  <td className="py-3 px-4 text-cyan-400 font-mono">${s.alma ? s.alma.toFixed(2) : '--'}</td>
                  <td className={cn('py-3 px-4 font-semibold', s.rsi > s.rsi_sma ? 'text-emerald-400' : 'text-red-400')}>
                    {s.rsi ? s.rsi.toFixed(2) : '--'}
                  </td>
                  <td className="py-3 px-4 text-amber-400 font-mono">{s.rsi_sma ? s.rsi_sma.toFixed(2) : '--'}</td>
                  <td className="py-3 px-4 text-purple-400 font-mono">${s.atr ? s.atr.toFixed(2) : '--'}</td>
                  <td className="py-3 px-4 font-mono">{s.adx != null ? s.adx.toFixed(1) : '--'}</td>
                  <td className="py-3 px-4 font-mono">${s.trend_sma ? s.trend_sma.toFixed(2) : '--'}</td>
                  <td className="py-3 px-4">
                    <Badge variant="outline" className={cn(
                      'text-[10px] font-bold px-2 py-0.5',
                      s.signal === 'LONG' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' :
                      s.signal === 'SHORT' ? 'text-red-400 border-red-500/30 bg-red-500/10' :
                      'text-slate-400 border-slate-500/30'
                    )}>
                      {s.signal}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">{s.decision}</td>
                  <td className="py-3 px-4">
                    <Badge variant="outline" className={s.executed ? 'text-emerald-400 border-emerald-500/30' : 'text-slate-500 border-slate-700'}>
                      {s.executed ? '✓ YES' : '○ NO'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
