import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '../../services/api';

export default function OrdersPanel({ symbol, orders: wsOrders }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchOrdersData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getOrders(symbol, 100);
      setOrders(data.orders || []);
    } catch (err) {
      setError(err.message || 'Failed to load orders history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (wsOrders && wsOrders.length > 0) {
      setOrders(wsOrders);
    } else {
      fetchOrdersData();
    }
  }, [symbol, wsOrders]);

  return (
    <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30">
      <CardHeader className="flex flex-row items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/[0.05]">
        <div className="flex items-center gap-2">
          <div>
            <CardTitle>Binance Orders & Algo Orders Audit Log</CardTitle>
            <CardDescription>Real-time WebSocket stream of standard orders (`order_id`) and conditional stop-loss orders (`algo_id`)</CardDescription>
          </div>
          <Badge variant="outline" className="text-emerald-400 border-emerald-500/20 bg-emerald-500/10 text-[10px] gap-1">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            Live Socket Stream
          </Badge>
        </div>
        <Button size="sm" variant="outline" onClick={fetchOrdersData} disabled={loading} className="text-xs">
          {loading ? '↻ Refreshing...' : '↻ Refresh'}
        </Button>
      </CardHeader>
      <CardContent className="p-0 overflow-x-auto">
        {error && <div className="p-4 text-sm text-red-500">{error}</div>}
        {!loading && orders.length === 0 ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400 text-sm">
            No order records logged yet for {symbol}.
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100 dark:bg-slate-900/60 text-slate-500 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-200 dark:border-white/[0.05]">
              <tr>
                <th className="py-3 px-4">Order ID</th>
                <th className="py-3 px-4">Algo ID</th>
                <th className="py-3 px-4">Purpose</th>
                <th className="py-3 px-4">Side</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Price</th>
                <th className="py-3 px-4">Stop Price</th>
                <th className="py-3 px-4">Qty</th>
                <th className="py-3 px-4">Executed Qty</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Created Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-white/[0.04]">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                  <td className="py-3 px-4 font-mono text-[11px] text-blue-400">{o.order_id || '--'}</td>
                  <td className="py-3 px-4 font-mono text-[11px] text-purple-400">{o.algo_id || '--'}</td>
                  <td className="py-3 px-4">
                    <Badge variant="outline" className="text-[10px] border-slate-300 dark:border-slate-700 bg-slate-500/5">
                      {o.purpose}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 font-bold">
                    <span className={o.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>{o.side}</span>
                  </td>
                  <td className="py-3 px-4 text-slate-400 font-semibold">{o.order_type}</td>
                  <td className="py-3 px-4 font-semibold text-slate-800 dark:text-slate-200">${o.price ? o.price.toFixed(2) : '0.00'}</td>
                  <td className="py-3 px-4 text-orange-400">${o.stop_price ? o.stop_price.toFixed(2) : '--'}</td>
                  <td className="py-3 px-4 font-mono">{o.quantity}</td>
                  <td className="py-3 px-4 font-mono text-emerald-400">{o.executed_qty}</td>
                  <td className="py-3 px-4">
                    <Badge variant="outline" className={cn(
                      'text-[10px] font-bold px-2 py-0.5',
                      o.status === 'FILLED' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' :
                      o.status === 'NEW' ? 'text-blue-400 border-blue-500/30 bg-blue-500/10' :
                      'text-slate-400 border-slate-500/30'
                    )}>
                      {o.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-slate-500">{o.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
