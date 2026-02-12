from pathlib import Path
from typing import Dict, Any, List
import uuid
import zipfile
import zipfile_deflate64  # noqa: F401  # Monkey-patches zipfile to support all compression methods
import py7zr
import subprocess
import tempfile
import shutil

from sqlalchemy.ext.asyncio import AsyncSession

from .base_parser import BaseParser
from app.utils.log_setup import get_logger
from app.crud import artifact as crud
from app.models.artifact import ArtifactClassification
from app.crud import job as job_crud

logger = get_logger(__name__)

# Maximum extraction depth to prevent zip bombs
MAX_EXTRACTION_DEPTH = 16

# Maximum total extracted size (10 GB)
MAX_TOTAL_EXTRACTED_SIZE = 10 * 1024 * 1024 * 1024

# Maximum number of files to extract
MAX_EXTRACTED_FILES = 50000


class ArchiveParser(BaseParser):
    """
    Parser for archive files (ZIP, 7z, RAR).
    
    Recursively extracts all files from archives and submits them as new artifacts
    for parsing. This enables automatic processing of forensic collection bundles.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify archive files by extension or magic bytes.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a supported archive format
        """
        # Check extension first
        lower_name = filename.lower()
        if any(lower_name.endswith(ext) for ext in ['.zip', '.7z', '.rar']):
            return True
        
        # Check magic bytes
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(8)
                
                # ZIP: PK\x03\x04 or PK\x05\x06 (empty archive)
                if magic[:4] in (b'PK\x03\x04', b'PK\x05\x06'):
                    return True
                
                # 7z: 37 7A BC AF 27 1C
                if magic[:6] == b'7z\xbc\xaf\x27\x1c':
                    return True
                
                # RAR: Rar!\x1a\x07 (RAR 1.5+) or Rar!\x1a\x07\x00 (RAR 5.0+)
                if magic[:4] == b'Rar!':
                    return True
                    
        except Exception as e:
            logger.debug(f"Failed to read magic bytes from {filename}: {e}")
            return False
        
        return False
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Extract archive and recursively submit contained files for parsing.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID of the archive
            file_path: Path to archive file
            
        Returns:
            Number of files extracted (not events - those come from sub-parsers)
        """
        logger.debug(f"Extracting archive: {file_path}")
        
        # Track extraction statistics
        stats = {
            'files_extracted': 0,
            'total_size': 0,
            'depth': 0,
            'archives_found': 0,
        }
        
        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory(prefix='archive_extract_') as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract archive
            try:
                await self._extract_archive(file_path, temp_path, stats)
            except Exception as e:
                logger.error(f"Failed to extract archive {file_path}: {e}", exc_info=True)
                raise RuntimeError(f"Archive extraction failed: {e}")
            
            # Recursively process extracted files
            try:
                await self._process_extracted_files(
                    db, 
                    investigation_id, 
                    temp_path, 
                    stats,
                    depth=1
                )
            except Exception as e:
                logger.error(f"Failed to process extracted files from {file_path}: {e}", exc_info=True)
                raise RuntimeError(f"Processing extracted files failed: {e}")
        
        logger.debug(
            f"Archive extraction complete: {stats['files_extracted']} files extracted, "
            f"{stats['archives_found']} nested archives found"
        )
        
        # Return number of files extracted (not events)
        return stats['files_extracted']
    
    async def _extract_archive(
        self, 
        archive_path: Path, 
        extract_to: Path,
        stats: Dict[str, Any]
    ):
        """
        Extract archive file to destination directory.
        
        Args:
            archive_path: Path to archive file
            extract_to: Destination directory
            stats: Statistics dictionary to update
            
        Raises:
            RuntimeError: If extraction fails or limits are exceeded
        """
        lower_name = archive_path.name.lower()
        
        try:
            if lower_name.endswith('.zip'):
                await self._extract_zip(archive_path, extract_to, stats)
            elif lower_name.endswith('.7z'):
                await self._extract_7z(archive_path, extract_to, stats)
            elif lower_name.endswith('.rar'):
                await self._extract_rar(archive_path, extract_to, stats)
            else:
                # Try to detect format from magic bytes
                with open(archive_path, 'rb') as f:
                    magic = f.read(4)
                    
                if magic[:2] == b'PK':
                    await self._extract_zip(archive_path, extract_to, stats)
                elif magic == b'Rar!':
                    await self._extract_rar(archive_path, extract_to, stats)
                else:
                    raise RuntimeError(f"Unknown archive format: {archive_path}")
                    
        except Exception as e:
            logger.error(f"Failed to extract {archive_path}: {e}", exc_info=True)
            raise
    
    async def _extract_zip(
        self, 
        archive_path: Path, 
        extract_to: Path,
        stats: Dict[str, Any]
    ):
        """Extract ZIP archive."""
        logger.debug(f"Extracting ZIP: {archive_path}")
        
        with zipfile.ZipFile(archive_path, 'r') as zf:
            # Check total size before extraction
            total_size = sum(info.file_size for info in zf.infolist())
            
            if stats['total_size'] + total_size > MAX_TOTAL_EXTRACTED_SIZE:
                raise RuntimeError(
                    f"Extraction size limit exceeded: {total_size:,} bytes "
                    f"(total: {stats['total_size'] + total_size:,}, limit: {MAX_TOTAL_EXTRACTED_SIZE:,})"
                )
            
            # Extract all files
            zf.extractall(extract_to)
            stats['total_size'] += total_size
            
            logger.debug(f"Extracted ZIP: {len(zf.namelist())} files, {total_size:,} bytes")
    
    async def _extract_7z(
        self, 
        archive_path: Path, 
        extract_to: Path,
        stats: Dict[str, Any]
    ):
        """Extract 7z archive."""
        logger.debug(f"Extracting 7z: {archive_path}")
        
        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
            # Get file list and sizes
            file_list = archive.getnames()
            
            # Calculate total size (7z doesn't provide easy access to uncompressed size)
            # We'll check during extraction instead
            
            # Extract all files
            archive.extractall(path=extract_to)
            
            # Calculate actual extracted size
            extracted_size = sum(
                (extract_to / name).stat().st_size 
                for name in file_list 
                if (extract_to / name).exists() and (extract_to / name).is_file()
            )
            
            if stats['total_size'] + extracted_size > MAX_TOTAL_EXTRACTED_SIZE:
                raise RuntimeError(
                    f"Extraction size limit exceeded: {extracted_size:,} bytes "
                    f"(total: {stats['total_size'] + extracted_size:,}, limit: {MAX_TOTAL_EXTRACTED_SIZE:,})"
                )
            
            stats['total_size'] += extracted_size
            
            logger.debug(f"Extracted 7z: {len(file_list)} files, {extracted_size:,} bytes")
    
    async def _extract_rar(
        self, 
        archive_path: Path, 
        extract_to: Path,
        stats: Dict[str, Any]
    ):
        """Extract RAR archive using unar command-line tool."""
        logger.debug(f"Extracting RAR: {archive_path}")
        
        # Use unar command-line tool (installed via apt-get)
        # unar is a free alternative to unrar
        try:
            result = subprocess.run(
                ['unar', '-o', str(extract_to), str(archive_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Calculate extracted size
            extracted_size = sum(
                f.stat().st_size 
                for f in extract_to.rglob('*') 
                if f.is_file()
            )
            
            if stats['total_size'] + extracted_size > MAX_TOTAL_EXTRACTED_SIZE:
                raise RuntimeError(
                    f"Extraction size limit exceeded: {extracted_size:,} bytes "
                    f"(total: {stats['total_size'] + extracted_size:,}, limit: {MAX_TOTAL_EXTRACTED_SIZE:,})"
                )
            
            stats['total_size'] += extracted_size
            
            # Count extracted files
            file_count = sum(1 for f in extract_to.rglob('*') if f.is_file())
            
            logger.debug(f"Extracted RAR: {file_count} files, {extracted_size:,} bytes")
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"RAR extraction failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                "unar command not found. Install with: apt-get install unar"
            )
    
    async def _process_extracted_files(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        directory: Path,
        stats: Dict[str, Any],
        depth: int = 1
    ):
        """
        Recursively process all extracted files.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            directory: Directory containing extracted files
            stats: Statistics dictionary
            depth: Current recursion depth
            
        Raises:
            RuntimeError: If depth or file count limits are exceeded
        """
        if depth > MAX_EXTRACTION_DEPTH:
            logger.debug(f"Maximum extraction depth ({MAX_EXTRACTION_DEPTH}) reached, stopping recursion")
            return
        
        # Recursively find all files
        for item in directory.rglob('*'):
            if not item.is_file():
                continue
            
            # Check file count limit
            if stats['files_extracted'] >= MAX_EXTRACTED_FILES:
                logger.debug(f"Maximum file count ({MAX_EXTRACTED_FILES}) reached, stopping extraction")
                return
            
            stats['files_extracted'] += 1
            
            # Read file content
            try:
                file_bytes = item.read_bytes()
            except Exception as e:
                logger.debug(f"Failed to read extracted file {item}: {e}")
                continue
            
            # Get relative path for filename (preserves directory structure)
            try:
                rel_path = item.relative_to(directory)
                # Replace path separators with double underscore to preserve structure
                # but avoid filesystem path issues
                filename = str(rel_path).replace('\\', '__').replace('/', '__')
            except ValueError:
                filename = item.name
            
            # Create artifact for extracted file
            try:
                artifact = await crud.create_artifact(
                    db,
                    investigation_id=investigation_id,
                    filename=filename,
                    classification=ArtifactClassification.UNKNOWN,  # Auto-detected by parser
                    file_bytes=file_bytes,
                )
                
                logger.debug(f"Created artifact {artifact.artifact_id} for extracted file: {filename}")
                
                # Create parsing job for this artifact
                job = await job_crud.enqueue_parsing_job(
                    db,
                    investigation_id=investigation_id,
                    artifact_id=artifact.artifact_id,
                )
                
                logger.debug(f"Queued parsing job {job.job_id} for artifact {artifact.artifact_id}")
                
            except Exception as e:
                #logger.info(f"Failed to create artifact for {filename}: {e}")
                logger.debug(f"Failed to create artifact for {filename}: {e}", exc_info=True)
                # Rollback to prevent transaction poisoning
                try:
                    await db.rollback()
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                # Continue processing other files
                continue


__all__ = ["ArchiveParser"]
