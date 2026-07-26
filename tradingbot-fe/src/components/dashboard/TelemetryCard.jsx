import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardAction, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

const CELLS = (liveStatus, symbol) => [
  { label: 'Wallet Balance', value: liveStatus ? parseFloat(liveStatus.available_balance).toFixed(2) : '--', unit: 'USDT', color: 'text-slate-800 dark:text-white' },
  { label: 'Position', value: liveStatus?.position_amt ? (Number(liveStatus.position_amt) > 0 ? 'LONG' : 'SHORT') : 'NONE', unit: '', color: liveStatus?.position_amt ? (Number(liveStatus.position_amt) > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-500 dark:text-slate-400' },
  { label: 'Mark Price', value: liveStatus?.mark_price > 0 ? parseFloat(liveStatus.mark_price).toFixed(2) : '--', unit: '', color: 'text-cyan-500 dark:text-cyan-400' },
  { label: 'Unrealized PnL', value: liveStatus?.unrealized_pnl != null ? parseFloat(liveStatus.unrealized_pnl).toFixed(4) : '0.0000', unit: 'USDT', color: liveStatus?.unrealized_pnl > 0 ? 'text-emerald-500 dark:text-emerald-400' : liveStatus?.unrealized_pnl < 0 ? 'text-red-500 dark:text-red-400' : 'text-slate-500 dark:text-slate-300' },
  { label: 'Realized PnL', value: liveStatus?.realized_pnl != null ? parseFloat(liveStatus.realized_pnl).toFixed(4) : '0.0000', unit: 'USDT', color: liveStatus?.realized_pnl > 0 ? 'text-emerald-500 dark:text-emerald-400' : liveStatus?.realized_pnl < 0 ? 'text-red-500 dark:text-red-400' : 'text-slate-500 dark:text-slate-300' },
  { label: 'Total Net PnL', value: liveStatus?.total_pnl != null ? parseFloat(liveStatus.total_pnl).toFixed(4) : (parseFloat(liveStatus?.realized_pnl || 0) + parseFloat(liveStatus?.unrealized_pnl || 0)).toFixed(4), unit: 'USDT', color: (liveStatus?.total_pnl ?? ((liveStatus?.realized_pnl || 0) + (liveStatus?.unrealized_pnl || 0))) > 0 ? 'text-emerald-500 dark:text-emerald-400 font-extrabold' : (liveStatus?.total_pnl ?? ((liveStatus?.realized_pnl || 0) + (liveStatus?.unrealized_pnl || 0))) < 0 ? 'text-red-500 dark:text-red-400 font-extrabold' : 'text-slate-500 dark:text-slate-300 font-extrabold' },
  { label: 'Entry Price', value: liveStatus?.entry_price > 0 ? parseFloat(liveStatus.entry_price).toFixed(2) : '--', unit: '', color: 'text-slate-800 dark:text-white' },
  { label: 'Entry Margin', value: liveStatus?.entry_margin > 0 ? parseFloat(liveStatus.entry_margin).toFixed(2) : '--', unit: 'USDT', color: 'text-indigo-500 dark:text-indigo-400' },
  { label: 'Entry Time', value: liveStatus?.entry_time ? liveStatus.entry_time.split(' ')[1] || liveStatus.entry_time : '--', unit: liveStatus?.entry_time ? liveStatus.entry_time.split(' ')[0] : '', color: 'text-slate-700 dark:text-slate-300' },
  { label: 'Leverage', value: liveStatus ? `${liveStatus.leverage}×` : '--', unit: '', color: 'text-violet-500 dark:text-violet-400' },
  { label: 'Current SL', value: liveStatus?.sl_price > 0 ? parseFloat(liveStatus.sl_price).toFixed(2) : '--', unit: '', color: 'text-orange-500 dark:text-orange-400' },
  { label: 'Current TP Value', value: liveStatus?.tp_price > 0 ? parseFloat(liveStatus.tp_price).toFixed(2) : '--', unit: '', color: 'text-emerald-500 dark:text-emerald-400' },
  { label: 'Current TP Level', value: liveStatus?.tp_level != null ? `Level ${liveStatus.tp_level}` : '--', unit: '', color: 'text-amber-500 dark:text-amber-400' },
  { label: 'Accumulated TP Hits', value: liveStatus?.tp_level != null ? `${liveStatus.tp_level}` : '--', unit: 'steps', color: 'text-blue-500 dark:text-blue-400' },
];

function MetricCell({ label, value, unit, color }) {
  return (
    <div className="flex flex-col gap-2 p-4 hover:bg-slate-100/50 dark:hover:bg-white/[0.02] transition-colors rounded-xl border border-slate-200 dark:border-white/[0.04] bg-slate-100/30 dark:bg-slate-900/40">
      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest truncate">{label}</span>
      <div className="flex items-baseline gap-1.5 overflow-hidden">
        <span className={cn('text-xl font-bold leading-none truncate', color)}>{value}</span>
        {unit && <span className="text-[10px] text-slate-500 font-semibold shrink-0">{unit}</span>}
      </div>
    </div>
  );
}

export default function TelemetryCard({ liveStatus, symbol, isBotRunning, onStart, onStop, onClear }) {
  return (
    <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30 transition-colors duration-300">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 px-6 py-4 border-b border-slate-200 dark:border-white/[0.05]">
        <div>
          <CardTitle>Live Exchange Status & Telemetry</CardTitle>
          <CardDescription>
            Real-time Binance Futures data
          </CardDescription>
        </div>

        <div className="flex items-center justify-between sm:justify-end w-full sm:w-auto gap-3 shrink-0">
          <Badge variant="outline" className={cn(
            "px-2 py-1 text-xs font-semibold border",
            isBotRunning
              ? "text-emerald-400 border-emerald-500/50 bg-emerald-500/10"
              : "text-slate-400 border-slate-500/40 bg-slate-500/10"
          )}>
            {isBotRunning ? '● Running' : '○ Stopped'}
          </Badge>

          <div className="flex items-center gap-2 pl-3 border-l border-white/10 dark:border-white/10">
            <Button
              size="sm"
              disabled={isBotRunning}
              onClick={onStart}
              className={cn(
                "font-semibold text-sm px-3 py-1.5 h-auto rounded-md transition-all duration-150",
                isBotRunning
                  ? "bg-emerald-500/50 text-white/50 cursor-not-allowed opacity-60 dark:bg-emerald-500/50 dark:text-white/50"
                  : "bg-emerald-500 hover:bg-emerald-400 text-white hover:shadow-md hover:shadow-emerald-500/40 dark:bg-emerald-500 dark:hover:bg-emerald-400"
              )}
            >
              ▶ Start
            </Button>

            <Button
              size="sm"
              disabled={!isBotRunning}
              onClick={onStop}
              className={cn(
                "font-semibold text-sm px-3 py-1.5 h-auto rounded-md transition-all duration-150",
                !isBotRunning
                  ? "bg-red-500/50 text-white/50 cursor-not-allowed opacity-60 dark:bg-red-500/50 dark:text-white/50"
                  : "bg-red-500 hover:bg-red-400 text-white hover:shadow-md hover:shadow-red-500/40 dark:bg-red-500 dark:hover:bg-red-400"
              )}
            >
              ■ Stop
            </Button>

            <Button
              size="sm"
              onClick={onClear}
              className="font-semibold text-sm px-3 py-1.5 h-auto rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-all duration-150"
              title="Clear bot state, logs, and telemetry files"
            >
              🗑️ Clear State
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3 p-4">
        {CELLS(liveStatus, symbol).map((cell) => (
          <MetricCell key={cell.label} {...cell} />
        ))}
      </CardContent>
    </Card>
  );
}