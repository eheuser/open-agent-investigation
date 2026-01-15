from typing import Optional
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.report import Report


async def get_latest_report(db: AsyncSession, investigation_id: UUID) -> Optional[Report]:
    """
    Get the most recent Report for a given investigation.

    Args:
        db (AsyncSession): Asynchronous SQLAlchemy session.
        investigation_id (UUID): Identifier of the investigation.

    Returns:
        Optional[Report]: The latest Report instance, or `None` if no reports exist.
    """
    stmt = (
        select(Report)
        .where(Report.investigation_id == investigation_id)
        .order_by(Report.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_report(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    title: str,
    markdown_content: str,
    user_prompt: Optional[str],
    artifacts_count: int,
    timeline_entries_count: int,
    event_types_count: int,
) -> Report:
    """
    Create a new report for the specified investigation, ensuring that only one report exists per investigation by deleting any previously stored reports.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used to interact with the database.
    investigation_id : UUID
        Unique identifier of the investigation to which the report belongs.
    user_id : int
        Identifier of the user who generated the report.
    title : str
        Title of the newly created report.
    markdown_content : str
        Full markdown content of the report.
    user_prompt : Optional[str]
        Custom prompt supplied by the user, if any; otherwise `None`.
    artifacts_count : int
        Number of artifacts referenced in the report.
    timeline_entries_count : int
        Number of timeline entries included in the report.
    event_types_count : int
        Number of distinct event types covered by the report.

    Returns
    -------
    Report
        The freshly created :class:`~app.models.Report` instance, persisted to the database and refreshed with its generated primary key.
    """
    # Delete any existing reports for this investigation
    await db.execute(delete(Report).where(Report.investigation_id == investigation_id))

    # Create new report
    report = Report(
        investigation_id=investigation_id,
        user_id=user_id,
        title=title,
        markdown_content=markdown_content,
        user_prompt=user_prompt,
        artifacts_count=artifacts_count,
        timeline_entries_count=timeline_entries_count,
        event_types_count=event_types_count,
    )

    db.add(report)
    await db.commit()
    await db.refresh(report)

    return report


async def delete_reports_for_investigation(db: AsyncSession, investigation_id: UUID) -> int:
    """
    Delete all reports associated with a specific investigation.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        The unique identifier of the investigation whose reports should be removed.

    Returns
    -------
    int
        The number of report records that were deleted from the database.
    """
    result = await db.execute(delete(Report).where(Report.investigation_id == investigation_id))
    await db.commit()
    return result.rowcount


__all__ = [
    "get_latest_report",
    "create_report",
    "delete_reports_for_investigation",
]
