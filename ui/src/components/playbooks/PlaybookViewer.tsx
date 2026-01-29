// ui/src/components/playbooks/PlaybookViewer.tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { 
  ArrowLeftIcon, 
  PencilIcon, 
  DocumentDuplicateIcon,
  CalendarIcon,
} from '@heroicons/react/24/outline';
import { Playbook, AnyPlaybook, isBasePlaybook } from '../../services/playbooks';
import 'highlight.js/styles/github-dark.css';

interface PlaybookViewerProps {
  playbook: AnyPlaybook;
  onBack: () => void;
  onEdit?: () => void;
  onClone?: () => void;
}

const PlaybookViewer: React.FC<PlaybookViewerProps> = ({
  playbook,
  onBack,
  onEdit,
  onClone,
}) => {
  const isBase = isBasePlaybook(playbook);
  const isEnabled = isBase ? true : playbook.is_enabled;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <ArrowLeftIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                  {playbook.name}
                </h1>
                {isBase ? (
                  <span className="inline-flex items-center px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-xs font-medium rounded">
                    Base Playbook
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 text-xs font-medium rounded">
                    Custom Playbook
                  </span>
                )}
                {!isEnabled && (
                  <span className="inline-flex items-center px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs font-medium rounded">
                    Disabled
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {playbook.description}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onClone && (
              <button
                onClick={onClone}
                className="flex items-center gap-2 px-4 py-2 bg-blue-100 dark:bg-blue-900/30 hover:bg-blue-200 dark:hover:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded-lg transition-colors"
              >
                <DocumentDuplicateIcon className="w-5 h-5" />
                <span>Clone</span>
              </button>
            )}
            {onEdit && (
              <button
                onClick={onEdit}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
              >
                <PencilIcon className="w-5 h-5" />
                <span>Edit</span>
              </button>
            )}
          </div>
        </div>

        {/* Metadata */}
        {!isBase && !isBasePlaybook(playbook) && (
          <div className="mt-4 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-center gap-1">
              <CalendarIcon className="w-4 h-4" />
              <span>Created {new Date(playbook.created_at).toLocaleDateString()}</span>
            </div>
            {playbook.updated_at !== playbook.created_at && (
              <div className="flex items-center gap-1">
                <CalendarIcon className="w-4 h-4" />
                <span>Updated {new Date(playbook.updated_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto prose prose-slate dark:prose-invert prose-pre:bg-gray-900 prose-pre:text-gray-100">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {playbook.playbook}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
};

export default PlaybookViewer;
