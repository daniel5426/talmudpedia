import os
import sys
import asyncio
from dotenv import load_dotenv

# Setup paths
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BACKEND_DIR)

# Load env vars BEFORE importing directory config
env_path = os.path.join(BACKEND_DIR, ".env")
print(f"Loading environment from {env_path}")
load_dotenv(env_path)

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from alembic import command
from alembic.config import Config
from app.db.postgres.engine import DATABASE_URL

async def reset_schema():
    # Log the URL (masked) to debugging
    masked_url = DATABASE_URL
    if "@" in masked_url:
        prefix, suffix = masked_url.rsplit("@", 1)
        masked_url = f"***@{suffix}"
    print(f"Connecting to database (Async): {masked_url}")

    # Use the retrieved DATABASE_URL
    # We use AUTOCOMMIT to ensure some commands (like DROP SCHEMA) work correctly without nested transactions
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    try:
        async with engine.connect() as conn:
            print("Configuring session...")
            # Disable statement timeout for this session
            await conn.execute(text("SET statement_timeout = 0;"))
            
            try:
                print("Attempting to terminate other connections...")
                # Terminate other connections to release locks
                await conn.execute(text("""
                    SELECT pg_terminate_backend(pid) 
                    FROM pg_stat_activity 
                    WHERE datname = current_database() 
                    AND pid <> pg_backend_pid()
                """))
            except Exception as e:
                print(f"Note: Could not terminate other connections (privilege issue): {e}")
                print("Proceeding anyway, but script might hang if locks exist.")
            
            print("Dropping public schema...")
            try:
                await conn.execute(text("DROP SCHEMA public CASCADE;"))
                await conn.execute(text("CREATE SCHEMA public;"))
                await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
                print("Schema reset complete.")
            except Exception as schema_err:
                print(f"Error dropping schema: {schema_err}")
                print("Attempting to drop all tables individually instead...")
                # Fallback: Find and drop all tables
                tables = await conn.execute(text("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                """))
                for row in tables:
                    table_name = row[0]
                    print(f"Dropping table {table_name}...")
                    await conn.execute(text(f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE;"))
                
                # Also types/enums
                types = await conn.execute(text("""
                    SELECT typname FROM pg_type t 
                    JOIN pg_namespace n ON n.oid = t.typnamespace 
                    WHERE n.nspname = 'public' AND typtype = 'e'
                """))
                for row in types:
                    type_name = row[0]
                    print(f"Dropping type {type_name}...")
                    await conn.execute(text(f"DROP TYPE IF EXISTS \"{type_name}\" CASCADE;"))
                
                print("Individual table cleanup complete.")
    finally:
        await engine.dispose()

def run_migrations():
    print("Running migrations...")
    alembic_ini_path = os.path.join(BACKEND_DIR, "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    
    # Alembic's command.upgrade is synchronous
    command.upgrade(alembic_cfg, "head")
    print("Database reset and migrated successfully.")

if __name__ == "__main__":
    print("WARNING: This will delete ALL data in the database.")
    confirm = input("Are you sure? Type 'yes' to proceed: ")
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    try:
        # Run async part
        asyncio.run(reset_schema())
        # Run sync part (Alembic)
        run_migrations()
    except Exception as e:
        print(f"Error during reset: {e}")
        import traceback
        traceback.print_exc()
