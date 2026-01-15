import React from 'react';
import type { MutationPreview } from './types';

interface MutationConfirmationProps {
  preview: MutationPreview;
  onConfirm: (confirmed: boolean) => void;
  isLoading: boolean;
}

const MutationConfirmation: React.FC<MutationConfirmationProps> = ({ 
  preview, 
  onConfirm, 
  isLoading 
}) => {
  return (
    <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-blue-50 dark:bg-blue-900/10 animate-pulse-slow">
      <div className="max-w-3xl mx-auto">
        <p className="text-sm text-blue-800 dark:text-blue-200 mb-3 text-center font-medium">
          ⚠️ Confirmation Required
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => onConfirm(false)}
            disabled={isLoading}
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(true)}
            disabled={isLoading}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-all shadow-lg"
          >
            ✓ Confirm Changes
          </button>
        </div>
      </div>
    </div>
  );
};

export default MutationConfirmation;
