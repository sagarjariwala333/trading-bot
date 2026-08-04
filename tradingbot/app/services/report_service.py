"""Service for compiling trade reports and system diagnostics."""

import io
import time
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.core.config import settings
from app.models.trading import TradeExecution, PerformanceMetrics, SystemLog, BotState, TradingPair

logger = logging.getLogger("ha_alma_bot")

class ReportService:
    """Service to gather trading metrics and build downloadable reports (Excel & PDF)."""

    @staticmethod
    def sync_binance_trades(db: Session, symbol: str = "ALL"):
        """Sync recent trade executions directly from Binance Futures API into PostgreSQL."""
        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            return

        try:
            from binance.client import Client
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, testnet=True)
            try:
                server_time = client.futures_time()['serverTime']
                client.timestamp_offset = server_time - int(time.time() * 1000)
            except Exception as time_err:
                logger.warning(f"Could not adjust Binance timestamp offset: {time_err}")

            symbols_to_sync = []
            if symbol != "ALL":
                symbols_to_sync = [symbol]
            else:
                pairs = db.query(TradingPair).all()
                symbols_to_sync = [p.symbol for p in pairs] if pairs else ["BTCUSDT", "ETHUSDT"]
                if "BTCUSDT" not in symbols_to_sync:
                    symbols_to_sync.append("BTCUSDT")

            for sym in symbols_to_sync:
                try:
                    raw_trades = client.futures_account_trades(symbol=sym, recvWindow=60000)
                    count_added = 0
                    for t in raw_trades:
                        trade_id = str(t['id'])
                        order_id = str(t['orderId'])
                        unique_exec_id = f"{order_id}_{trade_id}"

                        existing = db.query(TradeExecution).filter(
                            TradeExecution.order_id == unique_exec_id
                        ).first()

                        if not existing:
                            fill_dt = datetime.fromtimestamp(t['time'] / 1000, tz=timezone.utc).replace(tzinfo=None)
                            pnl = Decimal(str(t['realizedPnl']))
                            side = t['side']
                            sig = 'TAKE_PROFIT' if pnl > 0 else ('STOP_LOSS' if pnl < 0 else 'ENTRY')

                            exec_rec = TradeExecution(
                                symbol=sym,
                                order_id=unique_exec_id,
                                client_order_id=f"trade_{trade_id}",
                                order_type='LIMIT' if t.get('maker') else 'MARKET',
                                side=side,
                                quantity=Decimal(str(t['qty'])),
                                price=Decimal(str(t['price'])),
                                order_time=fill_dt,
                                fill_time=fill_dt,
                                commission=Decimal(str(t['commission'])),
                                commission_asset=t.get('commissionAsset', 'USDT'),
                                realized_pnl=pnl,
                                strategy_signal=sig
                            )
                            db.add(exec_rec)
                            count_added += 1
                    if count_added > 0:
                        db.commit()
                        logger.info(f"Synced {count_added} new trade executions for {sym} from Binance.")
                except Exception as sym_err:
                    logger.warning(f"Failed to sync Binance trades for {sym}: {sym_err}")
        except Exception as e:
            logger.error(f"Failed to initialize Binance trade sync: {e}")

    @staticmethod
    def get_report_summary_data(db: Session, symbol: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Compile a summary dictionary of all KPIs for a symbol and date range."""
        # Auto-sync trades from Binance prior to building summary
        ReportService.sync_binance_trades(db, symbol)

        # 1. Base Filters
        exec_filter = [
            TradeExecution.fill_time >= start_date,
            TradeExecution.fill_time <= end_date,
            TradeExecution.realized_pnl.isnot(None)
        ]
        log_filter = [
            SystemLog.created_at >= start_date,
            SystemLog.created_at <= end_date
        ]
        perf_filter = [
            PerformanceMetrics.date >= start_date,
            PerformanceMetrics.date <= end_date
        ]

        if symbol != "ALL":
            exec_filter.append(TradeExecution.symbol == symbol)
            log_filter.append(SystemLog.symbol == symbol)
            perf_filter.append(PerformanceMetrics.symbol == symbol)

        # 2. Query Trades
        trades = db.query(TradeExecution).filter(and_(*exec_filter)).all()
        
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if (t.realized_pnl or 0) > 0)
        losing_trades = sum(1 for t in trades if (t.realized_pnl or 0) <= 0)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        gross_profit = float(sum(t.realized_pnl for t in trades if (t.realized_pnl or 0) > 0))
        gross_loss = float(sum(t.realized_pnl for t in trades if (t.realized_pnl or 0) <= 0))
        net_pnl = gross_profit + gross_loss
        
        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else (gross_profit if gross_profit > 0 else 1.0)
        total_commission = float(sum(t.commission or 0 for t in trades))

        # 3. Directional Split (Long vs Short)
        # In this system, entry positions are BUY (Long) or SELL (Short).
        # Therefore, realized_pnl is generated at exit.
        # SELL exit = Long closed, BUY exit = Short closed.
        long_trades = [t for t in trades if t.side == "SELL"]
        short_trades = [t for t in trades if t.side == "BUY"]

        long_count = len(long_trades)
        long_wins = sum(1 for t in long_trades if (t.realized_pnl or 0) > 0)
        long_win_rate = (long_wins / long_count * 100) if long_count > 0 else 0.0
        long_pnl = float(sum(t.realized_pnl or 0 for t in long_trades))

        short_count = len(short_trades)
        short_wins = sum(1 for t in short_trades if (t.realized_pnl or 0) > 0)
        short_win_rate = (short_wins / short_count * 100) if short_count > 0 else 0.0
        short_pnl = float(sum(t.realized_pnl or 0 for t in short_trades))

        # 4. Take Profit & Stop Loss Progression
        tp1_hits = sum(1 for t in trades if t.strategy_signal == "TAKE_PROFIT" and t.tp_level == 1)
        tp2_hits = sum(1 for t in trades if t.strategy_signal == "TAKE_PROFIT" and t.tp_level == 2)
        tp3_hits = sum(1 for t in trades if t.strategy_signal == "TAKE_PROFIT" and t.tp_level == 3)
        sl_hits = sum(1 for t in trades if t.strategy_signal == "STOP_LOSS")

        # 5. Holding Duration & Latency
        durations = []
        latencies = []
        for t in trades:
            if t.fill_time and t.order_time:
                latencies.append((t.fill_time - t.order_time).total_seconds())
        
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

        # 6. System Diagnostic Errors
        errors = db.query(SystemLog).filter(
            and_(
                *log_filter,
                SystemLog.level.in_(["ERROR", "CRITICAL"])
            )
        ).all()

        err_2021 = sum(1 for log in errors if "-2021" in log.message or "immediately trigger" in log.message)
        err_2013 = sum(1 for log in errors if "-2013" in log.message or "Order does not exist" in log.message)
        err_2011 = sum(1 for log in errors if "-2011" in log.message or "Unknown order sent" in log.message)
        other_errors = len(errors) - (err_2021 + err_2013 + err_2011)

        # 7. Max Drawdown from PerformanceMetrics
        perf_data = db.query(PerformanceMetrics).filter(and_(*perf_filter)).all()
        max_dd = float(min((p.max_drawdown or 0 for p in perf_data), default=0.0))

        # 8. List of last 10 trades for preview
        recent_trades_data = []
        recent_trades = db.query(TradeExecution).filter(
            and_(*exec_filter)
        ).order_by(desc(TradeExecution.fill_time)).limit(10).all()

        for t in recent_trades:
            recent_trades_data.append({
                "id": t.id,
                "symbol": t.symbol,
                "fill_time": t.fill_time.isoformat() if t.fill_time else None,
                "side": t.side,
                "order_type": t.order_type,
                "price": float(t.price),
                "quantity": float(t.quantity),
                "realized_pnl": float(t.realized_pnl or 0.0),
                "strategy_signal": t.strategy_signal,
                "commission": float(t.commission or 0.0)
            })

        return {
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "financials": {
                "net_pnl": round(net_pnl, 4),
                "gross_profit": round(gross_profit, 4),
                "gross_loss": round(gross_loss, 4),
                "profit_factor": round(profit_factor, 2),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(win_rate, 2),
                "total_commission": round(total_commission, 4),
                "max_drawdown": round(max_dd, 4)
            },
            "directional": {
                "long_count": long_count,
                "long_win_rate": round(long_win_rate, 2),
                "long_pnl": round(long_pnl, 4),
                "short_count": short_count,
                "short_win_rate": round(short_win_rate, 2),
                "short_pnl": round(short_pnl, 4)
            },
            "strategy": {
                "tp1_hits": tp1_hits,
                "tp2_hits": tp2_hits,
                "tp3_hits": tp3_hits,
                "sl_hits": sl_hits
            },
            "system_health": {
                "avg_latency_seconds": round(avg_latency, 3),
                "total_errors": len(errors),
                "err_2021_count": err_2021,
                "err_2013_count": err_2013,
                "err_2011_count": err_2011,
                "other_errors_count": other_errors
            },
            "recent_trades": recent_trades_data
        }

    @staticmethod
    def generate_excel_report(db: Session, symbol: str, start_date: datetime, end_date: datetime) -> bytes:
        """Generate a multi-tab Excel spreadsheet representing the report."""
        import pandas as pd

        # Fetch raw data
        exec_filter = [TradeExecution.fill_time >= start_date, TradeExecution.fill_time <= end_date]
        log_filter = [SystemLog.created_at >= start_date, SystemLog.created_at <= end_date]
        if symbol != "ALL":
            exec_filter.append(TradeExecution.symbol == symbol)
            log_filter.append(SystemLog.symbol == symbol)

        executions = db.query(TradeExecution).filter(and_(*exec_filter)).order_by(desc(TradeExecution.fill_time)).all()
        logs = db.query(SystemLog).filter(and_(*log_filter)).order_by(desc(SystemLog.created_at)).all()
        summary = ReportService.get_report_summary_data(db, symbol, start_date, end_date)

        # 1. Summary Sheet DataFrame
        summary_rows = [
            {"Metric": "Report Symbol", "Value": summary["symbol"]},
            {"Metric": "Start Date", "Value": summary["start_date"]},
            {"Metric": "End Date", "Value": summary["end_date"]},
            {"Metric": "--- Financials ---", "Value": ""},
            {"Metric": "Net P&L ($)", "Value": summary["financials"]["net_pnl"]},
            {"Metric": "Gross Profit ($)", "Value": summary["financials"]["gross_profit"]},
            {"Metric": "Gross Loss ($)", "Value": summary["financials"]["gross_loss"]},
            {"Metric": "Profit Factor", "Value": summary["financials"]["profit_factor"]},
            {"Metric": "Total Trades", "Value": summary["financials"]["total_trades"]},
            {"Metric": "Win Rate (%)", "Value": summary["financials"]["win_rate"]},
            {"Metric": "Total Commission ($)", "Value": summary["financials"]["total_commission"]},
            {"Metric": "Max Drawdown (%)", "Value": summary["financials"]["max_drawdown"]},
            {"Metric": "--- Directional Performance ---", "Value": ""},
            {"Metric": "Long Trades Count", "Value": summary["directional"]["long_count"]},
            {"Metric": "Long Win Rate (%)", "Value": summary["directional"]["long_win_rate"]},
            {"Metric": "Long P&L ($)", "Value": summary["directional"]["long_pnl"]},
            {"Metric": "Short Trades Count", "Value": summary["directional"]["short_count"]},
            {"Metric": "Short Win Rate (%)", "Value": summary["directional"]["short_win_rate"]},
            {"Metric": "Short P&L ($)", "Value": summary["directional"]["short_pnl"]},
            {"Metric": "--- Strategy & Protective Orders ---", "Value": ""},
            {"Metric": "Take Profit 1 Hits", "Value": summary["strategy"]["tp1_hits"]},
            {"Metric": "Take Profit 2 Hits", "Value": summary["strategy"]["tp2_hits"]},
            {"Metric": "Take Profit 3 Hits", "Value": summary["strategy"]["tp3_hits"]},
            {"Metric": "Stop Loss Hits", "Value": summary["strategy"]["sl_hits"]},
            {"Metric": "--- System Health & Latency ---", "Value": ""},
            {"Metric": "Avg Execution Latency (sec)", "Value": summary["system_health"]["avg_latency_seconds"]},
            {"Metric": "Total Log Errors", "Value": summary["system_health"]["total_errors"]},
            {"Metric": "Binance Error -2021 Count (SL Placement)", "Value": summary["system_health"]["err_2021_count"]},
            {"Metric": "Binance Error -2013 Count (Order status)", "Value": summary["system_health"]["err_2013_count"]},
            {"Metric": "Binance Error -2011 Count (Cancel failed)", "Value": summary["system_health"]["err_2011_count"]},
        ]
        df_summary = pd.DataFrame(summary_rows)

        # 2. Executions Sheet DataFrame
        exec_rows = []
        for e in executions:
            exec_rows.append({
                "ID": e.id,
                "Symbol": e.symbol,
                "Order ID": e.order_id,
                "Client Order ID": e.client_order_id,
                "Order Type": e.order_type,
                "Side": e.side,
                "Quantity": float(e.quantity),
                "Price": float(e.price),
                "Commission": float(e.commission or 0.0),
                "Commission Asset": e.commission_asset,
                "Realized P&L": float(e.realized_pnl or 0.0) if e.realized_pnl is not None else None,
                "Order Time": e.order_time.isoformat() if e.order_time else None,
                "Fill Time": e.fill_time.isoformat() if e.fill_time else None,
                "Strategy Signal": e.strategy_signal,
                "TP Level": e.tp_level
            })
        df_exec = pd.DataFrame(exec_rows)

        # 3. System Logs Sheet DataFrame
        log_rows = []
        for l in logs:
            log_rows.append({
                "Timestamp": l.created_at.isoformat() if l.created_at else None,
                "Level": l.level,
                "Logger": l.logger_name,
                "Symbol": l.symbol,
                "Message": l.message,
                "Extra Data": str(l.extra_data) if l.extra_data else ""
            })
        df_logs = pd.DataFrame(log_rows)

        # Create output buffer
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name="Summary Overview", index=False)
            df_exec.to_excel(writer, sheet_name="Order Executions", index=False)
            df_logs.to_excel(writer, sheet_name="System Health Logs", index=False)
            
        return output.getvalue()

    @staticmethod
    def generate_pdf_report(db: Session, symbol: str, start_date: datetime, end_date: datetime) -> bytes:
        """Generate a professionally designed PDF performance report using reportlab."""
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        summary = ReportService.get_report_summary_data(db, symbol, start_date, end_date)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#0F172A'),
            spaceAfter=15
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#64748B'),
            spaceAfter=25
        )
        h2_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1E293B'),
            spaceBefore=15,
            spaceAfter=10
        )
        body_style = ParagraphStyle(
            'BodyDark',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#334155')
        )
        bold_body_style = ParagraphStyle(
            'BoldBodyDark',
            parent=body_style,
            fontName='Helvetica-Bold'
        )

        elements = []

        # 1. Header Section
        elements.append(Paragraph(f"Trading Bot Performance Audit", title_style))
        elements.append(Paragraph(
            f"<b>Asset Symbol:</b> {summary['symbol']} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Period:</b> {summary['start_date'][:10]} to {summary['end_date'][:10]} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Generated At:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            subtitle_style
        ))
        
        # 2. Summary Grid (Financial KPIs)
        elements.append(Paragraph("1. Financial Summary Indicators", h2_style))
        
        pnl_val = summary['financials']['net_pnl']
        pnl_color = '#10B981' if pnl_val >= 0 else '#EF4444'
        pnl_str = f"+${pnl_val:.4f}" if pnl_val >= 0 else f"-${abs(pnl_val):.4f}"
        
        kpi_data = [
            [
                Paragraph("<b>Net Profit / Loss</b>", body_style), 
                Paragraph(f"<font color='{pnl_color}'><b>{pnl_str}</b></font>", bold_body_style)
            ],
            [
                Paragraph("<b>Win Rate</b>", body_style), 
                Paragraph(f"{summary['financials']['win_rate']}%", body_style)
            ],
            [
                Paragraph("<b>Profit Factor</b>", body_style), 
                Paragraph(f"{summary['financials']['profit_factor']}", body_style)
            ],
            [
                Paragraph("<b>Max Drawdown</b>", body_style), 
                Paragraph(f"{summary['financials']['max_drawdown']:.4f}%", body_style)
            ],
            [
                Paragraph("<b>Total Closed Trades</b>", body_style), 
                Paragraph(str(summary['financials']['total_trades']), body_style)
            ],
            [
                Paragraph("<b>Total Commission Paid</b>", body_style), 
                Paragraph(f"${summary['financials']['total_commission']:.4f}", body_style)
            ]
        ]
        
        kpi_table = Table(kpi_data, colWidths=[200, 300])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#E2E8F0')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 15))

        # 3. Directional Breakdown
        elements.append(Paragraph("2. Directional Performance (Long vs. Short)", h2_style))
        dir_data = [
            [
                Paragraph("<b>Direction</b>", bold_body_style),
                Paragraph("<b>Position Count</b>", bold_body_style),
                Paragraph("<b>Win Rate</b>", bold_body_style),
                Paragraph("<b>Realized PnL</b>", bold_body_style)
            ],
            [
                Paragraph("🟢 LONG Positions", body_style),
                Paragraph(str(summary['directional']['long_count']), body_style),
                Paragraph(f"{summary['directional']['long_win_rate']}%", body_style),
                Paragraph(f"${summary['directional']['long_pnl']:.4f}", body_style)
            ],
            [
                Paragraph("🔴 SHORT Positions", body_style),
                Paragraph(str(summary['directional']['short_count']), body_style),
                Paragraph(f"{summary['directional']['short_win_rate']}%", body_style),
                Paragraph(f"${summary['directional']['short_pnl']:.4f}", body_style)
            ]
        ]
        dir_table = Table(dir_data, colWidths=[150, 110, 110, 130])
        dir_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(dir_table)
        elements.append(Spacer(1, 15))

        # 4. Strategy Protections & SL/TP Progression
        elements.append(Paragraph("3. Strategy Progression & Protective Fills", h2_style))
        strat_data = [
            [
                Paragraph("<b>Take Profit 1 Hits</b>", body_style), Paragraph(str(summary['strategy']['tp1_hits']), body_style),
                Paragraph("<b>Take Profit 2 Hits</b>", body_style), Paragraph(str(summary['strategy']['tp2_hits']), body_style)
            ],
            [
                Paragraph("<b>Take Profit 3 Hits</b>", body_style), Paragraph(str(summary['strategy']['tp3_hits']), body_style),
                Paragraph("<b>Stop Loss Hits</b>", body_style), Paragraph(str(summary['strategy']['sl_hits']), body_style)
            ]
        ]
        strat_table = Table(strat_data, colWidths=[150, 100, 150, 100])
        strat_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(strat_table)
        elements.append(Spacer(1, 15))

        # 5. System Health & Binance API Diagnostics
        elements.append(Paragraph("4. Technical System Health & Diagnostics", h2_style))
        health_status = "HEALTHY" if summary['system_health']['total_errors'] == 0 else "WARNING / ERRORS DETECTED"
        health_color = '#10B981' if summary['system_health']['total_errors'] == 0 else '#F59E0B'
        
        health_data = [
            [
                Paragraph("<b>System Diagnostic Status</b>", body_style),
                Paragraph(f"<font color='{health_color}'><b>{health_status}</b></font>", bold_body_style)
            ],
            [
                Paragraph("<b>Avg Fill Latency (sec)</b>", body_style),
                Paragraph(f"{summary['system_health']['avg_latency_seconds']} seconds", body_style)
            ],
            [
                Paragraph("<b>Binance Order Immediate Trigger (Code -2021)</b>", body_style),
                Paragraph(str(summary['system_health']['err_2021_count']), body_style)
            ],
            [
                Paragraph("<b>Binance Order Not Found (Code -2013)</b>", body_style),
                Paragraph(str(summary['system_health']['err_2013_count']), body_style)
            ],
            [
                Paragraph("<b>Binance Cancel Fail (Code -2011)</b>", body_style),
                Paragraph(str(summary['system_health']['err_2011_count']), body_style)
            ],
            [
                Paragraph("<b>Other System/Engine Errors</b>", body_style),
                Paragraph(str(summary['system_health']['other_errors_count']), body_style)
            ]
        ]
        health_table = Table(health_data, colWidths=[280, 220])
        health_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('PADDING', (0,0), (-1,-1), 7),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(health_table)

        doc.build(elements)
        return buffer.getvalue()
