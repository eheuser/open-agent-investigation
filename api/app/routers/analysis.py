from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from uuid import UUID
from typing import List, Optional, Dict, Any
import asyncio

from ..deps import get_db, get_current_user
from ..models.user import User
from ..crud.investigation import check_investigation_access
from ..analysis.autoruns import AutorunsAnalyzer
from ..analysis.execution_evidence import ExecutionEvidenceAnalyzer
from ..analysis.browsed_urls import BrowsedURLsAnalyzer
from ..analysis.logons import LogonsAnalyzer
from ..analysis.user_activity import UserActivityAnalyzer
from app.utils.log_setup import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def check_parsing_status(db: AsyncSession, investigation_id: UUID) -> Dict[str, Any]:
    """
    Check the status of artifact parsing for an investigation.
    
    Args:
        db: Database session
        investigation_id: UUID of the investigation
        
    Returns:
        Dictionary containing:
            - has_pending_jobs: Whether there are pending/running parsing jobs
            - pending_count: Number of pending jobs
            - running_count: Number of running jobs
            - total_jobs: Total number of parsing jobs
    """
    query = text(
        """
        SELECT 
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'running') as running_count,
            COUNT(*) as total_jobs
        FROM jobs_parsing
        WHERE investigation_id = :investigation_id
        """
    )
    
    result = await db.execute(query, {"investigation_id": str(investigation_id)})
    row = result.fetchone()
    
    if row:
        pending_count = row[0] or 0
        running_count = row[1] or 0
        total_jobs = row[2] or 0
        has_pending_jobs = (pending_count + running_count) > 0
        
        return {
            "has_pending_jobs": has_pending_jobs,
            "pending_count": pending_count,
            "running_count": running_count,
            "total_jobs": total_jobs,
        }
    
    return {
        "has_pending_jobs": False,
        "pending_count": 0,
        "running_count": 0,
        "total_jobs": 0,
    }


async def wait_for_parsing_completion(
    db: AsyncSession, 
    investigation_id: UUID, 
    max_wait_seconds: int = 30,
    poll_interval: float = 0.5
) -> bool:
    """
    Wait for all parsing jobs to complete for an investigation.
    
    Args:
        db: Database session
        investigation_id: UUID of the investigation
        max_wait_seconds: Maximum time to wait in seconds
        poll_interval: How often to check status in seconds
        
    Returns:
        True if parsing completed, False if timed out
    """
    elapsed = 0.0
    
    while elapsed < max_wait_seconds:
        status = await check_parsing_status(db, investigation_id)
        
        if not status["has_pending_jobs"]:
            logger.debug(f"All parsing jobs completed for investigation {investigation_id}")
            return True
        
        logger.debug(
            f"Waiting for parsing completion: {status['pending_count']} pending, "
            f"{status['running_count']} running (elapsed: {elapsed:.1f}s)"
        )
        
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    
    logger.warning(
        f"Timed out waiting for parsing completion after {max_wait_seconds}s "
        f"for investigation {investigation_id}"
    )
    return False


@router.get("/autoruns/categories")
async def list_autoruns_categories(
    user: User = Depends(get_current_user),
):
    """
    List available Autoruns analysis categories.

    Returns:
        List of category dictionaries with 'name' and 'description'
    """
    analyzer = AutorunsAnalyzer()
    categories = analyzer.get_categories()
    return {"categories": categories, "total": len(categories)}


