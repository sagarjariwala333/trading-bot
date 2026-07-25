import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardAction, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectTrigger, SelectValue,
  SelectContent, SelectItem,
} from '@/components/ui/select';

const NUMERIC_FIELDS = [
  { key: 'leverage',         label: 'Leverage',    limitKey: 'leverage' },
  { key: 'alma_window',      label: 'ALMA Window', limitKey: 'alma_window' },
  { key: 'rsi_period',       label: 'RSI Period',  limitKey: 'rsi_period' },
  { key: 'rsi_sma_period',   label: 'RSI SMA',     limitKey: 'rsi_sma_period' },
  { key: 'atr_period',       label: 'ATR Window',  limitKey: 'atr_period' },
  { key: 'trend_sma_period', label: 'Trend SMA',   limitKey: 'trend_sma_period' },
];

export default function ConfigPanel({ config, limits, isBotRunning, isConfigSaving, onChange, onSave, onReset }) {
  return (
    <Card className="border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl shadow-xl shadow-black/30 flex flex-col">
      <CardHeader className="px-6 py-4 border-b border-white/[0.05]">
        <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">
          Strategy Configuration
        </CardTitle>
        <CardAction>
          <Button variant="outline" size="sm" onClick={onReset} disabled={isBotRunning}
            className="border-white/[0.08] bg-slate-800/70 text-slate-300 hover:bg-slate-700/70 hover:text-white">
            ↺ Reset Defaults
          </Button>
        </CardAction>
      </CardHeader>

      {config ? (
        <form onSubmit={onSave} className="flex flex-col flex-1">
          <CardContent className="grid grid-cols-2 gap-4 pt-5 flex-1">
            {/* Timeframe — full width */}
            <div className="col-span-2 flex flex-col gap-1.5">
              <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">
                Candlestick Timeframe
              </Label>
              <Select value={config.interval} onValueChange={(v) => onChange('interval', v)} disabled={isBotRunning}>
                <SelectTrigger className="w-full bg-[#060913]/90 border-white/[0.08] text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['1m','5m','15m','1h','4h','12h','1d'].map((tf) => (
                    <SelectItem key={tf} value={tf}>{tf}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {isBotRunning && <p className="text-[10px] text-slate-600 italic">Stop the bot to change timeframe.</p>}
            </div>

            {/* Numeric fields */}
            {NUMERIC_FIELDS.map(({ key, label, limitKey }) => {
              const lim = limits[limitKey];
              return (
                <div key={key} className="flex flex-col gap-1.5">
                  <Label htmlFor={key} className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">
                    {label}
                  </Label>
                  <Input
                    id={key} type="number" value={config[key]}
                    min={lim?.[0]} max={lim?.[1]}
                    onChange={(e) => onChange(key, e.target.value)}
                    className="bg-[#060913]/90 border-white/[0.08] text-slate-200"
                  />
                  {key === 'leverage' && lim && (
                    <span className="text-[10px] text-slate-600">Range: {lim[0]}–{lim[1]}</span>
                  )}
                </div>
              );
            })}
          </CardContent>

          <div className="px-6 pb-5 pt-2">
            <Button type="submit" disabled={isConfigSaving} className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-900/30">
              {isConfigSaving ? 'Saving…' : 'Save Strategy Settings'}
            </Button>
          </div>
        </form>
      ) : (
        <CardContent className="flex-1 flex items-center justify-center text-slate-600 text-sm italic py-12">
          Loading configuration…
        </CardContent>
      )}
    </Card>
  );
}
