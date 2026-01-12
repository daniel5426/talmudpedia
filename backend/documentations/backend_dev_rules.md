Architectural Rules You Should Enforce

To keep FastAPI from becoming a problem:

1. No Business Logic in Routers

Routers should:

Validate

Authenticate

Dispatch

Nothing else.

2. Framework-Agnostic Core

All of this must live outside FastAPI:

Agent compiler

Execution engine

Policy evaluation

Model resolution

Tool execution

FastAPI should be replaceable without touching core logic.

3. Explicit API Versioning

You will break APIs.

Use:

/api/v1/
/api/v2/

4. Streaming Is a First-Class Path

Design streaming endpoints intentionally.
Do not bolt them on.