# Web Crawler Crawl4AI Dev Setup

Last Updated: 2026-03-08

## Overview
The `web_crawler` pipeline source operator is backed by a self-hosted Crawl4AI service. In v1, the app expects Crawl4AI to run as a separate process/container and connects to it over HTTP.

## Environment
- `CRAWL4AI_BASE_URL` is required.
- `CRAWL4AI_BEARER_TOKEN` is optional and only needed if the local or hosted Crawl4AI server is configured to require auth.

Example:

```bash
export CRAWL4AI_BASE_URL=http://localhost:11235
unset CRAWL4AI_BEARER_TOKEN
```

## Local Development
By default, the backend now auto-bootstraps a local Crawl4AI Docker container during app startup when `CRAWL4AI_BASE_URL` points at `127.0.0.1`/`localhost` and Docker is available.

The default local env values in `backend/.env` are:

```bash
CRAWL4AI_BASE_URL=http://127.0.0.1:11235
LOCAL_CRAWL4AI_AUTO_BOOTSTRAP=1
LOCAL_CRAWL4AI_IMAGE=unclecode/crawl4ai:latest
LOCAL_CRAWL4AI_CONTAINER_NAME=talmudpedia-crawl4ai-dev
```

If you want to run Crawl4AI manually instead, keep the same base URL and start the container yourself before executing a pipeline that uses `web_crawler`.

Example:

```bash
docker run --rm -p 11235:11235 --shm-size=1g unclecode/crawl4ai:latest
```

Then run the backend normally and execute a pipeline with a `web_crawler` node.

## Failure Mode
If Crawl4AI is not reachable, the pipeline run fails explicitly at the `web_crawler` step with a connection or configuration error. There is no native in-app fallback crawler in v1.

## Node Config
The node keeps the original crawl controls and now exposes only a small set of high-value Crawl4AI options:

- `content_preference`: choose whether the node prefers `fit_markdown`, `raw_markdown`, `html`, or `auto`.
- `wait_until`: browser readiness target before extraction starts.
- `page_timeout_ms`: per-page timeout for slow sites.
- `scan_full_page`: scroll long pages before content extraction.

No existing field was removed in this pass to avoid breaking saved pipelines.
