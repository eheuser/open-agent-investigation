import React from 'react';
import {
  CpuChipIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';

interface RoutingBadgeProps {
  handlerType: 'agent' | 'rag' | 'timeline' | 'general_chat';
  handlerDisplayName: string;
  playbookName?: string;
  playbookDisplayName?: string;
  stats?: {
    sources_retrieved?: number;
    expansion_terms?: number;
    entries_affected?: number;
    effort_level?: string;
    max_turns?: number;
  };
}

const RoutingBadge: React.FC<RoutingBadgeProps> = ({
  handlerType,
  handlerDisplayName,
  playbookName,
  playbookDisplayName,
  stats,
}) => {
  // Icon mapping
  const getIcon = () => {
    switch (handlerType) {
      case 'agent':
        return <CpuChipIcon className="w-4 h-4" />;
      case 'rag':
        return <SparklesIcon className="w-4 h-4" />;
      case 'timeline':
        return <ClockIcon className="w-4 h-4" />;
      case 'general_chat':
        return <ChatBubbleLeftRightIcon className="w-4 h-4" />;
      default:
        return <ChatBubbleLeftRightIcon className="w-4 h-4" />;
    }
  };

  // Color mapping
  const getColorClasses = () => {
    switch (handlerType) {
      case 'agent':
        return 'bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-700';
      case 'rag':
        return 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700';
      case 'timeline':
        return 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-700';
      case 'general_chat':
        return 'bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-900/30 dark:text-gray-300 dark:border-gray-700';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-900/30 dark:text-gray-300 dark:border-gray-700';
    }
  };

  // Format stats display
  const getStatsText = () => {
    if (!stats) return null;

    const parts: string[] = [];

    if (handlerType === 'agent') {
      if (stats.effort_level) {
        parts.push(`${stats.effort_level} effort`);
      }
      if (stats.max_turns) {
        parts.push(`${stats.max_turns} turns max`);
      }
    } else if (handlerType === 'rag') {
      if (stats.sources_retrieved !== undefined) {
        parts.push(`${stats.sources_retrieved} sources`);
      }
      if (stats.expansion_terms !== undefined && stats.expansion_terms > 0) {
        parts.push(`${stats.expansion_terms} terms`);
      }
    } else if (handlerType === 'timeline') {
      if (stats.entries_affected !== undefined) {
        parts.push(`${stats.entries_affected} entries`);
      }
    }

    return parts.length > 0 ? parts.join(' • ') : null;
  };

  const statsText = getStatsText();

  return (
    <div className="mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
      {/* Single line layout with all info */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Main handler badge */}
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${getColorClasses()}`}
        >
          {getIcon()}
          <span>{handlerDisplayName}</span>
        </span>

        {/* Stats badge */}
        {statsText && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
            {statsText}
          </span>
        )}

        {/* Playbook badge (for agent handler) - inline with others */}
        {handlerType === 'agent' && playbookDisplayName && (
          <>
            <span className="text-xs text-gray-400 dark:text-gray-600">•</span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-500 dark:text-gray-400">Playbook:</span>
              <span
                className="inline-flex items-center px-2 py-0.5 rounded bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-700/50 text-xs font-medium"
                title={playbookName}
              >
                {playbookDisplayName}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default RoutingBadge;
