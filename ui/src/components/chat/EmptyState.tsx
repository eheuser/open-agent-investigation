import React from 'react';
import { ChatBubbleLeftIcon, DocumentArrowUpIcon } from '@heroicons/react/24/outline';

const EmptyState: React.FC = () => {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center max-w-lg px-4">
        <div className="mb-4">
          <div className="w-16 h-16 mx-auto bg-gradient-to-br from-blue-500 to-purple-600 dark:bg-gray-700 dark:bg-gradient-to-br dark:from-gray-600 dark:to-gray-600 rounded-2xl flex items-center justify-center">
            <ChatBubbleLeftIcon className="w-8 h-8 text-white" />
          </div>
        </div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-2">
          Start Your Investigation
        </h2>
        <p className="text-gray-600 dark:text-gray-400 text-sm mb-6">
          Ask the forensic assistant questions about your evidence to begin analysis.
        </p>
        
        {/* Upload Instructions */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-left">
          <div className="flex items-start gap-3">
            <DocumentArrowUpIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">
                Upload Artifacts
              </h3>
              <p className="text-xs text-blue-800 dark:text-blue-200">
                Drag and drop forensic artifacts (EVTX, Registry, MFT, Prefetch, LNK files, Browser History files and more) anywhere on this window to upload and parse them automatically.
              </p>
            </div>
          </div>
        </div>
        
        {/* Example Questions */}
        <div className="mt-6 text-left">
          <h3 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
            Example questions:
          </h3>
          <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
            <li>• "Find failed authentication attempts"</li>
            <li>• "Show me processes executed by user Administrator"</li>
            <li>• "List network connections from the last 24 hours"</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default EmptyState;
