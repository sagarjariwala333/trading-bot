import { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';


import AlertBanner    from '../components/dashboard/AlertBanner';
import DashboardHeader from '../components/dashboard/DashboardHeader';
import TelemetryCard  from '../components/dashboard/TelemetryCard';
import LogsPanel      from '../components/dashboard/LogsPanel';
import ConfigPanel    from '../components/dashboard/ConfigPanel';
import BacktestPanel  from '../components/dashboard/BacktestPanel';

export default function Dashboard() {
  // ── State ──────────────────────────────────────────────────────────────
  const [symbol, setSymbol]           = useState('BTCUSDT');
  const [isConnected, setIsConnected] = useState(false);
  const [errorMsg, setErrorMsg]       = useState(null);
  const [successMsg, setSuccessMsg]   = useState(null);
  const [isBotRunning, setIsBotRunning] = useState(false);
  const [liveStatus, setLiveStatus]   = useState(null);
  const [logs, setLogs]               = useState([]);
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
    if (!window.confirm(`Are you sure you want to clear bot_state.json, live_status.json, bot.log, and reset database state for ${symbol}?`)) {
      return;
    }
    try {
      const r = await api.clearBotInstance(symbol);
      if (r.success) {
        setIsBotRunning(false);
        setLiveStatus(null);
        setLogs([]);
        alert('success', r.message);
      } else {
        alert('error', r.message);
      }
    } catch (e) {
      alert('error', `Failed to clear instance: ${e.message}`);
    }
  };

  const handleCloseTrade = async () => {
    if (!window.confirm(`Are you sure you want to close the open trade and cancel all orders for ${symbol}?`)) {
      return;
    }
    try {
      const r = await api.closeTrade(symbol);
      if (r.success) {
        alert('success', r.message);
      } else {
        alert('error', r.message);
      }
    } catch (e) {
      alert('error', `Failed to close trade: ${e.message}`);
    }
  };

  const handleResetBot = async () => {
    if (!window.confirm(`Are you sure you want to COMPLETELY reset the bot for ${symbol}? This will stop the bot, close trades, reset state, and restore default config.`)) {
      return;
    }
    try {
      const r = await api.resetBot(symbol);
      if (r.success) {
        setIsBotRunning(false);
        setLiveStatus(null);
        setLogs([]);
        await fetchConfig(); // Reload config
        alert('success', r.message);
      } else {
        alert('error', r.message);
      }
    } catch (e) {
      alert('error', `Failed to reset bot: ${e.message}`);
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

        <TelemetryCard liveStatus={liveStatus} symbol={symbol} isBotRunning={isBotRunning} onStart={handleStartBot} onStop={handleStopBot} onClear={handleClearInstance} onCloseTrade={handleCloseTrade} onReset={handleResetBot} />

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
    </div>
  );
}
