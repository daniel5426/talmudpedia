FROM unclecode/crawl4ai:latest

USER root
RUN apt-get update && apt-get install -y --no-install-recommends socat && rm -rf /var/lib/apt/lists/*

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 11235

ENTRYPOINT ["/start.sh"]
