const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export const reportService = {
  /**
   * Fetch summarized KPI metrics for the reports dashboard.
   */
  async getReportSummary(symbol = 'ALL', startDate = '', endDate = '') {
    let url = `${BASE_URL}/reports/summary?symbol=${symbol}`;
    if (startDate) url += `&start_date=${startDate}`;
    if (endDate) url += `&end_date=${endDate}`;
    
    const res = await fetch(url);
    if (!res.ok) {
      const errMsg = await res.text();
      throw new Error(errMsg || 'Failed to fetch report summary');
    }
    return res.json();
  },

  /**
   * Triggers a browser file download of the PDF or Excel sheet report.
   */
  async downloadReport(symbol = 'ALL', startDate = '', endDate = '', format = 'pdf') {
    let url = `${BASE_URL}/reports/download?symbol=${symbol}&format=${format}`;
    if (startDate) url += `&start_date=${startDate}`;
    if (endDate) url += `&end_date=${endDate}`;

    const res = await fetch(url);
    if (!res.ok) {
      const errMsg = await res.text();
      throw new Error(errMsg || 'Failed to download report');
    }

    const blob = await res.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    
    const extension = format.toLowerCase() === 'excel' ? 'xlsx' : 'pdf';
    const filename = `trading_report_${symbol}_${startDate || 'period'}.${extension}`;
    
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    
    // Cleanup DOM and memory
    link.remove();
    window.URL.revokeObjectURL(downloadUrl);
  }
};
