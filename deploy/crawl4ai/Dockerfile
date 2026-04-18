FROM unclecode/crawl4ai:latest

USER root
RUN apt-get update && apt-get install -y --no-install-recommends socat && rm -rf /var/lib/apt/lists/*

ENV HOME=/tmp/crawl4ai-home \
    XDG_CACHE_HOME=/tmp/crawl4ai-cache \
    XDG_CONFIG_HOME=/tmp/crawl4ai-config \
    XDG_DATA_HOME=/tmp/crawl4ai-data \
    CRAWL4AI_DB_PATH=/tmp/crawl4ai-data/crawl4ai.db \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN mkdir -p "$HOME" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" \
    && chmod -R 777 "$HOME" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 11235

ENTRYPOINT ["/start.sh"]
