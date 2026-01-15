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

interface Props {
  investigationId: string;
  onUploadComplete?: () => void;
  initialFiles?: File[];
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

enum ArtifactClassification {
  SYSTEM_HIVE = 0,
  LOG_FILE = 1,
  BINARY = 2,
  ARCHIVE = 3,
  UNKNOWN = 4,
}

const CLASSIFICATION_LABELS: Record<ArtifactClassification, string> = {
  [ArtifactClassification.SYSTEM_HIVE]: 'Registry Hive',
  [ArtifactClassification.LOG_FILE]: 'Log File (EVTX)',
  [ArtifactClassification.BINARY]: 'Binary (EXE, DLL, Prefetch, LNK)',
  [ArtifactClassification.ARCHIVE]: 'Archive (MFT, ZIP)',
  [ArtifactClassification.UNKNOWN]: 'Unknown',
};

/**
 * Check file magic bytes to identify file type
 * @param file The file to check
 * @returns Promise with the detected classification or null if not detected
 */
const checkFileMagic = async (file: File): Promise<ArtifactClassification | null> => {
  // Read first 5 bytes to check magic signatures
  const slice = file.slice(0, 5);
  const buffer = await slice.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  
  // Check for Registry Hive: starts with "regf" (0x72 0x65 0x67 0x66)
  if (bytes.length >= 4 && 
      bytes[0] === 0x72 && bytes[1] === 0x65 && 
      bytes[2] === 0x67 && bytes[3] === 0x66) {
    return ArtifactClassification.SYSTEM_HIVE;
  }
  
  // Check for MFT: starts with "FILE0" (0x46 0x49 0x4C 0x45 0x30)
  if (bytes.length >= 5 && 
      bytes[0] === 0x46 && bytes[1] === 0x49 && 
      bytes[2] === 0x4C && bytes[3] === 0x45 && 
      bytes[4] === 0x30) {
    return ArtifactClassification.ARCHIVE;
  }
  
  return null;
};

const FileDropzone: React.FC<Props> = ({
  investigationId,
  onUploadComplete,
  initialFiles
}) => {
            const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileClassifications, setFileClassifications] = useState<Record<string, ArtifactClassification>>({});
  const [pollingInterval, setPollingInterval] = useState<number | null>(null);

  // Handle initial files if provided
  useEffect(() => {
    if (initialFiles && initialFiles.length > 0) {
      onDrop(initialFiles);
    }
  }, [initialFiles]);

        const onDrop = useCallback(
    async (files: File[]) => {
      setSelectedFiles(files);
      
      // Auto-detect classification based on file magic and extension
      const classifications: Record<string, ArtifactClassification> = {};
      
      for (const file of files) {
        // First, try to detect by file magic bytes
        const magicClassification = await checkFileMagic(file);
        
        if (magicClassification !== null) {
          classifications[file.name] = magicClassification;
          continue;
        }
        
        // Fall back to extension-based detection
        const ext = file.name.toLowerCase();
        if (ext.endsWith('.evtx')) {
          classifications[file.name] = ArtifactClassification.LOG_FILE;
        } else if (ext.endsWith('.reg') || ext.includes('hive') || ext.includes('ntuser')) {
          classifications[file.name] = ArtifactClassification.SYSTEM_HIVE;
        } else if (ext.endsWith('.exe') || ext.endsWith('.dll') || ext.endsWith('.pf') || ext.endsWith('.lnk')) {
          classifications[file.name] = ArtifactClassification.BINARY;
        } else if (ext.endsWith('.zip') || ext.endsWith('.mft') || ext.includes('$mft')) {
          classifications[file.name] = ArtifactClassification.ARCHIVE;
        } else {
          classifications[file.name] = ArtifactClassification.UNKNOWN;
        }
      }
      
      setFileClassifications(classifications);
    },
    []
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

  const handleUpload = async () => {
    setUploading(true);
    const newUploads: UploadedFile[] = [];
    
    try {
      for (const file of selectedFiles) {
        const classification = fileClassifications[file.name] ?? ArtifactClassification.UNKNOWN;
        
        // Add to uploaded files with 'uploading' status
        const uploadingFile: UploadedFile = {
          fileName: file.name,
          artifactId: -1,
          jobId: -1,
          status: 'uploading',
          progress: 0,
        };
        newUploads.push(uploadingFile);
        setUploadedFiles(prev => [...prev, uploadingFile]);
        
        const form = new FormData();
        form.append('file', file);
        form.append('investigation_id', investigationId);
        form.append('classification', classification.toString());

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
      }
      
      setSelectedFiles([]);
      setFileClassifications({});
      onUploadComplete?.();
    } catch (error: any) {
      console.error('Upload failed:', error);
      
      // Mark failed uploads
      setUploadedFiles(prev =>
        prev.map(f =>
          f.status === 'uploading'
            ? { ...f, status: 'failed', error: error.message || 'Upload failed' }
            : f
        )
      );
    } finally {
      setUploading(false);
    }
  };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ 
    onDrop,
    disabled: uploading,
  });

          return (
    <div className="flex flex-col h-full">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all flex-shrink-0 ${
          isDragActive 
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
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex-shrink-0">
          Selected Files ({selectedFiles.length}):
        </p>
        
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
                          <span className={`text-xs ${
                            isCompleted ? 'text-green-700 dark:text-green-300' :
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
                      
                      {/* Classification dropdown - hide when uploading */}
                      {!uploadedFile && (
                        <select
                          value={fileClassifications[file.name] ?? ArtifactClassification.UNKNOWN}
                          onChange={(e) => setFileClassifications(prev => ({
                            ...prev,
                            [file.name]: parseInt(e.target.value) as ArtifactClassification
                          }))}
                          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                        >
                          {Object.entries(CLASSIFICATION_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
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
              setFileClassifications({});
            }}
            disabled={uploading}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-900 dark:text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
};

export default FileDropzone;
