from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.autoruns import AutorunsAnalyzer
from app.analysis.execution_evidence import ExecutionEvidenceAnalyzer
from app.analysis.browsed_urls import BrowsedURLsAnalyzer
from app.analysis.logons import LogonsAnalyzer
from app.utils.log_setup import get_logger

logger = get_logger(__name__)


# Module registry mapping module IDs to their analyzers
ANALYSIS_MODULES = {
    "autoruns": {
        "name": "Autoruns",
        "description": "Windows autostart persistence mechanisms",
        "analyzer_class": AutorunsAnalyzer,
        "filter_param": "categories",
        "get_filters": lambda a: [cat["name"] for cat in a.get_categories()],
    },
    "execution_evidence": {
        "name": "Execution Evidence",
        "description": "Windows execution artifacts (ShimCache, AmCache, Prefetch, SRUM, etc.)",
        "analyzer_class": ExecutionEvidenceAnalyzer,
        "filter_param": "categories",
        "get_filters": lambda a: [cat["key"] for cat in a.get_categories()],
    },
    "browsed_urls": {
        "name": "Browsed URLs",
        "description": "Browser history from Chrome, Firefox, and Edge",
        "analyzer_class": BrowsedURLsAnalyzer,
        "filter_param": "browsers",
        "get_filters": lambda a: [b["key"] for b in a.get_browsers()],
    },
    "logons": {
        "name": "Logons",
        "description": "Logon, logoff, and failed logon events",
        "analyzer_class": LogonsAnalyzer,
        "filter_param": None,  # Multiple filter types
        "get_filters": None,  # Dynamic filters
    },
}


