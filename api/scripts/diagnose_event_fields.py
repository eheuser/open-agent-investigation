#!/usr/bin/env python3
"""
Diagnostic script to analyze event field structures in the database.

This script connects to the database and samples events from each event type
to show what fields are actually present. This helps identify field mapping
issues between parsers and analyzers.

Usage:
    # From within API container:
    docker compose exec api python scripts/diagnose_event_fields.py
    
    # From Windows host (requires port 5432 exposed):
    python api/scripts/diagnose_event_fields.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Override DATABASE_URL for Windows host execution
if sys.platform == 'win32':
    # Running from Windows - use localhost instead of 'db' service name
    os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:example@localhost:5432/open_agent_inv'

from sqlalchemy import text
from app.core.database import async_session_factory
import json


async def analyze_event_fields():
    """Analyze event field structures for all event types."""
    
    async with async_session_factory() as db:
        # Get all event types
        result = await db.execute(
            text("""
                SELECT event_type, COUNT(*) as count
                FROM events
                GROUP BY event_type
                ORDER BY count DESC
            """)
        )
        
        event_types = result.fetchall()
        
        print("\n" + "="*80)
        print("EVENT TYPE FIELD ANALYSIS")
        print("="*80 + "\n")
        
        # Focus on execution-related event types
        execution_types = [
            'registry_amcache',
            'registry_shimcache', 
            'registry_userassist',
            'registry_bam',
            'prefetch_execution',
            'jumplist_entry',
            'lnk_file',
            'srum_data',
            'pca_execution',
        ]
        
        for event_type, count in event_types:
            if event_type not in execution_types:
                continue
                
            print(f"\n{'='*80}")
            print(f"EVENT TYPE: {event_type}")
            print(f"Total Count: {count:,}")
            print(f"{'='*80}\n")
            
            # Get 3 sample events
            sample_result = await db.execute(
                text("""
                    SELECT event_id, payload
                    FROM events
                    WHERE event_type = :event_type
                    ORDER BY event_ts DESC
                    LIMIT 3
                """),
                {"event_type": event_type}
            )
            
            samples = sample_result.fetchall()
            
            if not samples:
                print("  No events found\n")
                continue
            
            # Collect all unique fields from samples
            all_fields = set()
            for event_id, payload in samples:
                if isinstance(payload, dict):
                    all_fields.update(payload.keys())
            
            print(f"Unique Fields ({len(all_fields)}):")
            print("-" * 80)
            
            # Show field names and sample values
            for field in sorted(all_fields):
                # Get a sample value from first event
                sample_value = samples[0][1].get(field)
                
                # Format sample value
                if sample_value is None:
                    value_str = "null"
                elif isinstance(sample_value, (str, int, float, bool)):
                    value_str = str(sample_value)[:60]
                elif isinstance(sample_value, dict):
                    value_str = f"<dict with {len(sample_value)} keys>"
                elif isinstance(sample_value, list):
                    value_str = f"<list with {len(sample_value)} items>"
                else:
                    value_str = f"<{type(sample_value).__name__}>"
                
                print(f"  {field:30} = {value_str}")
            
            print()
            
            # Show full sample event
            print("Sample Event (Event ID: {}):".format(samples[0][0]))
            print("-" * 80)
            print(json.dumps(samples[0][1], indent=2, default=str)[:1000])
            if len(json.dumps(samples[0][1], indent=2, default=str)) > 1000:
                print("  ... (truncated)")
            print()
        
        print("\n" + "="*80)
        print("FIELD MAPPING RECOMMENDATIONS")
        print("="*80 + "\n")
        
        print("Based on the analysis above, update the following methods:")
        print("1. ExecutionEvidenceAnalyzer._extract_executable_path()")
        print("2. ExecutionEvidenceAnalyzer._extract_additional_data()")
        print()
        print("Common field name patterns to check:")
        print("  - Executable path: name, path, file_path, image_path, executable")
        print("  - File size: size, file_size, length")
        print("  - Hash: sha1, sha256, md5, hash")
        print("  - Timestamp: timestamp, last_execution, modified_time, link_date")
        print()


if __name__ == "__main__":
    asyncio.run(analyze_event_fields())
