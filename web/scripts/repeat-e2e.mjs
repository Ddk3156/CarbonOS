import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const n = Number(process.argv[2] || 10);
const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

for (let i = 1; i <= n; i += 1) {
  console.log(`\n=== Playwright run ${i}/${n} ===`);
  const r = spawnSync("npx", ["playwright", "test"], { cwd: web, stdio: "inherit", shell: true });
  if (r.status !== 0) {
    console.error(`Failed on run ${i}`);
    process.exit(r.status || 1);
  }
}
console.log(`\nPassed ${n} consecutive Playwright runs.`);
