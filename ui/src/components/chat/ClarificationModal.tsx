import React, { useState } from 'react';
import type { ClarificationRequest } from './types';

interface ClarificationModalProps {
  request: ClarificationRequest;
  onSubmit: (values: Record<string, any>) => void;
  onCancel: () => void;
}

const ClarificationModal: React.FC<ClarificationModalProps> = ({ request, onSubmit, onCancel }) => {
  const [values, setValues] = useState<Record<string, any>>({});

  const handleSubmit = () => {
    onSubmit(values);
  };

  return (
    <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
          {request.policy_title} - Configuration
        </h3>
        <div className="space-y-4">
          {request.missing_rules.map((rule) => (
            <div key={rule.name}>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {rule.description || rule.name}
              </label>
              {rule.options && rule.options.length > 0 ? (
                <select
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  value={values[rule.name] || ''}
                  onChange={(e) => setValues(prev => ({
                    ...prev,
                    [rule.name]: e.target.value
                  }))}
                >
                  <option value="">Select...</option>
                  {rule.options.map(opt => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  value={values[rule.name] || ''}
                  onChange={(e) => setValues(prev => ({
                    ...prev,
                    [rule.name]: e.target.value
                  }))}
                />
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-6">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded-md"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
};

export default ClarificationModal;
