/**
 * Error card component.
 * Displays error messages with appropriate styling.
 */
import React from 'react';
import { ChatMessage } from '../../hooks/useInvestigationChat';
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid';

interface ErrorCardProps {
  message: ChatMessage;
}

const ErrorCard: React.FC<ErrorCardProps> = ({ message }) => {
  return (
    <div className="flex justify-start w-full">
      <div className="w-full max-w-4xl bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-300 dark:border-red-700 shadow-sm">
        <div className="flex items-start gap-3 px-4 py-3">
          <ExclamationTriangleIcon className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-medium text-red-900 dark:text-red-100 mb-1">
              Error
            </div>
            <div className="text-sm text-red-800 dark:text-red-200 whitespace-pre-wrap">
              {message.content}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ErrorCard;
