import { useRef, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardAction, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export default function LogsPanel({ logs }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <Card className="border-slate-200 dark:border-white/[0.06] bg-white dark:bg-[#0d1220]/80 backdrop-blur-xl shadow-md dark:shadow-xl dark:shadow-black/30 flex flex-col">
      <CardHeader className="px-6 py-4 border-b border-slate-200 dark:border-white/[0.05]">
        <CardTitle className="text-sm font-bold text-slate-300 uppercase tracking-wider">
          Live Process Logs
        </CardTitle>
        <CardAction>
          <Badge variant="outline" className="text-slate-500 border-white/[0.06] bg-slate-900/60 text-[11px]">
            {logs.length} lines
          </Badge>
        </CardAction>
      </CardHeader>

      <CardContent className="p-0 flex-1">
        <div
          ref={containerRef}
          className="h-[420px] overflow-y-auto p-5 bg-slate-950 dark:bg-[#02050e] text-[12.5px] leading-relaxed flex flex-col gap-0.5"
          style={{ fontFamily: "'JetBrains Mono', monospace", scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.1) transparent' }}
        >
          {logs.length === 0 ? (
            <span className="text-slate-600 italic">Connecting to stream — waiting for log records…</span>
          ) : (
            logs.map((log, idx) => {
              const isErr  = log.includes('ERROR')   || log.includes('Exception');
              const isWarn = log.includes('WARNING')  || log.includes('⚠️');
              return (
                <div key={idx} className={cn('py-0.5 border-b border-white/[0.025] break-all',
                  isErr ? 'text-red-400' : isWarn ? 'text-amber-400' : 'text-sky-400')}>
                  {log}
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}
