"""
Analysis API Router

Provides endpoints for forensic analysis modules including Autoruns and future analyzers.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional, Dict, Any

from ..deps import get_db, get_current_user
from ..models.user import User
from ..crud.investigation import check_investigation_access
from ..analysis.autoruns import AutorunsAnalyzer

router = APIRouter()


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
        # Future modules can be added here:
        # {
        #     "id": "timeline_analysis",
        #     "name": "Timeline Analysis",
        #     "description": "Temporal analysis of events",
        #     "icon": "clock",
        # },
        # {
        #     "id": "network_analysis",
        #     "name": "Network Analysis",
        #     "description": "Network connection and DNS analysis",
        #     "icon": "globe",
        # },
    ]

    return {"modules": modules, "total": len(modules)}
