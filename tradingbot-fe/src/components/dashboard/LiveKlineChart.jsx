import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';
import Chart from 'chart.js/auto';

const LiveKlineChart = ({ symbol }) => {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    // Initialize WebSocket for Kline data
    const intervalSec = 2;
    const wsUrl = `${api.WS_BASE_URL}/ws/kline/live?symbol=${symbol}&interval_seconds=${intervalSec}`;
    const socket = new WebSocket(wsUrl);
    setWs(socket);

    socket.onopen = () => {
      console.log('Kline WS connected');
    };
    socket.onclose = () => {
      console.log('Kline WS closed, reconnecting in 5s');
      setTimeout(() => {
        // Reconnect by updating state (triggering effect)
        setWs(null);
      }, 5000);
    };
    socket.onerror = (err) => {
      console.error('Kline WS error', err);
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // data contains Binance kline fields
        const ts = new Date(data.t).toLocaleTimeString(); // open time
        const close = parseFloat(data.c);
        addDataPoint(ts, close);
      } catch (e) {
        console.error('Kline WS parse error', e);
      }
    };

    return () => {
      socket.close();
    };
  }, [symbol]);

  const addDataPoint = (label, value) => {
    if (!chartRef.current) return;
    const chart = chartRef.current;
    chart.data.labels.push(label);
    chart.data.datasets[0].data.push(value);
    // Keep only latest 50 points
    if (chart.data.labels.length > 50) {
      chart.data.labels.shift();
      chart.data.datasets[0].data.shift();
    }
    chart.update('quiet');
  };

  useEffect(() => {
    if (!canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(58,123,213,0.6)');
    gradient.addColorStop(1, 'rgba(58,123,213,0)');

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: `${symbol} Live Close`,
            data: [],
            borderColor: '#3a7bd5',
            backgroundColor: gradient,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: 'index',
            intersect: false,
          },
        },
        scales: {
          x: { display: false },
          y: { display: false },
        },
        animation: {
          duration: 500,
          easing: 'easeOutQuart',
        },
      },
    });
  }, []);

  return (
    <div className="glass-card p-4 rounded-lg shadow-lg" style={{ height: '300px', backdropFilter: 'blur(12px)' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
};

export default LiveKlineChart;
