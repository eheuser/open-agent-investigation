import React, { useState, useEffect } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import FileDropzone from '../FileDropzone';
import ConfigurationErrorModal from '../ConfigurationErrorModal';
import { useLLMConfig } from '../../hooks/useLLMConfig';

interface UploadModalProps {
  investigationId: string;
  onClose: () => void;
  initialFiles?: File[];
}

const UploadModal: React.FC<UploadModalProps> = ({ investigationId, onClose, initialFiles }) => {
  const { hasConfig, isLoading, checkConfig } = useLLMConfig();
  const [showConfigError, setShowConfigError] = useState(false);

  useEffect(() => {
    // Check config when modal opens
    const validateConfig = async () => {
      const isValid = await checkConfig();
      if (!isValid) {
        setShowConfigError(true);
      }
    };
    validateConfig();
  }, []);

  const handleCloseConfigError = () => {
    setShowConfigError(false);
    onClose(); // Also close the upload modal
  };

  return (
    <>
      <ConfigurationErrorModal
        isOpen={showConfigError}
        onClose={handleCloseConfigError}
        title="LLM Configuration Required"
        message="You must configure an LLM provider before uploading artifacts. Artifact processing requires LLM capabilities for parsing and analysis."
        showSettingsButton={true}
      />
      <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full flex flex-col" style={{ height: '650px', maxHeight: '90vh' }}>
          <div className="flex items-center justify-between p-6 pb-4 flex-shrink-0">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Upload Artifacts
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
          <div className="flex-1 px-6 pb-6 min-h-0">
            <FileDropzone
              investigationId={investigationId}
              initialFiles={initialFiles}
              maxFiles={50}
              concurrentUploads={5}
              onUploadComplete={() => {
                setTimeout(() => onClose(), 1500);
              }}
            />
          </div>
        </div>
      </div>
    </>
  );
};

export default UploadModal;
