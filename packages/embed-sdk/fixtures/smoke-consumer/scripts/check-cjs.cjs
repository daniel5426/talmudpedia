const sdk = require("@agents24/embed-sdk");

if (typeof sdk.EmbeddedAgentClient !== "function") {
  throw new Error("CommonJS EmbeddedAgentClient export is missing.");
}

if (typeof sdk.EmbeddedAgentSDKError !== "function") {
  throw new Error("CommonJS EmbeddedAgentSDKError export is missing.");
}
