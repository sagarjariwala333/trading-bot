import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '../../services/api';

export default function TradesPanel({ symbol, trades: wsTrades, summary: wsSummary }) {
  const [trades, setTrades] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTradesData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTrades(symbol, 100);
      setTrades(data.trades || []);
      setSummary(data.summary || null);
    } catch (err) {
      setError(err.message || 'Failed to load trades history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (wsTrades && wsTrades.length > 0) {
      setTrades(wsTrades);
      if (wsSummary) setSummary(wsSummary);
    } else {
      fetchTradesData();
    }
  }, [symbol, wsTrades, wsSummary]);

  return (
    <div className="flex flex-col gap-5">
      {/* Summary Performance Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <div className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl flex flex-col gap-1">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Total Trades</span>
          <span className="text-2xl font-black text-slate-800 dark:text-white">{summary ? summary.total_trades : '--'}</span>
        </div>

        <div className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl flex flex-col gap-1">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Win Rate</span>
          <span className="text-2xl font-black text-emerald-500">{summary ? `${summary.win_rate}%` : '--'}</span>
        </div>

        <div className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl flex flex-col gap-1">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Total Realized PnL</span>
          <span className={cn('text-2xl font-black', summary?.total_pnl > 0 ? 'text-emerald-400' : summary?.total_pnl < 0 ? 'text-red-400' : 'text-slate-400')}>
            {summary ? `${summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl} USDT` : '--'}
          </span>
        </div>

        <div className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl flex flex-col gap-1">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Est. Exchange Fees</span>
          <span className="text-2xl font-black text-amber-400">{summary ? `${summary.total_fees} USDT` : '--'}</span>
        </div>

        <div className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl flex flex-col gap-1">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Avg PnL / Trade</span>
          <span className={cn('text-2xl font-black', summary?.avg_pnl > 0 ? 'text-emerald-400' : summary?.avg_pnl < 0 ? 'text-red-400' : 'text-slate-400')}>
            {summary ? `${summary.avg_pnl >= 0 ? '+' : ''}${summary.avg_pnl} USDT` : '--'}
          </span>
        </div>
      </div>

      {/* Trades History Table Card */}
      <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30">
        <CardHeader className="flex flex-row items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/[0.05]">
          <div className="flex items-center gap-2">
            <div>
              <CardTitle>Trade History & PnL Audit</CardTitle>
              <CardDescription>Real-time WebSocket stream of closed trades, leverage, fees, and ROE%</CardDescription>
            </div>
            <Badge variant="outline" className="text-emerald-400 border-emerald-500/20 bg-emerald-500/10 text-[10px] gap-1">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
              Live Socket Stream
            </Badge>
          </div>
          <Button size="sm" variant="outline" onClick={fetchTradesData} disabled={loading} className="text-xs">
            {loading ? '↻ Refreshing...' : '↻ Refresh'}
          </Button>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {error && <div className="p-4 text-sm text-red-500">{error}</div>}
          {!loading && trades.length === 0 ? (
            <div className="p-8 text-center text-slate-500 dark:text-slate-400 text-sm">
              No completed trades recorded yet for {symbol}.
            </div>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 dark:bg-slate-900/60 text-slate-500 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-200 dark:border-white/[0.05]">
                <tr>
                  <th className="py-3 px-4">Trade ID</th>
                  <th className="py-3 px-4">Direction</th>
                  <th className="py-3 px-4">Entry / Exit Price</th>
                  <th className="py-3 px-4">Qty</th>
                  <th className="py-3 px-4">Leverage</th>
                  <th className="py-3 px-4">TP Hits</th>
                  <th className="py-3 px-4">Gross PnL</th>
                  <th className="py-3 px-4">Fees</th>
                  <th className="py-3 px-4">Net PnL</th>
                  <th className="py-3 px-4">ROE %</th>
                  <th className="py-3 px-4">Exit Reason</th>
                  <th className="py-3 px-4">Entry Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-white/[0.04]">
                {trades.map((t) => (
                  <tr key={t.trade_id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600 dark:text-slate-300">{t.trade_id.slice(0, 16)}</td>
                    <td className="py-3 px-4">
                      <Badge variant="outline" className={cn(
                        'font-bold text-[10px] px-2 py-0.5',
                        t.direction === 'LONG' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : 'text-red-400 border-red-500/30 bg-red-500/10'
                      )}>
                        {t.direction}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-800 dark:text-slate-200">
                      ${t.entry_price ? t.entry_price.toFixed(2) : '--'} $\rightarrow$ ${t.exit_price ? t.exit_price.toFixed(2) : '--'}
                    </td>
                    <td className="py-3 px-4 font-mono">{t.quantity}</td>
                    <td className="py-3 px-4 text-violet-400 font-bold">{t.leverage}×</td>
                    <td className="py-3 px-4 text-amber-400 font-semibold">{t.tp_levels_hit} steps</td>
                    <td className={cn('py-3 px-4 font-semibold', t.gross_pnl >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                      {t.gross_pnl >= 0 ? '+' : ''}{t.gross_pnl ? t.gross_pnl.toFixed(4) : '0.00'} USDT
                    </td>
                    <td className="py-3 px-4 text-slate-400">${t.estimated_fees ? t.estimated_fees.toFixed(4) : '0.00'}</td>
                    <td className={cn('py-3 px-4 font-extrabold', t.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                      {t.realized_pnl >= 0 ? '+' : ''}{t.realized_pnl ? t.realized_pnl.toFixed(4) : '0.00'} USDT
                    </td>
                    <td className={cn('py-3 px-4 font-bold', t.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                      {t.return_pct >= 0 ? '+' : ''}{t.return_pct ? t.return_pct.toFixed(2) : '0.00'}%
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="outline" className="text-[10px] border-slate-300 dark:border-slate-700">
                        {t.close_reason}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-slate-500">{t.entry_time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
