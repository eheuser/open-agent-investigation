import React, { useState } from 'react';
import AutorunsViewer from './AutorunsViewer';
import ExecutionEvidenceViewer from './ExecutionEvidenceViewer';
import BrowsedURLsViewer from './BrowsedURLsViewer';
import LogonsViewer from './LogonsViewer';
import {
  RocketLaunchIcon,
  PlayCircleIcon,
  GlobeAltIcon,
  UserCircleIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';

interface Props {
  investigationId: string;
}

type AnalysisModule = 'autoruns' | 'execution_evidence' | 'browsed_urls' | 'logons' | null;

const AnalysisViewer: React.FC<Props> = ({ investigationId }) => {
  const [selectedModule, setSelectedModule] = useState<AnalysisModule>('autoruns');

  // Analysis modules configuration
  const modules = [
    {
      id: 'autoruns' as const,
      name: 'Autoruns',
      description: 'Windows autostart persistence analysis',
      icon: RocketLaunchIcon,
      color: 'blue',
    },
    {
      id: 'execution_evidence' as const,
      name: 'Execution Evidence',
      description: 'Windows execution artifacts (ShimCache, AmCache, Prefetch, SRUM, etc.)',
      icon: PlayCircleIcon,
      color: 'purple',
    },
    {
      id: 'browsed_urls' as const,
      name: 'Browsed URLs',
      description: 'Browser history from Chrome, Firefox, and Edge',
      icon: GlobeAltIcon,
      color: 'indigo',
    },
    {
      id: 'logons' as const,
      name: 'Logons',
      description: 'Logon, logoff, and failed logon events',
      icon: UserCircleIcon,
      color: 'green',
    },
  ];

  return (
    <div className="flex h-full bg-white dark:bg-gray-900">
      {/* Left Sidebar - Module List */}
      <div className="w-64 border-r border-gray-200 dark:border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Analysis Modules
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Select a module to analyze artifacts
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="p-2 space-y-1">
            {modules.map((module) => {
              const Icon = module.icon;
              const isSelected = selectedModule === module.id;

              return (
                <button
                  key={module.id}
                  onClick={() => setSelectedModule(module.id)}
                  className={`w-full flex items-start gap-3 p-3 rounded-lg transition-colors ${isSelected
                      ? 'bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800 border border-transparent'
                    }`}
                >
                  <Icon
                    className={`w-5 h-5 mt-0.5 flex-shrink-0 ${isSelected
                        ? 'text-blue-600 dark:text-blue-400'
                        : 'text-gray-400 dark:text-gray-500'
                      }`}
                  />
                  <div className="flex-1 text-left min-w-0">
                    <div
                      className={`text-sm font-medium ${isSelected
                          ? 'text-blue-900 dark:text-blue-100'
                          : 'text-gray-900 dark:text-white'
                        }`}
                    >
                      {module.name}
                    </div>
                    <div
                      className={`text-xs mt-0.5 ${isSelected
                          ? 'text-blue-700 dark:text-blue-300'
                          : 'text-gray-500 dark:text-gray-400'
                        }`}
                    >
                      {module.description}
                    </div>
                  </div>
                  <ChevronRightIcon
                    className={`w-4 h-4 flex-shrink-0 mt-1 transition-opacity ${isSelected
                        ? 'text-blue-600 dark:text-blue-400 opacity-100'
                        : 'opacity-0'
                      }`}
                  />
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right Content - Selected Module */}
      <div className="flex-1 overflow-hidden">
        {selectedModule === 'autoruns' && (
          <AutorunsViewer investigationId={investigationId} />
        )}
        {selectedModule === 'execution_evidence' && (
          <ExecutionEvidenceViewer investigationId={investigationId} />
        )}
        {selectedModule === 'browsed_urls' && (
          <BrowsedURLsViewer investigationId={investigationId} />
        )}
        {selectedModule === 'logons' && (
          <LogonsViewer investigationId={investigationId} />
        )}
        {!selectedModule && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md px-4">
              <RocketLaunchIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                Select an Analysis Module
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Choose a module from the left sidebar to begin analysis.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AnalysisViewer;
