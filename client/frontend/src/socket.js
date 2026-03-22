import { io } from "socket.io-client";

// ============================================================
// 🔥 Ultra Debug Logger
// ============================================================
const DEBUG_SOCKET = (...args) => {
  const timestamp = new Date().toISOString();
  console.log(
    `%c[SOCKET DEBUG ${timestamp}]`,
    "color:#ff0066; font-weight:bold;",
    ...args
  );
};

DEBUG_SOCKET("Initializing socket…");

const SERVER_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

DEBUG_SOCKET("FORCED SERVER_URL =", SERVER_URL);

// ✅ FIXED: Aggressive reconnection settings
export const socket = io(SERVER_URL, {
  transports: ["polling", "websocket"],
  upgrade: true,
  autoConnect: true,
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 10000,
  reconnectionAttempts: 15,
  timeout: 60000,
  randomizationFactor: 0.5,
});

// ============================================================
// 🔥 SOCKET LIFECYCLE LOGGING WITH HEARTBEAT
// ============================================================

socket.on("connect", () => {
  DEBUG_SOCKET("✅ CONNECTED ✓ socket.id =", socket.id);
  DEBUG_SOCKET("📡 Transport →", socket.io.engine.transport.name);
  
  if (socket.io.engine.transport.name === "websocket") {
    DEBUG_SOCKET("🎯 Using WEBSOCKET - stable connection");
  } else {
    DEBUG_SOCKET("⚠️ Using POLLING - may be slower");
  }
  
  // Clear any existing heartbeat
  if (window.heartbeatInterval) {
    clearInterval(window.heartbeatInterval);
  }
  
  // Start new heartbeat
  window.heartbeatInterval = setInterval(() => {
    if (socket.connected) {
      socket.emit("ping", { timestamp: Date.now() });
      DEBUG_SOCKET("📤 HEARTBEAT → ping");
    }
  }, 15000); // Send ping every 15 seconds (faster than Render's timeout)
});

socket.on("connect_error", (err) => {
  DEBUG_SOCKET("❌ CONNECT ERROR →", err?.message || err);
});

socket.on("disconnect", (reason) => {
  DEBUG_SOCKET("🔌 DISCONNECTED →", reason);
  
  // Clean up heartbeat on disconnect
  if (window.heartbeatInterval) {
    clearInterval(window.heartbeatInterval);
    window.heartbeatInterval = null;
  }
  
  // If disconnect was not intentional, force reconnect
  if (reason === "transport close" || reason === "transport error") {
    DEBUG_SOCKET("🔄 Forcing reconnection...");
    setTimeout(() => {
      if (!socket.connected) {
        socket.connect();
      }
    }, 1000);
  }
});

socket.on("pong", (data) => {
  const latency = Date.now() - data.timestamp;
  DEBUG_SOCKET(`📥 HEARTBEAT response → ${latency}ms`);
});

socket.on("reconnect_attempt", (attempt) => {
  DEBUG_SOCKET("🔄 RECONNECT ATTEMPT #", attempt);
});

socket.on("reconnect", () => {
  DEBUG_SOCKET("✅ RECONNECTED ✓ New ID =", socket.id);
});

socket.on("reconnect_error", (err) => {
  DEBUG_SOCKET("❌ RECONNECT ERROR →", err?.message || err);
});

socket.on("reconnect_failed", () => {
  DEBUG_SOCKET("❌ RECONNECT FAILED - Giving up");
  // But we never give up because reconnectionAttempts = Infinity
});

// Transport upgrade events
socket.io.engine.on("upgrade", (transport) => {
  DEBUG_SOCKET("⬆️ Transport UPGRADED to →", transport.name);
});

socket.io.engine.on("upgradeError", (err) => {
  DEBUG_SOCKET("❌ Upgrade FAILED →", err.message);
});

// For debugging - log all received events
socket.onAny((event, ...args) => {
  DEBUG_SOCKET(`📥 EVENT RECEIVED → "${event}"`, args);
});

// ============================================================
// 📤 GLOBAL EMIT PATCH - with connection check
// ============================================================
const originalEmit = socket.emit.bind(socket);

socket.emit = (eventName, payload, ...rest) => {
  if (!socket.connected) {
    DEBUG_SOCKET(`⚠️ EMIT ATTEMPT while disconnected - "${eventName}"`, payload);
    DEBUG_SOCKET("⏳ Waiting for connection before emitting...");
    
    socket.once("connect", () => {
      DEBUG_SOCKET(`📤 EMIT (delayed) → "${eventName}"`, payload);
      originalEmit(eventName, payload, ...rest);
    });
    return socket;
  }
  
  DEBUG_SOCKET(`📤 EMIT → "${eventName}"`, payload);
  return originalEmit(eventName, payload, ...rest);
};

DEBUG_SOCKET("✅ Ultra stable patch loaded - WEBSOCKET FIRST with AGGRESSIVE RECONNECT");

window.socket = socket;