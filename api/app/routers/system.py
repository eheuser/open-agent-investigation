"""
System status and statistics endpoints.
Provides on-demand system health and usage statistics.
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.utils.log_setup import get_logger

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
        # Detailed investigation statistics with event and timeline embedding coverage
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    i.investigation_id,
                    i.title,
                    u.username as owner,
                    i.created_at,
                    COUNT(DISTINCT e.event_id) AS total_events,
                    COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NOT NULL) AS events_with_embeddings,
                    COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NULL) AS events_without_embeddings,
                    ROUND(
                        100.0 * COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NOT NULL) / 
                        NULLIF(COUNT(DISTINCT e.event_id), 0), 
                        2
                    ) AS event_embedding_coverage_percent,
                    COUNT(DISTINCT te.entry_id) AS total_timeline_entries,
                    COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NOT NULL) AS timeline_with_embeddings,
                    COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NULL) AS timeline_without_embeddings,
                    ROUND(
                        100.0 * COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NOT NULL) / 
                        NULLIF(COUNT(DISTINCT te.entry_id), 0), 
                        2
                    ) AS timeline_embedding_coverage_percent
                FROM investigations i
                LEFT JOIN users u ON u.user_id = i.owner_user_id
                LEFT JOIN events e ON e.investigation_id = i.investigation_id
                LEFT JOIN embeddings emb_e ON emb_e.owner_type = 'tool' AND emb_e.owner_id = e.event_id
                LEFT JOIN timeline_entries te ON te.investigation_id = i.investigation_id
                GROUP BY i.investigation_id, i.title, u.username, i.created_at
                ORDER BY i.created_at DESC
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
        # Total artifacts and storage
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    COUNT(*) as total,
                    COALESCE(SUM(length(blob)), 0) as total_size_bytes
                FROM artifacts
            """)
        )
        row = result.fetchone()
        artifacts_total = row[0] if row else 0
        artifacts_size_bytes = row[1] if row else 0
        
        # Artifacts by classification
        result = await db.execute(  # type: ignore
            text("""
                SELECT classification, COUNT(*) as count
                FROM artifacts
                GROUP BY classification
                ORDER BY count DESC
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
                    length(a.blob) as size_bytes,
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
        # Event embedding coverage
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    COUNT(DISTINCT e.event_id) AS total_events,
                    COUNT(DISTINCT e.event_id) FILTER (WHERE emb.id IS NOT NULL) AS events_with_embeddings,
                    COUNT(DISTINCT e.event_id) FILTER (WHERE emb.id IS NULL) AS events_without_embeddings,
                    ROUND(
                        100.0 * COUNT(DISTINCT e.event_id) FILTER (WHERE emb.id IS NOT NULL) / 
                        NULLIF(COUNT(DISTINCT e.event_id), 0), 
                        2
                    ) AS embedding_coverage_percent
                FROM events e
                LEFT JOIN embeddings emb 
                    ON emb.owner_type = 'tool' 
                    AND emb.owner_id = e.event_id
            """)
        )
        row = result.fetchone()
        events_total = row[0] if row else 0
        events_with_embeddings = row[1] if row else 0
        events_without_embeddings = row[2] if row else 0
        embedding_coverage_percent = float(row[3]) if row and row[3] else 0.0
        
        # Events by type (top 20)
        result = await db.execute(  # type: ignore
            text("""
                SELECT event_type, COUNT(*) as count
                FROM events
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 20
            """)
        )
        events_by_type = [
            {"event_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        # Events by investigation
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    i.investigation_id,
                    i.title,
                    COUNT(e.event_id) as event_count
                FROM investigations i
                LEFT JOIN events e ON e.investigation_id = i.investigation_id
                GROUP BY i.investigation_id, i.title
                ORDER BY event_count DESC
                LIMIT 10
            """)
        )
        events_by_investigation = [
            {
                "investigation_id": str(row[0]),
                "title": row[1],
                "event_count": row[2],
            }
            for row in result.fetchall()
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
        # Total embeddings
        result = await db.execute(text("SELECT COUNT(*) FROM embeddings"))  # type: ignore
        embeddings_total = result.scalar() or 0
        
        # Embeddings by owner type
        result = await db.execute(  # type: ignore
            text("""
                SELECT owner_type, COUNT(*) as count
                FROM embeddings
                GROUP BY owner_type
                ORDER BY count DESC
            """)
        )
        embeddings_by_owner_type = [
            {"owner_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        # Embeddings by model
        result = await db.execute(  # type: ignore
            text("""
                SELECT model_name, COUNT(*) as count
                FROM embeddings
                GROUP BY model_name
                ORDER BY count DESC
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
        # Timeline entries
        result = await db.execute(text("SELECT COUNT(*) FROM timeline_entries"))  # type: ignore
        timeline_total = result.scalar() or 0
        
        # Timeline by type
        result = await db.execute(  # type: ignore
            text("""
                SELECT entry_type, COUNT(*) as count
                FROM timeline_entries
                GROUP BY entry_type
                ORDER BY count DESC
            """)
        )
        timeline_by_type = [
            {"entry_type": row[0], "count": row[1]} for row in result.fetchall()
        ]
        
        # Timeline embedding coverage
        result = await db.execute(  # type: ignore
            text("""
                SELECT 
                    COUNT(*) FILTER (WHERE embedding_id IS NOT NULL) as with_embeddings,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE embedding_id IS NOT NULL) / 
                        NULLIF(COUNT(*), 0), 
                        2
                    ) as coverage_percent
                FROM timeline_entries
            """)
        )
        row = result.fetchone()
        timeline_with_embeddings = row[0] if row else 0
        timeline_embedding_coverage = float(row[1]) if row and row[1] else 0.0
        
        stats["timeline"] = {
            "total": timeline_total,
            "by_type": timeline_by_type,
            "with_embeddings": timeline_with_embeddings,
            "embedding_coverage_percent": timeline_embedding_coverage,
        }
        
        # ===== JOBS =====
        # Parsing jobs
        result = await db.execute(  # type: ignore
            text("""
                SELECT status, COUNT(*) as count
                FROM jobs_parsing
                GROUP BY status
            """)
        )
        parsing_jobs = {row[0]: row[1] for row in result.fetchall()}
        
        # Agent jobs
        result = await db.execute(  # type: ignore
            text("""
                SELECT status, COUNT(*) as count
                FROM jobs_agents
                GROUP BY status
            """)
        )
        agent_jobs = {row[0]: row[1] for row in result.fetchall()}
        
        # Embedding jobs
        result = await db.execute(  # type: ignore
            text("""
                SELECT status, COUNT(*) as count
                FROM jobs_embedding
                GROUP BY status
            """)
        )
        embedding_jobs = {row[0]: row[1] for row in result.fetchall()}
        
        stats["jobs"] = {
            "parsing": {
                "pending": parsing_jobs.get("pending", 0),
                "running": parsing_jobs.get("running", 0),
                "completed": parsing_jobs.get("completed", 0),
                "failed": parsing_jobs.get("failed", 0),
            },
            "agents": {
                "pending": agent_jobs.get("pending", 0),
                "running": agent_jobs.get("running", 0),
                "completed": agent_jobs.get("completed", 0),
                "failed": agent_jobs.get("failed", 0),
            },
            "embedding": {
                "pending": embedding_jobs.get("pending", 0),
                "running": embedding_jobs.get("running", 0),
                "completed": embedding_jobs.get("completed", 0),
                "failed": embedding_jobs.get("failed", 0),
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
            logger.error(f"Database health check failed: {e}")
            stats["database"] = {"status": "error", "message": str(e)}
        
        logger.info(f"System status retrieved by user {current_user.username}")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to retrieve system status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system status: {str(e)}",
        )


__all__ = ["router"]
