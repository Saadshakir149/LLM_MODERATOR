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

// ============================================================
// 🟦 CRITICAL FIX: WEBSOCKET FIRST, POLLING AS FALLBACK
// ============================================================

const SERVER_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

DEBUG_SOCKET("FORCED SERVER_URL =", SERVER_URL);

// ✅ FIXED: Use WebSocket FIRST, polling as fallback
export const socket = io(SERVER_URL, {
  transports: ["websocket", "polling"], // 👈 WebSocket FIRST, polling fallback
  upgrade: true,                         // 👈 Allow transport upgrades
  autoConnect: true,
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  reconnectionAttempts: 20,
  timeout: 30000,                        // 👈 Increased timeout
  forceNew: true
});

// ============================================================
// 🔥 SOCKET LIFECYCLE LOGGING WITH HEARTBEAT
// ============================================================

socket.on("connect", () => {
  DEBUG_SOCKET("✅ CONNECTED ✓ socket.id =", socket.id);
  DEBUG_SOCKET("📡 Transport →", socket.io.engine.transport.name);
  
  // Log which transport is being used
  if (socket.io.engine.transport.name === "websocket") {
    DEBUG_SOCKET("🎯 Using WEBSOCKET - stable connection");
  } else {
    DEBUG_SOCKET("⚠️ Using POLLING - may be slower");
  }
  
  // ============================================================
  // 🟢 HEARTBEAT - Keeps connection alive
  // ============================================================
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
  }, 25000); // Send ping every 25 seconds
});

socket.on("connect_error", (err) => {
  DEBUG_SOCKET("❌ CONNECT ERROR →", err?.message || err);
});

socket.on("disconnect", (reason) => {
  DEBUG_SOCKET("🔌 DISCONNECTED →", reason);
  
  // ============================================================
  // 🟢 CLEAN UP HEARTBEAT ON DISCONNECT
  // ============================================================
  if (window.heartbeatInterval) {
    clearInterval(window.heartbeatInterval);
    window.heartbeatInterval = null;
  }
});

// ============================================================
// 🟢 PONG LISTENER - Confirms heartbeat response
// ============================================================
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
  // Check if socket is connected before emitting
  if (!socket.connected) {
    DEBUG_SOCKET(`⚠️ EMIT ATTEMPT while disconnected - "${eventName}"`, payload);
    DEBUG_SOCKET("⏳ Waiting for connection before emitting...");
    
    // Wait for connection then emit
    socket.once("connect", () => {
      DEBUG_SOCKET(`📤 EMIT (delayed) → "${eventName}"`, payload);
      originalEmit(eventName, payload, ...rest);
    });
    return socket;
  }
  
  DEBUG_SOCKET(`📤 EMIT → "${eventName}"`, payload);
  return originalEmit(eventName, payload, ...rest);
};

DEBUG_SOCKET("✅ Ultra stable patch loaded - WEBSOCKET FIRST with HEARTBEAT");

// Make socket globally available for debugging
window.socket = socket;