import React, { memo, useState } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { TagIcon, XMarkIcon } from '@heroicons/react/24/outline';

interface EntityNodeData {
  label: string;
  tags: string[];
  rawData: Record<string, any>;
  onSelect: () => void;
  onDelete?: () => void;
}

const EntityNode: React.FC<NodeProps<EntityNodeData>> = ({ data, selected }) => {
  const [isHovered, setIsHovered] = useState(false);
  const isSuspicious = data.tags?.includes('suspicious') || data.tags?.includes('threat');
  const isFile = data.rawData?.node_type === 'file';
  const isProcess = data.rawData?.node_type === 'process';
  const isNetwork = data.rawData?.node_type === 'network';

  // Determine node color based on type and tags
  const getNodeColor = () => {
    if (isSuspicious) return 'border-red-500 bg-red-50 dark:bg-red-900/20';
    if (isFile) return 'border-blue-500 bg-blue-50 dark:bg-blue-900/20';
    if (isProcess) return 'border-purple-500 bg-purple-50 dark:bg-purple-900/20';
    if (isNetwork) return 'border-green-500 bg-green-50 dark:bg-green-900/20';
    return 'border-gray-300 bg-white dark:bg-gray-800';
  };

  const getIconEmoji = () => {
    if (isFile) return '📄';
    if (isProcess) return '⚙️';
    if (isNetwork) return '🌐';
    return '🔹';
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onDelete) {
      data.onDelete();
    }
  };

  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 shadow-md transition-all duration-200 min-w-[200px] max-w-[280px] relative ${getNodeColor()} ${
        selected ? 'ring-2 ring-blue-500 shadow-lg' : ''
      }`}
      onClick={data.onSelect}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Delete button on hover */}
      {isHovered && data.onDelete && (
        <button
          onClick={handleDelete}
          className="absolute -top-2 -right-2 w-6 h-6 bg-red-600 hover:bg-red-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all z-10"
          title="Delete node"
        >
          <XMarkIcon className="w-4 h-4" />
        </button>
      )}
      <Handle 
        type="target" 
        position={Position.Top} 
        className="w-3 h-3 !bg-gray-400" 
      />
      
      <div className="flex items-start gap-2">
        <span className="text-xl flex-shrink-0">{getIconEmoji()}</span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm text-gray-900 dark:text-white truncate">
            {data.label}
          </div>
          
          {data.tags && data.tags.length > 0 && (
            <div className="flex items-center gap-1 mt-1 flex-wrap">
              <TagIcon className="w-3 h-3 text-gray-400 flex-shrink-0" />
              {data.tags.slice(0, 2).map((tag: string, idx: number) => (
                <span
                  key={idx}
                  className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-xs"
                >
                  {tag}
                </span>
              ))}
              {data.tags.length > 2 && (
                <span className="text-xs text-gray-500">+{data.tags.length - 2}</span>
              )}
            </div>
          )}
        </div>
      </div>
      
      <Handle 
        type="source" 
        position={Position.Bottom} 
        className="w-3 h-3 !bg-gray-400" 
      />
    </div>
  );
};

export default memo(EntityNode);
