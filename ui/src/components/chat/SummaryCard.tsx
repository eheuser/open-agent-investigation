/**
 * Summary card component.
 * Displays investigation completion summary with stats.
 */
import React from 'react';
import { ChatMessage } from '../../hooks/useInvestigationChat';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CheckCircleIcon } from '@heroicons/react/24/solid';

interface SummaryCardProps {
  message: ChatMessage;
}

const SummaryCard: React.FC<SummaryCardProps> = ({ message }) => {
  const stats = message.metadata?.stats;

  // Clean tool-exec placeholders, JSON code blocks, and starting analysis text from summary content
  const summaryContent = (message.content || message.metadata?.summary || 'No summary available.')
    .replace(/<tool-exec[^>]*><\/tool-exec>/g, '') // Self-closing tags
    .replace(/<tool-exec[^>]*>[\s\S]*?<\/tool-exec>/g, '') // Tags with content
    .replace(/```json[\s\S]*?```/g, '') // Remove JSON code blocks
    .replace(/```[\s\S]*?```/g, '') // Remove any other code blocks
    .replace(/\{[\s\S]*?"summary"[\s\S]*?\}/g, '') // Remove inline JSON objects
    .replace(/Starting analysis\.{3}/g, '') // Remove starting analysis text
    .replace(/Starting analysis\.{3}/g, '') // Remove starting analysis text (no emoji)
    .replace(/^🤖\s*/g, '') // Remove leading robot emoji
    .replace(/^##\s*Investigation Complete\s*/g, '') // Remove header (already in UI)
    .replace(/\n{3,}/g, '\n\n') // Clean up excessive newlines
    .trim();

  return (
    <div className="flex justify-start w-full">
      <div className="w-full max-w-4xl bg-green-50 dark:bg-green-900/20 rounded-lg border-2 border-green-300 dark:border-green-700 shadow-md">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 bg-green-100 dark:bg-green-900/30 rounded-t-lg border-b border-green-300 dark:border-green-700">
          <CheckCircleIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
          <span className="font-semibold text-green-900 dark:text-green-100">
            Investigation Complete
          </span>
        </div>

        {/* Stats */}
        {stats && (
          <div className="px-4 py-3 grid grid-cols-3 gap-4 border-b border-green-200 dark:border-green-800">
            {stats.events_analyzed !== undefined && (
              <div className="text-center">
                <div className="text-2xl font-bold text-green-700 dark:text-green-300">
                  {stats.events_analyzed}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  Events Analyzed
                </div>
              </div>
            )}
            {stats.timeline_entries_created !== undefined && (
              <div className="text-center">
                <div className="text-2xl font-bold text-green-700 dark:text-green-300">
                  {stats.timeline_entries_created}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  Timeline Entries
                </div>
              </div>
            )}
            {stats.turns_executed !== undefined && (
              <div className="text-center">
                <div className="text-2xl font-bold text-green-700 dark:text-green-300">
                  {stats.turns_executed}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  Turns Executed
                </div>
              </div>
            )}
          </div>
        )}

        {/* Summary content */}
        <div className="px-4 py-3">
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {summaryContent}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SummaryCard;
