import http from "node:http";
import path from "node:path";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { middleware } from "./runtime/web/server/index.mjs";
import { approveTechniquePreference, readTechniquePreferences } from "./runtime/director.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const origin = "http://127.0.0.1:45839";
const token = process.env.CORTEX_SESSION;
if (!token || token.length < 32) throw new Error("Inicie o Clip Studio pelo executável.");
const python = path.join(root, ".venv/Scripts/python.exe");
const commands = new Set(["render", "live", "modelar", "jobs", "open", "classic", "rhythm", "cancel", "open-live", "ai-setup"]);
function run(command, data) {
  return new Promise((resolve, reject) => {
    const child = execFile(python, ["-X", "utf8", path.join(root, "desktop_actions.py"), command],
      { cwd: root, windowsHide: true, maxBuffer: 512000 }, (err, out, stderr) => {
        if (err) return reject(new Error(stderr.trim() || "Falha no motor local."));
        try { resolve(JSON.parse(out)); } catch (error) { reject(error); }
      });
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(data));
  });
}
let editing = false;
const server = http.createServer(async (req, res) => {
  if (req.headers.host !== "127.0.0.1:45839" || req.headers["x-cortex-session"] !== token) {
    res.writeHead(403).end(); return;
  }
  delete req.headers["x-cortex-session"];
  if (req.url === "/_desktop/ready") { res.end("ready"); return; }
  if (!req.url.startsWith("/_desktop/")) { await middleware(req, res); return; }
  const command = req.url.slice(10);
  if (req.method !== "POST" || req.headers.origin !== origin || !commands.has(command)) {
    res.writeHead(403).end(); return;
  }
  const exclusive = ["live", "modelar", "render"].includes(command);
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
