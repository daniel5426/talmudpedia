import { EmbeddedAgentClient, EmbeddedAgentSDKError } from "@talmudpedia/embed-sdk";

if (typeof EmbeddedAgentClient !== "function") {
  throw new Error("EmbeddedAgentClient export is missing.");
}

if (typeof EmbeddedAgentSDKError !== "function") {
  throw new Error("EmbeddedAgentSDKError export is missing.");
}
