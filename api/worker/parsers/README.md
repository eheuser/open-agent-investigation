# Windows Artifact Parsers

This directory contains forensic parsers for Windows artifacts. Each parser extracts events from specific artifact types and stores them in the unified `events` table.

## Overview

The parser system uses a dispatcher pattern (`dispatcher.py`) that routes artifacts to specialized parsers based on:
- **Artifact Classification** (LOG_FILE, SYSTEM_HIVE, BINARY, ARCHIVE)
- **File Extension** (.evtx, .pf, .lnk, etc.)
- **Filename Patterns** (History, places.sqlite, wpndatabase.db, etc.)
- **Path Context** (Tasks folder, CryptNetUrlCache folder, etc.)

## Supported Artifacts

### Archive Parser (Special)

| Parser | Artifact Type | File Extensions | Event Type | Description |
|--------|---------------|-----------------|------------|-------------|
| **archive_parser.py** | Archives | `.zip`, `.7z`, `.rar` | N/A (extracts files) | Recursive archive extraction for forensic collection bundles |

**Important:** The archive parser does NOT generate events directly. Instead, it:
1. Extracts all files from the archive (recursively)
2. Creates new artifacts for each extracted file
3. Queues parsing jobs for each artifact
4. Supports nested archives up to 5 levels deep

**Safety Limits:**
- Maximum extraction depth: 5 levels
- Maximum total extracted size: 10 GB
- Maximum file count: 50,000 files

### Artifact Parsers

| Parser | Artifact Type | File Extensions | Event Type | Description |
|--------|---------------|-----------------|------------|-------------|
| **evtx_parser.py** | Windows Event Logs | `.evtx` | `evtx_<channel>_<id>` | Security, System, Application logs |
| **registry_parser.py** | Registry Hives | `SYSTEM`, `SOFTWARE`, `SAM`, `NTUSER.DAT` | `registry_*` | Windows Registry analysis |
| **prefetch_parser.py** | Prefetch Files | `.pf` | `prefetch_execution` | Program execution tracking |
| **lnk_parser.py** | Shortcuts | `.lnk` | `lnk_file` | Shortcut file metadata |
| **mft_parser.py** | Master File Table | `$MFT`, `.mft` | `mft_entry` | NTFS file system records |
| **jumplist_parser.py** | Jump Lists | `.automaticDestinations-ms`, `.customDestinations-ms` | `jumplist_entry` | Recently accessed files |
| **browser_history_parser.py** | Browser History | `History` (Chrome/Edge), `places.sqlite` (Firefox), `WebCacheV*.dat` (Legacy Edge) | `browser_history` | Web browsing activity |
| **windows_artifacts_parser.py** | Multiple Windows Artifacts | `.pca`, `.job`, `.xml`, `.db`, `.dat`, `.edb` | Various | See details below |

### Catch-All Parser

| Parser | Artifact Type | File Extensions | Event Type | Description |
|--------|---------------|-----------------|------------|-------------|
| **file_metadata_parser.py** | Any File (Fallback) | All files | `file_metadata` | Static analysis and metadata extraction |

## Detailed Parser Documentation

### Archive Parser (`archive_parser.py`)

**Purpose:** Automatically extract and process forensic collection bundles.

**Supported Formats:**
- **ZIP** - Standard ZIP archives (`.zip`)
- **7z** - 7-Zip archives (`.7z`)
- **RAR** - RAR archives (`.rar`)

