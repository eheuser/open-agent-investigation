from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid
import json
import hashlib
import math
import string
import re
import struct

from sqlalchemy.ext.asyncio import AsyncSession

from .base_parser import BaseParser
from .utils import flatten_dict, sanitize_for_jsonb

from app.utils.log_setup import get_logger

logger = get_logger(__name__)

# Configuration constants
MAX_FILE_SIZE_FOR_ANALYSIS = 500 * 1024 * 1024  # 500 MB limit
MAX_STRINGS_SIZE = 32 * 1024  # 32 KB of strings data
MIN_STRING_LENGTH = 4  # Minimum string length to extract
CHUNK_SIZE = 8192  # Read file in 8KB chunks for efficiency


def _calculate_hashes(file_path: Path) -> Dict[str, str]:
    """
    Calculate MD5, SHA1, and SHA256 hashes of a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with 'md5', 'sha1', 'sha256' keys
    """
    md5_hash = hashlib.md5()
    sha1_hash = hashlib.sha1()
    sha256_hash = hashlib.sha256()
    
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                md5_hash.update(chunk)
                sha1_hash.update(chunk)
                sha256_hash.update(chunk)
        
        return {
            'md5': md5_hash.hexdigest(),
            'sha1': sha1_hash.hexdigest(),
            'sha256': sha256_hash.hexdigest(),
        }
    except Exception as e:
        logger.warning(f"Failed to calculate hashes for {file_path}: {e}")
        return {
            'md5': "",
            'sha1': "",
            'sha256': "",
        }


def _calculate_entropy(data: bytes) -> float:
    """
    Calculate Shannon entropy of data.
    
    High entropy (close to 8.0) may indicate encryption or compression.
    Low entropy indicates structured or repetitive data.
    
    Args:
        data: Bytes to analyze
        
    Returns:
        Entropy value between 0.0 and 8.0
    """
    if not data:
        return 0.0
    
    # Count byte frequencies
    byte_counts = [0] * 256
    for byte in data:
        byte_counts[byte] += 1
    
    # Calculate entropy
    entropy = 0.0
    data_len = len(data)
    
    for count in byte_counts:
        if count == 0:
            continue
        probability = count / data_len
        entropy -= probability * math.log2(probability)
    
    return entropy


def _extract_strings(file_path: Path, max_size: int = MAX_STRINGS_SIZE) -> Dict[str, Any]:
    """
    Extract printable ASCII and Unicode strings from a file.
    
    Args:
        file_path: Path to the file
        max_size: Maximum bytes of string data to extract
        
    Returns:
        Dictionary with 'ascii_strings', 'unicode_strings', and 'total_strings' count
    """
    ascii_strings = []
    unicode_strings = []
    total_bytes_extracted = 0
    
    # Regex patterns for strings
    ascii_pattern = re.compile(b'[\x20-\x7e]{' + str(MIN_STRING_LENGTH).encode() + b',}')
    # Unicode pattern (UTF-16 LE) - common in Windows
    unicode_pattern = re.compile(b'(?:[\x20-\x7e]\x00){' + str(MIN_STRING_LENGTH).encode() + b',}')
    
    try:
        with open(file_path, 'rb') as f:
            # Read file in chunks to avoid loading entire file into memory
            while total_bytes_extracted < max_size:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                
                # Extract ASCII strings
                for match in ascii_pattern.finditer(chunk):
                    if total_bytes_extracted >= max_size:
                        break
                    try:
                        s = match.group().decode('ascii')
                        ascii_strings.append(s)
                        total_bytes_extracted += len(s)
                    except:
                        continue
                
                # Extract Unicode strings (UTF-16 LE)
                for match in unicode_pattern.finditer(chunk):
                    if total_bytes_extracted >= max_size:
                        break
                    try:
                        s = match.group().decode('utf-16-le')
                        unicode_strings.append(s)
                        total_bytes_extracted += len(s)
                    except:
                        continue
                
                if total_bytes_extracted >= max_size:
                    break
        
        # Deduplicate and limit strings
        ascii_strings = list(set(ascii_strings))[:500]  # Keep up to 500 unique ASCII strings
        unicode_strings = list(set(unicode_strings))[:500]  # Keep up to 500 unique Unicode strings
        
        return {
            'ascii_strings': ascii_strings,
            'unicode_strings': unicode_strings,
            'total_strings': len(ascii_strings) + len(unicode_strings),
            'truncated': total_bytes_extracted >= max_size,
        }
    
    except Exception as e:
        logger.warning(f"Failed to extract strings from {file_path}: {e}")
        return {
            'ascii_strings': [],
            'unicode_strings': [],
            'total_strings': 0,
            'truncated': False,
        }


