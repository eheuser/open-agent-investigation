#!/usr/bin/env python3
"""
Apply LLM configuration from .llm_config.env file to admin user.

This script reads LLM provider settings from a .llm_config.env file
and applies them to the admin user's configuration in the database.

It is designed to run automatically on container startup to enable
headless configuration without using the UI.

Usage:
    python apply_llm_config.py [--config-file PATH]

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (required)

Exit Codes:
    0: Success (config applied or skipped)
    1: Error (database connection, validation, etc.)
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.user import User
from app.crud.llm_config import create_llm_config, get_active_llm_config, update_llm_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean from string (true/false, yes/no, 1/0)."""
    if not value:
        return default
    return value.lower() in ("true", "yes", "1", "on")


def parse_int(value: Optional[str], default: Optional[int] = None) -> Optional[int]:
    """Parse integer from string, return default if invalid."""
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer value: {value}, using default: {default}")
        return default


def parse_float(value: Optional[str], default: Optional[float] = None) -> Optional[float]:
    """Parse float from string, return default if invalid."""
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid float value: {value}, using default: {default}")
        return default


def load_llm_config(config_file: Path) -> Optional[Dict[str, Any]]:
    """
    Load LLM configuration from .env file.
    
    Args:
        config_file: Path to .llm_config.env file
        
    Returns:
        Dictionary of configuration values, or None if file doesn't exist
    """
    if not config_file.exists():
        logger.info(f"Config file not found: {config_file}")
        return None
    
    logger.info(f"Loading LLM configuration from: {config_file}")
    
    # Parse .env file
    config_vars = {}
    with open(config_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE
            if '=' not in line:
                logger.warning(f"Line {line_num}: Invalid format (missing '='): {line}")
                continue
            
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            config_vars[key] = value
    
    # Validate required fields
    required_fields = [
        'LLM_PROVIDER_NAME',
        'LLM_API_ENDPOINT',
        'LLM_MODEL_NAME',
    ]
    
    missing_fields = [f for f in required_fields if not config_vars.get(f)]
    if missing_fields:
        logger.error(f"Missing required fields: {', '.join(missing_fields)}")
        return None
    
    # Build configuration dictionary
    config = {
        # Basic LLM configuration
        'provider_name': config_vars.get('LLM_PROVIDER_NAME'),
        'api_endpoint': config_vars.get('LLM_API_ENDPOINT'),
        'api_key': config_vars.get('LLM_API_KEY') or None,
        'model_name': config_vars.get('LLM_MODEL_NAME'),
        'max_context_length': parse_int(
            config_vars.get('LLM_MAX_CONTEXT_LENGTH'), 
            default=8192
        ),
        'temperature': parse_float(
            config_vars.get('LLM_TEMPERATURE'), 
            default=0.70
        ),
        
        # Advanced LLM parameters
        'top_p': parse_float(config_vars.get('LLM_TOP_P')),
        'top_k': parse_int(config_vars.get('LLM_TOP_K')),
        'min_p': parse_float(config_vars.get('LLM_MIN_P')),
        'timeout': parse_int(config_vars.get('LLM_TIMEOUT'), default=300),
        'allow_concurrent_llm_calls': parse_bool(
            config_vars.get('LLM_ALLOW_CONCURRENT'), 
            default=False
        ),
        
        # Embedding configuration
        'embedding_provider': config_vars.get('EMBEDDING_PROVIDER') or None,
        'embedding_api_url': config_vars.get('EMBEDDING_API_URL') or None,
        'embedding_api_key': config_vars.get('EMBEDDING_API_KEY') or None,
        'embedding_model_name': config_vars.get('EMBEDDING_MODEL_NAME') or None,
        'embedding_max_context_length': parse_int(
            config_vars.get('EMBEDDING_MAX_CONTEXT_LENGTH'),
            default=8192
        ),
        'reranker_model_name': config_vars.get('RERANKER_MODEL_NAME') or None,
        'reranker_max_context_length': parse_int(
            config_vars.get('RERANKER_MAX_CONTEXT_LENGTH'),
            default=8192
        ),
        'allow_concurrent_embedding_calls': parse_bool(
            config_vars.get('EMBEDDING_ALLOW_CONCURRENT'),
            default=False
        ),
        
        'is_active': True,
    }
    
    # Log configuration summary (mask API keys)
    logger.info("LLM Configuration loaded:")
    logger.info(f"  Provider: {config['provider_name']}")
    logger.info(f"  Endpoint: {config['api_endpoint']}")
    logger.info(f"  Model: {config['model_name']}")
    logger.info(f"  Max Context: {config['max_context_length']} tokens")
    logger.info(f"  Temperature: {config['temperature']}")
    logger.info(f"  API Key: {'***' if config['api_key'] else 'None'}")
    
    if config['embedding_provider']:
        logger.info(f"  Embedding Provider: {config['embedding_provider']}")
        logger.info(f"  Embedding Model: {config['embedding_model_name']}")
        logger.info(f"  Embedding API Key: {'***' if config['embedding_api_key'] else 'None'}")
    
    return config


async def get_admin_user(db: AsyncSession) -> Optional[User]:
    """Get the admin user from the database."""
    result = await db.execute(
        select(User).where(User.username == 'admin')
    )
    return result.scalar_one_or_none()


async def apply_config(config: Dict[str, Any], db: AsyncSession) -> bool:
    """
    Apply LLM configuration to admin user.
    
    Args:
        config: Configuration dictionary
        db: Database session
        
    Returns:
        True if configuration was applied, False otherwise
    """
    # Get admin user
    admin_user = await get_admin_user(db)
    if not admin_user:
        logger.error("Admin user not found in database")
        return False
    
    logger.info(f"Found admin user (ID: {admin_user.user_id})")
    
    # Check if active config already exists
    existing_config = await get_active_llm_config(db, admin_user.user_id)
    
    if existing_config:
        logger.info(f"Updating existing LLM config (ID: {existing_config.config_id})")
        
        # Update existing config
        updated_config = await update_llm_config(
            db,
            existing_config.config_id,
            **config
        )
        
        if updated_config:
            logger.info("✓ LLM configuration updated successfully")
            return True
        else:
            logger.error("Failed to update LLM configuration")
            return False
    else:
        logger.info("Creating new LLM configuration")
        
        # Create new config
        new_config = await create_llm_config(
            db,
            user_id=admin_user.user_id,
            **config
        )
        
        if new_config:
            logger.info(f"✓ LLM configuration created successfully (ID: {new_config.config_id})")
            return True
        else:
            logger.error("Failed to create LLM configuration")
            return False


async def main(config_file: Path) -> int:
    """
    Main entry point.
    
    Args:
        config_file: Path to .llm_config.env file
        
    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Check for DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return 1
    
    # Load configuration
    config = load_llm_config(config_file)
    if not config:
        logger.info("No valid LLM configuration found, skipping")
        return 0  # Not an error - just skip if no config file
    
    # Create database engine
    try:
        engine = create_async_engine(database_url, echo=False)
        async_session_maker = sessionmaker(
            engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        return 1
    
    # Apply configuration
    try:
        async with async_session_maker() as db:
            success = await apply_config(config, db)
            if not success:
                return 1
    except Exception as e:
        logger.error(f"Failed to apply LLM configuration: {e}", exc_info=True)
        return 1
    finally:
        await engine.dispose()
    
    return 0


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Apply LLM configuration from .env file to admin user'
    )
    parser.add_argument(
        '--config-file',
        type=Path,
        default=Path('/app/.llm_config.env'),
        help='Path to .llm_config.env file (default: /app/.llm_config.env)'
    )
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(args.config_file))
    sys.exit(exit_code)
