"""FastAPI API endpoints for generating and downloading reports."""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.report_service import ReportService

logger = logging.getLogger("ha_alma_bot")

router = APIRouter()

def parse_dates(start_date_str: str = None, end_date_str: str = None):
    """Utility to parse incoming string dates with default fallbacks (last 30 days)."""
    try:
        if end_date_str:
            # Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
            if "T" in end_date_str:
                end_date = datetime.fromisoformat(end_date_str)
            else:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_date = datetime.utcnow()

        if start_date_str:
            if "T" in start_date_str:
                start_date = datetime.fromisoformat(start_date_str)
            else:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        else:
            start_date = end_date - timedelta(days=30)
            
        return start_date, end_date
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use YYYY-MM-DD. Error: {e}")

@router.get("/summary")
def get_report_summary(
    symbol: str = Query("ALL", description="Trading pair symbol or 'ALL'"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Retrieve summarized KPIs for a trading symbol/period for on-screen dashboard preview."""
    s_date, e_date = parse_dates(start_date, end_date)
    try:
        return ReportService.get_report_summary_data(db, symbol, s_date, e_date)
    except Exception as e:
        logger.error(f"Failed to generate report summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error compiling report summary: {str(e)}")

@router.get("/download")
def download_report(
    symbol: str = Query("ALL", description="Trading pair symbol or 'ALL'"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    format: str = Query("pdf", description="Report format: 'pdf' or 'excel'"),
    db: Session = Depends(get_db)
):
    """Generate and download a formatted PDF or Excel spreadsheet report."""
    s_date, e_date = parse_dates(start_date, end_date)
    
    try:
        if format.lower() == "excel":
            file_bytes = ReportService.generate_excel_report(db, symbol, s_date, e_date)
            filename = f"trading_report_{symbol}_{s_date.strftime('%Y%m%d')}_{e_date.strftime('%Y%m%d')}.xlsx"
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif format.lower() == "pdf":
            file_bytes = ReportService.generate_pdf_report(db, symbol, s_date, e_date)
            filename = f"trading_report_{symbol}_{s_date.strftime('%Y%m%d')}_{e_date.strftime('%Y%m%d')}.pdf"
            media_type = "application/pdf"
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Supported values: 'pdf', 'excel'")

        # Return file stream
        import io
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Failed to download report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating export: {str(e)}")
