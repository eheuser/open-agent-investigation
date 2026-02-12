import React, { useCallback, useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import api from '../services/api';
import {
  CloudArrowUpIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';
import ConfigurationErrorModal from './ConfigurationErrorModal';
import { useLLMConfig } from '../hooks/useLLMConfig';

interface Props {
  investigationId: string;
  onUploadComplete?: () => void;
  initialFiles?: File[];
  maxFiles?: number;  // Maximum files to upload at once
  concurrentUploads?: number;  // Number of concurrent uploads
}

interface UploadedFile {
  fileName: string;
  artifactId: number;
  jobId: number;
  status: 'uploading' | 'queued' | 'parsing' | 'completed' | 'failed';
  progress?: number;
  error?: string;
  eventCount?: number;
}

const FileDropzone: React.FC<Props> = ({
  investigationId,
  onUploadComplete,
  initialFiles,
  maxFiles = 50,  // Default max 50 files
  concurrentUploads = 3,  // Default 3 concurrent uploads
}) => {
  const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pollingInterval, setPollingInterval] = useState<number | null>(null);
  const { hasConfig, checkConfig } = useLLMConfig();
  const [showConfigError, setShowConfigError] = useState(false);

  // Handle initial files if provided
  useEffect(() => {
    if (initialFiles && initialFiles.length > 0) {
      onDrop(initialFiles);
    }
  }, [initialFiles]);

  const onDrop = useCallback(
    (files: File[]) => {
      // Limit number of files
      if (files.length > maxFiles) {
        alert(`You can only upload up to ${maxFiles} files at once. Please select fewer files.`);
        return;
      }
      setSelectedFiles(files);
    },
    [maxFiles]
  );

  // Poll for job status updates
  useEffect(() => {
    const pollJobStatus = async () => {
      const pendingJobs = uploadedFiles.filter(
        f => f.status === 'queued' || f.status === 'parsing'
      );

      if (pendingJobs.length === 0) {
        if (pollingInterval) {
          clearInterval(pollingInterval);
          setPollingInterval(null);
        }
        return;
      }

      try {
        // Fetch status for all pending jobs
        const updates = await Promise.all(
          pendingJobs.map(async (file) => {
            try {
              const response = await api.get(`/api/v1/jobs/parsing/${file.jobId}`);
              return {
                jobId: file.jobId,
                status: response.data.status,
                error: response.data.error_message,
                eventCount: response.data.event_count,
              };
            } catch (err) {
              return { jobId: file.jobId, status: file.status };
            }
          })
        );

        // Update file statuses
        setUploadedFiles(prev =>
          prev.map(file => {
            const update = updates.find(u => u.jobId === file.jobId);
            if (!update) return file;

            return {
              ...file,
              status: update.status === 'completed' ? 'completed' :
                update.status === 'failed' ? 'failed' :
                  update.status === 'running' ? 'parsing' : file.status,
              error: update.error,
              eventCount: update.eventCount,
            };
          })
        );
      } catch (err) {
        console.error('Failed to poll job status:', err);
      }
    };

    // Start polling if we have pending jobs and not already polling
    const hasPendingJobs = uploadedFiles.some(
      f => f.status === 'queued' || f.status === 'parsing'
    );

    if (hasPendingJobs && !pollingInterval) {
      const interval = setInterval(pollJobStatus, 2000); // Poll every 2 seconds
      setPollingInterval(interval);
    }

    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [uploadedFiles, pollingInterval]);

  const uploadSingleFile = async (file: File): Promise<void> => {
    const form = new FormData();
    form.append('file', file);
    form.append('investigation_id', investigationId);

    try {
      const response = await api.post('/api/v1/artifacts/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const progress = progressEvent.total
            ? Math.round((progressEvent.loaded * 100) / progressEvent.total)
            : 0;

          setUploadedFiles(prev =>
            prev.map(f =>
              f.fileName === file.name && f.status === 'uploading'
                ? { ...f, progress }
                : f
            )
          );
        },
      });

      // Update with artifact_id and job_id, set status to 'queued'
      setUploadedFiles(prev =>
        prev.map(f =>
          f.fileName === file.name && f.status === 'uploading'
            ? {
              ...f,
              artifactId: response.data.artifact_id,
              jobId: response.data.job_id,
              status: 'queued',
              progress: 100,
            }
            : f
        )
      );
    } catch (error: any) {
      console.error(`Upload failed for ${file.name}:`, error);

      // Mark this specific file as failed
      setUploadedFiles(prev =>
        prev.map(f =>
          f.fileName === file.name && f.status === 'uploading'
            ? {
              ...f,
              status: 'failed',
              error: error.response?.data?.detail || error.message || 'Upload failed'
            }
            : f
        )
      );
    }
  };

  const handleUpload = async () => {
    // Check for LLM config before uploading
    const isValid = await checkConfig();
    if (!isValid) {
      setShowConfigError(true);
      return;
    }

    setUploading(true);

    try {
      // Initialize all files with 'uploading' status
      const initialUploads: UploadedFile[] = selectedFiles.map(file => ({
        fileName: file.name,
        artifactId: -1,
        jobId: -1,
        status: 'uploading' as const,
        progress: 0,
      }));

      setUploadedFiles(prev => [...prev, ...initialUploads]);

      // Upload files in batches to avoid overwhelming the server
      for (let i = 0; i < selectedFiles.length; i += concurrentUploads) {
        const batch = selectedFiles.slice(i, i + concurrentUploads);
        await Promise.all(batch.map(file => uploadSingleFile(file)));
      }

      setSelectedFiles([]);
      onUploadComplete?.();
    } catch (error: any) {
      console.error('Upload batch failed:', error);
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled: uploading,
  });

  return (
    <>
      <ConfigurationErrorModal
        isOpen={showConfigError}
        onClose={() => setShowConfigError(false)}
        title="LLM Configuration Required"
        message="You must configure an LLM provider before uploading artifacts. Artifact processing and parsing require LLM capabilities for analysis and embedding generation."
        showSettingsButton={true}
      />
      <div className="flex flex-col h-full">
        {/* Dropzone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all flex-shrink-0 ${isDragActive
              ? 'border-blue-500 bg-blue-50 dark:border-gray-400 dark:bg-gray-800'
              : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/50'
            }`}
        >
          <input {...getInputProps()} />

          <div className="flex flex-col items-center gap-2">
            <div className="p-3 bg-blue-100 dark:bg-gray-700 rounded-full">
              <CloudArrowUpIcon className="w-6 h-6 text-blue-600 dark:text-gray-300" />
            </div>

            {isDragActive ? (
              <p className="text-blue-600 dark:text-gray-300 font-medium text-sm">
                Drop the files here...
              </p>
            ) : (
              <>
                <p className="text-gray-900 dark:text-white font-medium text-sm">
                  Drag & drop files here
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  or click to browse
                </p>
              </>
            )}
          </div>
        </div>

        {/* Selected Files List */}
        <div className="flex-1 mt-4 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2 flex-shrink-0">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Selected Files ({selectedFiles.length}):
            </p>
            {selectedFiles.length > maxFiles && (
              <p className="text-xs text-red-600 dark:text-red-400 font-medium">
                Limit: {maxFiles} files max
              </p>
            )}
          </div>

          <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-y-auto" style={{ height: '250px' }}>
            {selectedFiles.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center">
                  No files selected
                </p>
              </div>
            ) : (
              <div className="p-2 space-y-2">
                {selectedFiles.map((file) => {
                  const uploadedFile = uploadedFiles.find(f => f.fileName === file.name);
                  const isUploading = uploadedFile?.status === 'uploading';
                  const isQueued = uploadedFile?.status === 'queued';
                  const isParsing = uploadedFile?.status === 'parsing';
                  const isCompleted = uploadedFile?.status === 'completed';
                  const isFailed = uploadedFile?.status === 'failed';

                  return (
                    <div key={file.name} className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg relative overflow-hidden">
                      {/* Progress bar background */}
                      {isUploading && uploadedFile?.progress !== undefined && (
                        <div
                          className="absolute inset-0 bg-blue-100 dark:bg-blue-900/20 transition-all duration-300"
                          style={{ width: `${uploadedFile.progress}%` }}
                        />
                      )}

                      <div className="relative">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            {/* Status Icon */}
                            {isUploading && (
                              <ArrowPathIcon className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin flex-shrink-0" />
                            )}
                            {isQueued && (
                              <ClockIcon className="w-4 h-4 text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
                            )}
                            {isParsing && (
                              <ArrowPathIcon className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin flex-shrink-0" />
                            )}
                            {isCompleted && (
                              <CheckCircleIcon className="w-4 h-4 text-green-600 dark:text-green-400 flex-shrink-0" />
                            )}
                            {isFailed && (
                              <ExclamationCircleIcon className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
                            )}

                            <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {file.name}
                            </span>
                          </div>
                          <span className="text-xs text-gray-500 dark:text-gray-400 ml-2 flex-shrink-0">
                            {(file.size / 1024).toFixed(1)} KB
                          </span>
                        </div>

                        {/* Status message */}
                        {uploadedFile && (
                          <div className="mb-2">
                            <span className={`text-xs ${isCompleted ? 'text-green-700 dark:text-green-300' :
                                isFailed ? 'text-red-700 dark:text-red-300' :
                                  isParsing ? 'text-blue-700 dark:text-blue-300' :
                                    'text-yellow-700 dark:text-yellow-300'
                              }`}>
                              {isUploading && `Uploading... ${uploadedFile.progress}%`}
                              {isQueued && 'Queued for parsing'}
                              {isParsing && 'Parsing...'}
                              {isCompleted && `✓ Completed - ${uploadedFile.eventCount || 0} events`}
                              {isFailed && `Failed: ${uploadedFile.error || 'Unknown error'}`}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        {selectedFiles.length > 0 && (
          <div className="flex gap-2 mt-4 flex-shrink-0">
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? 'Uploading...' : 'Upload Files'}
            </button>

            <button
              onClick={() => {
                setSelectedFiles([]);
              }}
              disabled={uploading}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-900 dark:text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </>
  );
};

export default FileDropzone;
