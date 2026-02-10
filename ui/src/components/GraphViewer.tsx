/**
 * GraphViewer - Wrapper component that renders the interactive graph
 * This file now delegates to InteractiveGraphViewer for the full graph experience
 */
import React from 'react';
import InteractiveGraphViewer from './InteractiveGraphViewer';

type Props = {
  investigationId: string;
  onCountsChange?: (nodeCount: number, edgeCount: number) => void;
};

const GraphViewer: React.FC<Props> = ({ investigationId, onCountsChange }) => {
  return (
    <div className="h-full w-full">
      <InteractiveGraphViewer investigationId={investigationId} onCountsChange={onCountsChange} />
    </div>
  );
};

export default GraphViewer;
