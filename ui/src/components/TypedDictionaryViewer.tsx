import React, { useState } from 'react';
import {
  ChevronRightIcon,
  ChevronDownIcon,
  ClipboardDocumentIcon,
  ArrowTopRightOnSquareIcon,
  PlusIcon,
  MinusIcon,
} from '@heroicons/react/24/outline';

interface TypedDictionaryViewerProps {
  data: Record<string, any>;
  title?: string;
  onAddToTimeline?: (key: string, value: any) => void;
  onOpenInPanel?: (key: string, value: any) => void;
}

type ValueType =
  | 'scalar'
  | 'identifier'
  | 'ip'
  | 'domain'
  | 'timestamp'
  | 'long_text'
  | 'code'
  | 'binary'
  | 'object'
  | 'array';

interface TypedValue {
  type: ValueType;
  value: any;
  preview?: string;
  badge?: string;
}

const TypedDictionaryViewer: React.FC<TypedDictionaryViewerProps> = ({
  data,
  title = 'Event Data',
  onAddToTimeline,
  onOpenInPanel,
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Detect value type and return typed metadata
  const detectType = (value: any): TypedValue => {
    if (value === null || value === undefined) {
      return { type: 'scalar', value: String(value) };
    }

    const strValue = String(value);

    // Object or Array
    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return {
          type: 'array',
          value,
          preview: `[${value.length} items]`,
        };
      }
      return {
        type: 'object',
        value,
        preview: `{${Object.keys(value).length} fields}`,
      };
    }

    // Timestamp (ISO 8601 or epoch)
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
      return {
        type: 'timestamp',
        value,
        preview: formatTimestamp(value),
      };
    }
    if (typeof value === 'number' && value > 1000000000 && value < 9999999999999) {
      return {
        type: 'timestamp',
        value,
        preview: formatTimestamp(new Date(value * 1000).toISOString()),
      };
    }

    // IP Address
    if (typeof value === 'string' && /^(\d{1,3}\.){3}\d{1,3}$/.test(value)) {
      return {
        type: 'ip',
        value,
        badge: 'IPv4',
      };
    }
    if (typeof value === 'string' && /^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$/.test(value)) {
      return {
        type: 'ip',
        value,
        badge: 'IPv6',
      };
    }

    // Domain
    if (typeof value === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$/.test(value)) {
      return {
        type: 'domain',
        value,
        badge: 'Domain',
      };
    }

    // Identifier (GUID, SID, hex strings)
    if (typeof value === 'string') {
      // GUID
      if (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/i.test(value)) {
        return {
          type: 'identifier',
          value,
          badge: 'GUID',
        };
      }
      // SID
      if (/^S-1-[0-59]-\d+-\d+-\d+-\d+-\d+$/i.test(value)) {
        return {
          type: 'identifier',
          value,
          badge: 'SID',
        };
      }
      // Hex string (0x prefix or all hex)
      if (/^0x[0-9a-fA-F]+$/.test(value) || (/^[0-9a-fA-F]{8,}$/.test(value) && value.length % 2 === 0)) {
        return {
          type: 'identifier',
          value,
          badge: 'Hex',
        };
      }
    }

    // Code/JSON (contains brackets, braces, semicolons, keywords)
    if (typeof value === 'string' && (
      value.includes('{') ||
      value.includes('[') ||
      value.includes(';') ||
      /\b(function|class|const|let|var|if|else|return)\b/.test(value)
    )) {
      return {
        type: 'code',
        value,
        preview: value.substring(0, 100) + (value.length > 100 ? '...' : ''),
        badge: 'Code',
      };
    }

    // Long text (> 100 chars)
    if (typeof value === 'string' && value.length > 100) {
      return {
        type: 'long_text',
        value,
        preview: value.substring(0, 100) + '...',
        badge: 'Text',
      };
    }

    // Binary/high entropy
    if (typeof value === 'string' && calculateEntropy(value) > 4.5) {
      return {
        type: 'binary',
        value,
        preview: value.substring(0, 40) + '...',
        badge: 'Binary',
      };
    }

    // Scalar (short, simple values)
    return {
      type: 'scalar',
      value: strValue,
    };
  };

  const formatTimestamp = (isoString: string): string => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      let relative = '';
      if (diffMins < 1) relative = 'just now';
      else if (diffMins < 60) relative = `${diffMins}m ago`;
      else if (diffHours < 24) relative = `${diffHours}h ago`;
      else if (diffDays < 7) relative = `${diffDays}d ago`;
      else relative = date.toLocaleDateString();

      return `${relative} (${date.toLocaleString()})`;
    } catch {
      return isoString;
    }
  };

  const calculateEntropy = (str: string): number => {
    const freq: Record<string, number> = {};
    for (const char of str) {
      freq[char] = (freq[char] || 0) + 1;
    }
    let entropy = 0;
    const len = str.length;
    for (const count of Object.values(freq)) {
      const p = count / len;
      entropy -= p * Math.log2(p);
    }
    return entropy;
  };

  const toggleExpanded = (e: React.MouseEvent, key: string) => {
    e.stopPropagation();
    const newExpanded = new Set(expandedKeys);
    if (newExpanded.has(key)) {
      newExpanded.delete(key);
    } else {
      newExpanded.add(key);
    }
    setExpandedKeys(newExpanded);
  };

  const copyToClipboard = (e: React.MouseEvent, key: string, value: any) => {
    e.stopPropagation();
    const text = typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const renderValue = (key: string, typedValue: TypedValue) => {
    const isExpanded = expandedKeys.has(key);

    switch (typedValue.type) {
      case 'scalar':
        return (
          <div className="flex items-center gap-2">
            <span className="text-gray-900 dark:text-gray-100 font-mono text-sm break-all overflow-wrap-anywhere">
              {typedValue.value}
            </span>
            <button
              onClick={(e) => copyToClipboard(e, key, typedValue.value)}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
              title="Copy"
            >
              {copiedKey === key ? (
                <span className="text-xs text-green-600 dark:text-green-400">✓</span>
              ) : (
                <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              )}
            </button>
          </div>
        );

      case 'identifier':
        return (
          <div className="flex items-center gap-2">
            {typedValue.badge && (
              <span className="px-1.5 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs rounded font-medium">
                {typedValue.badge}
              </span>
            )}
            <code className="text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-xs font-mono break-all overflow-wrap-anywhere">
              {typedValue.value}
            </code>
            <button
              onClick={(e) => copyToClipboard(e, key, typedValue.value)}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
              title="Copy"
            >
              {copiedKey === key ? (
                <span className="text-xs text-green-600 dark:text-green-400">✓</span>
              ) : (
                <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              )}
            </button>
          </div>
        );

      case 'ip':
      case 'domain':
        return (
          <div className="flex items-center gap-2">
            {typedValue.badge && (
              <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs rounded font-medium">
                {typedValue.badge}
              </span>
            )}
            <code className="text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-xs font-mono break-all overflow-wrap-anywhere">
              {typedValue.value}
            </code>
            <button
              onClick={(e) => copyToClipboard(e, key, typedValue.value)}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
              title="Copy"
            >
              {copiedKey === key ? (
                <span className="text-xs text-green-600 dark:text-green-400">✓</span>
              ) : (
                <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              )}
            </button>
          </div>
        );

      case 'timestamp':
        return (
          <div className="flex items-center gap-2">
            <span className="text-gray-900 dark:text-gray-100 text-sm">
              {typedValue.preview}
            </span>
            <button
              onClick={(e) => copyToClipboard(e, key, typedValue.value)}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
              title="Copy"
            >
              {copiedKey === key ? (
                <span className="text-xs text-green-600 dark:text-green-400">✓</span>
              ) : (
                <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              )}
            </button>
          </div>
        );

      case 'long_text':
      case 'code':
      case 'binary':
        return (
          <div className="flex flex-col gap-2 w-full">
            {/* Always show buttons on top row */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0 overflow-hidden">
                {typedValue.badge && (
                  <span className="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-xs rounded font-medium flex-shrink-0">
                    {typedValue.badge}
                  </span>
                )}
                {!isExpanded && (
                  <span className="text-gray-600 dark:text-gray-400 text-sm truncate block">
                    {typedValue.preview}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={(e) => toggleExpanded(e, key)}
                  className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0"
                  title={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? (
                    <MinusIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  ) : (
                    <PlusIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  )}
                </button>
                {onOpenInPanel && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenInPanel(key, typedValue.value);
                    }}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors flex-shrink-0"
                    title="Open in side panel"
                  >
                    <ArrowTopRightOnSquareIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
                  </button>
                )}
                <button
                  onClick={(e) => copyToClipboard(e, key, typedValue.value)}
                  className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors flex-shrink-0"
                  title="Copy"
                >
                  {copiedKey === key ? (
                    <span className="text-xs text-green-600 dark:text-green-400">✓</span>
                  ) : (
                    <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
                  )}
                </button>
              </div>
            </div>
            {isExpanded && (
              <div className="w-full">
                <pre className="text-xs bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-gray-200 p-3 rounded overflow-auto max-h-96 border border-gray-200 dark:border-gray-700 whitespace-pre-wrap break-words">
                  {typedValue.value}
                </pre>
              </div>
            )}
          </div>
        );

      case 'object':
      case 'array':
        return (
          <div className="flex flex-col gap-2 w-full">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0 overflow-hidden">
                <span className="px-1.5 py-0.5 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 text-xs rounded font-medium flex-shrink-0">
                  {typedValue.type === 'array' ? 'Array' : 'Object'}
                </span>
                <span className="text-gray-600 dark:text-gray-400 text-sm flex-shrink-0">
                  {typedValue.preview}
                </span>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={(e) => toggleExpanded(e, key)}
                  className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0"
                  title={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? (
                    <MinusIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  ) : (
                    <PlusIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  )}
                </button>
                <button
                  onClick={(e) => copyToClipboard(e, key, typedValue.value)}
                  className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors flex-shrink-0"
                  title="Copy JSON"
                >
                  {copiedKey === key ? (
                    <span className="text-xs text-green-600 dark:text-green-400">✓</span>
                  ) : (
                    <ClipboardDocumentIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
                  )}
                </button>
              </div>
            </div>
            {isExpanded && (
              <div className="w-full ml-4 border-l-2 border-gray-300 dark:border-gray-700 pl-3">
                <TypedDictionaryViewer
                  data={typedValue.value}
                  title=""
                  onOpenInPanel={onOpenInPanel}
                />
              </div>
            )}
          </div>
        );

      default:
        return <span className="text-gray-500 dark:text-gray-400 text-sm">Unknown type</span>;
    }
  };

  const entries = Object.entries(data);

  return (
    <div className="w-full">
      {title && (
        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
          {title}
        </h4>
      )}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <table className="w-full table-fixed">
          <colgroup>
            <col style={{ width: '30%' }} />
            <col style={{ width: '70%' }} />
          </colgroup>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {entries.map(([key, value]) => {
              const typedValue = detectType(value);
              return (
                <tr
                  key={key}
                  className="group hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <td className="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 align-top break-words">
                    <span className="font-mono break-words">{key}</span>
                  </td>
                  <td className="px-3 py-2 text-sm text-gray-900 dark:text-gray-100 align-top break-words overflow-hidden">
                    {renderValue(key, typedValue)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TypedDictionaryViewer;
