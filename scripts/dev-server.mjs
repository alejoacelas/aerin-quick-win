import { createServer } from "node:http";
import { createRequire } from "node:module";
import { extname, join, normalize } from "node:path";
import { readFile } from "node:fs/promises";

const require = createRequire(import.meta.url);
const searchHandler = require("../api/search.js");
const catalogHandler = require("../api/catalog.js");

const port = Number(process.env.PORT || 3050);
const root = process.cwd();
const publicRoot = join(root, "public");

const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
};

function mockVercelReq(request, url) {
  const query = {};
  for (const [key, value] of url.searchParams.entries()) {
    query[key] = value;
  }
  return { method: request.method, headers: request.headers, query };
}

function mockVercelRes(response) {
  return {
    setHeader(name, value) {
      response.setHeader(name, value);
    },
    status(code) {
      response.statusCode = code;
      return this;
    },
    send(body) {
      response.end(body);
    },
    json(body) {
      if (!response.hasHeader("Content-Type")) {
        response.setHeader("Content-Type", "application/json; charset=utf-8");
      }
      response.end(JSON.stringify(body));
    },
  };
}

async function serveStatic(pathname, response) {
  const routePath = pathname === "/" ? "/index.html" : pathname;
  const safePath = normalize(routePath).replace(/^(\.\.(\/|\\|$))+/, "");
  const filePath = join(publicRoot, safePath);
  if (!filePath.startsWith(publicRoot)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  try {
    const body = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": types[extname(filePath)] || "application/octet-stream",
    });
    response.end(body);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://localhost:${port}`);

  if (url.pathname === "/query" || url.pathname === "/api/search") {
    searchHandler(mockVercelReq(request, url), mockVercelRes(response));
    return;
  }

  if (url.pathname === "/catalog" || url.pathname === "/api/catalog") {
    catalogHandler(mockVercelReq(request, url), mockVercelRes(response));
    return;
  }

  if (url.pathname === "/prompt") {
    await serveStatic("/agent-instructions.md", response);
    return;
  }

  if (url.pathname === "/human" || url.pathname === "/context") {
    await serveStatic("/human.html", response);
    return;
  }

  await serveStatic(url.pathname, response);
}).listen(port, () => {
  console.log(`Aerin instructions site running at http://localhost:${port}`);
});
