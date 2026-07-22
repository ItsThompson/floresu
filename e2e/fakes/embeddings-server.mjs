/**
 * A minimal OpenAI-compatible embeddings server for the E2E stack.
 *
 * The backend's embedding provider POSTs `{ model, input, dimensions }` to
 * `/v1/embeddings` and expects `{ data: [{ index, embedding }] }`. This server
 * answers with deterministic unit vectors derived from each input string, so the
 * query-embedding path resolves instantly and offline: no run ever calls OpenAI.
 * Vectors are deterministic (a seeded PRNG over the text) so repeated embeds of
 * the same text are identical, matching the content-hash freshness model.
 */
import { createServer } from "node:http";

const DIMENSION = 1536;
const PORT = Number(process.env.FAKE_EMBEDDINGS_PORT ?? 9010);

/** A tiny deterministic PRNG (mulberry32) seeded from the input text. */
function seededVector(text) {
  let seed = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    seed ^= text.charCodeAt(i);
    seed = Math.imul(seed, 16777619);
  }
  let state = seed >>> 0;
  const raw = [];
  let sumSquares = 0;
  for (let i = 0; i < DIMENSION; i += 1) {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    const value = ((t ^ (t >>> 14)) >>> 0) / 4294967296 - 0.5;
    raw.push(value);
    sumSquares += value * value;
  }
  const norm = Math.sqrt(sumSquares) || 1;
  return raw.map((value) => value / norm);
}

const server = createServer((req, res) => {
  // Health probe so Playwright's `webServer` readiness check passes.
  if (req.method === "GET") {
    res.writeHead(200, { "content-type": "text/plain" }).end("ok");
    return;
  }
  if (req.method !== "POST" || !req.url?.startsWith("/v1/embeddings")) {
    res.writeHead(404).end();
    return;
  }
  const chunks = [];
  req.on("data", (chunk) => chunks.push(chunk));
  req.on("end", () => {
    let inputs = [];
    try {
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      inputs = Array.isArray(body.input) ? body.input : body.input ? [body.input] : [];
    } catch {
      res.writeHead(400).end();
      return;
    }
    const data = inputs.map((text, index) => ({
      index,
      embedding: seededVector(String(text)),
      object: "embedding",
    }));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ object: "list", model: "e2e-fake", data }));
  });
});

server.listen(PORT, () => {
  process.stdout.write(`fake-embeddings listening on :${PORT}\n`);
});
