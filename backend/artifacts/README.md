# Artifacts Directory

This directory contains code artifacts for the platform's operator ecosystem.

## Structure

```
artifacts/
├── builtin/           # Platform-provided operators
│   └── html_cleaner/
│       ├── artifact.yaml
│       └── handler.py
├── custom/            # User-promoted artifacts (from UI drafts)
└── contrib/           # Community/third-party artifacts
```

## Artifact Format

Each artifact is a directory containing:

- `artifact.yaml` - Manifest with metadata, input/output types, and config schema
- `handler.py` - Python module with an `execute(context)` function

## Creating a New Artifact

1. Create a new directory under the appropriate namespace
2. Add `artifact.yaml` with the required fields
3. Add `handler.py` implementing the `execute(context)` function
4. Restart the backend to register the artifact
