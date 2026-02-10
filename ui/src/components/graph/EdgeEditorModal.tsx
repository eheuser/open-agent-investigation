import React, { useState, useEffect } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { GraphEdge, GraphNode } from '../../services/graphApi';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSave: (edge: {
    source_id: number;
    target_id: number;
    relationship: string;
    data: Record<string, any>;
    tags: string[];
  }) => void;
  edge?: GraphEdge | null;
  nodes: GraphNode[];
  preselectedSource?: number;
  preselectedTarget?: number;
  title?: string;
}

const EdgeEditorModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onSave,
  edge,
  nodes,
  preselectedSource,
  preselectedTarget,
  title = 'Create Edge',
}) => {
  const [sourceId, setSourceId] = useState<number | ''>('');
  const [targetId, setTargetId] = useState<number | ''>('');
  const [relationship, setRelationship] = useState('');
  const [dataJson, setDataJson] = useState('{}');
  const [tagsInput, setTagsInput] = useState('');
  const [jsonError, setJsonError] = useState('');

  useEffect(() => {
    if (edge) {
      setSourceId(edge.source_id);
      setTargetId(edge.target_id);
      setRelationship(edge.relationship);
      setDataJson(JSON.stringify(edge.data || {}, null, 4));
      setTagsInput(edge.tags.join(', '));
    } else {
      setSourceId(preselectedSource || '');
      setTargetId(preselectedTarget || '');
      setRelationship('');
      // Prepopulate with name field for new edges
      setDataJson(JSON.stringify({ name: '' }, null, 4));
      setTagsInput('');
    }
    setJsonError('');
  }, [edge, isOpen, preselectedSource, preselectedTarget]);

  const handleSave = () => {
    // Validate
    if (!sourceId || !targetId || !relationship.trim()) {
      return;
    }

    // Validate JSON
    let parsedData: Record<string, any>;
    try {
      parsedData = JSON.parse(dataJson);
    } catch (error) {
      setJsonError('Invalid JSON format');
      return;
    }

    // Parse tags
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    onSave({
      source_id: Number(sourceId),
      target_id: Number(targetId),
      relationship: relationship.trim(),
      data: parsedData,
      tags,
    });

    onClose();
  };

  if (!isOpen) return null;

  // Helper function to get display name for a node
  const getNodeDisplayName = (node: GraphNode): string => {
    const name = node.data?.name || node.label;
    return `${name} (ID: ${node.node_id})`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            <XMarkIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Source Node */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Source Node *
            </label>
            <select
              value={sourceId}
              onChange={(e) => setSourceId(Number(e.target.value))}
              disabled={!!edge}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              required
            >
              <option value="">Select source node</option>
              {nodes.map((node) => (
                <option key={node.node_id} value={node.node_id}>
                  {getNodeDisplayName(node)}
                </option>
              ))}
            </select>
          </div>

          {/* Target Node */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Target Node *
            </label>
            <select
              value={targetId}
              onChange={(e) => setTargetId(Number(e.target.value))}
              disabled={!!edge}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              required
            >
              <option value="">Select target node</option>
              {nodes.map((node) => (
                <option key={node.node_id} value={node.node_id}>
                  {getNodeDisplayName(node)}
                </option>
              ))}
            </select>
          </div>

          {/* Relationship */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Relationship *
            </label>
            <input
              type="text"
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="e.g., CONNECTS_TO, OWNS, CREATED"
              required
            />
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Tags
            </label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="suspicious, important, verified"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Comma-separated tags
            </p>
          </div>

          {/* Data (JSON) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Data (JSON)
            </label>
            <textarea
              value={dataJson}
              onChange={(e) => {
                setDataJson(e.target.value);
                setJsonError('');
              }}
              rows={6}
              className={`w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent ${jsonError
                  ? 'border-red-500 dark:border-red-400'
                  : 'border-gray-300 dark:border-gray-600'
                }`}
              placeholder='{"key": "value"}'
            />
            {jsonError && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{jsonError}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700 flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!sourceId || !targetId || !relationship.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {edge ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default EdgeEditorModal;
