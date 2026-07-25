import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Select, SelectTrigger, SelectValue,
  SelectContent, SelectItem,
} from '@/components/ui/select';
import EquityCurve from './EquityCurve';
import { cn } from '@/lib/utils';

const METRICS = (r) => [
  { label: 'Initial Margin', val: `${r.starting_balance.toFixed(2)} USDT`, color: '' },
  { label: 'Final Balance',  val: `${r.final_balance.toFixed(2)} USDT`,   color: r.final_balance >= r.starting_balance ? 'text-emerald-400' : 'text-red-400' },
  { label: 'Total Trades',   val: String(r.total_trades),                  color: '' },
  { label: 'Win Rate',       val: `${r.win_rate_pct.toFixed(1)}%`,         color: '' },
  { label: 'Fees Paid',      val: `${(r.trades?.reduce((a, t) => a + t.fees_paid, 0) ?? 0).toFixed(2)} USDT`, color: '' },
  { label: 'Net ROI',        val: `${(((r.final_balance - r.starting_balance) / r.starting_balance) * 100).toFixed(2)}%`, color: r.final_balance >= r.starting_balance ? 'text-emerald-400' : 'text-red-400' },
];

export default function BacktestPanel({
  datasets, selectedDataset, onDatasetChange,
  backtestBalance, onBalanceChange,
  backtestLeverage, onLeverageChange,
  isBacktesting, onRun,
  backtestResult,
}) {
  return (
    <Card className="border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl shadow-xl shadow-black/30">
      <CardHeader className="px-6 py-4 border-b border-white/[0.05]">
        <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">
          Backtesting Strategy Sandbox
        </CardTitle>
        <CardDescription>Simulate strategy on historical datasets</CardDescription>
      </CardHeader>

      <CardContent className="p-6 flex flex-col gap-5">
        {/* Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 items-end">
          <div className="flex flex-col gap-1.5">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Dataset</Label>
            <Select value={selectedDataset} onValueChange={onDatasetChange}>
              <SelectTrigger className="w-full bg-[#060913]/90 border-white/[0.08] text-slate-200">
                <SelectValue placeholder="Select dataset…" />
              </SelectTrigger>
              <SelectContent>
                {datasets.map((ds) => (
                  <SelectItem key={ds.name} value={ds.name}>
                    {ds.name} ({(ds.size_bytes / 1024).toFixed(1)} KB)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Initial Balance (USDT)</Label>
            <Input type="number" value={backtestBalance} onChange={(e) => onBalanceChange(e.target.value)}
              className="bg-[#060913]/90 border-white/[0.08] text-slate-200" />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Leverage</Label>
            <Input type="number" value={backtestLeverage} min="1" max="125"
              onChange={(e) => onLeverageChange(e.target.value)}
              className="bg-[#060913]/90 border-white/[0.08] text-slate-200" />
          </div>

          <Button onClick={onRun} disabled={isBacktesting}
            className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-900/30">
            {isBacktesting ? '⏳ Running…' : '▶ Execute Backtest'}
          </Button>
        </div>

        {/* Results */}
        {backtestResult && (
          <>
            <Separator className="bg-white/[0.05]" />
            <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5">
              {/* Metrics table */}
              <Card className="border-white/[0.06] bg-[#060913]/60">
                <CardHeader className="px-4 py-3 border-b border-white/[0.05]">
                  <CardTitle className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    Performance Summary
                  </CardTitle>
                </CardHeader>
                <Table>
                  <TableBody>
                    {METRICS(backtestResult).map(({ label, val, color }) => (
                      <TableRow key={label} className="border-white/[0.04] hover:bg-white/[0.02]">
                        <TableCell className="text-slate-500 py-2.5 px-4">{label}</TableCell>
                        <TableCell className={cn('text-right font-bold py-2.5 px-4', color || 'text-slate-200')}>{val}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>

              {/* Equity chart */}
              <Card className="border-white/[0.06] bg-[#060913]/60 p-5 flex flex-col gap-3">
                <CardTitle className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  Equity Growth Curve
                </CardTitle>
                <div className="flex-1 flex items-center justify-center">
                  <EquityCurve equityCurve={backtestResult.equity_curve} />
                </div>
              </Card>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
