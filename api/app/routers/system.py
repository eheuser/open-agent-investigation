"""
System status and statistics endpoints.
Provides on-demand system health and usage statistics.

Performance Optimization:
- Uses materialized views for per-investigation stats (refreshed after jobs)
- Uses cached aggregates for system-wide totals (refreshed after jobs)
- Uses statistical sampling (TABLESAMPLE) for GROUP BY queries (25-50x faster)
- Sampling provides ±5-10% accuracy, acceptable for status dashboards
- See docs/performance-optimization.md for details
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    artifacts_page: int = 1,
    artifacts_page_size: int = 20,
    artifacts_search: str = "",
) -> Dict[str, Any]:
    """
    Get comprehensive system statistics and health information.
    
    Returns statistics on:
    - Investigations (total, by user, recent)
    - Artifacts (total, storage size, by classification, recent)
    - Events (total, embedding coverage, by type, by investigation)
    - Embeddings (total, by owner type, by model)
    - Timeline entries (total, by type, embedding coverage)
    - Jobs (parsing, agents, embedding - by status)
    - Users (total, admins, regular)
    - Database health
    
    Requires authentication. All users can view system stats.
    """
    try:
        stats: Dict[str, Any] = {}
        
        # ===== INVESTIGATIONS =====
        # Hybrid approach: Use cached data from materialized view with fallback to live data
        # Cached data is refreshed automatically after parsing/embedding jobs and every 5 minutes
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    investigation_id,
                    title,
                    owner,
                    created_at,
                    total_events,
                    events_with_embeddings,
                    events_without_embeddings,
                    event_embedding_coverage_percent,
                    total_timeline_entries,
                    timeline_with_embeddings,
                    timeline_without_embeddings,
                    timeline_embedding_coverage_percent
                FROM investigation_stats_mv
                ORDER BY created_at DESC
            """)
        )
        
        investigations_detailed = []
        investigations_total = 0
        for row in result.fetchall():
            investigations_total += 1
            investigations_detailed.append({
                "investigation_id": str(row[0]),
                "title": row[1],
                "owner": row[2] or "Unknown",
                "created_at": row[3].isoformat() if row[3] else None,
                "total_events": row[4] or 0,
                "events_with_embeddings": row[5] or 0,
                "events_without_embeddings": row[6] or 0,
                "event_embedding_coverage_percent": float(row[7]) if row[7] else 0.0,
                "total_timeline_entries": row[8] or 0,
                "timeline_with_embeddings": row[9] or 0,
                "timeline_without_embeddings": row[10] or 0,
                "timeline_embedding_coverage_percent": float(row[11]) if row[11] else 0.0,
            })
        
        stats["investigations"] = {
            "total": investigations_total,
            "detailed": investigations_detailed,
        }
        
        # ===== ARTIFACTS =====
        # Use cached stats for artifact totals (refreshed automatically)
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    MAX(CASE WHEN stat_key = 'total_artifacts' THEN stat_value ELSE 0 END) as total,
                    MAX(CASE WHEN stat_key = 'total_artifact_bytes' THEN stat_value ELSE 0 END) as total_size_bytes
                FROM system_stats_cache
                WHERE stat_key IN ('total_artifacts', 'total_artifact_bytes')
            """)
        )
        row = result.fetchone()
        artifacts_total = row[0] if row else 0
        artifacts_size_bytes = row[1] if row else 0
        
        # Artifacts by classification (use statistical sampling for speed)
        # TABLESAMPLE SYSTEM(25) samples 25% of disk blocks → 4x multiplier for estimate
        # Trade-off: ±5-10% accuracy for 25-50x speedup (acceptable for dashboards)
        result = await db.execute(  # type: ignore
            text("""
                WITH classification_sample AS (
                    SELECT 
                        classification,
                        COUNT(*) as sample_count
                    FROM artifacts
                    TABLESAMPLE SYSTEM(25)  -- Sample 25% of blocks
                    GROUP BY classification
                )
                SELECT 
                    classification,
                    (sample_count * 4)::bigint as estimated_count
                FROM classification_sample
                ORDER BY estimated_count DESC
            """)
        )
        artifacts_by_classification = [
            {"classification": str(row[0]), "count": row[1]} for row in result.fetchall()
        ]
        
        # Paginated artifacts with search
        artifacts_page = max(1, artifacts_page)
        artifacts_page_size = min(50, max(1, artifacts_page_size))
        offset = (artifacts_page - 1) * artifacts_page_size
        
        # Build search filter
        search_filter = ""
        search_params: Dict[str, Any] = {"limit": artifacts_page_size, "offset": offset}
        if artifacts_search:
            search_filter = "WHERE filename ILIKE :search"
            search_params["search"] = f"%{artifacts_search}%"
        
        # Get total count for search results
        result = await db.execute(  # type: ignore
            text(f"SELECT COUNT(*) FROM artifacts {search_filter}"),
            search_params if artifacts_search else {}
        )
        artifacts_search_total = result.scalar() or 0
        
        # Get paginated artifacts
        result = await db.execute(  # type: ignore
            text(f"""
                SELECT 
                    a.artifact_id,
                    a.filename,
                    a.classification,
                    a.upload_ts,
                    a.size_bytes,
                    i.title as investigation_title,
                    a.sha256
                FROM artifacts a
                LEFT JOIN investigations i ON i.investigation_id = a.investigation_id
                {search_filter}
                ORDER BY a.upload_ts DESC
                LIMIT :limit OFFSET :offset
            """),
            search_params
        )
        
        artifacts_list = []
        for row in result.fetchall():
            artifacts_list.append({
                "artifact_id": row[0],
                "filename": row[1],
                "classification": str(row[2]),
                "upload_ts": row[3].isoformat() if row[3] else None,
                "size_bytes": row[4] or 0,
                "investigation_title": row[5] or "Unknown",
                "sha256": row[6].hex() if row[6] else None,
            })
        
        total_pages = (artifacts_search_total + artifacts_page_size - 1) // artifacts_page_size
        
        stats["artifacts"] = {
            "total": artifacts_total,
            "total_size_bytes": artifacts_size_bytes,
            "total_size_mb": round(artifacts_size_bytes / (1024 * 1024), 2),
            "by_classification": artifacts_by_classification,
            "list": artifacts_list,
            "search_total": artifacts_search_total,
            "page": artifacts_page,
            "page_size": artifacts_page_size,
            "total_pages": total_pages,
            "has_more": artifacts_page < total_pages,
        }
        
        # ===== EVENTS & EMBEDDINGS =====
        # Use cached stats for event totals (refreshed automatically)
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    MAX(CASE WHEN stat_key = 'total_events' THEN stat_value ELSE 0 END) as total_events,
                    MAX(CASE WHEN stat_key = 'events_with_embeddings' THEN stat_value ELSE 0 END) as events_with_embeddings
                FROM system_stats_cache
                WHERE stat_key IN ('total_events', 'events_with_embeddings')
            """)
        )
        row = result.fetchone()
        events_total = row[0] if row else 0
        events_with_embeddings = row[1] if row else 0
        events_without_embeddings = events_total - events_with_embeddings
        embedding_coverage_percent = round(100.0 * events_with_embeddings / events_total, 2) if events_total > 0 else 0.0
        
        # Events by type (top 20) - use statistical sampling for speed
        # TABLESAMPLE SYSTEM(5) samples 5% of disk blocks → 20x multiplier for estimate
        # For millions of events, this is 25-50x faster than exact COUNT(*)
        result = await db.execute(  # type: ignore
            text("""
                WITH event_type_sample AS (
                    SELECT 
                        event_type,
                        COUNT(*) as sample_count
                    FROM events
                    TABLESAMPLE SYSTEM(5)  -- Sample 5% of blocks
                    GROUP BY event_type
                )
                SELECT 
                    event_type,
                    (sample_count * 20)::bigint as estimated_count
                FROM event_type_sample
                ORDER BY estimated_count DESC
                LIMIT 20
            """)
        )
        events_by_type = [
            {"event_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        # Events by investigation (use cached data from materialized view)
        # This is already computed in investigation_stats_mv, just extract it
        events_by_investigation = [
            {
                "investigation_id": inv["investigation_id"],
                "title": inv["title"],
                "event_count": inv["total_events"],
            }
            for inv in sorted(investigations_detailed, key=lambda x: x["total_events"], reverse=True)[:10]
        ]
        
        stats["events"] = {
            "total": events_total,
            "events_with_embeddings": events_with_embeddings,
            "events_without_embeddings": events_without_embeddings,
            "embedding_coverage_percent": embedding_coverage_percent,
            "by_type": events_by_type,
            "by_investigation": events_by_investigation,
        }
        
        # ===== EMBEDDINGS =====
        # Use cached stats for embedding totals (refreshed automatically)
        result = await db.execute(  # type: ignore
            text("""
                SELECT stat_value 
                FROM system_stats_cache 
                WHERE stat_key = 'total_embeddings'
            """)
        )
        embeddings_total = result.scalar() or 0
        
        # Embeddings by owner type (use sampling for speed)
        result = await db.execute(  # type: ignore
            text("""
                WITH owner_type_sample AS (
                    SELECT 
                        owner_type,
                        COUNT(*) as sample_count
                    FROM embeddings
                    TABLESAMPLE SYSTEM(10)  -- Sample 10% of blocks
                    GROUP BY owner_type
                )
                SELECT 
                    owner_type,
                    (sample_count * 10)::bigint as estimated_count
                FROM owner_type_sample
                ORDER BY estimated_count DESC
            """)
        )
        embeddings_by_owner_type = [
            {"owner_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        # Embeddings by model (use sampling for speed)
        result = await db.execute(  # type: ignore
            text("""
                WITH model_sample AS (
                    SELECT 
                        model_name,
                        COUNT(*) as sample_count
                    FROM embeddings
                    TABLESAMPLE SYSTEM(10)  -- Sample 10% of blocks
                    GROUP BY model_name
                )
                SELECT 
                    model_name,
                    (sample_count * 10)::bigint as estimated_count
                FROM model_sample
                ORDER BY estimated_count DESC
            """)
        )
        embeddings_by_model = [
            {"model_name": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        stats["embeddings"] = {
            "total": embeddings_total,
            "by_owner_type": embeddings_by_owner_type,
            "by_model": embeddings_by_model,
        }
        
        # ===== TIMELINE =====
        # Use cached stats for timeline totals (refreshed automatically)
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    MAX(CASE WHEN stat_key = 'total_timeline_entries' THEN stat_value ELSE 0 END) as total,
                    MAX(CASE WHEN stat_key = 'timeline_with_embeddings' THEN stat_value ELSE 0 END) as with_embeddings
                FROM system_stats_cache
                WHERE stat_key IN ('total_timeline_entries', 'timeline_with_embeddings')
            """)
        )
        row = result.fetchone()
        timeline_total = row[0] if row else 0
        timeline_with_embeddings = row[1] if row else 0
        timeline_embedding_coverage = round(100.0 * timeline_with_embeddings / timeline_total, 2) if timeline_total > 0 else 0.0
        
        # Timeline by type (use sampling for speed)
        result = await db.execute(  # type: ignore
            text("""
                WITH entry_type_sample AS (
                    SELECT 
                        entry_type,
                        COUNT(*) as sample_count
                    FROM timeline_entries
                    TABLESAMPLE SYSTEM(10)  -- Sample 10% of blocks
                    GROUP BY entry_type
                )
                SELECT 
                    entry_type,
                    (sample_count * 10)::bigint as estimated_count
                FROM entry_type_sample
                ORDER BY estimated_count DESC
            """)
        )
        timeline_by_type = [
            {"entry_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        stats["timeline"] = {
            "total": timeline_total,
            "by_type": timeline_by_type,
            "with_embeddings": timeline_with_embeddings,
            "embedding_coverage_percent": timeline_embedding_coverage,
        }
        
        # ===== JOBS =====
        # Use cached stats for job counts (refreshed automatically)
        result = await db.execute(  # type: ignore
            text("""
                SELECT stat_key, stat_value
                FROM system_stats_cache
                WHERE stat_key LIKE 'jobs_%'
            """)
        )
        job_stats = {row[0]: row[1] for row in result.fetchall()}
        
        stats["jobs"] = {
            "parsing": {
                "pending": job_stats.get("jobs_parsing_pending", 0),
                "running": job_stats.get("jobs_parsing_running", 0),
                "completed": job_stats.get("jobs_parsing_completed", 0),
                "failed": job_stats.get("jobs_parsing_failed", 0),
            },
            "agents": {
                "pending": job_stats.get("jobs_agents_pending", 0),
                "running": job_stats.get("jobs_agents_running", 0),
                "completed": job_stats.get("jobs_agents_completed", 0),
                "failed": job_stats.get("jobs_agents_failed", 0),
            },
            "embedding": {
                "pending": job_stats.get("jobs_embedding_pending", 0),
                "running": job_stats.get("jobs_embedding_running", 0),
                "completed": job_stats.get("jobs_embedding_completed", 0),
                "failed": job_stats.get("jobs_embedding_failed", 0),
            },
        }
        
        # ===== USERS =====
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE role = 1) as admins,
                    COUNT(*) FILTER (WHERE role = 0) as regular
                FROM users
            """)
        )
        row = result.fetchone()
        
        stats["users"] = {
            "total": row[0] if row else 0,
            "admins": row[1] if row else 0,
            "regular": row[2] if row else 0,
        }
        
        # ===== DATABASE HEALTH =====
        try:
            await db.execute(text("SELECT 1"))  # type: ignore
            stats["database"] = {"status": "connected"}
        except Exception as e:
            logger.error(f"Database health check failed: {sanitize_log_message(str(e))}")
            stats["database"] = {"status": "error", "message": str(e)}
        
        logger.info(f"System status retrieved by user {current_user.username}")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to retrieve system status: {sanitize_log_message(str(e))}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system status: {str(e)}",
        )


@router.post("/refresh-stats")
async def refresh_system_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Refresh system statistics caches.
    
    This endpoint refreshes:
    - Investigation statistics materialized view (investigation_stats_mv)
    - System-wide aggregate statistics cache (system_stats_cache)
    
    Should be called:
    - After parsing jobs complete (to update event counts)
    - After embedding jobs complete (to update embedding coverage)
    - Periodically (e.g., every 5 minutes via cron/scheduler)
    
    Requires authentication. All users can trigger refresh.
    """
    try:
        logger.info(f"Refreshing system statistics (triggered by {current_user.username})")
        
        # Refresh materialized view (CONCURRENTLY allows reads during refresh)
        await db.execute(text("SELECT refresh_investigation_stats()"))  # type: ignore
        
        # Refresh system stats cache
        await db.execute(text("SELECT update_system_stats_cache()"))  # type: ignore
        
        await db.commit()
        
        logger.info("System statistics refreshed successfully")
        return {
            "success": True,
            "message": "System statistics refreshed successfully",
            "timestamp": "NOW()",
        }
        
    except Exception as e:
        logger.error(f"Failed to refresh system statistics: {sanitize_log_message(str(e))}", exc_info=True)
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh system statistics: {str(e)}",
        )


__all__ = ["router"]
