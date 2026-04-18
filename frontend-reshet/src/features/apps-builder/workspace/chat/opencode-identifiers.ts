const PREFIXES = {
  message: "msg",
  part: "prt",
} as const;

const RANDOM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastTimestamp = 0;
let counter = 0;

function randomBase62(length: number): string {
  const bytes = new Uint8Array(length);
  globalThis.crypto.getRandomValues(bytes);
  let output = "";
  for (let index = 0; index < length; index += 1) {
    output += RANDOM_ALPHABET[bytes[index] % RANDOM_ALPHABET.length];
  }
  return output;
}

function nextId(prefix: keyof typeof PREFIXES): string {
  const currentTimestamp = Date.now();
  if (currentTimestamp !== lastTimestamp) {
    lastTimestamp = currentTimestamp;
    counter = 0;
  }
  counter += 1;
  const encoded = (BigInt(currentTimestamp) * BigInt(0x1000) + BigInt(counter)).toString(16).padStart(12, "0").slice(-12);
  return `${PREFIXES[prefix]}_${encoded}${randomBase62(14)}`;
}

export function createOpenCodeMessageId(): string {
  return nextId("message");
}

export function createOpenCodePartId(): string {
  return nextId("part");
}
