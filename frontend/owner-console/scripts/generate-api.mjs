import { constants } from "node:fs";
import { access, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const approvedPaths = [
  "/api/owner/v1/auth/login",
  "/api/owner/v1/auth/logout",
  "/api/owner/v1/auth/session",
  "/api/owner/v1/market/candles",
  "/api/owner/v1/overview",
  "/api/owner/v1/review",
  "/api/owner/v1/signals",
  "/api/owner/v1/signals/{signal_event_id}",
  "/api/owner/v1/tickets",
  "/api/owner/v1/tickets/{ticket_id}/causality",
  "/healthz",
];

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(frontendRoot, "../..");
const openApiDirectory = resolve(frontendRoot, ".openapi");
const openApiPath = resolve(openApiDirectory, "owner-console.json");
const schemaPath = resolve(frontendRoot, "src/api/schema.d.ts");
const exporterPath = resolve(repositoryRoot, "scripts/owner_console/export_openapi.py");
const openApiTypescriptPath = resolve(
  frontendRoot,
  "node_modules/.bin/openapi-typescript",
);

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    ...options,
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const detail = result.stderr.trim() || result.stdout.trim() || "no diagnostic output";
    throw new Error(`${command} exited ${result.status}: ${detail}`);
  }
  return result.stdout;
}

async function executable(path) {
  try {
    await access(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

async function repositoryPython() {
  const commonGitDirectory = run(
    "git",
    ["rev-parse", "--path-format=absolute", "--git-common-dir"],
  ).trim();
  const candidates = [
    resolve(repositoryRoot, ".venv/bin/python"),
    resolve(dirname(commonGitDirectory), ".venv/bin/python"),
  ];

  for (const candidate of candidates) {
    if (await executable(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    `repository Python is unavailable; checked ${candidates.join(", ")}`,
  );
}

function validatePaths(document) {
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("OpenAPI exporter did not return an object");
  }
  const paths = document.paths;
  if (!paths || typeof paths !== "object" || Array.isArray(paths)) {
    throw new Error("OpenAPI document has no paths object");
  }

  const generatedPaths = Object.keys(paths).sort();
  const exactApprovedPaths = [...approvedPaths].sort();
  if (
    generatedPaths.length !== exactApprovedPaths.length ||
    generatedPaths.some((path, index) => path !== exactApprovedPaths[index])
  ) {
    const approved = new Set(exactApprovedPaths);
    const generated = new Set(generatedPaths);
    const unapproved = generatedPaths.filter((path) => !approved.has(path));
    const missing = exactApprovedPaths.filter((path) => !generated.has(path));
    throw new Error(
      `OpenAPI paths differ from the approved set; unapproved=${JSON.stringify(unapproved)} missing=${JSON.stringify(missing)}`,
    );
  }
}

async function main() {
  await mkdir(openApiDirectory, { recursive: true });
  const python = await repositoryPython();
  const openApiJson = run(python, [exporterPath]);

  let openApiDocument;
  try {
    openApiDocument = JSON.parse(openApiJson);
  } catch (error) {
    throw new Error("OpenAPI exporter returned invalid JSON", { cause: error });
  }
  validatePaths(openApiDocument);

  await writeFile(openApiPath, openApiJson, "utf8");
  const schema = run(openApiTypescriptPath, [openApiPath], { cwd: frontendRoot });
  await writeFile(schemaPath, schema, "utf8");
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
