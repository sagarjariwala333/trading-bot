import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardAction } from '@/components/ui/card';
import {
  Select, SelectTrigger, SelectValue,
  SelectContent, SelectItem,
} from '@/components/ui/select';

export default function DashboardHeader({ isConnected, symbol, onSymbolChange }) {
  return (
    <Card className="border-white/[0.06] bg-[#0d1220]/80 backdrop-blur-xl shadow-xl shadow-black/30">
      <CardHeader className="flex-row items-center gap-4 p-5">
        <div className="flex-1">
          <CardTitle className="text-2xl md:text-3xl font-black tracking-tight bg-gradient-to-r from-blue-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            ALGO-HA TRADING BOT
          </CardTitle>
          <CardDescription className="flex items-center gap-2 mt-1.5">
            <span className={`w-2 h-2 rounded-full shrink-0 ${isConnected
              ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse'
              : 'bg-red-500'}`}
            />
            {isConnected ? 'API Connected — WebSocket Live' : 'API Disconnected — Reconnecting…'}
          </CardDescription>
        </div>

        <CardAction className="flex items-center gap-3">
          <Badge variant="outline" className="text-slate-400 border-slate-700/60 text-xs font-bold uppercase tracking-widest">
            Pair
          </Badge>
          <Select value={symbol} onValueChange={onSymbolChange}>
            <SelectTrigger className="w-52 bg-[#060913] border-white/[0.08] text-slate-200 focus:ring-blue-500/20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="BTCUSDT">BTCUSDT — Bitcoin</SelectItem>
              <SelectItem value="ETHUSDT">ETHUSDT — Ethereum</SelectItem>
              <SelectItem value="SOLUSDT">SOLUSDT — Solana</SelectItem>
              <SelectItem value="XRPUSDT">XRPUSDT — Ripple</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
    </Card>
  );
}
