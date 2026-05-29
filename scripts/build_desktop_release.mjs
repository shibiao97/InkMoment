#!/usr/bin/env node
import { accessSync, constants } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const pythonScript = join(root, "scripts", "build_desktop_release.py");
const args = process.argv.slice(2);

function exists(path) {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function pythonCandidates() {
  const candidates = [];
  if (process.env.INKMOMENT_PYTHON) {
    candidates.push([process.env.INKMOMENT_PYTHON]);
  }
  const venvPython = process.platform === "win32"
    ? join(root, ".venv", "Scripts", "python.exe")
    : join(root, ".venv", "bin", "python");
  if (exists(venvPython)) {
    candidates.push([venvPython]);
  }
  if (process.platform === "win32") {
    candidates.push(["py", "-3"], ["python"]);
  } else {
    candidates.push(["python3"], ["python"]);
  }
  return candidates;
}

let lastError = null;
for (const candidate of pythonCandidates()) {
  const result = spawnSync(candidate[0], [...candidate.slice(1), pythonScript, ...args], {
    cwd: root,
    env: process.env,
    stdio: "inherit",
    shell: false,
  });

  if (result.error) {
    lastError = result.error;
    continue;
  }
  process.exit(result.status ?? 1);
}

console.error(`Unable to start Python for desktop release build: ${lastError?.message || "not found"}`);
process.exit(1);