@router.get("/autoruns/{investigation_id}")
async def analyze_autoruns(
    investigation_id: UUID,
    categories: Optional[List[str]] = Query(None, description="Specific categories to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyze Windows autostart persistence mechanisms for an investigation.

    This endpoint queries registry events and other artifacts to identify programs
    configured to run automatically at system startup or user login.

    Args:
        investigation_id: UUID of the investigation to analyze
        categories: Optional list of category names to analyze (e.g., ["Logon", "Services"])
                   If not provided, all categories are analyzed.
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary containing:
            - entries: List of autorun entries found
            - total: Total number of entries
            - categories_analyzed: List of category names that were analyzed
            - summary: Summary statistics by category

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If analysis fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    try:
        # Initialize analyzer
        analyzer = AutorunsAnalyzer()

        # Run analysis
        entries = await analyzer.analyze(
            db=db, investigation_id=investigation_id, categories=categories
        )

        # Convert entries to dicts
        entries_data = [entry.to_dict() for entry in entries]

        # Generate summary statistics by category
        summary: Dict[str, int] = {}
        for entry in entries:
            category = entry.category
            summary[category] = summary.get(category, 0) + 1

        # Get list of analyzed categories
        if categories:
            categories_analyzed = categories
        else:
            categories_analyzed = [cat["name"] for cat in analyzer.get_categories()]

        return {
            "entries": entries_data,
            "total": len(entries_data),
            "categories_analyzed": categories_analyzed,
            "summary": summary,
        }

    except Exception as e:
        import logging

        logging.error(f"Autoruns analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/execution-evidence/categories")
async def list_execution_evidence_categories(
    user: User = Depends(get_current_user),
):
    """
    List available Execution Evidence analysis categories.

    Returns:
        List of category dictionaries with metadata
    """
    analyzer = ExecutionEvidenceAnalyzer()
    categories = analyzer.get_categories()
    return {"categories": categories, "total": len(categories)}


@router.get("/execution-evidence/{investigation_id}")
async def analyze_execution_evidence(
    investigation_id: UUID,
    categories: Optional[List[str]] = Query(None, description="Specific categories to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyze Windows execution evidence artifacts for an investigation.

    This endpoint queries execution artifacts like ShimCache, AmCache, Prefetch, SRUM,
    UserAssist, BAM/DAM, Jump Lists, LNK files, Syscache, and Shim databases.

    Args:
        investigation_id: UUID of the investigation to analyze
        categories: Optional list of category keys to analyze (e.g., ["shimcache", "prefetch"])
                   If not provided, all categories are analyzed.
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary containing:
            - entries: List of execution evidence entries found
            - total: Total number of entries
            - categories_analyzed: List of category names that were analyzed
            - summary: Summary statistics by category

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If analysis fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    try:
        # Check if parsing is still in progress
        parsing_status = await check_parsing_status(db, investigation_id)
        
        if parsing_status["has_pending_jobs"]:
            # Wait for parsing to complete (up to 30 seconds)
            logger.debug(
                f"Parsing in progress for investigation {investigation_id}: "
                f"{parsing_status['pending_count']} pending, {parsing_status['running_count']} running. "
                f"Waiting for completion..."
            )
            
            completed = await wait_for_parsing_completion(db, investigation_id, max_wait_seconds=30)
            
            if not completed:
                # Return partial results with a warning
                logger.warning(
                    f"Analysis started before parsing completed for investigation {investigation_id}. "
                    f"Results may be incomplete."
                )
        
        # Initialize analyzer
        analyzer = ExecutionEvidenceAnalyzer()

        # Run analysis
        entries = await analyzer.analyze(
            db=db, investigation_id=investigation_id, categories=categories
        )

        # Convert entries to dicts
        entries_data = [entry.to_dict() for entry in entries]

        # Generate summary statistics by category
        summary: Dict[str, int] = {}
        for entry in entries:
            category = entry.category
            summary[category] = summary.get(category, 0) + 1

        # Get list of analyzed categories
        if categories:
            categories_analyzed = categories
        else:
            categories_analyzed = [cat["key"] for cat in analyzer.get_categories()]

        return {
            "entries": entries_data,
            "total": len(entries_data),
            "categories_analyzed": categories_analyzed,
            "summary": summary,
        }

    except Exception as e:
        import logging

        logging.error(f"Execution evidence analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/debug/event-types/{investigation_id}")
async def debug_event_types(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Debug endpoint to show what event types exist in an investigation.
    
    This helps diagnose why analysis modules aren't finding events.
    
    Args:
        investigation_id: UUID of the investigation
        db: Database session (injected)
        user: Current user (injected)
        
    Returns:
        Dictionary containing event types and counts
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)
    
    try:
        query = text(
            """
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE investigation_id = :investigation_id
            GROUP BY event_type
            ORDER BY count DESC
            """
        )
        
        result = await db.execute(query, {"investigation_id": str(investigation_id)})
        rows = result.fetchall()
        
        event_types = []
        for row in rows:
            event_types.append({
                "event_type": row[0],
                "count": row[1]
            })
        
        return {
            "investigation_id": str(investigation_id),
            "total_events": sum(et["count"] for et in event_types),
            "unique_event_types": len(event_types),
            "event_types": event_types
        }
        
    except Exception as e:
        import logging
        
        logging.error(f"Failed to query event types: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to query event types: {str(e)}")


@router.delete("/cache/{investigation_id}")
async def clear_analysis_cache(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Clear all cached analysis results for an investigation.
    
    This forces all analysis modules to re-run on the next request,
    ensuring fresh results after new artifacts are uploaded.
    
    Args:
        investigation_id: UUID of the investigation
        db: Database session (injected)
        user: Current user (injected)
        
    Returns:
        Dictionary containing:
            - status: "ok"
            - message: Confirmation message
            - cleared_count: Number of cache entries cleared
            
    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If cache clearing fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)
    
    try:
        delete_query = text(
            """
            DELETE FROM analysis_results
            WHERE investigation_id = :investigation_id
            """
        )
        
        cursor_result: CursorResult = await db.execute(delete_query, {"investigation_id": str(investigation_id)})  # type: ignore
        cleared_count = cursor_result.rowcount or 0
        await db.commit()
        
        logger.debug(f"Cleared {cleared_count} cached analysis results for investigation {investigation_id}")
        
        return {
            "status": "ok",
            "message": f"Cleared {cleared_count} cached analysis results",
            "cleared_count": cleared_count,
        }
        
    except Exception as e:
        import logging
        
        logging.error(f"Failed to clear analysis cache: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/browsed-urls/browsers")
async def list_browsed_urls_browsers(
    user: User = Depends(get_current_user),
):
    """
    List supported browsers for browsed URLs analysis.

    Returns:
        List of browser dictionaries with metadata
    """
    analyzer = BrowsedURLsAnalyzer()
    browsers = analyzer.get_browsers()
    return {"browsers": browsers, "total": len(browsers)}


@router.get("/browsed-urls/{investigation_id}")
async def analyze_browsed_urls(
    investigation_id: UUID,
    browsers: Optional[List[str]] = Query(None, description="Specific browsers to filter by"),
    search: Optional[str] = Query(None, description="Search term for URL or title"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyze browsed URLs from browser history artifacts.

    This endpoint queries browser_history events from Chrome, Firefox, and Edge browsers.

    Args:
        investigation_id: UUID of the investigation to analyze
        browsers: Optional list of browser keys to filter by (e.g., ["chrome_chromium", "firefox"])
                 If not provided, all browsers are analyzed.
        search: Optional search term to filter URLs and titles
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary containing:
            - entries: List of browsed URL entries found
            - total: Total number of entries
            - browsers_analyzed: List of browser keys that were analyzed
            - summary: Summary statistics by browser

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If analysis fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    try:
        # Check if parsing is still in progress
        parsing_status = await check_parsing_status(db, investigation_id)
        
        if parsing_status["has_pending_jobs"]:
            # Wait for parsing to complete (up to 30 seconds)
            logger.debug(
                f"Parsing in progress for investigation {investigation_id}: "
                f"{parsing_status['pending_count']} pending, {parsing_status['running_count']} running. "
                f"Waiting for completion..."
            )
            
            completed = await wait_for_parsing_completion(db, investigation_id, max_wait_seconds=30)
            
            if not completed:
                # Return partial results with a warning
                logger.warning(
                    f"Analysis started before parsing completed for investigation {investigation_id}. "
                    f"Results may be incomplete."
                )
        
        # Initialize analyzer
        analyzer = BrowsedURLsAnalyzer()

        # Run analysis
        entries = await analyzer.analyze(
            db=db,
            investigation_id=investigation_id,
            browsers=browsers,
            search_term=search,
        )

        # Convert entries to dicts
        entries_data = [entry.to_dict() for entry in entries]

        # Generate summary statistics by browser
        summary: Dict[str, int] = {}
        for entry in entries:
            browser = entry.browser
            summary[browser] = summary.get(browser, 0) + 1

        # Get list of analyzed browsers
        if browsers:
            browsers_analyzed = browsers
        else:
            browsers_analyzed = [b["key"] for b in analyzer.get_browsers()]

        return {
            "entries": entries_data,
            "total": len(entries_data),
            "browsers_analyzed": browsers_analyzed,
            "summary": summary,
        }

    except Exception as e:
        import logging

        logging.error(f"Browsed URLs analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/logons/filter-categories")
async def list_logons_filter_categories(
    user: User = Depends(get_current_user),
):
    """
    List available filter categories for Logons analysis.

    Returns:
        Dictionary with three filter categories: logon_types, source_ips, logon_ids
    """
    analyzer = LogonsAnalyzer()
    categories = analyzer.get_filter_categories()
    return {"filter_categories": categories}


@router.get("/logons/dynamic-filters/{investigation_id}")
async def get_logons_dynamic_filters(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get dynamic filter values (source IPs and logon IDs) from actual data.

    Args:
        investigation_id: UUID of the investigation
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary with 'source_ips' and 'logon_ids' lists

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    analyzer = LogonsAnalyzer()
    filters = await analyzer.get_dynamic_filters(db, investigation_id)
    return {"dynamic_filters": filters}


@router.get("/logons/{investigation_id}")
async def analyze_logons(
    investigation_id: UUID,
    logon_types: Optional[List[str]] = Query(None, description="Specific logon types to filter by"),
    source_ips: Optional[List[str]] = Query(None, description="Specific source IPs to filter by"),
    usernames: Optional[List[str]] = Query(None, description="Specific usernames to filter by"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyze logon, logoff, and failed logon events for an investigation.

    This endpoint queries Windows Event Log events for logon-related activity.

    Args:
        investigation_id: UUID of the investigation to analyze
        logon_types: Optional list of logon types to filter by (e.g., ["Interactive", "Network"])
        source_ips: Optional list of source IP addresses to filter by
        usernames: Optional list of usernames to filter by
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary containing:
            - entries: List of logon entries found
            - total: Total number of entries
            - summary: Summary statistics by logon type and event action

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If analysis fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    try:
        # Check if parsing is still in progress
        parsing_status = await check_parsing_status(db, investigation_id)
        
        if parsing_status["has_pending_jobs"]:
            # Wait for parsing to complete (up to 30 seconds)
            logger.debug(
                f"Parsing in progress for investigation {investigation_id}: "
                f"{parsing_status['pending_count']} pending, {parsing_status['running_count']} running. "
                f"Waiting for completion..."
            )
            
            completed = await wait_for_parsing_completion(db, investigation_id, max_wait_seconds=30)
            
            if not completed:
                # Return partial results with a warning
                logger.warning(
                    f"Analysis started before parsing completed for investigation {investigation_id}. "
                    f"Results may be incomplete."
                )
        
        # Initialize analyzer
        analyzer = LogonsAnalyzer()

        # Run analysis
        entries = await analyzer.analyze(
            db=db,
            investigation_id=investigation_id,
            logon_types=logon_types,
            source_ips=source_ips,
            usernames=usernames,
        )

        # Convert entries to dicts
        entries_data = [entry.to_dict() for entry in entries]

        # Generate summary statistics
        summary: Dict[str, int] = {}
        for entry in entries:
            # Count by logon type
            logon_type_key = f"type_{entry.logon_type}"
            summary[logon_type_key] = summary.get(logon_type_key, 0) + 1
            
            # Count by event action
            action_key = f"action_{entry.event_action}"
            summary[action_key] = summary.get(action_key, 0) + 1

        return {
            "entries": entries_data,
            "total": len(entries_data),
            "summary": summary,
        }

    except Exception as e:
        import logging

        logging.error(f"Logons analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/user-activity/categories")
async def list_user_activity_categories(
    user: User = Depends(get_current_user),
):
    """
    List available User Activity analysis categories.

    Returns:
        List of category dictionaries with metadata
    """
    analyzer = UserActivityAnalyzer()
    categories = analyzer.get_categories()
    return {"categories": categories, "total": len(categories)}


@router.get("/user-activity/{investigation_id}")
async def analyze_user_activity(
    investigation_id: UUID,
    categories: Optional[List[str]] = Query(None, description="Specific categories to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyze Windows user activity artifacts for an investigation.

    This endpoint queries user activity artifacts like ShellBags, RecentDocs,
    OpenSaveMRU, TypedPaths, RunMRU, and WordWheelQuery.

    Args:
        investigation_id: UUID of the investigation to analyze
        categories: Optional list of category keys to analyze (e.g., ["shellbags", "recentdocs"])
                   If not provided, all categories are analyzed.
        db: Database session (injected)
        user: Current user (injected)

    Returns:
        Dictionary containing:
            - entries: List of user activity entries found
            - total: Total number of entries
            - categories_analyzed: List of category names that were analyzed
            - summary: Summary statistics by category

    Raises:
        HTTPException 403: If user doesn't have access to the investigation
        HTTPException 500: If analysis fails
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    try:
        # Check if parsing is still in progress
        parsing_status = await check_parsing_status(db, investigation_id)
        
        if parsing_status["has_pending_jobs"]:
            # Wait for parsing to complete (up to 30 seconds)
            logger.debug(
                f"Parsing in progress for investigation {investigation_id}: "
                f"{parsing_status['pending_count']} pending, {parsing_status['running_count']} running. "
                f"Waiting for completion..."
            )
            
            completed = await wait_for_parsing_completion(db, investigation_id, max_wait_seconds=30)
            
            if not completed:
                # Return partial results with a warning
                logger.warning(
                    f"Analysis started before parsing completed for investigation {investigation_id}. "
                    f"Results may be incomplete."
                )
        
        # Initialize analyzer
        analyzer = UserActivityAnalyzer()

        # Run analysis
        entries = await analyzer.analyze(
            db=db, investigation_id=investigation_id, categories=categories
        )

        # Convert entries to dicts
        entries_data = [entry.to_dict() for entry in entries]

        # Generate summary statistics by category
        summary: Dict[str, int] = {}
        for entry in entries:
            category = entry.category
            summary[category] = summary.get(category, 0) + 1

        # Get list of analyzed categories
        if categories:
            categories_analyzed = categories
        else:
            categories_analyzed = [cat["key"] for cat in analyzer.get_categories()]

        return {
            "entries": entries_data,
            "total": len(entries_data),
            "categories_analyzed": categories_analyzed,
            "summary": summary,
        }

    except Exception as e:
        import logging

        logging.error(f"User activity analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/modules")
async def list_analysis_modules(
    user: User = Depends(get_current_user),
):
    """
    List available analysis modules.

    Returns:
        List of available analysis modules with metadata
    """
    modules = [
        {
            "id": "autoruns",
            "name": "Autoruns",
            "description": "Windows autostart persistence mechanism analysis",
            "icon": "rocket-launch",
            "categories": len(AutorunsAnalyzer().get_categories()),
        },
        {
            "id": "execution_evidence",
            "name": "Execution Evidence",
            "description": "Windows execution artifact analysis (ShimCache, AmCache, Prefetch, SRUM, etc.)",
            "icon": "play-circle",
            "categories": len(ExecutionEvidenceAnalyzer().get_categories()),
        },
        {
            "id": "browsed_urls",
            "name": "Browsed URLs",
            "description": "Browser history analysis from Chrome, Firefox, and Edge",
            "icon": "globe-alt",
            "categories": len(BrowsedURLsAnalyzer().get_browsers()),
        },
        {
            "id": "logons",
            "name": "Logons",
            "description": "Logon, logoff, and failed logon event analysis",
            "icon": "user-circle",
            "categories": 3,  # Three filter categories: logon types, source IPs, logon IDs
        },
        {
            "id": "user_activity",
            "name": "User Activity",
            "description": "Windows user activity analysis (ShellBags, RecentDocs, OpenSaveMRU, TypedPaths, etc.)",
            "icon": "user",
            "categories": len(UserActivityAnalyzer().get_categories()),
        },
    ]

    return {"modules": modules, "total": len(modules)}
