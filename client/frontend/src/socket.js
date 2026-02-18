// ============================================================
// path: src/socket.js
// 🔥 ULTRA STABLE FIXED VERSION — POLLING ONLY — NO WEBSOCKET
// ============================================================

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
// 🟦 CRITICAL FIX: POLLING ONLY - NO WEBSOCKET
// ============================================================

const SERVER_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

DEBUG_SOCKET("FORCED SERVER_URL =", SERVER_URL);

// ✅ FIXED: Use ONLY polling transport, disable WebSocket completely
export const socket = io(SERVER_URL, {
  transports: ["polling"], // 👈 ONLY polling, NO websocket
  upgrade: false,          // 👈 NEVER try to upgrade to websocket
  autoConnect: true,
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  reconnectionAttempts: 20,
  timeout: 20000,
  forceNew: true
});

// ============================================================
// 🔥 SOCKET LIFECYCLE LOGGING
// ============================================================

socket.on("connect", () => {
  DEBUG_SOCKET("✅ CONNECTED ✓ socket.id =", socket.id);
  DEBUG_SOCKET("📡 Transport →", socket.io.engine.transport.name);
});

socket.on("connect_error", (err) => {
  DEBUG_SOCKET("❌ CONNECT ERROR →", err?.message || err);
});

socket.on("disconnect", (reason) => {
  DEBUG_SOCKET("🔌 DISCONNECTED →", reason);
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

// For debugging - log all received events
socket.onAny((event, ...args) => {
  DEBUG_SOCKET(`📥 EVENT RECEIVED → "${event}"`, args);
});

// ============================================================
// 📤 GLOBAL EMIT PATCH
// ============================================================
const originalEmit = socket.emit.bind(socket);

socket.emit = (eventName, payload, ...rest) => {
  DEBUG_SOCKET(`📤 EMIT → "${eventName}"`, payload);
  return originalEmit(eventName, payload, ...rest);
};

DEBUG_SOCKET("✅ Ultra stable patch loaded - POLLING ONLY");

// Make socket globally available for debugging
window.socket = socket;