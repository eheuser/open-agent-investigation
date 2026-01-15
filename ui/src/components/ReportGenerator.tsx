/**
 * Report Generator Component
 * 
 * Provides UI for generating investigation reports in markdown and PDF formats.
 */

import React, { useState, useEffect } from 'react';
import api from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ReportGeneratorProps {
  investigationId: string;
}

interface ReportData {
  markdown: string;
  title: string;
  generated_at: string;
  artifacts_count: number;
  timeline_entries_count: number;
  event_types_count: number;
}

export default function ReportGenerator({ investigationId }: ReportGeneratorProps) {
  const [loading, setLoading] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(true);
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [userPrompt, setUserPrompt] = useState('Create a narrative flow interpretation of the events.');
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Load existing report on mount
  useEffect(() => {
    const loadExistingReport = async () => {
      try {
        const response = await api.get(`/api/v1/reports/latest/${investigationId}`);
        setReportData(response.data);
      } catch (err: any) {
        // 404 is expected if no report exists yet
        if (err.response?.status !== 404) {
          console.error('Failed to load existing report:', err);
        }
      } finally {
        setLoadingExisting(false);
      }
    };

    loadExistingReport();
  }, [investigationId]);

  const handleGenerateMarkdown = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.post('/api/v1/reports/generate', {
        investigation_id: investigationId,
        user_prompt: userPrompt || null,
        format: 'markdown',
      });
      
      setReportData(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate report');
      console.error('Report generation error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    setLoading(true);
    setError(null);
    setReportData(null); // Clear previous preview
    
    try {
      const response = await api.post('/api/v1/reports/download', {
        investigation_id: investigationId,
        user_prompt: userPrompt || null,
        format: 'pdf',
      }, {
        responseType: 'blob',
      });
      
      // Create download link
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Extract filename from Content-Disposition header or use default
      const contentDisposition = response.headers['content-disposition'];
      let filename = 'investigation_report.pdf';
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/);
        if (filenameMatch) {
          filename = filenameMatch[1].trim();
        }
      }
      
      // Ensure proper .pdf extension (remove defanging)
      // Some browsers/proxies add underscore to potentially dangerous extensions
      filename = filename.replace(/\.pdf_?$/i, '.pdf');
      // Ensure it ends with .pdf
      if (!filename.toLowerCase().endsWith('.pdf')) {
        filename += '.pdf';
      }
      
      // Force the download attribute to use .pdf extension
      link.download = filename;
      link.setAttribute('download', filename); // Explicit attribute set
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      // Show success modal
      setError(null);
      setSuccessMessage(`Report "${filename}" downloaded successfully!`);
      setShowSuccessModal(true);
    } catch (err: any) {
      // Try to extract error from blob response
      let errorMessage = 'Failed to download PDF';
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const errorData = JSON.parse(text);
          errorMessage = errorData.detail || errorMessage;
        } catch {
          errorMessage = 'PDF generation failed (server error)';
        }
      } else {
        errorMessage = err.response?.data?.detail || err.message || errorMessage;
      }
      setError(errorMessage);
      console.error('PDF download error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full bg-white dark:bg-gray-900">
      {/* Left Column - Report Preview */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-700 p-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Investigation Report
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Generate comprehensive forensic reports with timeline, artifacts, and findings
          </p>
        </div>

        {/* Preview */}
        {reportData ? (
          <div className="flex-1 overflow-auto p-6">
          <div className="max-w-4xl mx-auto">
            {/* Metadata */}
            <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Report Metadata</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Generated:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">
                    {new Date(reportData.generated_at).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Artifacts:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">{reportData.artifacts_count}</span>
                </div>
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Timeline Entries:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">{reportData.timeline_entries_count}</span>
                </div>
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Event Types:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">{reportData.event_types_count}</span>
                </div>
              </div>
            </div>

            {/* Markdown Preview */}
            <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-h1:text-3xl prose-h2:text-2xl prose-h3:text-xl prose-table:text-sm">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  // Style tables properly
                  table: ({node, ...props}) => (
                    <div className="overflow-x-auto my-4">
                      <table className="min-w-full divide-y divide-gray-300 dark:divide-gray-700" {...props} />
                    </div>
                  ),
                  thead: ({node, ...props}) => (
                    <thead className="bg-gray-50 dark:bg-gray-800" {...props} />
                  ),
                  th: ({node, ...props}) => (
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider" {...props} />
                  ),
                  td: ({node, ...props}) => (
                    <td className="px-3 py-2 text-sm text-gray-900 dark:text-gray-100" {...props} />
                  ),
                  // Style code blocks
                  code: ({node, inline, className, children, ...props}: any) => {
                    const isInline = !className?.includes('language-');
                    if (isInline) {
                      return (
                        <code className="bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100 px-1.5 py-0.5 rounded font-mono text-xs" {...props}>
                          {children}
                        </code>
                      );
                    }
                    return (
                      <code className="block bg-gray-900 dark:bg-gray-950 text-gray-100 p-3 rounded font-mono text-xs overflow-x-auto" {...props}>
                        {children}
                      </code>
                    );
                  },
                  // Style horizontal rules
                  hr: ({node, ...props}) => (
                    <hr className="my-6 border-gray-300 dark:border-gray-700" {...props} />
                  ),
                }}
              >
                {reportData.markdown}
              </ReactMarkdown>
            </div>
          </div>
          </div>
        ) : !loading && !loadingExisting ? (
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="text-center">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                No report generated
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Click "Generate Preview" to create a report, or "Download PDF" for immediate download
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {/* Right Column - Report Controls */}
      <div className="w-1/3 min-w-[400px] border-l border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-800">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
            Report Generation
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Configure and generate investigation reports
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* User Prompt */}
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
              Custom Instructions (Optional)
            </label>
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Create a narrative flow interpretation of the events."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg 
                       bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={4}
              disabled={loading}
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Provide optional instructions to guide the report tone, focus, or format
            </p>
          </div>

          {/* Action Buttons */}
          <div className="space-y-2">
            <button
              onClick={handleGenerateMarkdown}
              disabled={loading}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 
                       text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Generating...' : 'Generate Preview'}
            </button>
            
            <button
              onClick={handleDownloadPDF}
              disabled={loading}
              className="w-full px-4 py-2 bg-emerald-700 hover:bg-emerald-800 disabled:bg-gray-400 
                       text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Generating...' : 'Download PDF'}
            </button>
          </div>

          {/* Error Display */}
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Loading Modal */}
      {loading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-8 max-w-md w-full mx-4">
            <div className="flex flex-col items-center">
              <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Generating Report
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 text-center">
                Please wait while we compile your investigation data and generate the report...
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Success Modal */}
      {showSuccessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-8 max-w-md w-full mx-4">
            <div className="flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Report Generated
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 text-center mb-6">
                {successMessage}
              </p>
              <button
                onClick={() => setShowSuccessModal(false)}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

