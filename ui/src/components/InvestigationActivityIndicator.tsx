// ui/src/components/InvestigationActivityIndicator.tsx
import React, { useEffect, useState } from 'react';
import api from '../services/api';

interface InvestigationActivity {
  hasParsingJobs: boolean;
  hasAgentJobs: boolean;
}

const InvestigationActivityIndicator: React.FC<{
  investigationId: string;
}> = ({ investigationId }) => {
  const [activity, setActivity] = useState<InvestigationActivity>({
    hasParsingJobs: false,
    hasAgentJobs: false,
  });

  useEffect(() => {
    // Skip if no investigation ID
    if (!investigationId) return;

    const checkActivity = async () => {
      try {
        // Check parsing jobs
        const [parsingResponse, agentResponse] = await Promise.all([
          api.get(`/api/v1/jobs/parsing/investigation/${investigationId}`),
          api.get(`/api/v1/jobs/agent/investigation/${investigationId}`)
        ]);

        const parsingJobs = parsingResponse.data.jobs || [];
        const agentJobs = agentResponse.data.jobs || [];

        const hasParsingActive = parsingJobs.some(
          (job: any) => job.status === 'pending' || job.status === 'running'
        );
        const hasAgentActive = agentJobs.some(
          (job: any) => job.status === 'pending' || job.status === 'running'
        );

        setActivity({
          hasParsingJobs: hasParsingActive,
          hasAgentJobs: hasAgentActive,
        });
      } catch (error) {
        console.error('Failed to check investigation activity:', error);
      }
    };

    // Initial check
    checkActivity();

    // Poll every 2 seconds
    const interval = setInterval(checkActivity, 2000);

    return () => clearInterval(interval);
  }, [investigationId]);

  // Determine if investigation is active
  const isActive = activity.hasParsingJobs || activity.hasAgentJobs;

  // If inactive, render nothing (chat icon will show instead)
  if (!isActive) {
    return null;
  }

  // Animated dot component for agent activity
  const ActiveDot: React.FC<{ color?: string }> = ({ color = 'bg-green-500' }) => (
    <span className="relative flex h-3 w-3">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${color}`}></span>
      <span className={`relative inline-flex rounded-full h-3 w-3 ${color}`}></span>
    </span>
  );

  // Parsing icon (blue spinning gears)
  const ParsingIcon: React.FC = () => (
    <div title="Parsing artifacts..." className="flex items-center">
      <svg className="animate-spin h-4 w-4 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>
  );

  // Agent icon (purple animated dot)
  const AgentIcon: React.FC = () => (
    <div title="Agent investigation running..." className="flex items-center">
      <ActiveDot color="bg-purple-500" />
    </div>
  );

  // Combined icon when both are active (gears + dot)
  const CombinedIcon: React.FC = () => (
    <div title="Multiple activities running..." className="flex items-center gap-1">
      <svg className="animate-spin h-4 w-4 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <ActiveDot color="bg-purple-500" />
    </div>
  );

  // Show appropriate icon based on activity type
  if (activity.hasParsingJobs && activity.hasAgentJobs) {
    return <CombinedIcon />;
  } else if (activity.hasParsingJobs) {
    return <ParsingIcon />;
  } else {
    return <AgentIcon />;
  }
};

export default InvestigationActivityIndicator;

