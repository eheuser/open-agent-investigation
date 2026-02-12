import React, { useState, useEffect, useMemo } from 'react';
import {
  XMarkIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';
import api from '../services/api';

interface ParsingJob {
  job_id: number;
  artifact_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

interface AgentJob {
  job_id: number;
  user_id: number;
  policy_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

interface JobsModalProps {
  investigationId: string;
  onClose: () => void;
}

const JobsModal: React.FC<JobsModalProps> = ({ investigationId, onClose }) => {
  const [parsingJobs, setParsingJobs] = useState<ParsingJob[]>([]);
  const [agentJobs, setAgentJobs] = useState<AgentJob[]>([]);
  const [artifacts, setArtifacts] = useState<Map<number, string>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search and filtering
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [jobTypeFilter, setJobTypeFilter] = useState<'all' | 'parsing' | 'agent'>('all');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const fetchJobs = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch parsing jobs
      const parsingResponse = await api.get(
        `/api/v1/jobs/parsing/investigation/${investigationId}`
      );
      setParsingJobs(parsingResponse.data.jobs || []);

      // Fetch agent jobs
      const agentResponse = await api.get(
        `/api/v1/jobs/agent/investigation/${investigationId}`
      );
      setAgentJobs(agentResponse.data.jobs || []);

      // Fetch artifacts to get filenames
      const artifactsResponse = await api.get(
        `/api/v1/artifacts/investigation/${investigationId}`
      );
      const artifactMap = new Map<number, string>();
      (artifactsResponse.data || []).forEach((artifact: any) => {
        artifactMap.set(artifact.artifact_id, artifact.filename);
      });
      setArtifacts(artifactMap);

    } catch (err: any) {
      console.error('Failed to fetch jobs:', err);
      setError(err.response?.data?.detail || 'Failed to load jobs');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    // Refresh every 2 seconds to get live updates
    const interval = setInterval(fetchJobs, 2000);
    return () => clearInterval(interval);
  }, [investigationId]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <ClockIcon className="w-5 h-5 text-yellow-500" />;
      case 'running':
        return <ArrowPathIcon className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircleIcon className="w-5 h-5 text-green-500" />;
      case 'failed':
        return <XCircleIcon className="w-5 h-5 text-red-500" />;
      default:
        return null;
    }
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = 'px-2 py-1 text-xs font-semibold rounded-full';
    switch (status) {
      case 'pending':
        return (
          <span className={`${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200`}>
            Pending
          </span>
        );
      case 'running':
        return (
          <span className={`${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200`}>
            Running
          </span>
        );
      case 'completed':
        return (
          <span className={`${baseClasses} bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200`}>
            Completed
          </span>
        );
      case 'failed':
        return (
          <span className={`${baseClasses} bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200`}>
            Failed
          </span>
        );
      default:
        return null;
    }
  };

  const formatDuration = (startedAt: string | null, finishedAt: string | null) => {
    if (!startedAt) return '-';
    const start = new Date(startedAt).getTime();
    const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
    const durationMs = end - start;
    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  // Filter and search jobs
  const filteredJobs = useMemo(() => {
    let allJobs: Array<(ParsingJob | AgentJob) & { jobType: 'parsing' | 'agent' }> = [];

    // Add job type to each job
    if (jobTypeFilter === 'all' || jobTypeFilter === 'parsing') {
      allJobs = [...allJobs, ...parsingJobs.map(job => ({ ...job, jobType: 'parsing' as const }))];
    }
    if (jobTypeFilter === 'all' || jobTypeFilter === 'agent') {
      allJobs = [...allJobs, ...agentJobs.map(job => ({ ...job, jobType: 'agent' as const }))];
    }

    // Filter by status
    if (statusFilter !== 'all') {
      allJobs = allJobs.filter(job => job.status === statusFilter);
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      allJobs = allJobs.filter(job => {
        const jobId = job.job_id.toString();

        if ('artifact_id' in job) {
          // Parsing job
          const artifactName = artifacts.get(job.artifact_id)?.toLowerCase() || '';
          const artifactId = job.artifact_id.toString();
          return jobId.includes(query) || artifactName.includes(query) || artifactId.includes(query);
        } else {
          // Agent job
          const policyId = job.policy_id.toLowerCase();
          return jobId.includes(query) || policyId.includes(query);
        }
      });
    }

    // Sort by created_at (newest first)
    allJobs.sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return dateB - dateA;
    });

    return allJobs;
  }, [parsingJobs, agentJobs, searchQuery, statusFilter, jobTypeFilter, artifacts]);

  // Paginate filtered jobs
  const paginatedJobs = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return filteredJobs.slice(startIndex, endIndex);
  }, [filteredJobs, currentPage, itemsPerPage]);

  const totalPages = Math.ceil(filteredJobs.length / itemsPerPage);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, statusFilter, jobTypeFilter]);

  // Render a single job card
  const renderJobCard = (job: (ParsingJob | AgentJob) & { jobType: 'parsing' | 'agent' }) => {
    const isParsingJob = 'artifact_id' in job;
    const title = isParsingJob
      ? (artifacts.get(job.artifact_id) || `Artifact #${job.artifact_id}`)
      : job.policy_id;
    const subtitle = `${job.jobType === 'parsing' ? 'Parsing' : 'Agent'} Job #${job.job_id}`;

    return (
      <div
        key={`${job.jobType}-${job.job_id}`}
        className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
      >
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-3">
            {getStatusIcon(job.status)}
            <div>
              <p className="font-medium text-gray-900 dark:text-white">
                {title}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {subtitle}
              </p>
            </div>
          </div>
          {getStatusBadge(job.status)}
        </div>

        <div className="grid grid-cols-3 gap-4 mt-3 text-sm">
          <div>
            <p className="text-gray-500 dark:text-gray-400">Created</p>
            <p className="text-gray-900 dark:text-white font-mono text-xs">
              {formatTimestamp(job.created_at)}
            </p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Duration</p>
            <p className="text-gray-900 dark:text-white font-mono">
              {formatDuration(job.started_at, job.finished_at)}
            </p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Finished</p>
            <p className="text-gray-900 dark:text-white font-mono text-xs">
              {formatTimestamp(job.finished_at)}
            </p>
          </div>
        </div>

        {job.error_message && (
          <div className={`mt-3 p-3 rounded border ${
            // Check if this is an actual error or just a status message
            job.status === 'failed' || job.error_message.toLowerCase().includes('error') || job.error_message.toLowerCase().includes('failed')
              ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
              : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
            }`}>
            <p className={`text-sm font-semibold mb-1 ${job.status === 'failed' || job.error_message.toLowerCase().includes('error') || job.error_message.toLowerCase().includes('failed')
                ? 'text-red-800 dark:text-red-200'
                : 'text-blue-800 dark:text-blue-200'
              }`}>
              {job.status === 'failed' || job.error_message.toLowerCase().includes('error') || job.error_message.toLowerCase().includes('failed') ? 'Error:' : 'Status:'}
            </p>
            <p className={`text-sm font-mono ${job.status === 'failed' || job.error_message.toLowerCase().includes('error') || job.error_message.toLowerCase().includes('failed')
                ? 'text-red-700 dark:text-red-300'
                : 'text-blue-700 dark:text-blue-300'
              }`}>
              {job.error_message}
            </p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-5xl w-full h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
              Job Queue
            </h3>
            <button
              onClick={onClose}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <XMarkIcon className="w-6 h-6 text-gray-500 dark:text-gray-400" />
            </button>
          </div>

          {/* Search and Filters */}
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Search */}
            <div className="flex-1 relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by job ID, artifact, or policy..."
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              />
            </div>

            {/* Job Type Filter */}
            <div className="flex items-center gap-2">
              <FunnelIcon className="w-5 h-5 text-gray-400" />
              <select
                value={jobTypeFilter}
                onChange={(e) => setJobTypeFilter(e.target.value as 'all' | 'parsing' | 'agent')}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              >
                <option value="all">All Types</option>
                <option value="parsing">Parsing</option>
                <option value="agent">Agent</option>
              </select>
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {/* Results count */}
          <div className="flex items-center justify-between text-sm">
            <p className="text-gray-600 dark:text-gray-400">
              Showing {paginatedJobs.length} of {filteredJobs.length} jobs
              {searchQuery && ` (filtered from ${parsingJobs.length + agentJobs.length} total)`}
            </p>
            {(searchQuery || statusFilter !== 'all' || jobTypeFilter !== 'all') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setStatusFilter('all');
                  setJobTypeFilter('all');
                }}
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading && !parsingJobs.length && !agentJobs.length ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <ArrowPathIcon className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-2" />
                <p className="text-gray-600 dark:text-gray-400">Loading jobs...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <XCircleIcon className="w-8 h-8 text-red-500 mx-auto mb-2" />
                <p className="text-red-600 dark:text-red-400">{error}</p>
              </div>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <FunnelIcon className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-600 dark:text-gray-400">No jobs match your filters</p>
                <button
                  onClick={() => {
                    setSearchQuery('');
                    setStatusFilter('all');
                    setJobTypeFilter('all');
                  }}
                  className="mt-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                >
                  Clear all filters
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {paginatedJobs.map(renderJobCard)}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Page {currentPage} of {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                  className="p-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeftIcon className="w-5 h-5" />
                </button>

                {/* Page numbers */}
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }

                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${currentPage === pageNum
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 border border-gray-300 dark:border-gray-600'
                          }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>

                <button
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                  className="p-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRightIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Auto-refreshing every 2 seconds
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default JobsModal;
