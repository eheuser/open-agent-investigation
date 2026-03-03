// ui/src/components/InvestigationActivityIndicator.tsx
import React, { useEffect, useState } from 'react';
import api from '../services/api';

interface InvestigationActivity {
  hasParsingJobs: boolean;
  hasAgentJobs: boolean;
  hasEmbeddingJobs: boolean;
}

const InvestigationActivityIndicator: React.FC<{
  investigationId: string;
}> = ({ investigationId }) => {
  const [activity, setActivity] = useState<InvestigationActivity>({
    hasParsingJobs: false,
    hasAgentJobs: false,
    hasEmbeddingJobs: false,
  });

  useEffect(() => {
    // Skip if no investigation ID
    if (!investigationId) return;

    const checkActivity = async () => {
      try {
        // Check parsing jobs, agent jobs, and embedding status
        const [parsingResponse, agentResponse, embeddingResponse] = await Promise.all([
          api.get(`/api/v1/jobs/parsing/investigation/${investigationId}`),
          api.get(`/api/v1/jobs/agent/investigation/${investigationId}`),
          api.get(`/api/v1/embeddings/status/${investigationId}`)
        ]);

        const parsingJobs = parsingResponse.data.jobs || [];
        const agentJobs = agentResponse.data.jobs || [];
        const embeddingStatus = embeddingResponse.data;

        const hasParsingActive = parsingJobs.some(
          (job: any) => job.status === 'pending' || job.status === 'running'
        );
        const hasAgentActive = agentJobs.some(
          (job: any) => job.status === 'pending' || job.status === 'running'
        );
        const hasEmbeddingActive = !embeddingStatus.is_complete;

        setActivity({
          hasParsingJobs: hasParsingActive,
          hasAgentJobs: hasAgentActive,
          hasEmbeddingJobs: hasEmbeddingActive,
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
  const isActive = activity.hasParsingJobs || activity.hasAgentJobs || activity.hasEmbeddingJobs;

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

  // Embedding icon (green spinning sparkles)
  const EmbeddingIcon: React.FC = () => (
    <div title="Generating embeddings..." className="flex items-center">
      <svg className="animate-spin h-4 w-4 text-green-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
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

  // Combined icon when multiple activities are active
  // Note: Parsing and embedding are mutually exclusive (only show one spinner)
  const CombinedIcon: React.FC = () => {
    return (
      <div title="Multiple activities running..." className="flex items-center gap-0.5">
        {/* Show parsing spinner if parsing is active, otherwise show embedding spinner */}
        {activity.hasParsingJobs ? (
          <svg className="animate-spin h-3.5 w-3.5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : activity.hasEmbeddingJobs ? (
          <svg className="animate-spin h-3.5 w-3.5 text-green-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : null}
        {activity.hasAgentJobs && (
          <ActiveDot color="bg-purple-500" />
        )}
      </div>
    );
  };

  // Show appropriate icon based on activity type
  // Priority: Parsing > Embedding (never show both spinners)
  // Agent jobs can combine with either parsing or embedding
  const hasParsingOrEmbedding = activity.hasParsingJobs || activity.hasEmbeddingJobs;
  const hasMultipleTypes = (hasParsingOrEmbedding && activity.hasAgentJobs);

  if (hasMultipleTypes) {
    // Show combined icon (parsing/embedding spinner + agent dot)
    return <CombinedIcon />;
  } else if (activity.hasParsingJobs) {
    // Parsing takes priority over embedding
    return <ParsingIcon />;
  } else if (activity.hasEmbeddingJobs) {
    return <EmbeddingIcon />;
  } else {
    // Only agent jobs
    return <AgentIcon />;
  }
};

export default InvestigationActivityIndicator;