def _detect_file_type(file_path: Path) -> Dict[str, Any]:
    """
    Detect file type using magic bytes.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with 'magic_bytes', 'file_type', and 'description'
    """
    # Common file signatures
    signatures = {
        b'\x4D\x5A': ('PE', 'Windows Executable (PE)'),
        b'\x7F\x45\x4C\x46': ('ELF', 'Linux Executable (ELF)'),
        b'\x50\x4B\x03\x04': ('ZIP', 'ZIP Archive'),
        b'\x50\x4B\x05\x06': ('ZIP', 'ZIP Archive (empty)'),
        b'\x50\x4B\x07\x08': ('ZIP', 'ZIP Archive (spanned)'),
        b'\x52\x61\x72\x21\x1A\x07': ('RAR', 'RAR Archive'),
        b'\x37\x7A\xBC\xAF\x27\x1C': ('7Z', '7-Zip Archive'),
        b'\x1F\x8B\x08': ('GZIP', 'GZIP Compressed'),
        b'\x42\x5A\x68': ('BZIP2', 'BZIP2 Compressed'),
        b'\x25\x50\x44\x46': ('PDF', 'PDF Document'),
        b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1': ('OLE', 'Microsoft Office Document (OLE)'),
        b'\x50\x4B\x03\x04\x14\x00\x06\x00': ('DOCX', 'Microsoft Office Open XML Document'),
        b'\xFF\xD8\xFF': ('JPEG', 'JPEG Image'),
        b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A': ('PNG', 'PNG Image'),
        b'\x47\x49\x46\x38': ('GIF', 'GIF Image'),
        b'\x42\x4D': ('BMP', 'Bitmap Image'),
        b'\x49\x49\x2A\x00': ('TIFF', 'TIFF Image (little-endian)'),
        b'\x4D\x4D\x00\x2A': ('TIFF', 'TIFF Image (big-endian)'),
        b'\x00\x00\x01\x00': ('ICO', 'Windows Icon'),
        b'ElfFile\x00': ('EVTX', 'Windows Event Log'),
        b'regf': ('REGISTRY', 'Windows Registry Hive'),
        b'SQLite format 3': ('SQLITE', 'SQLite Database'),
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00FILE': ('MFT', 'NTFS Master File Table'),
        b'\x4C\x00\x00\x00\x01\x14\x02\x00': ('LNK', 'Windows Shortcut'),
    }
    
    try:
        with open(file_path, 'rb') as f:
            header = f.read(20)  # Read first 20 bytes
            
            # Check signatures
            for magic, (file_type, description) in signatures.items():
                if header.startswith(magic):
                    return {
                        'magic_bytes': header[:len(magic)].hex(),
                        'file_type': file_type,
                        'description': description,
                    }
            
            # No match found
            return {
                'magic_bytes': header.hex(),
                'file_type': 'UNKNOWN',
                'description': 'Unknown file type',
            }
    
    except Exception as e:
        logger.warning(f"Failed to detect file type for {file_path}: {e}")
        return {
            'magic_bytes': None,
            'file_type': 'ERROR',
            'description': f'Error detecting file type: {e}',
        }


