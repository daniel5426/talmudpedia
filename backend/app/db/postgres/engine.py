import os
import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine, async_sessionmaker, AsyncEngine

# Postgres (Supabase) configuration from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    try:
        # Heroku/Supabase often sets the password plain text in DATABASE_URL,
        # but SQLAlchemy/asyncpg needs special chars to be URL-encoded.
        if "://" in DATABASE_URL:
             # Basic parse to handle simple cases where special chars might be in password
            scheme, rest = DATABASE_URL.split("://", 1)
            
            # Switch driver first
            if scheme == "postgres" or scheme == "postgresql":
                if "+asyncpg" not in scheme:
                    scheme = "postgresql+asyncpg"

            # Use rsplit('@', 1) to split at the LAST @, which separates creds from host.
            # This correctly handles passwords that contain '@'.
            if "@" in rest:
                creds, location = rest.rsplit("@", 1)
                
                if ":" in creds:
                    # Split username:password
                    u, p = creds.split(":", 1)
                    
                    # Log the username we found to verify we aren't truncating it
                    # (Helpful if error says "failed for user 'postgres'")
                    print(f"DEBUG: Parsed DB User: '{u}'")
                    print(f"DEBUG: Parsed DB Host: '{location}'")
                    
                    # Force encode the password part
                    p_encoded = urllib.parse.quote_plus(p)
                    DATABASE_URL = f"{scheme}://{u}:{p_encoded}@{location}"
                else:
                    # No password found in creds section
                    print("DEBUG: No password found in connection string credentials.")
                    DATABASE_URL = f"{scheme}://{rest}"
            else:
                 print("DEBUG: No '@' found in connection string (no host/creds separation).")
                 DATABASE_URL = f"{scheme}://{rest}"
                 
    except Exception as e:
        print(f"ERROR: Failed to re-encode DATABASE_URL password: {e}")
        # Fallback to simple replacement if parsing fails
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "postgres")
    # Quote password for URL characters (like &, $, #)
    quoted_password = urllib.parse.quote_plus(password)
    
    # Construct the Async Database URL
    DATABASE_URL = f"postgresql+asyncpg://{user}:{quoted_password}@{host}:{port}/{db}"
    print(f"DEBUG: Initializing DB Engine with URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'HIDDEN'}")  # Log host/db only
from sqlalchemy.pool import NullPool

def create_async_engine() -> AsyncEngine:
    """
    Creates and returns a new SQLAlchemy AsyncEngine instance.
    """
    # asyncpg struggles with disabling prepared statements reliably in some SQLAlchemy configurations
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    if "postgresql+psycopg://" not in url and "socket" not in url:
        # Fallback if URL was "postgres://" or otherwise
        if "postgres://" in url:
            url = url.replace("postgres://", "postgresql+psycopg://")
        elif "postgresql://" in url:
            url = url.replace("postgresql://", "postgresql+psycopg://")

    print(f"DEBUG: Creating Async Engine with Psycopg (v3) and prepare_threshold=None")
    return _create_async_engine(
        url,
        echo=False,
        # Disable pre-ping for transaction poolers to avoid 'SELECT 1' overhead/issues
        pool_pre_ping=False,
        # Use NullPool for external transaction pooling
        poolclass=NullPool,
        # Disable prepared statements for PgBouncer compatibility (Psycopg v3 specific)
        connect_args={"prepare_threshold": None},
    )

# Create a global engine instance
engine = create_async_engine()

# Create a session factory
# This is used in app/db/postgres/session.py as:
# async with sessionmaker() as session:
sessionmaker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)
