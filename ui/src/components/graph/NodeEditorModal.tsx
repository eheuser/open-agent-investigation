import React, { useState, useEffect } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { GraphNode } from '../../services/graphApi';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSave: (node: { label: string; data: Record<string, any>; tags: string[] }) => void;
  node?: GraphNode | null;
  title?: string;
}

const NodeEditorModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onSave,
  node,
  title = 'Create Node',
}) => {
  const [label, setLabel] = useState('');
  const [dataJson, setDataJson] = useState('{}');
  const [tagsInput, setTagsInput] = useState('');
  const [jsonError, setJsonError] = useState('');

  useEffect(() => {
    if (node) {
      setLabel(node.label);
      setDataJson(JSON.stringify(node.data || {}, null, 4));
      setTagsInput(node.tags.join(', '));
    } else {
      setLabel('');
      // Prepopulate with name field for new nodes
      setDataJson(JSON.stringify({ name: '' }, null, 4));
      setTagsInput('');
    }
    setJsonError('');
  }, [node, isOpen]);

  const handleSave = () => {
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
      label: label.trim(),
      data: parsedData,
      tags,
    });

    onClose();
  };

  if (!isOpen) return null;

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
          {/* Label */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Label *
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter node label"
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
              placeholder="tag1, tag2, tag3"
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
              rows={8}
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
            disabled={!label.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {node ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeEditorModal;
