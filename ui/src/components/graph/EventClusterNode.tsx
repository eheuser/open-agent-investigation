import React, { memo, useState } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { FolderIcon, ChevronDownIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/react/24/outline';

interface GraphEvent {
  label: string;
  data: {
    timestamp?: string;
    [key: string]: any;
  };
  [key: string]: any;
}

interface EventClusterNodeData {
  label: string;
  count: number;
  events: GraphEvent[];
  onExpand: () => void;
  onDelete?: () => void;
}

const EventClusterNode: React.FC<NodeProps<EventClusterNodeData>> = ({ data, selected }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onDelete) {
      data.onDelete();
    }
  };

  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 border-blue-500 bg-blue-50 dark:bg-blue-900/20 shadow-md transition-all duration-200 min-w-[220px] max-w-[300px] relative ${selected ? 'ring-2 ring-blue-500 shadow-lg' : ''
        }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Delete button on hover */}
      {isHovered && data.onDelete && (
        <button
          onClick={handleDelete}
          className="absolute -top-2 -right-2 w-6 h-6 bg-red-600 hover:bg-red-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all z-10"
          title="Delete cluster"
        >
          <XMarkIcon className="w-4 h-4" />
        </button>
      )}
      <Handle type="target" position={Position.Top} className="w-3 h-3 !bg-blue-500" />

      <div className="space-y-2">
        <div className="flex items-center gap-2 cursor-pointer" onClick={handleToggle}>
          <FolderIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="font-medium text-sm text-gray-900 dark:text-white truncate">
              {data.label}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">
              {data.count} event{data.count !== 1 ? 's' : ''}
            </div>
          </div>
          {isExpanded ? (
            <ChevronDownIcon className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRightIcon className="w-4 h-4 text-gray-500" />
          )}
        </div>

        {isExpanded && (
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {data.events.slice(0, 10).map((event: GraphEvent, idx: number) => (
              <div
                key={idx}
                className="text-xs p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700"
              >
                <div className="font-medium truncate">{event.label}</div>
                {event.data.timestamp && (
                  <div className="text-gray-500 dark:text-gray-400 mt-0.5">
                    {new Date(event.data.timestamp).toLocaleString()}
                  </div>
                )}
              </div>
            ))}
            {data.count > 10 && (
              <div className="text-xs text-center text-gray-500 dark:text-gray-400 py-1">
                +{data.count - 10} more events
              </div>
            )}
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="w-3 h-3 !bg-blue-500" />
    </div>
  );
};

export default memo(EventClusterNode);
