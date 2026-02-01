import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  BeakerIcon, 
  DocumentPlusIcon, 
  ChatBubbleLeftRightIcon,
  ChartBarIcon,
  ExclamationTriangleIcon 
} from '@heroicons/react/24/outline';
import { createInvestigation } from '../services/investigations';

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [isCreating, setIsCreating] = useState(false);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const createNewInvestigation = async () => {
    setIsCreating(true);
    try {
      const newInv = await createInvestigation({ title: 'New Investigation' });
      navigate(`/investigation/${newInv.investigation_id}`);
    } catch (error: any) {
      console.error('Failed to create investigation:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Unknown error';
      setErrorMessage(`Failed to create investigation: ${errMsg}`);
      setErrorModalOpen(true);
    } finally {
      setIsCreating(false);
    }
  };

  const features = [
    {
      icon: DocumentPlusIcon,
      title: 'Upload Artifacts',
      description: 'Upload registry hives, EVTX logs, binaries, and archives for analysis',
    },
    {
      icon: ChatBubbleLeftRightIcon,
      title: 'AI-Powered Analysis',
      description: 'Ask questions and let intelligent agents analyze your evidence',
    },
    {
      icon: ChartBarIcon,
      title: 'Knowledge Graph',
      description: 'Visualize relationships and build a comprehensive evidence map',
    },
  ];

  return (
    <div className="flex items-center justify-center h-full bg-white dark:bg-gray-900">
      <div className="max-w-4xl mx-auto px-6 py-12 text-center">
        {/* Hero Section */}
        <div className="mb-12">
          <div className="inline-flex items-center justify-center w-20 h-20 mb-6 bg-gradient-to-br from-blue-500 to-purple-600 dark:bg-gray-700 dark:bg-gradient-to-br dark:from-gray-600 dark:to-gray-600 rounded-3xl">
            <BeakerIcon className="w-12 h-12 text-white" />
          </div>
          
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-4">
            Welcome to Open Agent Investigation
          </h1>
          
          <p className="text-lg text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
            A chat-driven investigation platform for security analysts. Upload evidence, ask questions, and let agents help you uncover the truth.
          </p>

          <button
            onClick={createNewInvestigation}
            disabled={isCreating}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 dark:bg-gray-700 dark:hover:bg-gray-600 dark:disabled:bg-gray-500 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-colors shadow-lg shadow-blue-500/30 dark:shadow-none"
          >
            <DocumentPlusIcon className="w-5 h-5" />
            {isCreating ? 'Creating...' : 'Start New Investigation'}
          </button>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-3 gap-6 mt-16">
          {features.map((feature, idx) => {
            const Icon = feature.icon;
            return (
              <div
                key={idx}
                                  className="p-6 bg-gray-50 dark:bg-gray-800 rounded-2xl hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
              >
                <div className="inline-flex items-center justify-center w-12 h-12 mb-4 bg-blue-100 dark:bg-gray-700 rounded-xl">
                  <Icon className="w-6 h-6 text-blue-600 dark:text-gray-300" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>

                  {/* Footer Note */}
          <div className="mt-12 pt-8">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Open source and GPL-v3 licensed • Built for security professionals
            </p>
          </div>
      </div>

      {/* Error Modal */}
      {errorModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setErrorModalOpen(false)}
          />
          
          {/* Modal */}
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Error
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  {errorMessage}
                </p>
                <div className="flex justify-end">
                  <button
                    onClick={() => setErrorModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 transition-colors"
                  >
                    OK
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
