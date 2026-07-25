import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardAction, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

const CELLS = (liveStatus, symbol) => [
  { label: 'Wallet Balance', value: liveStatus ? parseFloat(liveStatus.available_balance).toFixed(2) : '--', unit: 'USDT', color: 'text-white' },
  { label: 'Position', value: liveStatus?.position_amt ? (Number(liveStatus.position_amt) > 0 ? 'LONG' : 'SHORT') : 'NONE', unit: '', color: liveStatus?.position_amt ? (Number(liveStatus.position_amt) > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-400' },
  { label: 'Mark Price', value: liveStatus?.mark_price > 0 ? parseFloat(liveStatus.mark_price).toFixed(2) : '--', unit: '', color: 'text-cyan-400' },
  { label: 'Unrealized PnL', value: liveStatus?.unrealized_pnl != null ? parseFloat(liveStatus.unrealized_pnl).toFixed(4) : '0.0000', unit: 'USDT', color: liveStatus?.unrealized_pnl > 0 ? 'text-emerald-400' : liveStatus?.unrealized_pnl < 0 ? 'text-red-400' : 'text-slate-300' },
  { label: 'Entry Price', value: liveStatus?.entry_price > 0 ? parseFloat(liveStatus.entry_price).toFixed(2) : '--', unit: '', color: 'text-white' },
  { label: 'Stop Loss', value: liveStatus?.sl_price > 0 ? parseFloat(liveStatus.sl_price).toFixed(2) : '--', unit: '', color: 'text-orange-400' },
  { label: 'Take Profit', value: liveStatus?.tp_price > 0 ? parseFloat(liveStatus.tp_price).toFixed(2) : '--', unit: '', color: 'text-emerald-400' },
  { label: 'Leverage', value: liveStatus ? `${liveStatus.leverage}×` : '--', unit: '', color: 'text-violet-400' },
];

function MetricCell({ label, value, unit, color }) {
  return (
    <div className="flex flex-col gap-3 p-5 hover:bg-white/[0.02] transition-colors rounded-xl border border-white/[0.04] bg-slate-900/40">
      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{label}</span>
      <div className="flex items-baseline gap-1.5">
        <span className={cn('text-2xl font-bold leading-none', color)}>{value}</span>
        {unit && <span className="text-[10px] text-slate-500 font-semibold shrink-0">{unit}</span>}
      </div>
    </div>
  );
}

export default function TelemetryCard({ liveStatus, symbol, isBotRunning, onStart, onStop }) {
  return (
    <Card className="border-white/[0.06] dark:border-white/[0.06] bg-[#0d1220]/80 dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-xl shadow-black/30 dark:shadow-black/30 transition-colors duration-300">
      <CardHeader className="flex items-center justify-between px-6 py-4 border-b border-white/[0.05] dark:border-white/[0.05]">
        <div>
          <CardTitle>Live Exchange Status & Telemetry</CardTitle>
          <CardDescription>
            Real-time Binance Futures data
          </CardDescription>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Badge variant="outline" className="px-2 py-1 text-xs font-semibold text-emerald-400 border-emerald-500/50 bg-emerald-500/10">
            ● Running
          </Badge>

          <div className="flex items-center gap-2 ml-2 pl-3 border-l border-white/10 dark:border-white/10">
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
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3 p-4">
        {CELLS(liveStatus, symbol).map((cell) => (
          <MetricCell key={cell.label} {...cell} />
        ))}
      </CardContent>
    </Card>
  );
}