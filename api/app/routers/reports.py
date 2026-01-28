from typing import Optional
from uuid import UUID
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import markdown as md

from weasyprint import HTML

from ..core.database import get_db
from ..deps import get_current_user
from ..models.user import User
from ..services.report_generator import generate_investigation_report
from ..crud.llm_config import get_active_llm_config
from ..crud import report as report_crud
from worker.core.llm_client import LLMClient

from ..utils.log_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    """Request to generate investigation report."""

    investigation_id: UUID
    user_prompt: Optional[str] = None
    format: str = "markdown"


class GenerateReportResponse(BaseModel):
    """Response from report generation."""

    markdown: str
    title: str
    generated_at: str
    artifacts_count: int
    timeline_entries_count: int
    event_types_count: int


class ReportMetadata(BaseModel):
    """Metadata for a stored report."""

    report_id: int
    investigation_id: UUID
    title: str
    user_prompt: Optional[str]
    artifacts_count: int
    timeline_entries_count: int
    event_types_count: int
    generated_at: datetime


@router.post("/generate", response_model=GenerateReportResponse)
async def generate_report(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a forensic investigation report in markdown format.

    Args:
        request (GenerateReportRequest): The request payload containing the investigation ID and optional user prompt.
        db (AsyncSession, optional): Database session dependency injected by FastAPI. Defaults to Depends(get_db).
        current_user (User, optional): Authenticated user injected by FastAPI. Defaults to Depends(get_current_user).

    Returns:
        GenerateReportResponse: A response model containing the generated report title, markdown content, artifact counts, and other metadata.

    Raises:
        HTTPException:
            - 400 if the underlying report generation returns an error.
            - 500 for any unexpected failures during processing.
    """
    try:
        llm_config = await get_active_llm_config(db, current_user.user_id)

        llm_client = None
        if llm_config:
            api_endpoint = str(llm_config.api_endpoint)
            model_name = str(llm_config.model_name)
            api_key_val = llm_config.api_key
            api_key = str(api_key_val) if api_key_val is not None else None

            llm_client = LLMClient(
                endpoint=api_endpoint,
                model=model_name,
                api_key=api_key,
            )

        # Generate report
        result = await generate_investigation_report(
            db=db,
            investigation_id=request.investigation_id,
            user_id=current_user.user_id,
            user_prompt=request.user_prompt,
            llm_client=llm_client,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        await report_crud.create_report(
            db=db,
            investigation_id=request.investigation_id,
            user_id=current_user.user_id,
            title=result["title"],
            markdown_content=result["markdown"],
            user_prompt=request.user_prompt,
            artifacts_count=result["artifacts_count"],
            timeline_entries_count=result["timeline_entries_count"],
            event_types_count=result["event_types_count"],
        )

        return GenerateReportResponse(**result)

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/latest/{investigation_id}")
async def get_latest_report(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the most recent forensic investigation report for a given investigation.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation whose latest report is requested.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected via FastAPI dependency injection; used to query the database.
    current_user: User, optional
        The authenticated user obtained from the security dependency; ensures the caller has appropriate access.

    Returns
    -------
    GenerateReportResponse
        An object containing the report's markdown content, title, generation timestamp (ISO-8601 string), and summary counts for artifacts, timeline entries, and event types.

    Raises
    ------
    HTTPException
        * 404 - No report exists for the specified investigation.
        * 500 - An unexpected error occurred while retrieving the report.
    """
    try:
        report = await report_crud.get_latest_report(db, investigation_id)

        if not report:
            raise HTTPException(status_code=404, detail="No report found for this investigation")

        return GenerateReportResponse(
            markdown=report.markdown_content,
            title=report.title,
            generated_at=report.generated_at.isoformat(),
            artifacts_count=report.artifacts_count,
            timeline_entries_count=report.timeline_entries_count,
            event_types_count=report.event_types_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve report: {str(e)}")


@router.get("/latest/{investigation_id}/metadata", response_model=ReportMetadata)
async def get_latest_report_metadata(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve metadata for the most recent report associated with a given investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation whose latest report metadata is requested.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session provided by FastAPI dependency injection. Defaults to Depends(get_db).
        current_user (User, optional): Authenticated user obtained via FastAPI dependency injection. Defaults to Depends(get_current_user).

    Returns:
        ReportMetadata: A data object containing the report's identifier, investigation ID, title, user prompt, counts of artifacts, timeline entries, event types, and the generation timestamp.

    Raises:
        HTTPException:
            - 404 if no report exists for the specified investigation.
            - 500 for any unexpected errors encountered while retrieving metadata.
    """
    try:
        report = await report_crud.get_latest_report(db, investigation_id)

        if not report:
            raise HTTPException(status_code=404, detail="No report found for this investigation")

        return ReportMetadata(
            report_id=report.report_id,
            investigation_id=report.investigation_id,
            title=report.title,
            user_prompt=report.user_prompt,
            artifacts_count=report.artifacts_count,
            timeline_entries_count=report.timeline_entries_count,
            event_types_count=report.event_types_count,
            generated_at=report.generated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve report metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve report metadata: {str(e)}")


@router.post("/download")
async def download_report_pdf(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download an investigation report as a PDF file.

    This endpoint generates a markdown version of the requested investigation report,
    optionally using a user-specific LLM configuration, stores the generated report in
    the database (replacing any existing report for the same investigation), converts
    the markdown to PDF with WeasyPrint, and returns the PDF as an attachment.

    Parameters
    ----------
    request: GenerateReportRequest
        The request payload containing the `investigation_id` to generate a report for
        and an optional `user_prompt` that will be passed to the LLM.
    db: AsyncSession, optional
        An asynchronous SQLAlchemy session provided by FastAPI's dependency injection.
    current_user: User, optional
        The authenticated user obtained via dependency injection; used to fetch the
        user's active LLM configuration and to associate the generated report with the
        correct owner.

    Returns
    -------
    Response
        A FastAPI `Response` object containing the PDF bytes, a media type of
        `application/pdf`, and a `Content-Disposition` header that forces download
        with a filename derived from the investigation title and the current UTC timestamp.

    Raises
    ------
    HTTPException
        * 400 - The report generation failed (error details returned by the
          `generate_investigation_report` helper).
        * 401/403 - Authentication or authorization failures propagated from the
          `get_current_user` dependency.
        * 501 - PDF conversion is unavailable because WeasyPrint is not installed.
        * 413 - The generated PDF exceeds the maximum allowed size of 10 MiB.
        * 500 - An unexpected error occurred during PDF generation; the original
          exception message is included in the response detail.
    """
    try:
        llm_config = await get_active_llm_config(db, current_user.user_id)

        llm_client = None
        if llm_config:
            api_endpoint = str(llm_config.api_endpoint)
            model_name = str(llm_config.model_name)
            api_key_val = llm_config.api_key
            api_key = str(api_key_val) if api_key_val is not None else None

            llm_client = LLMClient(
                endpoint=api_endpoint,
                model=model_name,
                api_key=api_key,
            )

        result = await generate_investigation_report(
            db=db,
            investigation_id=request.investigation_id,
            user_id=current_user.user_id,
            user_prompt=request.user_prompt,
            llm_client=llm_client,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        await report_crud.create_report(
            db=db,
            investigation_id=request.investigation_id,
            user_id=current_user.user_id,
            title=result["title"],
            markdown_content=result["markdown"],
            user_prompt=request.user_prompt,
            artifacts_count=result["artifacts_count"],
            timeline_entries_count=result["timeline_entries_count"],
            event_types_count=result["event_types_count"],
        )

        markdown_content = result["markdown"]
        investigation_title = result["title"]

        pdf_bytes = await _convert_markdown_to_pdf(markdown_content)

        # Check size
        size_mb = len(pdf_bytes) / (1024 * 1024)
        if size_mb > 10:
            raise HTTPException(
                status_code=413, detail=f"PDF too large ({size_mb:.1f} MB). Maximum size is 10 MB."
            )

        # Return as downloadable file
        filename = f"{investigation_title.replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


async def _convert_markdown_to_pdf(markdown_content: str) -> bytes:
    """
    Converts a Markdown string to a PDF document.

    Args:
        markdown_content: The source text in Markdown format to be rendered.

    Returns:
        A bytes object containing the generated PDF data.

    Raises:
        Any exception raised by the underlying Markdown conversion or WeasyPrint rendering process will propagate to the caller.
    """
    # Convert markdown to HTML
    html_content = md.markdown(markdown_content, extensions=["tables", "fenced_code", "codehilite"])

    # Wrap in HTML template
    html_full = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 1.5cm;
        }}
        body {{
            font-family: Arial, sans-serif;
            font-size: 9pt;
            line-height: 1.4;
            color: #333;
        }}
        h1 {{
            font-size: 16pt;
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 6px;
            margin-top: 0;
            margin-bottom: 12px;
        }}
        h2 {{
            font-size: 13pt;
            color: #34495e;
            margin-top: 18px;
            margin-bottom: 10px;
            border-bottom: 1px solid #bdc3c7;
            padding-bottom: 3px;
        }}
        h3 {{
            font-size: 11pt;
            color: #7f8c8d;
            margin-top: 12px;
            margin-bottom: 6px;
        }}
        p {{
            margin: 6px 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 10px 0;
            font-size: 8pt;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 4px 6px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}
        code {{
            background-color: #ecf0f1;
            padding: 1px 3px;
            border-radius: 2px;
            font-family: 'Courier New', monospace;
            font-size: 8pt;
        }}
        pre {{
            background-color: #2c3e50;
            color: #ecf0f1;
            padding: 6px;
            border-radius: 3px;
            font-size: 8pt;
        }}
        hr {{
            border: none;
            border-top: 1px solid #bdc3c7;
            margin: 16px 0;
        }}
        ul, ol {{
            margin: 6px 0;
            padding-left: 20px;
        }}
        li {{
            margin: 3px 0;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>
"""

    # Convert HTML to PDF
    pdf_file = BytesIO()
    HTML(string=html_full).write_pdf(pdf_file)

    pdf_bytes = pdf_file.getvalue()

    logger.info(f"Generated PDF: {len(pdf_bytes):,} bytes")

    return pdf_bytes


__all__ = ["router"]