async def query_analysis_module(
    db: AsyncSession,
    investigation_id: str,
    module_id: str,
    page: int = 1,
    page_size: int = 50,
    filters: Optional[Dict[str, List[str]]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query a forensic analysis module for investigation insights.
    
    Analysis modules provide high-level insights from forensic artifacts:
    - **autoruns**: Windows autostart persistence mechanisms (registry, services, scheduled tasks)
    - **execution_evidence**: Program execution artifacts (ShimCache, AmCache, Prefetch, SRUM, UserAssist, BAM/DAM)
    - **browsed_urls**: Browser history from Chrome, Firefox, and Edge
    - **logons**: Logon, logoff, and failed logon events from Windows Event Logs
    
    Use this tool to explore processed forensic data instead of querying raw events directly.
    Results are paginated (max 50 per page) to keep responses focused.
    
    **When to use this tool:**
    - Investigating persistence mechanisms → use "autoruns"
    - Finding program execution evidence → use "execution_evidence"
    - Analyzing web browsing activity → use "browsed_urls"
    - Tracking user logon activity → use "logons"
    
    **Available filters by module:**
    - **autoruns**: categories (e.g., ["Logon", "Services", "Scheduled Tasks"])
    - **execution_evidence**: categories (e.g., ["shimcache", "prefetch", "amcache"])
    - **browsed_urls**: browsers (e.g., ["chrome_chromium", "firefox", "edge"])
    - **logons**: logon_types (e.g., ["Interactive", "RemoteInteractive"]), source_ips, usernames
    
    Args:
        db: Database session
        investigation_id: UUID of the investigation
        module_id: Analysis module to query (autoruns, execution_evidence, browsed_urls, logons)
        page: Page number (1-indexed, default: 1)
        page_size: Results per page (max 50, default: 50)
        filters: Optional filters specific to the module (e.g., {"categories": ["Logon", "Services"]})
        description: Human-readable description of what you're looking for (for logging)
        
    Returns:
        Dictionary containing:
            - status: "ok" or "error"
            - module_id: The queried module ID
            - module_name: Human-readable module name
            - entries: List of analysis results for the current page
            - total: Total number of results (across all pages)
            - page: Current page number
            - page_size: Results per page
            - total_pages: Total number of pages
            - has_more: Whether there are more pages available
            - summary: Statistics about the results
            - applied_filters: Filters that were applied
            - error_msg: Error message if status is "error"
            
    Example usage:
        # Get first page of autorun entries
        result = await query_analysis_module(
            db=db,
            investigation_id="123e4567-e89b-12d3-a456-426614174000",
            module_id="autoruns",
            page=1,
            filters={"categories": ["Logon", "Services"]},
            description="Looking for persistence mechanisms in Logon and Services"
        )
        
        # Get logon events from specific IP
        result = await query_analysis_module(
            db=db,
            investigation_id="123e4567-e89b-12d3-a456-426614174000",
            module_id="logons",
            page=1,
            filters={"source_ips": ["192.168.1.100"], "logon_types": ["RemoteInteractive"]},
            description="Looking for RDP logons from 192.168.1.100"
        )
    """
    try:
        # Validate module ID
        if module_id not in ANALYSIS_MODULES:
            available = ", ".join(ANALYSIS_MODULES.keys())
            return {
                "status": "error",
                "error_msg": f"Unknown module '{module_id}'. Available modules: {available}",
            }
        
        module_info = ANALYSIS_MODULES[module_id]
        
        # Validate pagination
        page = max(1, page)
        page_size = min(50, max(1, page_size))
        
        # Initialize analyzer
        analyzer_class = module_info["analyzer_class"]
        analyzer = analyzer_class()
        
        # Prepare filter arguments based on module type
        analyze_kwargs = {
            "db": db,
            "investigation_id": UUID(investigation_id),
        }
        
        # Apply filters based on module
        applied_filters = {}
        if filters:
            if module_id == "logons":
                # Logons has multiple filter types
                if "logon_types" in filters:
                    analyze_kwargs["logon_types"] = filters["logon_types"]
                    applied_filters["logon_types"] = filters["logon_types"]
                if "source_ips" in filters:
                    analyze_kwargs["source_ips"] = filters["source_ips"]
                    applied_filters["source_ips"] = filters["source_ips"]
                if "usernames" in filters:
                    analyze_kwargs["usernames"] = filters["usernames"]
                    applied_filters["usernames"] = filters["usernames"]
            elif module_id == "browsed_urls":
                # Browsed URLs uses "browsers" parameter
                if "browsers" in filters:
                    analyze_kwargs["browsers"] = filters["browsers"]
                    applied_filters["browsers"] = filters["browsers"]
            else:
                # Autoruns and Execution Evidence use "categories" parameter
                if "categories" in filters:
                    analyze_kwargs["categories"] = filters["categories"]
                    applied_filters["categories"] = filters["categories"]
        
        # Run analysis
        logger.info(
            f"Querying {module_id} module for investigation {investigation_id} "
            f"(page {page}, filters: {applied_filters})"
        )
        
        entries = await analyzer.analyze(**analyze_kwargs)
        
        # Convert to dicts
        entries_data = [entry.to_dict() for entry in entries]
        total = len(entries_data)
        
        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        # Get page slice
        page_entries = entries_data[start_idx:end_idx]
        
        # Generate summary statistics
        summary: Dict[str, int] = {}
        
        if module_id == "autoruns":
            for entry in entries:
                category = entry.category
                summary[category] = summary.get(category, 0) + 1
        elif module_id == "execution_evidence":
            for entry in entries:
                category = entry.category
                summary[category] = summary.get(category, 0) + 1
        elif module_id == "browsed_urls":
            for entry in entries:
                browser = entry.browser
                summary[browser] = summary.get(browser, 0) + 1
        elif module_id == "logons":
            for entry in entries:
                # Count by logon type
                logon_type = entry.logon_type
                summary[f"type_{logon_type}"] = summary.get(f"type_{logon_type}", 0) + 1
                # Count by event action
                action = entry.event_action
                summary[f"action_{action}"] = summary.get(f"action_{action}", 0) + 1
        
        result = {
            "status": "ok",
            "module_id": module_id,
            "module_name": module_info["name"],
            "entries": page_entries,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_more": page < total_pages,
            "summary": summary,
            "applied_filters": applied_filters,
        }
        
        # Log for agent context
        if description:
            logger.info(
                f"Analysis module query: {description} → "
                f"Found {total} total results, returning page {page}/{total_pages}"
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Analysis module query failed for {module_id}: {e}", exc_info=True)
        return {
            "status": "error",
            "error_msg": f"Analysis module query failed: {str(e)}",
        }


async def list_analysis_modules(
    db: AsyncSession,
    investigation_id: str,
) -> Dict[str, Any]:
    """
    List available forensic analysis modules for an investigation.
    
    Use this tool to discover what analysis modules are available before querying them.
    Each module provides high-level insights from different forensic artifact types.
    
    Args:
        db: Database session
        investigation_id: UUID of the investigation
        
    Returns:
        Dictionary containing:
            - status: "ok" or "error"
            - modules: List of available modules with metadata
            - total: Number of available modules
            
    Example result:
        {
            "status": "ok",
            "modules": [
                {
                    "id": "autoruns",
                    "name": "Autoruns",
                    "description": "Windows autostart persistence mechanisms",
                    "available_filters": ["Logon", "Services", "Scheduled Tasks", ...]
                },
                {
                    "id": "execution_evidence",
                    "name": "Execution Evidence",
                    "description": "Windows execution artifacts",
                    "available_filters": ["shimcache", "prefetch", "amcache", ...]
                },
                ...
            ],
            "total": 4
        }
    """
    try:
        modules = []
        
        for module_id, module_info in ANALYSIS_MODULES.items():
            analyzer = module_info["analyzer_class"]()
            
            # Get available filters
            available_filters = []
            if module_id == "logons":
                # Logons has static logon types
                filter_cats = analyzer.get_filter_categories()
                available_filters = [lt["key"] for lt in filter_cats.get("logon_types", [])]
            elif module_info["get_filters"]:
                available_filters = module_info["get_filters"](analyzer)
            
            modules.append({
                "id": module_id,
                "name": module_info["name"],
                "description": module_info["description"],
                "available_filters": available_filters,
            })
        
        return {
            "status": "ok",
            "modules": modules,
            "total": len(modules),
        }
        
    except Exception as e:
        logger.error(f"Failed to list analysis modules: {e}", exc_info=True)
        return {
            "status": "error",
            "error_msg": f"Failed to list analysis modules: {str(e)}",
        }


__all__ = [
    "query_analysis_module",
    "list_analysis_modules",
]
