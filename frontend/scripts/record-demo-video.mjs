import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, rename, rm } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

const FRONTEND_DIR = resolve(new URL(".", import.meta.url).pathname, "..");
const REPO_DIR = resolve(FRONTEND_DIR, "..");
const VIDEO_DIR = resolve(REPO_DIR, "demo");
const TMP_VIDEO_DIR = resolve(REPO_DIR, ".tmp-demo-video");
const FINAL_VIDEO_PATH = resolve(VIDEO_DIR, "project-demo.webm");
const APP_URL = "http://127.0.0.1:5173";
const API_BASE = "http://localhost:8000";

async function waitForServer(url, timeoutMs = 45_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server is not ready yet.
    }
    await delay(500);
  }
  throw new Error(`Frontend server did not become ready within ${timeoutMs}ms`);
}

async function stopProcess(proc) {
  if (!proc || proc.killed) return;
  proc.kill("SIGTERM");
  await Promise.race([
    new Promise((resolveExit) => proc.once("exit", resolveExit)),
    delay(3_000),
  ]);
  if (!proc.killed) proc.kill("SIGKILL");
}

function createMockHandlers(page) {
  const predictionId = "demo-video-prediction";
  const outputFiles = [
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1024&q=80",
    "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?auto=format&fit=crop&w=1024&q=80",
  ];
  let pollCount = 0;

  page.route("**/generate", async (route, request) => {
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({
      status: 200,
      headers: { "Access-Control-Allow-Origin": "*" },
      json: {
        id: predictionId,
        url: `${API_BASE}/predictions/${predictionId}`,
        status: "starting",
      },
    });
  });

  page.route(`**/predictions/${predictionId}`, async (route) => {
    pollCount += 1;
    const isReady = pollCount >= 3;
    await route.fulfill({
      status: 200,
      headers: { "Access-Control-Allow-Origin": "*" },
      json: {
        id: predictionId,
        url: `${API_BASE}/predictions/${predictionId}`,
        status: isReady ? "succeeded" : "processing",
        files: isReady ? outputFiles : [],
        num_outputs: 2,
      },
    });
  });
}

async function main() {
  await mkdir(VIDEO_DIR, { recursive: true });
  await mkdir(TMP_VIDEO_DIR, { recursive: true });
  if (existsSync(FINAL_VIDEO_PATH)) await rm(FINAL_VIDEO_PATH);

  const frontendServer = spawn(
    "npm",
    ["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
    {
      cwd: FRONTEND_DIR,
      stdio: "inherit",
      env: process.env,
    }
  );

  try {
    await waitForServer(APP_URL);

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      recordVideo: {
        dir: TMP_VIDEO_DIR,
        size: { width: 1440, height: 900 },
      },
    });
    const page = await context.newPage();
    createMockHandlers(page);

    await page.goto(APP_URL, { waitUntil: "networkidle" });
    await page.waitForTimeout(900);
    await page.fill(
      "#prompt",
      "TOK cinematic portrait of a traveler in a neon city, dramatic lighting, ultra detailed."
    );
    await page.waitForTimeout(800);
    await page.fill("#numOutputs", "2");
    await page.waitForTimeout(600);
    await page.click('button[type="submit"]');

    await page.waitForTimeout(2_200);
    await page.waitForSelector("text=Status: succeeded", { timeout: 20_000 });
    await page.waitForTimeout(1_200);
    await page.click(".cell-image-wrap");
    await page.waitForTimeout(2_000);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1_000);
    await page.hover(".cell-download");
    await page.waitForTimeout(1_800);

    const video = page.video();
    await context.close();
    await browser.close();
    const tempVideoPath = await video.path();
    await rename(tempVideoPath, FINAL_VIDEO_PATH);
    console.log(`Demo video saved to: ${FINAL_VIDEO_PATH}`);
  } finally {
    await stopProcess(frontendServer);
    await rm(TMP_VIDEO_DIR, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("Failed to record demo video:", error);
  process.exitCode = 1;
});