**How It Works:**
1. User uploads a ZIP/7z/RAR file
2. Archive parser is selected (first in dispatcher list)
3. Archive is extracted to temporary directory
4. For each extracted file:
   - Sanitize filename (replace `/` and `\` with `__` to preserve structure)
   - Create new artifact record in database
   - Write file to investigation's `raw_files` directory
   - Queue parsing job for the artifact
5. If nested archives are found, repeat recursively (up to 5 levels)

**Filename Sanitization:**
To preserve directory structure while avoiding filesystem issues, path separators are replaced:
- `Windows/System32/winevt/logs/Security.evtx` → `Windows__System32__winevt__logs__Security.evtx`
- This allows you to identify the original location while keeping all files in a flat directory

**Safety Features:**
```python
# Protection against zip bombs and malicious archives
MAX_EXTRACTION_DEPTH = 5        # Prevent infinite recursion
MAX_TOTAL_EXTRACTED_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB limit
MAX_EXTRACTED_FILES = 50000     # Prevent excessive file creation
```

**Example Use Case:**
```bash
# User uploads forensic_collection.zip containing:
# ├── C/
# │   ├── Windows/
# │   │   ├── System32/
# │   │   │   └── winevt/
# │   │   │       └── Logs/
# │   │   │           ├── Security.evtx
# │   │   │           └── System.evtx
# │   │   └── Prefetch/
# │   │       └── CHROME.EXE-A1B2C3D4.pf
# │   └── Users/
# │       └── jsmith/
# │           └── NTUSER.DAT
# └── Registry/
#     ├── SYSTEM
#     └── SOFTWARE

# Result:
# - Archive parser extracts all files
# - Creates 6 artifacts (Security.evtx, System.evtx, CHROME.EXE-*.pf, NTUSER.DAT, SYSTEM, SOFTWARE)
# - Queues 6 parsing jobs
# - EVTX parser processes Security.evtx and System.evtx
# - Prefetch parser processes CHROME.EXE-*.pf
# - Registry parser processes NTUSER.DAT, SYSTEM, SOFTWARE
# - User sees all events in unified events table
```

**Features:**
- Upload entire forensic collections as a single ZIP file
- No need to extract archives manually before upload
- Preserves directory structure for context
- Handles complex evidence packages (e.g., nested archive bundles)

**Error Handling:**
- Corrupted archives: Logged as error, parsing job marked as failed
- Exceeds size limit: RuntimeError raised, extraction stops
- Exceeds depth limit: Warning logged, recursion stops at current level
- Individual file failures: Logged, processing continues with remaining files

---

### Jump List Parser (`jumplist_parser.py`)

**Artifact Types:**
- **Automatic Destinations** (`.automaticDestinations-ms`): OLE compound files containing LNK streams
- **Custom Destinations** (`.customDestinations-ms`): Direct LNK file entries

**Event Type:** `jumplist_entry`

**Payload Fields:**
```json
{
  "jumplist_type": "automatic_destinations | custom_destinations",
  "app_id": "Application ID from filename",
  "entry_number": "Entry index (custom destinations only)",
  "offset": "Byte offset in file",
  "file_path": "Source filename"
}
```

**Why This Matters:**
- Shows which files a user recently opened in each application
- Helps reconstruct user activity timelines
- Can reveal deleted files that were recently accessed
- Useful for identifying exfiltrated documents

---

### Browser History Parser (`browser_history_parser.py`)

**Supported Browsers:**

#### Chrome / Chromium-based Edge
- **File:** `History` (SQLite database)
- **Tables:** `urls`, `visits`
- **Timestamp Format:** Microseconds since 1601-01-01

**Payload Fields:**
```json
{
  "browser": "chrome_chromium",
  "url": "Full URL",
  "title": "Page title",
  "visit_count": "Total visits",
  "typed_count": "Manually typed count",
  "transition_type": "Navigation type",
  "source_file": "History"
}
```

#### Firefox
- **File:** `places.sqlite` (SQLite database)
- **Tables:** `moz_places`, `moz_historyvisits`
- **Timestamp Format:** Microseconds since Unix epoch

**Payload Fields:**
```json
{
  "browser": "firefox",
  "url": "Full URL",
  "title": "Page title",
  "visit_count": "Total visits",
  "typed": "Manually typed flag",
  "visit_type": "Visit type code",
  "source_file": "places.sqlite"
}
```

#### Legacy Edge
- **File:** `WebCacheV*.dat` (ESE database)
- **Library:** `pyesedb`
- **Timestamp Format:** FILETIME (100-nanosecond intervals since 1601-01-01)

**Why This Matters:**
- Shows what websites the user visited and when
- Reveals search terms and downloaded files
- Can identify phishing sites or malicious downloads
- Correlates with network logs and malware execution

**Limitations:**
- Limited to 10,000 most recent entries per database (configurable)

---

### Windows Artifacts Parser (`windows_artifacts_parser.py`)

This multi-purpose parser handles various Windows forensic artifacts:

#### 1. CryptNetUrlCache
**Files:** Certificate revocation list cache files  
**Event Type:** `cryptnet_cache`  
**Why This Matters:** Tracks certificate validation activity (useful for SSL/TLS analysis and identifying certificate-based attacks)

**Payload Fields:**
```json
{
  "artifact_type": "cryptnet_url_cache",
  "url": "CRL distribution point URL",
  "last_download_time": "Unix timestamp",
  "last_modification_time": "Unix timestamp",
  "file_path": "Source filename"
}
```

**Binary Format:**
- 116-byte header with timestamps and URL size
- UTF-16-LE encoded URL
- Timestamps in Windows FILETIME format

#### 2. Program Compatibility Assistant (PCA)
**Files:** `.pca` files  
**Event Type:** `pca_execution`  
**Why This Matters:** Shows which programs were executed and when (useful for malware execution timelines)

**Payload Fields:**
```json
{
  "artifact_type": "pca_launch",
  "file_name": "PCA filename",
  "file_size": "Size in bytes",
  "file_path": "Full path"
}
```

#### 3. Scheduled Tasks
**Files:** `.job` (legacy), `.xml` (modern)  
**Event Type:** `scheduled_task`  
**Why This Matters:** Identifies persistence mechanisms and automated malware execution

**Payload Fields (XML):**
```json
{
  "artifact_type": "scheduled_task_xml",
  "task_name": "Task name",
  "author": "Task creator",
  "description": "Task description",
  "actions": ["command1", "command2"],
  "file_path": "Full path"
}
```

**Payload Fields (Job):**
```json
{
  "artifact_type": "scheduled_task_job",
  "task_name": "Task name from filename",
  "file_size": "Size in bytes",
  "file_path": "Full path"
}
```

#### 4. SRUM Database
**Files:** `srudb.dat`  
**Event Type:** `srum_data`  
**Why This Matters:** Shows which applications used network bandwidth (useful for identifying data exfiltration)

**Library:** `pyesedb`

**Payload Fields:**
```json
{
  "artifact_type": "srum_database",
  "table_name": "GUID-based table name",
  "data": {
    "TimeStamp": "Record timestamp",
    "AppId": "Application identifier",
    "BytesSent": "Network bytes sent",
    "BytesRecvd": "Network bytes received"
  },
  "source_file": "srudb.dat"
}
```

**Key Tables:**
- `{973F5D5C-1D90-4944-BE8E-24B94231A174}` - Network Usage
- `{D10CA2FE-6FCF-4F6D-848E-B2E99266FA89}` - Application Resource Usage
- `{DD6636C4-8929-4683-974E-22C046A43763}` - Network Connectivity

**Limitations:**
- Limited to 1,000 records per table (configurable)

#### 5. Windows Search Database
**Files:** `Windows.edb`  
**Event Type:** `windows_search`  
**Why This Matters:** Reveals files the user searched for or accessed (even if deleted)

**Library:** `pyesedb`

**Payload Fields:**
```json
{
  "artifact_type": "windows_search_database",
  "table_name": "SystemIndex table name",
  "data": {
    "System_ItemUrl": "File/item URL",
    "System_ItemName": "Filename",
    "System_ItemPathDisplay": "Display path",
    "System_DateModified": "Modification timestamp",
    "System_Size": "File size",
    "System_FileExtension": "Extension",
    "System_Kind": "Item type",
    "System_Author": "Author/owner"
  },
  "source_file": "Windows.edb"
}
```

**Key Tables:**
- `SystemIndex_0A` - Main index table
- `SystemIndex_*` - Additional index tables

**Limitations:**
- Limited to 5,000 records per table (configurable)

#### 6. Bitmap Cache
**Files:** `thumbcache_*.db`, `iconcache_*.db`  
**Event Type:** `bitmap_cache`  
**Why This Matters:** Proves a user viewed specific images or documents (thumbnails persist even after file deletion)

**Payload Fields:**
```json
{
  "artifact_type": "bitmap_cache_thumbnail | bitmap_cache_icon",
  "file_name": "Cache filename",
  "file_size": "Size in bytes",
  "file_path": "Full path"
}
```

#### 7. Windows Notification Database
**Files:** `wpndatabase.db` (SQLite)  
**Event Type:** `notification`  
**Why This Matters:** Can show evidence of ransomware or malware notifications

**Payload Fields:**
```json
{
  "artifact_type": "windows_notification",
  "notification_id": "Unique ID",
  "notification_type": "Type code",
  "payload_preview": "First 200 chars",
  "expiry_time": "Expiration timestamp",
  "source_file": "wpndatabase.db"
}
```

**Database Schema:**
```sql
SELECT Id, Type, Payload, ExpiryTime, ArrivalTime
FROM Notification
ORDER BY ArrivalTime DESC
```

---

### File Metadata Parser (`file_metadata_parser.py`)

**Purpose:** Catch-all parser that extracts comprehensive metadata and performs static analysis on any file that doesn't match a specialized parser.

**Event Type:** `file_metadata`

**Extracted Information:**

#### 1. File Hashes
- **MD5** - Fast hash for deduplication
- **SHA1** - Standard forensic hash
- **SHA256** - Cryptographically secure hash

#### 2. File Metadata
- File size (bytes)
- Modified time (from filesystem)
- Created time (from filesystem)
- Accessed time (from filesystem)

#### 3. File Type Detection
- **Magic Bytes** - First 20 bytes in hex
- **File Type** - Detected type (PE, ZIP, PDF, etc.)
- **Description** - Human-readable type description

**Supported File Types:**
- Windows Executables (PE, ELF)
- Archives (ZIP, RAR, 7z, GZIP, BZIP2)
- Documents (PDF, Office formats)
- Images (JPEG, PNG, GIF, BMP, TIFF, ICO)
- Forensic Artifacts (EVTX, Registry, MFT, LNK)
- Databases (SQLite)

#### 4. Entropy Analysis
- **Shannon Entropy** (0.0 - 8.0)
- High entropy (~8.0) indicates encryption or compression
- Low entropy indicates structured or repetitive data
- Calculated on first 64 KB sample for performance

#### 5. String Extraction
- **ASCII Strings** - Printable ASCII characters (min 4 chars)
- **Unicode Strings** - UTF-16 LE strings (min 4 chars)
- Up to 32 KB of string data extracted
- Deduplication applied
- Limited to 500 unique strings per type

#### 6. PE Header Analysis (Windows Executables)
- **PE Type** - PE32 or PE32+
- **Machine Type** - i386, x64, ARM, ARM64, IA64
- **Number of Sections**
- **Compile Timestamp** - When executable was built
- **Is DLL** - Whether file is a DLL
- **Is Executable** - Whether file is an EXE

**Payload Fields:**
```json
{
  "artifact_type": "file_metadata",
  "filename": "example.exe",
  "file_size": 1024000,
  "modified_time": "2024-01-15T10:30:00",
  "created_time": "2024-01-15T10:30:00",
  "accessed_time": "2024-01-15T10:30:00",
  "hashes": {
    "md5": "5d41402abc4b2a76b9719d911017c592",
    "sha1": "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
    "sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706..."
  },
  "file_type": {
    "magic_bytes": "4d5a9000",
    "file_type": "PE",
    "description": "Windows Executable (PE)"
  },
  "entropy": 7.2345,
  "strings": {
    "ascii_strings": ["kernel32.dll", "GetProcAddress", ...],
    "unicode_strings": ["Microsoft Corporation", ...],
    "total_strings": 234,
    "truncated": false
  },
  "pe_info": {
    "pe_type": "PE32+",
    "machine": "x64",
    "num_sections": 6,
    "compile_timestamp": "2024-01-01T12:00:00",
    "is_dll": false,
    "is_executable": true
  }
}
```

**Forensic Value:**
- **File Identification** - Hash-based lookups in threat intelligence databases
- **Malware Detection** - High entropy may indicate packed/encrypted malware
- **String Analysis** - Extract URLs, file paths, registry keys, function names
- **PE Analysis** - Identify executable characteristics and compile timestamps
- **Timeline Reconstruction** - File timestamps provide activity context
- **Baseline Creation** - Document all files in forensic collection

**Performance Considerations:**
- **Size Limit:** Files larger than 500 MB skip full analysis (metadata only)
- **Streaming:** Files read in 8 KB chunks to minimize memory usage
- **Sampling:** Entropy calculated on first 64 KB for performance
- **String Limits:** Maximum 32 KB of string data, 500 unique strings per type

**Use Cases:**
1. **Unknown File Types** - Analyze files without specialized parsers
2. **Malware Triage** - Quick hash and entropy analysis
3. **Bulk Processing** - Extract metadata from entire forensic collections
4. **Baseline Creation** - Document all files in investigation
5. **String Searching** - Find IOCs (URLs, IPs, file paths) in binary files

**Limitations:**
- No deep binary analysis (disassembly, decompilation)
- Limited to 500 MB files for full analysis
- String extraction may miss obfuscated strings
- PE analysis is basic (no import table, sections, resources)

**Example Workflow:**
```bash
# Upload unknown binary file
# → FileMetadataParser triggered (catch-all)
# → Hash calculated: SHA256 = abc123...
# → Entropy: 7.8 (high - possibly packed)
# → Strings extracted: "kernel32.dll", "VirtualAlloc", "CreateRemoteThread"
# → PE info: x64 executable, compiled 2024-01-01
# → Submit hash to VirusTotal for threat intelligence
# → Search strings for IOCs in other artifacts
```

**Integration with Other Parsers:**
The file metadata parser serves as a **fallback** in two ways:

1. **Primary Fallback (Catch-All)**: Registered **last** in the dispatcher parser list
   - If no specialized parser identifies the file, FileMetadataParser is selected
   - Ensures unknown file types still get documented

2. **Error Fallback**: Automatically invoked when specialized parsers fail
   - If any parser (EVTX, Registry, etc.) throws an exception during parsing
   - Dispatcher automatically retries with FileMetadataParser
   - Prevents complete parsing failure - at minimum, file metadata is extracted
   - Logs original error and fallback attempt for debugging

This dual-fallback approach ensures:
1. Specialized parsers (EVTX, Registry, etc.) are tried first
2. Files matching specialized parsers get deep analysis
3. Unknown files still get documented with metadata
4. Corrupted/malformed files get metadata extraction instead of complete failure
5. **Every uploaded file generates at least one event**

**Error Handling:**
- **Parser Failures**: If a specialized parser fails, FileMetadataParser is automatically invoked as fallback
- **Large files** (>500 MB): Metadata-only extraction, analysis skipped
- **Hash calculation failures**: Logged as warning, continues with remaining analysis
- **String extraction failures**: Logged as warning, empty strings returned
- **PE parsing failures**: Logged as debug, PE info omitted from payload
- **FileMetadataParser failures**: If FileMetadataParser itself fails, error is raised (no further fallback)

**Fallback Workflow Example:**
```
1. User uploads corrupted Security.evtx file
2. EvtxParser.identify() returns True (matches .evtx extension)
3. EvtxParser.parse() throws exception (corrupted file)
4. Dispatcher catches exception and logs warning
5. Dispatcher invokes FileMetadataParser.parse() as fallback
6. FileMetadataParser extracts: hashes, file size, timestamps, entropy
7. Result: 1 file_metadata event created instead of complete failure
8. Investigator can still see file existed and check hash against known good files
```

---

## Parser Architecture

### Common Pattern

All parsers follow this structure:

```python
async def parse_<artifact_type>(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse artifact and return number of events inserted.
    """
    # 1. Extract data from artifact
    events = []
    
    # 2. Parse artifact-specific format
    # ...
    
    # 3. Create event dictionaries
    for item in parsed_data:
        events.append({
            "timestamp": datetime_object,
            "payload": flatten_dict(data_dict)
        })
    
    # 4. Insert into database
    db_events = []
    for event_data in events:
        db_events.append({
            "event_ts": event_data["timestamp"],
            "artifact_id": artifact_id,
            "event_type": "artifact_specific_type",
            "payload": json.dumps(event_data["payload"])
        })
    
    await _insert_event_batch(db, investigation_id, db_events)
    
    return len(db_events)
```

### Key Functions

**`flatten_dict(data: Dict) -> Dict`** (`utils.py`)
- Converts nested dictionaries to flat structure with dot notation
- Example: `{"a": {"b": 1}}` → `{"a.b": 1}`
- Simplifies JSONB querying

**`_insert_event_batch(db, investigation_id, events)`**
- Bulk inserts events into `events` table
- Uses parameterized queries to prevent SQL injection
- Handles transaction management (commit/rollback)

---

## Adding Parsers

### Critical Encoding Considerations

**Before implementing any parser, understand these encoding requirements:**

#### 1. **Always Use Error Handling in Decode Operations**

Windows artifacts often contain non-ASCII characters (Chinese, Japanese, Korean, Cyrillic, etc.) in filenames, registry values, and binary data.

```python
# ❌ WRONG - Will crash on non-ASCII data
text = bytes_data.decode('utf-16-le')
text = bytes_data.decode('ascii')

# ✅ CORRECT - Handles encoding errors gracefully
text = bytes_data.decode('utf-16-le', errors='ignore')  # Skip invalid bytes
text = bytes_data.decode('utf-16-le', errors='replace')  # Replace with �
text = bytes_data.decode('ascii', errors='ignore')
```

**Common encoding scenarios:**
- **UTF-16-LE**: Windows uses this for most Unicode strings (registry, NTFS, executables)
- **ASCII**: Legacy systems, some binary formats
- **UTF-8**: Modern formats, JSON, XML

#### 2. **Sanitize ALL Data Before JSONB Storage**

PostgreSQL JSONB cannot handle:
- Null bytes (`\x00`, `\u0000`)
- Unpaired UTF-16 surrogates
- Invalid Unicode sequences
- Certain control characters

```python
from .utils import sanitize_for_jsonb

# After creating payload, ALWAYS sanitize
payload = flatten_dict({
    "key_path": registry_key_path,
    "value_data": decoded_value,
    "file_name": extracted_filename
})

# ✅ CRITICAL - Sanitize before JSON serialization
payload = sanitize_for_jsonb(payload)

event = {
    "event_ts": event_ts,
    "artifact_id": artifact_id,
    "event_type": "my_event",
    "payload": json.dumps(payload)  # Now safe for JSONB
}
```

**What `sanitize_for_jsonb()` does:**
- Removes null bytes (`\x00`)
- Re-encodes strings as UTF-8 to remove surrogate pairs
- Strips control characters (except `\n`, `\r`, `\t`)
- Converts bytes to hex or UTF-8
- Recursively processes nested dicts/lists

#### 3. **Handle Filenames with Non-ASCII Characters**

Extracted files may have Unicode filenames that need special handling:

```python
# When extracting from archives or parsing paths
try:
    # Use Path.as_posix() for consistent separators
    path_str = file_path.as_posix()
    
    # Encode/decode to handle invalid sequences
    safe_filename = path_str.encode('utf-8', errors='replace').decode('utf-8')
except (UnicodeDecodeError, UnicodeEncodeError):
    # Fallback to ASCII representation
    safe_filename = path_str.encode('ascii', errors='replace').decode('ascii')
```

#### 4. **Remove Null Bytes from Strings**

Many Windows artifacts contain null-terminated strings. Remove nulls before storage:

```python
# After decoding UTF-16-LE strings
decoded = value_bytes.decode('utf-16-le', errors='ignore')

# ✅ Remove null bytes and strip whitespace
cleaned = decoded.replace('\x00', '').strip()

# For split operations on null-terminated strings
text = decoded.split('\x00')[0]  # Get first null-terminated string
```

#### 5. **Validate Timestamps Before Use**

Invalid timestamps can cause crashes. Always validate:

```python
try:
    # Windows FILETIME (100-nanosecond intervals since 1601-01-01)
    if filetime > 0 and filetime < 200000000000000000:  # Sanity check
        epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
        timestamp = epoch + timedelta(microseconds=filetime / 10)
    else:
        timestamp = None  # Invalid timestamp
except (ValueError, OverflowError):
    timestamp = None  # Parsing failed

# Skip events without valid timestamps (forensically invalid)
if timestamp is None:
    logger.debug("Skipping event without valid timestamp")
    continue
```

#### 6. **Use Sanitized Logging**

User-controlled data in logs can cause log injection attacks:

```python
from app.utils.security import sanitize_log_message

# ❌ WRONG - Allows log injection
logger.error(f"Failed to parse {filename}: {error}")

# ✅ CORRECT - Sanitizes newlines and control characters
logger.error(
    f"Failed to parse {sanitize_log_message(filename)}: "
    f"{sanitize_log_message(str(error))}",
    exc_info=True
)
```

**What to sanitize in logs:**
- Filenames (user-controlled)
- Error messages (may contain user data)
- Registry keys/values
- URLs, paths, command lines

**What NOT to sanitize:**
- Integer IDs (investigation_id, artifact_id, event_id)
- Counters (len(), count)
- Internal constants

#### 7. **Handle Bytes Objects Properly**

When encountering bytes in parsed data:

```python
if isinstance(value, bytes):
    try:
        # Try UTF-16-LE first (common in Windows)
        decoded = value.decode('utf-16-le', errors='ignore').strip('\x00')
        if decoded:  # Only use if non-empty
            result = decoded
        else:
            # Fall back to hex representation
            result = value.hex()
    except:
        # Last resort: hex representation
        result = value.hex()
```

#### 8. **Test with Non-ASCII Data**

Always test parsers with:
- Chinese/Japanese/Korean filenames
- Cyrillic characters
- Emoji and special symbols
- Null bytes in strings
- Very long strings (>10KB)
- Corrupted/truncated data

```python
# Example test fixture
test_cases = [
    b'\xe4\xb8\xad\xe6\x96\x87',  # Chinese (UTF-8)
    b'\x2d\x4e\x87\x65',  # Chinese (UTF-16-LE)
    b'test\x00\x00string',  # Null bytes
    b'\xff\xfe\x00\x00',  # Invalid UTF-16-LE
    b'\xf0\x9f\x98\x80',  # Emoji (UTF-8)
]
```

### Step 1: Create Parser File

```python
# api/worker/parsers/my_parser.py
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .utils import flatten_dict, sanitize_for_jsonb
from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)


async def parse_my_artifact(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse custom artifact type.
    
    ENCODING CONSIDERATIONS:
    - All string decoding uses errors='ignore' or errors='replace'
    - All payloads are sanitized with sanitize_for_jsonb() before storage
    - Null bytes are removed from strings
    - Timestamps are validated before use
    - Log messages are sanitized
    """
    logger.debug(f"Parsing custom artifact: {sanitize_log_message(str(file_path))}")
    
    try:
        events = []
        
        # Extract data
        with open(file_path, "rb") as f:
            data = f.read()
        
        # Example: Parse binary data with proper encoding handling
        # Assume data contains UTF-16-LE encoded strings
        try:
            # ✅ Use error handling in decode
            text = data.decode('utf-16-le', errors='ignore')
            # ✅ Remove null bytes
            text = text.replace('\x00', '').strip()
        except Exception as e:
            logger.debug(f"Failed to decode data: {sanitize_log_message(str(e))}")
            text = data.hex()  # Fallback to hex representation
        
        # Validate timestamp (example: extract from file metadata)
        try:
            event_ts = datetime.fromtimestamp(file_path.stat().st_mtime)
        except (OSError, ValueError):
            # Skip events without valid timestamps
            logger.debug("Skipping artifact without valid timestamp")
            return 0
        
        # Create payload
        payload = flatten_dict({
            "artifact_type": "my_custom_type",
            "data": text,
            "file_name": file_path.name,
            "file_size": len(data)
        })
        
        # ✅ CRITICAL - Sanitize payload before JSONB storage
        payload = sanitize_for_jsonb(payload)
        
        events.append({
            "timestamp": event_ts,
            "payload": payload
        })
        
        # Insert events
        db_events = []
        for event_data in events:
            db_events.append({
                "event_ts": event_data["timestamp"],
                "artifact_id": artifact_id,
                "event_type": "my_artifact",
                "payload": json.dumps(event_data["payload"])
            })
        
        await _insert_event_batch(db, investigation_id, db_events)
        
        logger.debug(f"Parsed {len(db_events)} events from: {sanitize_log_message(file_path.name)}")
        return len(db_events)
    
    except Exception as e:
        logger.error(
            f"Failed to parse artifact {sanitize_log_message(str(file_path))}: "
            f"{sanitize_log_message(str(e))}",
            exc_info=True
        )
        raise RuntimeError(f"Parsing failed: {sanitize_log_message(str(e))}")


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: List[Dict[str, Any]],
):
    """Insert events into database."""
    if not events:
        return
    
    for event in events:
        event["investigation_id"] = investigation_id
    
    insert_query = text(
        """
        INSERT INTO events (investigation_id, event_ts, artifact_id, event_type, payload)
        VALUES (:investigation_id, :event_ts, :artifact_id, :event_type, CAST(:payload AS jsonb))
    """
    )
    
    try:
        await db.execute(insert_query, events)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to insert events: {e}", exc_info=True)
        await db.rollback()
        raise


__all__ = ["parse_my_artifact"]
```

### Step 2: Update Dispatcher

Edit `dispatcher.py`:

```python
# Add import
from .my_parser import parse_my_artifact

# Add routing logic in parse_artifact()
elif classification == ArtifactClassification.BINARY:
    ext = artifact.filename.lower()
    
    # Add your condition
    if ext.endswith(".myext"):
        events_inserted = await parse_my_artifact(db, investigation_id, artifact_id, file_path)
    # ... existing conditions
```

### Step 3: Update __init__.py

```python
from .my_parser import parse_my_artifact

__all__ = [
    # ... existing exports
    "parse_my_artifact",
]
```

---

## Testing Parsers

### Unit Testing

```python
import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from worker.parsers.my_parser import parse_my_artifact

@pytest.mark.asyncio
async def test_parse_my_artifact(db_session: AsyncSession):
    """Test custom artifact parser."""
    investigation_id = uuid.uuid4()
    artifact_id = 1
    file_path = Path("tests/fixtures/test_artifact.myext")
    
    # Run parser
    events_inserted = await parse_my_artifact(
        db_session, investigation_id, artifact_id, file_path
    )
    
    # Verify results
    assert events_inserted > 0
```

### Manual Testing

```bash
# 1. Upload artifact via UI
# 2. Check worker logs
docker compose logs -f worker | grep "Parsing"

# 3. Query events
docker compose exec api psql -U postgres -d open_agent_inv -c \
  "SELECT event_type, COUNT(*) FROM events GROUP BY event_type;"
```

---

## Performance Considerations

### Batch Insertion
- Use `_insert_event_batch()` for bulk inserts
- Default batch size: all events from single artifact
- Consider chunking for very large artifacts (>10,000 events)

### Memory Management
- Stream large files instead of loading entirely into memory
- Process artifacts in chunks where possible
- Close database connections properly

### Error Handling
- Always wrap parsing logic in try/except
- Log errors with `exc_info=True` for debugging
- Raise `RuntimeError` with descriptive messages
- Rollback transactions on failure

---

## Dependencies

### Required Libraries

- **Core:** `sqlalchemy`, `asyncpg`, `pathlib`
- **Archives:** `zipfile` (built-in), `py7zr`, `rarfile`
- **EVTX:** `evtx` (Rust-based parser)
- **Registry:** `regipy`
- **Prefetch:** `prefetch2es`
- **LNK:** `LnkParse3`
- **MFT:** `mft`
- **Browser History:** `sqlite3` (built-in)
- **Scheduled Tasks XML:** `xml.etree.ElementTree` (built-in)

### All Libraries Included

All required libraries are included in `requirements.txt`:
- **Archive Extraction:** `py7zr==0.21.*`, `rarfile==4.2`
- **Jump Lists:** `olefile==0.47`
- **ESE Databases:** `pyesedb==20240420`
- **Browser History:** `sqlite3` (built-in)
- **Scheduled Tasks:** `xml.etree.ElementTree` (built-in)

**Note:** RAR extraction requires `unar` binary installed on the system:
```bash
# Ubuntu/Debian
apt-get install unar

# Alpine (Docker)
apk add unar

# macOS
brew install unar
```

`unar` is a free alternative to `unrar` and is available in Debian's main repositories.

---

## Forensic Best Practices

### Timestamp Handling
- Always use forensically valid timestamps from artifacts
- Never use `datetime.now()` unless artifact lacks timestamps
- Preserve original timestamp formats in payload
- Convert to UTC for `event_ts` column
- **Validate timestamps before use** - check for overflow, underflow, and invalid values
- **Skip events without valid timestamps** - forensically invalid to fabricate timestamps

### Data Integrity
- Store complete raw data in payload when possible
- Use `flatten_dict()` for consistent structure
- Preserve original field names
- Document any transformations in payload
- **Always sanitize data with `sanitize_for_jsonb()`** before storage
- **Remove null bytes** from strings before insertion

### Encoding Safety (CRITICAL)
- **Use `errors='ignore'` or `errors='replace'`** in ALL decode operations
- **Sanitize ALL payloads** with `sanitize_for_jsonb()` before JSON serialization
- **Remove null bytes** (`\x00`) from strings - PostgreSQL JSONB cannot handle them
- **Handle bytes objects** - try UTF-8/UTF-16-LE decode, fall back to hex
- **Test with non-ASCII data** - Chinese, Japanese, Korean, Cyrillic, emoji
- **Validate string lengths** - very long strings (>1MB) should be truncated

### Logging Safety
- **Sanitize user-controlled data** in log messages with `sanitize_log_message()`
- **Never log raw filenames, paths, or error messages** without sanitization
- **Log integer IDs directly** - no sanitization needed for investigation_id, artifact_id, etc.
- **Use `exc_info=True`** for exception logging to capture stack traces

### Event Types
- Use descriptive, consistent event type names
- Format: `<artifact>_<subtype>` (e.g., `evtx_security_4624`)
- Document all event types in parser docstrings

### Error Recovery
- Log warnings for partial parsing failures
- Continue processing remaining data
- Return count of successfully parsed events
- Include error context in logs (sanitized)
- **Rollback database transactions** on failure to prevent poisoned sessions

---

## Troubleshooting

### Common Issues

**Problem:** Parser not triggered  
**Solution:** Check dispatcher routing logic and file extension matching

**Problem:** No events inserted  
**Solution:** Verify artifact file format and check parser logs

**Problem:** Timestamp errors  
**Solution:** Validate timestamp conversion logic and timezone handling

**Problem:** Database insertion fails  
**Solution:** Check JSONB payload validity and transaction state

### Debug Logging

```python
from app.utils.security import sanitize_log_message

# ✅ CORRECT - Sanitize user-controlled data
logger.debug(
    f"Processing {len(data)} bytes from {sanitize_log_message(str(file_path))}"
)
logger.debug(f"Extracted {len(events)} events")  # Count is safe

# For payload samples, limit size and sanitize
if events:
    sample = str(events[0])[:500]  # Limit length
    logger.debug(f"Event payload sample: {sanitize_log_message(sample)}")

# ❌ WRONG - Allows log injection
logger.debug(f"Processing {file_path}")  # Unsanitized filename
logger.error(f"Error: {error_message}")  # Unsanitized error
```

### Encoding Test Cases

Test your parser with these challenging inputs:

```python
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_parser_with_unicode(db_session):
    """Test parser handles Unicode filenames and content."""
    # Create test file with Chinese characters
    test_file = Path("tests/fixtures/测试文件.dat")
    test_file.write_bytes(b'\xe4\xb8\xad\xe6\x96\x87\x00\x00')  # Chinese + nulls
    
    events = await parse_my_artifact(db_session, investigation_id, artifact_id, test_file)
    assert events > 0  # Should not crash

@pytest.mark.asyncio
async def test_parser_with_null_bytes(db_session):
    """Test parser handles null bytes in data."""
    test_file = Path("tests/fixtures/null_bytes.dat")
    test_file.write_bytes(b'test\x00\x00string\x00')
    
    events = await parse_my_artifact(db_session, investigation_id, artifact_id, test_file)
    assert events > 0
    
    # Verify no null bytes in database
    result = await db.execute(
        "SELECT payload FROM events WHERE artifact_id = :id",
        {"id": artifact_id}
    )
    payload = result.fetchone()[0]
    assert '\x00' not in json.dumps(payload)

@pytest.mark.asyncio
async def test_parser_with_invalid_utf16(db_session):
    """Test parser handles invalid UTF-16 sequences."""
    test_file = Path("tests/fixtures/invalid_utf16.dat")
    test_file.write_bytes(b'\xff\xfe\x00\xd8\x00\x00')  # Unpaired surrogate
    
    events = await parse_my_artifact(db_session, investigation_id, artifact_id, test_file)
    # Should not crash, even if no events extracted
    assert events >= 0
```

---

## Future Enhancements

### Planned Parsers
- **Amcache.hve** - Application execution tracking
- **ShimCache** - Application compatibility cache
- **BITS** - Background Intelligent Transfer Service
- **USB Device History** - USB connection logs
- **PowerShell History** - ConsoleHost_history.txt

### Parser Improvements
- Thumbnail extraction from Bitmap Cache
- Enhanced browser history with downloads and cookies
- Additional SRUM table support
- Windows Search query history extraction

### Performance Optimizations
- Parallel parsing for multiple artifacts
- Streaming parsers for very large files
- Incremental parsing with checkpoints
- Parser result caching

---

## References

### Documentation
- [Main README](../../../README.md) - Project overview
- [Worker README](../README.md) - Worker architecture
- [Database Schema](../../../db/README.md) - Events table structure

### External Resources
- [EVTX Format](https://github.com/omerbenamram/evtx)
- [Registry Format](https://github.com/mkorman90/regipy)
- [Jump Lists](https://github.com/EricZimmerman/JumpList)
- [Browser Forensics](https://www.sans.org/white-papers/33427/)
- [Windows Artifacts](https://github.com/Invoke-IR/PowerForensics)

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../../../README.md).