def _extract_pe_info(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract basic PE (Portable Executable) header information.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with PE info or None if not a PE file
    """
    try:
        with open(file_path, 'rb') as f:
            # Check DOS header
            dos_header = f.read(64)
            if len(dos_header) < 64 or dos_header[:2] != b'MZ':
                return None
            
            # Get PE header offset
            pe_offset = struct.unpack('<I', dos_header[60:64])[0]
            
            # Read PE signature
            f.seek(pe_offset)
            pe_sig = f.read(4)
            if pe_sig != b'PE\x00\x00':
                return None
            
            # Read COFF header (20 bytes)
            coff_header = f.read(20)
            if len(coff_header) < 20:
                return None
            
            machine = struct.unpack('<H', coff_header[0:2])[0]
            num_sections = struct.unpack('<H', coff_header[2:4])[0]
            timestamp = struct.unpack('<I', coff_header[4:8])[0]
            characteristics = struct.unpack('<H', coff_header[16:18])[0]
            
            # Machine types
            machine_types = {
                0x014c: 'i386',
                0x0200: 'IA64',
                0x8664: 'x64',
                0x01c0: 'ARM',
                0xaa64: 'ARM64',
            }
            
            # Parse timestamp (Unix epoch)
            compile_time = None
            if timestamp > 0:
                try:
                    compile_time = datetime.fromtimestamp(timestamp).isoformat()
                except:
                    compile_time = None
            
            return {
                'pe_type': 'PE32+' if machine == 0x8664 else 'PE32',
                'machine': machine_types.get(machine, f'Unknown (0x{machine:04x})'),
                'num_sections': num_sections,
                'compile_timestamp': compile_time,
                'is_dll': bool(characteristics & 0x2000),
                'is_executable': bool(characteristics & 0x0002),
            }
    
    except Exception as e:
        logger.debug(f"Failed to extract PE info from {file_path}: {e}")
        return None


class FileMetadataParser(BaseParser):
    """
    Catch-all parser for file metadata and static analysis.
    
    This parser serves as a fallback for files that don't match any specialized
    parser. It extracts comprehensive metadata and performs static analysis.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        This parser accepts ALL files as a fallback.
        
        It should be registered LAST in the dispatcher's parser list so that
        specialized parsers have priority.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            Always returns True (catch-all parser)
        """
        # Always return True - this is the catch-all parser
        # It should be registered last in the dispatcher
        return True
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Extract file metadata and perform static analysis.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to file
            
        Returns:
            Number of events inserted (always 1 for metadata)
        """
        try:
            # Get file stats
            stat = file_path.stat()
            file_size = stat.st_size
            
            # Check file size limit
            if file_size > MAX_FILE_SIZE_FOR_ANALYSIS:
                logger.warning(
                    f"File {file_path.name} ({file_size:,} bytes) exceeds analysis limit "
                    f"({MAX_FILE_SIZE_FOR_ANALYSIS:,} bytes). Extracting basic metadata only."
                )
                # Extract only basic metadata for very large files
                payload = {
                    'artifact_type': 'file_metadata',
                    'filename': file_path.name,
                    'file_size': file_size,
                    'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'accessed_time': datetime.fromtimestamp(stat.st_atime).isoformat(),
                    'analysis_skipped': True,
                    'skip_reason': 'File exceeds size limit for analysis',
                }
            else:
                # Calculate hashes
                hashes = _calculate_hashes(file_path)
                
                # Detect file type
                file_type_info = _detect_file_type(file_path)
                
                # Calculate entropy (read first 64KB for performance)
                entropy = 0.0
                try:
                    with open(file_path, 'rb') as f:
                        sample_data = f.read(65536)  # 64 KB sample
                        entropy = _calculate_entropy(sample_data)
                except Exception as e:
                    logger.warning(f"Failed to calculate entropy for {file_path}: {e}")
                
                # Extract strings
                strings_data = _extract_strings(file_path)
                
                # Extract PE info if applicable
                pe_info = _extract_pe_info(file_path)
                
                # Build comprehensive payload
                payload = {
                    'artifact_type': 'file_metadata',
                    'filename': file_path.name,
                    'file_size': file_size,
                    'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'accessed_time': datetime.fromtimestamp(stat.st_atime).isoformat(),
                    'hashes': hashes,
                    'file_type': file_type_info,
                    'entropy': round(entropy, 4),
                    'strings': strings_data,
                }
                
                # Add PE info if available
                if pe_info:
                    payload['pe_info'] = pe_info
            
            # Flatten payload
            payload = flatten_dict(payload)
            
            # Sanitize payload for JSONB storage
            payload = sanitize_for_jsonb(payload)
            
            # Use submission time as event timestamp
            event_ts = datetime.now()
            
            # Create event
            event = {
                'event_ts': event_ts,
                'artifact_id': artifact_id,
                'event_type': 'file_metadata',
                'payload': json.dumps(payload),
            }
            
            # Insert event
            await self._insert_event_batch(db, investigation_id, [event])
            
            logger.info(
                f"Extracted metadata for {file_path.name}: "
                f"{file_size:,} bytes, entropy={round(entropy, 2) if file_size <= MAX_FILE_SIZE_FOR_ANALYSIS else 'N/A'}, "
                f"type={file_type_info.get('file_type', 'UNKNOWN') if file_size <= MAX_FILE_SIZE_FOR_ANALYSIS else 'UNKNOWN'}"
            )
            
            return 1
        
        except Exception as e:
            logger.error(f"Failed to extract metadata from {file_path}: {e}", exc_info=True)
            raise RuntimeError(f"File metadata extraction failed: {e}")


__all__ = ["FileMetadataParser"]
