export type EmbeddedAgentSDKErrorKind = "http" | "network" | "protocol";

type EmbeddedAgentSDKErrorOptions = {
  kind: EmbeddedAgentSDKErrorKind;
  status?: number;
  details?: unknown;
  cause?: unknown;
};

export class EmbeddedAgentSDKError extends Error {
  public readonly kind: EmbeddedAgentSDKErrorKind;
  public readonly status?: number;
  public readonly details?: unknown;

  constructor(message: string, options: EmbeddedAgentSDKErrorOptions) {
    super(message, "cause" in Error.prototype ? { cause: options.cause } : undefined);
    this.name = "EmbeddedAgentSDKError";
    this.kind = options.kind;
    this.status = options.status;
    this.details = options.details;
    if (!("cause" in this) && options.cause !== undefined) {
      Object.defineProperty(this, "cause", {
        configurable: true,
        enumerable: false,
        value: options.cause,
        writable: true,
      });
    }
  }
}
