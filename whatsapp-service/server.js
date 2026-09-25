"use strict";

const crypto = require("crypto");
const express = require("express");
const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

const port = Number(process.env.PORT || "3000");
const apiToken = process.env.WHATSAPP_API_TOKEN || "";
const clientId = process.env.WHATSAPP_CLIENT_ID || "leads";
const sessionPath = process.env.WHATSAPP_SESSION_PATH || "/app/session";

if (!apiToken) {
  throw new Error("WHATSAPP_API_TOKEN is required.");
}

removeChromiumProfileLocks(sessionPath);

let state = "initializing";
let sendQueue = Promise.resolve();

const client = new Client({
  authStrategy: new LocalAuth({ clientId, dataPath: sessionPath }),
  puppeteer: {
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium",
    headless: "new",
    args: [
      "--headless=new",
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
    ],
  },
});

client.on("qr", (qr) => {
  state = "waiting_for_qr";
  console.log("Scan this QR in WhatsApp: Settings -> Linked devices -> Link a device");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  state = "authenticated";
  console.log("WhatsApp session authenticated. Waiting for the client to become ready.");
});

client.on("ready", () => {
  state = "ready";
  console.log("WhatsApp bridge is ready.");
});

client.on("auth_failure", (message) => {
  state = "auth_failure";
  console.error(`WhatsApp authentication failed: ${message}`);
});

client.on("disconnected", (reason) => {
  state = "disconnected";
  console.error(`WhatsApp disconnected: ${reason}`);
  setTimeout(() => process.exit(1), 1000);
});

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "32kb" }));

app.get("/health", (_request, response) => {
  response.json({ status: state, ready: state === "ready" });
});

app.post("/send", authorize, async (request, response) => {
  const phone = String(request.body?.phone || "").replace(/\D/g, "");
  const message = String(request.body?.message || "").trim();

  if (!/^\d{8,15}$/.test(phone)) {
    return response.status(422).json({ detail: "Invalid international phone number." });
  }
  if (!message) {
    return response.status(422).json({ detail: "Message is empty." });
  }
  if (state !== "ready") {
    return response.status(503).json({
      detail: `WhatsApp is not ready (state: ${state}). Check the service logs and scan the QR code.`,
    });
  }

  try {
    const result = await enqueueSend(async () => {
      const numberId = await client.getNumberId(phone);
      if (!numberId) {
        const error = new Error("No WhatsApp account was found for this phone number.");
        error.code = "NOT_FOUND";
        throw error;
      }
      return client.sendMessage(numberId._serialized, message);
    });

    const messageId = result?.id?._serialized || null;
    if (!messageId) {
      console.warn("WhatsApp send returned no message id.");
    }

    return response.json({
      status: "sent",
      message_id: messageId,
    });
  } catch (error) {
    if (error.code === "NOT_FOUND") {
      return response.status(404).json({ detail: error.message });
    }
    console.error("WhatsApp send failed:", error);
    return response.status(500).json({ detail: "WhatsApp send failed." });
  }
});

function authorize(request, response, next) {
  const header = request.get("authorization") || "";
  const provided = header.startsWith("Bearer ") ? header.slice(7) : "";
  const expectedBuffer = Buffer.from(apiToken);
  const providedBuffer = Buffer.from(provided);
  const valid =
    expectedBuffer.length === providedBuffer.length &&
    crypto.timingSafeEqual(expectedBuffer, providedBuffer);

  if (!valid) {
    return response.status(401).json({ detail: "Invalid API token." });
  }
  return next();
}

function enqueueSend(operation) {
  const current = sendQueue.then(operation, operation);
  sendQueue = current.catch(() => undefined);
  return current;
}

function removeChromiumProfileLocks(rootPath) {
  if (!fs.existsSync(rootPath)) {
    return;
  }

  const stack = [rootPath];
  while (stack.length > 0) {
    const currentPath = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(currentPath, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const entryPath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        stack.push(entryPath);
        continue;
      }
      if (entry.name.startsWith("Singleton")) {
        try {
          fs.rmSync(entryPath, { force: true });
          console.log(`Removed stale Chromium profile lock: ${entryPath}`);
        } catch (error) {
          console.warn(`Could not remove Chromium profile lock ${entryPath}:`, error);
        }
      }
    }
  }
}

const server = app.listen(port, "0.0.0.0", () => {
  console.log(`WhatsApp bridge HTTP service listening on port ${port}.`);
});

client.initialize().catch((error) => {
  state = "failed";
  console.error("WhatsApp initialization failed:", error);
  process.exit(1);
});

async function shutdown() {
  server.close();
  try {
    await client.destroy();
  } finally {
    process.exit(0);
  }
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
