import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.resolve(web, "..");

function run(cmd, args, cwd, name) {
  const child = spawn(cmd, args, { cwd, stdio: "inherit", shell: true, env: process.env });
  child.on("exit", (code) => {
    if (code) process.exitCode = code;
  });
  child.on("error", (err) => {
    console.error(`[${name}]`, err);
    process.exit(1);
  });
  return child;
}

const PY = process.platform === "win32" ? "python" : "python3";
const api = run(PY, ["-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"], root, "api");
const webDev = run("npx", ["vite", "--host", "127.0.0.1", "--port", "5173"], web, "web");

function shutdown() {
  api.kill();
  webDev.kill();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
