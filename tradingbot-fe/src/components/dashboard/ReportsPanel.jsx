import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog } from '@/components/ui/dialog';
import { reportService } from '@/services/reportService';
import { cn } from '@/lib/utils';

export default function ReportsPanel() {
  const [symbol, setSymbol] = useState('ALL');
  const [modalConfig, setModalConfig] = useState({ open: false, title: '', description: '', variant: 'destructive', type: 'alert' });

  // Default dates: last 30 days
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState(() => {
    return new Date().toISOString().split('T')[0];
  });

  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState(null);
  const [error, setError] = useState(null);

  const fetchSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await reportService.getReportSummary(symbol, startDate, endDate);
      setSummary(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch report summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, [symbol, startDate, endDate]);

  const handleDownload = async (format) => {
    setDownloadingFormat(format);
    try {
      await reportService.downloadReport(symbol, startDate, endDate, format);
    } catch (err) {
      setModalConfig({
        open: true,
        title: 'Download Failed',
        description: `Error generating ${format.toUpperCase()} report: ${err.message}`,
        variant: 'destructive',
        type: 'alert'
      });
    } finally {
      setDownloadingFormat(null);
    }
  };

  const financials = summary?.financials || {};
  const directional = summary?.directional || {};
  const strategy = summary?.strategy || {};
  const health = summary?.system_health || {};
  const recentTrades = summary?.recent_trades || [];

  return (
    <div className="flex flex-col gap-6 text-slate-800 dark:text-slate-100 pb-10">
      
      {/* Page Title & Export Actions */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">📊 Performance & Diagnostic Report Center</h1>
          <p className="text-slate-400 text-sm">Analyze trading PnL metrics, TP/SL parameters, and system exceptions.</p>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => handleDownload('excel')}
            disabled={downloadingFormat !== null}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold flex items-center gap-2 rounded-lg"
          >
            {downloadingFormat === 'excel' ? '⏳ Generating...' : '📥 Download Excel Sheet'}
          </Button>

          <Button
            onClick={() => handleDownload('pdf')}
            disabled={downloadingFormat !== null}
            className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 rounded-lg"
          >
            {downloadingFormat === 'pdf' ? '⏳ Generating...' : '📄 Download PDF Report'}
          </Button>
        </div>
      </div>

      {/* Date & Symbol Filters */}
      <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl">
        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
          <div className="flex flex-col gap-2">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Symbol Filter</Label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-slate-50 dark:bg-[#060913]/90 border border-slate-200 dark:border-white/[0.08] text-slate-800 dark:text-slate-200 rounded-lg p-2.5 text-sm"
            >
              <option value="ALL">ALL PAIRS</option>
              <option value="BTCUSDT">BTC/USDT</option>
              <option value="ETHUSDT">ETH/USDT</option>
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Start Date</Label>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bg-slate-50 dark:bg-[#060913]/90 border-slate-200 dark:border-white/[0.08] text-slate-800 dark:text-slate-200"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">End Date</Label>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bg-slate-50 dark:bg-[#060913]/90 border-slate-200 dark:border-white/[0.08] text-slate-800 dark:text-slate-200"
            />
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="bg-red-500/10 border border-red-500/50 text-red-200 rounded-lg p-4 text-sm font-semibold">
          ⚠️ {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
          <span>Compiling trade logs and system telemetry...</span>
        </div>
      ) : summary ? (
        <>
          {/* Main Financial KPI Indicators */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            
            {/* PnL Card */}
            <Card className="bg-white dark:bg-[#0d1220]/80 border-slate-200 dark:border-white/[0.06]">
              <CardContent className="pt-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Net P&L</span>
                <span className={cn(
                  "text-2xl font-extrabold block mt-2",
                  (financials.net_pnl || 0) >= 0 ? "text-emerald-400" : "text-red-400"
                )}>
                  {(financials.net_pnl || 0) >= 0 ? '+' : ''}${financials.net_pnl?.toFixed(4) || '0.0000'}
                </span>
                <span className="text-[10px] text-slate-500 mt-1 block">Gross profit: ${financials.gross_profit?.toFixed(2)}</span>
              </CardContent>
            </Card>

            {/* Win Rate Card */}
            <Card className="bg-white dark:bg-[#0d1220]/80 border-slate-200 dark:border-white/[0.06]">
              <CardContent className="pt-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Win Rate</span>
                <span className="text-2xl font-extrabold block mt-2 text-indigo-400">
                  {financials.win_rate || '0.0'}%
                </span>
                <span className="text-[10px] text-slate-500 mt-1 block">
                  {financials.winning_trades} Wins / {financials.losing_trades} Losses
                </span>
              </CardContent>
            </Card>

            {/* Profit Factor Card */}
            <Card className="bg-white dark:bg-[#0d1220]/80 border-slate-200 dark:border-white/[0.06]">
              <CardContent className="pt-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Profit Factor</span>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-2xl font-extrabold text-white">
                    {financials.profit_factor || '1.00'}
                  </span>
                  <Badge className={cn(
                    "text-[10px] py-0.5 px-1.5",
                    (financials.profit_factor || 0) >= 1.5 ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" :
                    (financials.profit_factor || 0) >= 1.0 ? "bg-amber-500/20 text-amber-400 border-amber-500/30" :
                    "bg-red-500/20 text-red-400 border-red-500/30"
                  )}>
                    {(financials.profit_factor || 0) >= 1.5 ? "Healthy" : (financials.profit_factor || 0) >= 1.0 ? "Fair" : "Unprofitable"}
                  </Badge>
                </div>
                <span className="text-[10px] text-slate-500 mt-1 block">Ratio of gross gains/losses</span>
              </CardContent>
            </Card>

            {/* Drawdown Card */}
            <Card className="bg-white dark:bg-[#0d1220]/80 border-slate-200 dark:border-white/[0.06]">
              <CardContent className="pt-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Max Drawdown</span>
                <span className="text-2xl font-extrabold block mt-2 text-rose-400">
                  {financials.max_drawdown?.toFixed(4) || '0.0000'}%
                </span>
                <span className="text-[10px] text-slate-500 mt-1 block">Maximum peak-to-trough drop</span>
              </CardContent>
            </Card>

            {/* Fees/Commissions Card */}
            <Card className="bg-white dark:bg-[#0d1220]/80 border-slate-200 dark:border-white/[0.06]">
              <CardContent className="pt-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Commission Drag</span>
                <span className="text-2xl font-extrabold block mt-2 text-amber-400">
                  -${financials.total_commission?.toFixed(4) || '0.0000'}
                </span>
                <span className="text-[10px] text-slate-500 mt-1 block">Exchange transaction fees</span>
              </CardContent>
            </Card>
          </div>

          {/* Directional Split & TP/SL Metrics */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Directional performance (Long vs. Short) */}
            <Card className="border-slate-200 dark:border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl">
              <CardHeader className="border-b border-white/[0.05]">
                <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">Directional Split</CardTitle>
                <CardDescription>Performance comparison for Long and Short orders.</CardDescription>
              </CardHeader>
              <CardContent className="pt-6 flex flex-col gap-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-900/40 border border-white/[0.03] rounded-lg">
                    <span className="text-emerald-400 text-xs font-semibold block">🟢 LONG POSITIONS</span>
                    <span className="text-2xl font-bold text-white block mt-2">${directional.long_pnl?.toFixed(2) || '0.00'}</span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Count: {directional.long_count} &nbsp;&bull;&nbsp; Win Rate: {directional.long_win_rate}%
                    </span>
                  </div>

                  <div className="p-4 bg-slate-900/40 border border-white/[0.03] rounded-lg">
                    <span className="text-red-400 text-xs font-semibold block">🔴 SHORT POSITIONS</span>
                    <span className="text-2xl font-bold text-white block mt-2">${directional.short_pnl?.toFixed(2) || '0.00'}</span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Count: {directional.short_count} &nbsp;&bull;&nbsp; Win Rate: {directional.short_win_rate}%
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Protective Orders & TP Ladders */}
            <Card className="border-slate-200 dark:border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl">
              <CardHeader className="border-b border-white/[0.05]">
                <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">Strategy protective hits</CardTitle>
                <CardDescription>Distribution of exit triggers and TP ladder steps.</CardDescription>
              </CardHeader>
              <CardContent className="pt-6 flex flex-col gap-4">
                <div className="flex flex-col gap-3">
                  {/* Progress bars for TP levels */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Take Profit Level 1</span>
                      <span className="font-bold text-emerald-400">{strategy.tp1_hits || 0} hits</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-2">
                      <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${Math.min(100, (strategy.tp1_hits || 0) * 10)}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Take Profit Level 2</span>
                      <span className="font-bold text-emerald-400">{strategy.tp2_hits || 0} hits</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-2">
                      <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${Math.min(100, (strategy.tp2_hits || 0) * 10)}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Take Profit Level 3</span>
                      <span className="font-bold text-emerald-400">{strategy.tp3_hits || 0} hits</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-2">
                      <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${Math.min(100, (strategy.tp3_hits || 0) * 10)}%` }}></div>
                    </div>
                  </div>

                  <div className="border-t border-white/[0.05] pt-3 mt-1">
                    <div className="flex justify-between text-xs">
                      <span>Total Hard Stop Loss hits</span>
                      <span className="font-bold text-red-400">{strategy.sl_hits || 0} hits</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Diagnostic System Health Exception logs */}
          <Card className="border-slate-200 dark:border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl">
            <CardHeader className="border-b border-white/[0.05]">
              <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">System Exception & API Diagnostic Log</CardTitle>
              <CardDescription>Audit panel logs counts of exchange API rejections and errors.</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-center">
                
                {/* Health indicator */}
                <div className="flex flex-col items-center justify-center p-6 border-r border-white/[0.05]">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Diagnostic Status</span>
                  <div className="mt-3">
                    {health.total_errors === 0 ? (
                      <Badge className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1 text-xs">
                        ● System Healthy
                      </Badge>
                    ) : (
                      <Badge className="bg-amber-500/20 text-amber-400 border border-amber-500/30 px-3 py-1 text-xs">
                        ⚠ Exceptions Logged ({health.total_errors})
                      </Badge>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-500 mt-3 text-center">Avg Latency: {health.avg_latency_seconds}s</span>
                </div>

                {/* API error list breakdown */}
                <div className="md:col-span-3 grid grid-cols-3 gap-4">
                  <div className="p-4 bg-slate-900/40 border border-white/[0.03] rounded-lg text-center">
                    <span className="text-[10px] font-bold text-slate-500 block uppercase">Error -2021 (Trigger SL)</span>
                    <span className="text-2xl font-bold text-amber-400 block mt-1">{health.err_2021_count || 0}</span>
                  </div>

                  <div className="p-4 bg-slate-900/40 border border-white/[0.03] rounded-lg text-center">
                    <span className="text-[10px] font-bold text-slate-500 block uppercase">Error -2013 (Order Lost)</span>
                    <span className="text-2xl font-bold text-amber-400 block mt-1">{health.err_2013_count || 0}</span>
                  </div>

                  <div className="p-4 bg-slate-900/40 border border-white/[0.03] rounded-lg text-center">
                    <span className="text-[10px] font-bold text-slate-500 block uppercase">Error -2011 (Cancel Fail)</span>
                    <span className="text-2xl font-bold text-amber-400 block mt-1">{health.err_2011_count || 0}</span>
                  </div>
                </div>

              </div>
            </CardContent>
          </Card>

          {/* Recent Trades Preview */}
          <Card className="border-slate-200 dark:border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl">
            <CardHeader className="border-b border-white/[0.05]">
              <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">Recent Executions Preview</CardTitle>
              <CardDescription>List of last 10 closed trade operations in specified date range.</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-slate-900/60 border-b border-white/[0.05]">
                  <TableRow>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-6">Fill Time</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Pair</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Type</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Side</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Price</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Quantity</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pr-6 text-right">Realized PnL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentTrades.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-6 text-slate-500 text-sm">
                        No closed trade records found for this period.
                      </TableCell>
                    </TableRow>
                  ) : (
                    recentTrades.map((t, idx) => (
                      <TableRow key={t.id || idx} className="border-b border-white/[0.03] hover:bg-white/[0.01]">
                        <TableCell className="text-xs text-slate-400 pl-6">
                          {t.fill_time ? new Date(t.fill_time).toLocaleString() : '--'}
                        </TableCell>
                        <TableCell className="text-xs font-semibold text-white">{t.symbol}</TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className="text-[10px] bg-slate-800/40 text-slate-300 border-white/5">
                            {t.order_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          <span className={cn(
                            "font-bold text-xs",
                            t.side === 'BUY' ? "text-emerald-400" : "text-red-400"
                          )}>
                            {t.side}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-slate-300">${t.price?.toFixed(2)}</TableCell>
                        <TableCell className="text-xs text-slate-300">{t.quantity}</TableCell>
                        <TableCell className={cn(
                          "text-xs font-bold pr-6 text-right",
                          t.realized_pnl >= 0 ? "text-emerald-400" : "text-red-400"
                        )}>
                          {t.realized_pnl >= 0 ? '+' : ''}${t.realized_pnl?.toFixed(4)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="text-center text-slate-400 py-10">No report summary available. Make sure your dates are valid.</div>
      )}

      {/* Styled Modal Dialog for Alerts */}
      <Dialog
        open={modalConfig.open}
        onClose={() => setModalConfig({ ...modalConfig, open: false })}
        title={modalConfig.title}
        description={modalConfig.description}
        variant={modalConfig.variant}
        type={modalConfig.type}
      />
    </div>
  );
}
