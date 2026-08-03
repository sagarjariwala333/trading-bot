const BASE_URL = import.meta.env.VITE_API_BASE_URL
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL

export const api = {
  // Config endpoints
  async getConfig(symbol = 'BTCUSDT') {
    const res = await fetch(`${BASE_URL}/config?symbol=${symbol}`);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch config');
    return res.json();
  },

  async updateConfig(symbol, configData) {
    const res = await fetch(`${BASE_URL}/config?symbol=${symbol}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(configData),
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to update config');
    return res.json();
  },

  async resetConfig(symbol) {
    const res = await fetch(`${BASE_URL}/config/reset?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to reset config');
    return res.json();
  },

  // Bot control endpoints
  async getBotStatus(symbol, logLines = 100) {
    const res = await fetch(`${BASE_URL}/bot/status?symbol=${symbol}&log_lines=${logLines}`);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch bot status');
    return res.json();
  },

  async startBot(symbol) {
    const res = await fetch(`${BASE_URL}/bot/start?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to start bot');
    return res.json();
  },

  async stopBot(symbol) {
    const res = await fetch(`${BASE_URL}/bot/stop?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to stop bot');
    return res.json();
  },

  async getBotLogs(symbol, lines = 150, level = 'ALL', search = '') {
    let url = `${BASE_URL}/bot/logs?symbol=${symbol}&lines=${lines}&level=${level}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch bot logs');
    return res.json();
  },

  async clearBotInstance(symbol) {
    const res = await fetch(`${BASE_URL}/bot/clear?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to clear bot instance');
    return res.json();
  },

  async closeTrade(symbol) {
    const res = await fetch(`${BASE_URL}/bot/close-trade?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to close trade');
    return res.json();
  },

  async resetBot(symbol) {
    const res = await fetch(`${BASE_URL}/bot/reset?symbol=${symbol}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to reset bot');
    return res.json();
  },

  // Backtest endpoints
  async getDatasets() {
    const res = await fetch(`${BASE_URL}/backtest/datasets`);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch datasets');
    return res.json();
  },

  async runBacktest(payload) {
    const res = await fetch(`${BASE_URL}/backtest/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to run backtest');
    return res.json();
  },

  // Market endpoints
  async downloadMarketData(payload) {
    const res = await fetch(`${BASE_URL}/market/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to download market data');
    return res.json();
  },

  async getKlines(symbol, interval = null, limit = 100) {
    let url = `${BASE_URL}/market/klines?symbol=${symbol}&limit=${limit}`;
    if (interval) url += `&interval=${interval}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch klines');
    return res.json();
  },

  // Indicators endpoints
  async getLatestSignal(symbol, interval = null) {
    let url = `${BASE_URL}/indicators/latest?symbol=${symbol}`;
    if (interval) url += `&interval=${interval}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text() || 'Failed to fetch latest signal');
    return res.json();
  },

  async calculateIndicators(payload) {
    const res = await fetch(`${BASE_URL}/indicators/calculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text() || 'Failed to calculate indicators');
    return res.json();
  },

  // WebSocket Live Stream Helper
  getLiveWebSocket(symbol, intervalSeconds = 2) {
    return new WebSocket(`${WS_BASE_URL}/ws/live?symbol=${symbol}&interval_seconds=${intervalSeconds}`);
  }
};
