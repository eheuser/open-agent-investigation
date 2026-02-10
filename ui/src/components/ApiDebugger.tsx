import React, { useState } from 'react';
import { createInvestigation, getInvestigations } from '../services/investigations';

/**
 * Debug component to test API connectivity
 * Add this temporarily to your app to test the API
 */
const ApiDebugger: React.FC = () => {
  const [result, setResult] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const testCreate = async () => {
    setLoading(true);
    setResult('Testing...');
    try {
      const inv = await createInvestigation({ title: 'Test Investigation' });
      setResult(`✅ Success! Created investigation: ${JSON.stringify(inv, null, 2)}`);
    } catch (error: any) {
      setResult(`❌ Error: ${JSON.stringify({
        message: error.message,
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        headers: error.response?.headers,
      }, null, 2)}`);
    } finally {
      setLoading(false);
    }
  };

  const testList = async () => {
    setLoading(true);
    setResult('Testing...');
    try {
      const invs = await getInvestigations();
      setResult(`✅ Success! Found ${invs.length} investigations:\n${JSON.stringify(invs, null, 2)}`);
    } catch (error: any) {
      setResult(`❌ Error: ${JSON.stringify({
        message: error.message,
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
      }, null, 2)}`);
    } finally {
      setLoading(false);
    }
  };

  const testAuth = () => {
    const token = localStorage.getItem('token');
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        setResult(`✅ Token found:\n${JSON.stringify(payload, null, 2)}`);
      } catch (e) {
        setResult(`❌ Invalid token format`);
      }
    } else {
      setResult(`❌ No token found in localStorage`);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 bg-white dark:bg-gray-800 border-2 border-blue-500 rounded-lg shadow-2xl p-4 max-w-2xl max-h-96 overflow-auto z-50">
      <h3 className="text-lg font-bold mb-3 text-gray-900 dark:text-white">API Debugger</h3>

      <div className="flex gap-2 mb-3">
        <button
          onClick={testAuth}
          className="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white text-sm rounded"
        >
          Check Auth
        </button>
        <button
          onClick={testList}
          disabled={loading}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm rounded"
        >
          List Investigations
        </button>
        <button
          onClick={testCreate}
          disabled={loading}
          className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white text-sm rounded"
        >
          Create Investigation
        </button>
      </div>

      <pre className="bg-gray-100 dark:bg-gray-900 p-3 rounded text-xs overflow-auto max-h-64 text-gray-900 dark:text-gray-100">
        {result || 'Click a button to test...'}
      </pre>
    </div>
  );
};

export default ApiDebugger;
