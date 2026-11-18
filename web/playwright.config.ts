import {defineConfig} from "@playwright/test";
import {fileURLToPath} from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const executablePath = process.env.P3_CHROMIUM;
export default defineConfig({
  testDir: "./tests", testMatch: "**/*.spec.ts", workers: 1, timeout: 45_000,
  use: {baseURL: "http://127.0.0.1:8765", browserName:"chromium",
        viewport:{width:1440,height:1050}, launchOptions: executablePath ? {executablePath} : undefined},
  webServer: {
    cwd: root,
    command: "uv run --frozen --extra dev python scripts/start_observatory.py --artifacts " +
      JSON.stringify(process.env.P3_ARTIFACT_ROOT ?? "dist/observatory-inputs"),
    url: "http://127.0.0.1:8765/api/v1/datasets", timeout: 120_000,
    reuseExistingServer: false
  }
});
