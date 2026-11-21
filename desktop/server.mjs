import http from "node:http";
import path from "node:path";
import { execFile } from "node:child_process";
import { timingSafeEqual } from "node:crypto";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { middleware } from "./runtime/web/server/index.mjs";
import { approveTechniquePreference, readTechniquePreferences } from "./runtime/director.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const origin = "http://127.0.0.1:45839";
const token = process.env.CORTEX_SESSION;
let launchCode = process.env.CORTEX_LAUNCH_CODE;
const launchDeadline = Date.now() + 120_000;
delete process.env.CORTEX_SESSION;
delete process.env.CORTEX_LAUNCH_CODE;
if (!token || token.length < 32) throw new Error("Inicie o Clip Studio pelo executável.");
const python = path.join(root, ".venv/Scripts/python.exe");
const commands = new Set(["render", "live", "modelar", "jobs", "open", "rhythm", "cancel", "open-live", "pick", "ai-status", "ai-install", "update-status", "update-install", "library", "clip-open-studio", "agenda", "schedule", "review", "youtube-account", "youtube-connect", "publish", "retention"]);
const longRequests = new Set(["pick", "modelar", "ai-install", "youtube-connect", "publish"]);
function matches(value, expected) {
  return typeof value === "string" && typeof expected === "string" && value.length === expected.length &&
    Buffer.byteLength(value) === Buffer.byteLength(expected) && timingSafeEqual(Buffer.from(value), Buffer.from(expected));
}
function run(command, data) {
  return new Promise((resolve, reject) => {
    const child = execFile(python, ["-X", "utf8", path.join(root, "desktop_actions.py"), command],
      { cwd: root, windowsHide: true, maxBuffer: 512000, timeout: longRequests.has(command) ? 0 : 25000 }, (err, out, stderr) => {
        if (err) return reject(new Error(stderr.trim() || "Falha no motor local."));
        try { resolve(JSON.parse(out)); } catch (error) { reject(error); }
      });
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(data));
  });
}
let editing = false;
async function sendClip(req, res, id) {
  const { file } = await run("clip-preview", { id });
  const { size } = await stat(file);
  const range = req.headers.range;
  const bounds = range?.match(/^bytes=(\d+)-(\d*)$/);
  const start = bounds ? Number(bounds[1]) : 0;
  const end = bounds?.[2] ? Math.min(size - 1, Number(bounds[2])) : size - 1;
  if ((range && !bounds) || start > end) {
    res.writeHead(416, { "Content-Range": `bytes */${size}` }).end();
    return;
  }
  const headers = { "Content-Type": "video/mp4", "Accept-Ranges": "bytes", "Content-Length": end - start + 1 };
  if (range) headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
  res.writeHead(range ? 206 : 200, headers);
  if (req.method === "HEAD") { res.end(); return; }
  const stream = createReadStream(file, { start, end });
  stream.on("error", () => res.destroy());
  res.on("close", () => stream.destroy());
  stream.pipe(res);
}

const server = http.createServer(async (req, res) => {
  if (req.headers.host !== "127.0.0.1:45839") {
    res.writeHead(403).end(); return;
  }
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  res.setHeader("X-Frame-Options", "DENY");
  const url = new URL(origin + req.url);
  if (url.pathname === "/_desktop/session") {
    res.setHeader("Cache-Control", "no-store");
    if (req.method !== "GET" || Date.now() > launchDeadline || !matches(url.searchParams.get("code"), launchCode)) {
      res.writeHead(403).end(); return;
    }
    launchCode = undefined;
    res.writeHead(303, { Location: "/", "Set-Cookie": `cortex_desktop=${token}; Path=/; SameSite=Strict; HttpOnly` }).end();
    return;
  }
  const cookie = (req.headers.cookie || "").split(/;\s*/).find(value => value.startsWith("cortex_desktop="))?.slice(15);
  if (!matches(req.headers["x-cortex-session"], token) && !matches(cookie, token)) {
    res.writeHead(403).end(); return;
  }
  delete req.headers["x-cortex-session"];
  if (req.headers.cookie) req.headers.cookie = req.headers.cookie.split(/;\s*/).filter(value => !value.startsWith("cortex_desktop=")).join("; ");
  if (req.url === "/_desktop/ready") { res.end("ready"); return; }
  if (!req.url.startsWith("/_desktop/")) { await middleware(req, res); return; }
  if (url.pathname === "/_desktop/media" && ["GET", "HEAD"].includes(req.method)) {
    res.setHeader("Cache-Control", "no-store");
    try { await sendClip(req, res, url.searchParams.get("id")); }
    catch { res.writeHead(404).end(); }
    return;
  }
  const command = req.url.slice(10);
  if (req.method !== "POST" || req.headers.origin !== origin || !commands.has(command)) {
    res.writeHead(403).end(); return;
  }
  res.setHeader("Cache-Control", "no-store");
  const exclusive = ["live", "modelar", "render", "pick", "update-install", "publish", "youtube-connect"].includes(command);
  if (exclusive && editing) { res.writeHead(409).end("Conclua a seleção aberta."); return; }
  if (exclusive) editing = true;
  try {
    let body = "";
    for await (const chunk of req) {
      body += chunk; if (Buffer.byteLength(body) > 8192) throw new Error("Pedido muito longo.");
    }
    const memoryFile = path.join(root, "work/director-preferences.json");
    if (command === "rhythm") {
      const memory = await readTechniquePreferences(memoryFile);
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({seconds: memory.targetShotSeconds}));
      return;
    }
    const result = await run(command, JSON.parse(body || "{}"));
    if (result.profile) {
      const p = result.profile;
      try {
        const memory = await approveTechniquePreference(path.join(root, "work/director-preferences.json"), {
          approved: true, inputHash: p.preset_sha256, sourceHashes: p.source_hashes,
          targetShotSeconds: p.reference_shot_seconds, approvedAt: new Date().toISOString()
        });
        result.message += " Ritmo das referências aprovadas: " + memory.targetShotSeconds + " s por plano.";
      } catch { result.message += " A memória de ritmo precisa de revisão."; }
      delete result.profile;
    }
    res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(result));
  } catch (error) { res.writeHead(400, {"Content-Type": "text/plain; charset=utf-8"}).end(String(error.message)); }
  finally { if (exclusive) editing = false; }
});
server.listen(45839, "127.0.0.1");
process.stdin.resume();
process.stdin.on("end", () => process.exit(0));
