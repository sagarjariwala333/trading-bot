import { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import AlertBanner    from '../components/dashboard/AlertBanner';
import DashboardHeader from '../components/dashboard/DashboardHeader';
import TelemetryCard  from '../components/dashboard/TelemetryCard';
import LogsPanel      from '../components/dashboard/LogsPanel';
import ConfigPanel    from '../components/dashboard/ConfigPanel';
import BacktestPanel  from '../components/dashboard/BacktestPanel';
import TradesPanel    from '../components/dashboard/TradesPanel';
import OrdersPanel    from '../components/dashboard/OrdersPanel';
import SignalsPanel   from '../components/dashboard/SignalsPanel';

export default function Dashboard() {
  // ── State ──────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab]     = useState('dashboard'); // 'dashboard' | 'trades' | 'orders' | 'signals'
  const [symbol, setSymbol]           = useState('BTCUSDT');
  const [isConnected, setIsConnected] = useState(false);
  const [errorMsg, setErrorMsg]       = useState(null);
  const [successMsg, setSuccessMsg]   = useState(null);
  const [isBotRunning, setIsBotRunning] = useState(false);
  const [liveStatus, setLiveStatus]   = useState(null);
  const [logs, setLogs]               = useState([]);
  const [trades, setTrades]           = useState([]);
  const [tradeSummary, setTradeSummary] = useState(null);
  const [orders, setOrders]           = useState([]);
  const [signals, setSignals]         = useState([]);

  const [config, setConfig]           = useState(null);
  const [limits, setLimits]           = useState({});
  const [isConfigSaving, setIsConfigSaving] = useState(false);
  const [datasets, setDatasets]             = useState([]);
  const [selectedDataset, setSelectedDataset] = useState('');
  const [backtestBalance, setBacktestBalance] = useState(1000);
  const [backtestLeverage, setBacktestLeverage] = useState(10);
  const [backtestResult, setBacktestResult]     = useState(null);
  const [isBacktesting, setIsBacktesting]       = useState(false);
  const wsRef = useRef(null);

  // ── Helpers ────────────────────────────────────────────────────────────
  const alert = (type, msg) => {
    if (type === 'error') { setErrorMsg(msg);   setTimeout(() => setErrorMsg(null),   5000); }
    else                  { setSuccessMsg(msg);  setTimeout(() => setSuccessMsg(null), 5000); }
  };

  // ── Effects ────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchConfig();
    fetchDatasets();
    connectWebSocket();
    return () => wsRef.current?.close();
  }, [symbol]);

  // ── API calls ──────────────────────────────────────────────────────────
  const fetchConfig = async () => {
    try { const d = await api.getConfig(symbol); setConfig(d.config); setLimits(d.limits || {}); }
    catch (e) { alert('error', `Failed to load config: ${e.message}`); }
  };

  const fetchDatasets = async () => {
    try {
      const d = await api.getDatasets();
      setDatasets(d);
      if (d.length > 0 && !selectedDataset) setSelectedDataset(d[0].name);
    } catch (e) { alert('error', `Failed to load datasets: ${e.message}`); }
  };

  const connectWebSocket = () => {
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        return;
      }
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
    }
    const ws = api.getLiveWebSocket(symbol, 2);
    wsRef.current = ws;
    ws.onopen    = () => { setIsConnected(true); setErrorMsg(null); };
    ws.onclose   = () => { 
      setIsConnected(false); 
      setTimeout(() => { 
        if (wsRef.current === ws && (ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING)) { 
          connectWebSocket(); 
        } 
      }, 5000); 
    };
    ws.onerror   = () => setIsConnected(false);
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        setIsBotRunning(d.is_running);
        setLiveStatus(d.live_status);
        if (d.logs) setLogs(d.logs);
        if (d.trades) setTrades(d.trades);
        if (d.summary) setTradeSummary(d.summary);
        if (d.orders) setOrders(d.orders);
        if (d.signals) setSignals(d.signals);
      } catch (err) { console.error('WS parse error', err); }
    };
  };

  const handleStartBot = async () => {
    try { const r = await api.startBot(symbol); r.success ? (alert('success', r.message), setIsBotRunning(true)) : alert('error', r.message); }
    catch (e) { alert('error', `Failed to start bot: ${e.message}`); }
  };

  const handleStopBot = async () => {
    try { const r = await api.stopBot(symbol); r.success ? (alert('success', r.message), setIsBotRunning(false)) : alert('error', r.message); }
    catch (e) { alert('error', `Failed to stop bot: ${e.message}`); }
  };

  const handleClearInstance = async () => {
    if (!window.confirm(`Are you sure you want to clear instance state, logs, and database tracking for ${symbol}?`)) {
      return;
    }
    try {
      const r = await api.clearBotInstance(symbol);
      if (r.success) {
        setIsBotRunning(false);
        setLiveStatus(null);
        setLogs([]);
        setTrades([]);
        setOrders([]);
        setSignals([]);
        alert('success', r.message);
      } else {
        alert('error', r.message);
      }
    } catch (e) {
      alert('error', `Failed to clear instance: ${e.message}`);
    }
  };

  const handleConfigChange = (field, val) => {
    if (!config) return;
    const lim = limits[field];
    let v = val;
    if (lim?.[2] === 'int')   v = parseInt(val, 10)  || 0;
    if (lim?.[2] === 'float') v = parseFloat(val)     || 0.0;
    setConfig({ ...config, [field]: v });
  };

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    if (!config) return;
    setIsConfigSaving(true);
    try { const r = await api.updateConfig(symbol, config); setConfig(r.config); alert('success', 'Strategy configuration updated.'); }
    catch (e) { alert('error', `Failed to save: ${e.message}`); }
    finally { setIsConfigSaving(false); }
  };

  const handleResetConfig = async () => {
    try { const r = await api.resetConfig(symbol); setConfig(r.config); alert('success', 'Configuration reset to defaults.'); }
    catch (e) { alert('error', `Failed to reset: ${e.message}`); }
  };

  const handleRunBacktest = async () => {
    if (!selectedDataset) { alert('error', 'Please select a dataset first.'); return; }
    setIsBacktesting(true); setBacktestResult(null);
    try {
      const r = await api.runBacktest({ dataset_name: selectedDataset, starting_balance: parseFloat(backtestBalance) || 1000, leverage: parseInt(backtestLeverage, 10) || 10 });
      setBacktestResult(r); alert('success', 'Backtest executed successfully!');
    } catch (e) { alert('error', `Backtest failed: ${e.message}`); }
    finally { setIsBacktesting(false); }
  };

  const TABS = [
    { id: 'dashboard', label: '📊 Live Dashboard' },
    { id: 'trades',    label: '📈 Trades & PnL Performance' },
    { id: 'orders',    label: '📋 Order Audit Trail' },
    { id: 'signals',   label: '🔍 Strategy Signals & Decisions' },
  ];

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#060913] text-slate-800 dark:text-slate-100">
      <div className="max-w-[1920px] mx-auto px-6 py-6 flex flex-col gap-5">

        <AlertBanner
          errorMsg={errorMsg} successMsg={successMsg}
          onDismissError={() => setErrorMsg(null)}
          onDismissSuccess={() => setSuccessMsg(null)}
        />

        <DashboardHeader isConnected={isConnected} symbol={symbol} onSymbolChange={setSymbol} />

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-b border-slate-200 dark:border-white/[0.08] pb-1 overflow-x-auto">
          {TABS.map((t) => (
            <Button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              variant="ghost"
              className={cn(
                'font-bold text-xs sm:text-sm px-4 py-2.5 rounded-lg transition-all duration-200',
                activeTab === t.id
                  ? 'bg-blue-500/10 text-blue-500 border border-blue-500/30 dark:bg-blue-500/20 dark:text-blue-400 dark:border-blue-400/30'
                  : 'text-slate-500 hover:bg-slate-200/50 dark:hover:bg-white/[0.04] dark:text-slate-400'
              )}
            >
              {t.label}
            </Button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'dashboard' && (
          <div className="flex flex-col gap-5">
            <TelemetryCard liveStatus={liveStatus} symbol={symbol} isBotRunning={isBotRunning} onStart={handleStartBot} onStop={handleStopBot} onClear={handleClearInstance} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <LogsPanel logs={logs} />
              <ConfigPanel
                config={config} limits={limits} isBotRunning={isBotRunning} isConfigSaving={isConfigSaving}
                onChange={handleConfigChange} onSave={handleSaveConfig} onReset={handleResetConfig}
              />
            </div>

            <BacktestPanel
              datasets={datasets} selectedDataset={selectedDataset} onDatasetChange={setSelectedDataset}
              backtestBalance={backtestBalance} onBalanceChange={setBacktestBalance}
              backtestLeverage={backtestLeverage} onLeverageChange={setBacktestLeverage}
              isBacktesting={isBacktesting} onRun={handleRunBacktest}
              backtestResult={backtestResult}
            />
          </div>
        )}

        {activeTab === 'trades' && <TradesPanel symbol={symbol} trades={trades} summary={tradeSummary} />}

        {activeTab === 'orders' && <OrdersPanel symbol={symbol} orders={orders} />}

        {activeTab === 'signals' && <SignalsPanel symbol={symbol} signals={signals} />}

      </div>
    </div>
  );
}
