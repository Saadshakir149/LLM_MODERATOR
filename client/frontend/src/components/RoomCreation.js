// ============================================================
// path: src/components/RoomCreation.jsx
// COMPLETELY FIXED VERSION - Join Room Button Working, No Page Refresh
// ============================================================

import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { socket } from "../socket";
import ShareableLinks from "./ShareableLinks";
import {
  MdPerson,
  MdMeetingRoom,
  MdPlayArrow,
  MdLogin,
  MdPsychology,
  MdSchool,
  MdGroups,
  MdAutoAwesome
} from "react-icons/md";

export default function RoomCreation() {
  const [roomId, setRoomId] = useState("");
  const [userName, setUserName] = useState("");
  const [major, setMajor] = useState("computer_science");
  const [activeModerator, setActiveModerator] = useState(true);
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);
  const navigate = useNavigate();

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // ============================================================
  // ✅ FIXED: Create Room Function
  // ============================================================
  const createRoom = () => {
  const name = userName.trim();
  if (!name) {
    alert("Please enter your name first.");
    return;
  }

  setLoading(true);
  console.log("Creating room for:", name);

  let connectTimeoutId = null;

  const cleanup = () => {
    if (connectTimeoutId) {
      clearTimeout(connectTimeoutId);
      connectTimeoutId = null;
    }
  };

  const onRoomCreated = (data) => {
    cleanup();
    socket.off("error", onError);
    console.log("Room created:", data);
    if (!mountedRef.current) return;
    setLoading(false);
    navigate(
      `/chat/${data.room_id}?userName=${encodeURIComponent(name)}&major=${major}&activeModerator=${activeModerator}`
    );
  };

  const onError = (error) => {
    cleanup();
    socket.off("room_created", onRoomCreated);
    console.error("Room creation error:", error);
    if (!mountedRef.current) return;
    setLoading(false);
    const msg =
      typeof error === "string"
        ? error
        : error?.message || "Failed to create room. Please try again.";
    alert(msg);
  };

  // Register handlers BEFORE emit — otherwise a fast server response can be missed.
  socket.once("room_created", onRoomCreated);
  socket.once("error", onError);

  const emitCreateRoom = () => {
    console.log("Emitting create_room event");
    socket.emit("create_room", {
      user_name: name,
      major: major,
      moderatorMode: activeModerator ? "active" : "passive",
    });
  };

  if (socket.connected) {
    emitCreateRoom();
  } else {
    console.log("Socket not connected, connecting now...");
    socket.connect();
    socket.once("connect", () => {
      console.log("Socket connected, now emitting");
      emitCreateRoom();
    });
    connectTimeoutId = setTimeout(() => {
      if (!socket.connected) {
        socket.off("room_created", onRoomCreated);
        socket.off("error", onError);
        if (mountedRef.current) {
          setLoading(false);
          alert("Connection timeout. Please check your internet and try again.");
        }
      }
    }, 15000);
  }
};
  // ============================================================
  // ✅ FIXED: Join Room Function - No Page Refresh, Proper Loading
  // ============================================================
  const joinRoom = (e) => {
    // ✅ PREVENT ANY DEFAULT BEHAVIOR (form submission, page refresh)
    if (e) e.preventDefault();
    
    if (loading) return;

    const name = userName.trim();
    const id = roomId.trim();

    if (!name) {
      alert("Please enter your name first.");
      return;
    }
    if (!id) {
      alert("Please enter a Room ID.");
      return;
    }

    // ✅ Show loading state
    setLoading(true);
    
    // ✅ Navigate to chat room
    navigate(
      `/chat/${encodeURIComponent(id)}?userName=${encodeURIComponent(name)}&major=${major}&activeModerator=${activeModerator}`
    );
    
    // ✅ DO NOT setLoading(false) here - navigation will unmount component
  };

  return (
    <div className="min-h-screen gradient-bg py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Hero Section */}
        <div className="text-center mb-12 animate-slide-up">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 flex items-center justify-center">
              <MdAutoAwesome className="text-2xl text-white" />
            </div>
            <h1 className="text-4xl md:text-5xl font-bold gradient-text">
              LLM Moderator
            </h1>
          </div>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Collaborative storytelling with AI-powered moderation. Create, join, or share rooms instantly.
          </p>
        </div>

        {/* Main Content */}
        <div className="grid md:grid-cols-2 gap-8">
          {/* Left: Shareable Links */}
          <div className="space-y-8">
            <ShareableLinks />
            
            {/* Stats/Info Card */}
            <div className="card p-6">
              <div className="flex items-center gap-3 mb-4">
                <MdGroups className="text-2xl text-indigo-600" />
                <h3 className="text-xl font-bold text-gray-800">How It Works</h3>
              </div>
              <ul className="space-y-3">
                <li className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-indigo-600">1</span>
                  </div>
                  <span className="text-gray-600">Choose your mode (Active or Passive)</span>
                </li>
                <li className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-indigo-600">2</span>
                  </div>
                  <span className="text-gray-600">Share the link or join manually</span>
                </li>
                <li className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-indigo-600">3</span>
                  </div>
                  <span className="text-gray-600">Collaborate with AI moderation</span>
                </li>
                <li className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-indigo-600">4</span>
                  </div>
                  <span className="text-gray-600">Receive personalized feedback</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Right: Create/Join Form */}
          <div className="glass-card p-8 rounded-3xl shadow-2xl border border-white/40">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-gray-800 mb-2">Manual Room Setup</h2>
              <p className="text-gray-600">Create or join a room with custom settings</p>
            </div>

            <div className="space-y-6">
              {/* User Info */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  <div className="flex items-center gap-2">
                    <MdPerson className="text-gray-400" />
                    <span>Your Name</span>
                  </div>
                </label>
                <input
                  type="text"
                  placeholder="Enter your display name"
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  className="input-field"
                  disabled={loading}
                />
              </div>

              {/* Major Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  <div className="flex items-center gap-2">
                    <MdSchool className="text-gray-400" />
                    <span>Academic Major</span>
                  </div>
                </label>
                <select
                  value={major}
                  onChange={(e) => setMajor(e.target.value)}
                  className="input-field"
                  disabled={loading}
                >
                  <optgroup label="STEM">
                    <option value="computer_science">Computer Science</option>
                    <option value="data_science">Data Science</option>
                    <option value="engineering">Engineering</option>
                    <option value="mathematics">Mathematics</option>
                  </optgroup>
                  <optgroup label="Humanities">
                    <option value="education">Education</option>
                    <option value="psychology">Psychology</option>
                    <option value="sociology">Sociology</option>
                  </optgroup>
                  <optgroup label="Business">
                    <option value="business">Business</option>
                    <option value="economics">Economics</option>
                  </optgroup>
                  <optgroup label="Creative">
                    <option value="media">Media</option>
                    <option value="design">Design</option>
                    <option value="architecture">Architecture</option>
                  </optgroup>
                  <optgroup label="Health">
                    <option value="nursing">Nursing</option>
                    <option value="health_science">Health Science</option>
                  </optgroup>
                </select>
              </div>

              {/* Moderator Toggle */}
              <div className="p-4 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
                      <MdPsychology className="text-xl text-indigo-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-800">AI Moderator</h4>
                      <p className="text-sm text-gray-600">
                        {activeModerator ? "Active engagement mode" : "Passive observation mode"}
                      </p>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={activeModerator}
                      onChange={(e) => setActiveModerator(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gradient-to-r peer-checked:from-indigo-500 peer-checked:to-purple-500"></div>
                  </label>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="space-y-4">
                <button
                  onClick={createRoom}
                  disabled={loading || !userName.trim()}
                  className="w-full btn-primary py-3 flex items-center justify-center gap-2"
                >
                  <MdPlayArrow className="text-xl" />
                  {loading ? "Creating..." : "Create New Room"}
                </button>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-gray-200"></div>
                  </div>
                  <div className="relative flex justify-center text-sm">
                    <span className="px-4 bg-white text-gray-500">Or join existing room</span>
                  </div>
                </div>

                {/* ============================================================
                    ✅ COMPLETELY FIXED: Join Room Section - NO PAGE REFRESH
                    ============================================================ */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <MdMeetingRoom className="text-gray-400" />
                      <span>Room ID</span>
                    </div>
                  </label>
                  
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Enter room ID to join"
                      value={roomId}
                      onChange={(e) => setRoomId(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault(); // ✅ CRITICAL: Prevent form submission
                          joinRoom(e);
                        }
                      }}
                      className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none transition"
                      disabled={loading}
                    />
                    <button
                      onClick={(e) => joinRoom(e)}
                      disabled={loading || !userName.trim() || !roomId.trim()}
                      className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 font-medium whitespace-nowrap"
                    >
                      <MdLogin size={18} />
                      {loading ? "Joining..." : "Join"}
                    </button>
                  </div>
                  
                  {/* ✅ Helpful validation messages */}
                  {!userName.trim() && roomId.trim() && (
                    <p className="text-xs text-red-500 mt-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 bg-red-500 rounded-full"></span>
                      Please enter your name first
                    </p>
                  )}
                  {userName.trim() && !roomId.trim() && (
                    <p className="text-xs text-gray-500 mt-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 bg-gray-400 rounded-full"></span>
                      Enter a room ID to join
                    </p>
                  )}
                  {userName.trim() && roomId.trim() && (
                    <p className="text-xs text-green-600 mt-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 bg-green-500 rounded-full"></span>
                      Ready to join: <span className="font-mono bg-green-50 px-1 py-0.5 rounded">
                        {roomId.substring(0, 8)}...{roomId.substring(roomId.length - 4)}
                      </span>
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}