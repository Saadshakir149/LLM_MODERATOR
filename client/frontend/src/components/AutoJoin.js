// =========================
// Auto Join Component - FIXED VERSION
// Automatically assigns user to available room with socket connection check
// =========================
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { socket } from '../socket'; // 👈 IMPORT SOCKET

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export default function AutoJoin() {
  const { mode } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const joinRoom = async () => {
      try {
        setLoading(true);
        setError(null);

        // ============================================================
        // 🟢 FIX #1: Ensure socket is connected before proceeding
        // ============================================================
        if (!socket.connected) {
          console.log("🔌 AutoJoin: Socket not connected, connecting...");
          socket.connect();
          
          // Wait for connection with timeout
          await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
              reject(new Error("Socket connection timeout"));
            }, 5000);
            
            socket.once("connect", () => {
              clearTimeout(timeout);
              console.log("✅ AutoJoin: Socket connected");
              resolve();
            });
          });
        } else {
          console.log("✅ AutoJoin: Socket already connected");
        }

        // ============================================================
        // 🟢 FIX #2: Call backend to get/create room
        // ============================================================
        console.log(`📡 AutoJoin: Fetching room for mode: ${mode}`);
        const response = await fetch(`${API_URL}/join/${mode}`);
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || 'Failed to join room');
        }

        console.log("✅ AutoJoin: Room assigned:", data);

        // Use the username from backend or generate one
        const userName = data.user_name || `Student ${Math.floor(Math.random() * 1000)}`;

        // ============================================================
        // 🟢 FIX #3: Navigate to chat room
        // ============================================================
        navigate(`/chat/${data.room_id}?userName=${encodeURIComponent(userName)}`);

      } catch (err) {
        console.error('❌ AutoJoin Error:', err);
        setError(err.message);
        setLoading(false);
      }
    };

    if (mode === 'active' || mode === 'passive') {
      joinRoom();
    } else {
      setError('Invalid mode. Use /join/active or /join/passive');
      setLoading(false);
    }
  }, [mode, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full">
        {loading ? (
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <h2 className="text-2xl font-bold text-gray-800 mb-2">
              Finding Available Room...
            </h2>
            <p className="text-gray-600">
              {mode === 'active' ? 'Active Mode' : 'Passive Mode'}
            </p>
            <p className="text-sm text-gray-500 mt-4">
              Please wait while we assign you to a room
            </p>
          </div>
        ) : error ? (
          <div className="text-center">
            <div className="text-red-500 text-5xl mb-4">⚠️</div>
            <h2 className="text-2xl font-bold text-gray-800 mb-2">
              Error
            </h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={() => navigate('/')}
              className="bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-700 transition"
            >
              Go Home
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}