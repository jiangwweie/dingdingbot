import http from "node:http";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(root, "dist");
const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}
const port = Number(args.get("--port") ?? process.env.PORT ?? "5186");
const apiTarget = args.get("--api-target") ?? process.env.OWNER_RUNTIME_API_PROXY_TARGET ?? "";

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".woff2", "font/woff2"],
]);

function safeDistPath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0] || "/");
  const relative = decoded === "/" ? "index.html" : decoded.replace(/^\/+/, "");
  const resolved = path.resolve(distDir, relative);
  if (!resolved.startsWith(distDir)) {
    return path.join(distDir, "index.html");
  }
  return resolved;
}

async function proxyApi(request, response) {
  if (!apiTarget) {
    response.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    response.end("API proxy target is not configured");
    return;
  }
  const target = new URL(request.url || "/", apiTarget);
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const upstream = await fetch(target, {
    method: request.method,
    headers: {
      accept: request.headers.accept || "*/*",
      "content-type": request.headers["content-type"] || "application/json",
      cookie: request.headers.cookie || "",
    },
    body: request.method === "GET" || request.method === "HEAD" ? undefined : Buffer.concat(chunks),
    redirect: "manual",
  });
  const headers = {};
  upstream.headers.forEach((value, key) => {
    if (!["content-encoding", "content-length", "transfer-encoding"].includes(key)) {
      headers[key] = value;
    }
  });
  const setCookie = typeof upstream.headers.getSetCookie === "function"
    ? upstream.headers.getSetCookie()
    : upstream.headers.get("set-cookie");
  if (setCookie) {
    headers["set-cookie"] = setCookie;
  }
  response.writeHead(upstream.status, headers);
  response.end(Buffer.from(await upstream.arrayBuffer()));
}

async function serveStatic(request, response) {
  let filePath = safeDistPath(request.url || "/");
  try {
    const info = await stat(filePath);
    if (info.isDirectory()) {
      filePath = path.join(filePath, "index.html");
    }
  } catch {
    filePath = path.join(distDir, "index.html");
  }
  try {
    const info = await stat(filePath);
    if (!info.isFile()) throw new Error("not_file");
    response.writeHead(200, {
      "content-type": contentTypes.get(path.extname(filePath)) || "application/octet-stream",
    });
    const stream = createReadStream(filePath);
    stream.on("error", (error) => {
      if (!response.headersSent) {
        response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      }
      response.end(`Static file read failed: ${error instanceof Error ? error.message : String(error)}`);
    });
    stream.pipe(response);
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

const server = http.createServer((request, response) => {
  if ((request.url || "").startsWith("/api/")) {
    proxyApi(request, response).catch((error) => {
      response.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
      response.end(`API proxy failed: ${error instanceof Error ? error.message : String(error)}`);
    });
    return;
  }
  serveStatic(request, response).catch((error) => {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end(`Static server failed: ${error instanceof Error ? error.message : String(error)}`);
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Owner console static server: http://127.0.0.1:${port}`);
});
