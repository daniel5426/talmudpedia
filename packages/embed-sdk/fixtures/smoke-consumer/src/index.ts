import { EmbeddedAgentClient, type EmbeddedAgentRuntimeEvent } from "@talmudpedia/embed-sdk";

const client = new EmbeddedAgentClient({
  baseUrl: "https://api.example.com",
  apiKey: "tpk_demo.secret",
  fetchImpl: fetch,
});

const handleEvent = (event: EmbeddedAgentRuntimeEvent) => {
  void event.seq;
};

void client;
void handleEvent;
