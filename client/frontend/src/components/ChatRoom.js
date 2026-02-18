// ============================================================
// ChatRoom.js - PURE TEXT, NO VOICE, NO CLUTTER
// ============================================================
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { socket } from "../socket";
import {
  MdSend,
  MdExitToApp,
  MdContentCopy,
  MdCheck,
  MdPerson,
  MdChat
} from "react-icons/md";

// ============================================================
// 🎨 USER COLOR SYSTEM
// ============================================================
const USER_COLORS = [
  { bg: "bg-gradient-to-r from-blue-100 to-blue-200", border: "border-blue-300", text: "text-blue-700", accent: "bg-blue-500" },
  { bg: "bg-gradient-to-r from-green-100 to-emerald-200", border: "border-green-300", text: "text-green-700", accent: "bg-green-500" },
  { bg: "bg-gradient-to-r from-purple-100 to-purple-200", border: "border-purple-300", text: "text-purple-700", accent: "bg-purple-500" },
  { bg: "bg-gradient-to-r from-pink-100 to-pink-200", border: "border-pink-300", text: "text-pink-700", accent: "bg-pink-500" },
  { bg: "bg-gradient-to-r from-indigo-100 to-indigo-200", border: "border-indigo-300", text: "text-indigo-700", accent: "bg-indigo-500" },
  { bg: "bg-gradient-to-r from-teal-100 to-teal-200", border: "border-teal-300", text: "text-teal-700", accent: "bg-teal-500" },
];

const getUserColor = (userName, currentUserName) => {
  if (userName === currentUserName) {
    return USER_COLORS[0];
  }
  let hash = 0;
  for (let i = 0; i < userName.length; i++) {
    hash = userName.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % USER_COLORS.length;
  return USER_COLORS[index];
};

// ============================================================
// 🎯 MAIN CHATROOM COMPONENT - PURE TEXT, NO VOICE
// ============================================================
export default function ChatRoom() {
  const { roomId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const userName = useMemo(
    () => new URLSearchParams(location.search).get("userName") || "Anonymous",
    [location.search]
  );

  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isLoadingFeedback, setIsLoadingFeedback] = useState(false);
  const [showParticipants, setShowParticipants] = useState(false);
  const [participants, setParticipants] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState("connecting");

  const messagesEndRef = useRef(null);

  // ============================================================
  // 🔊 LOCAL SEND SOUND (keep for feedback)
  // ============================================================
  const [sendSound] = useState(() => {
    const audio = new Audio();
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    audio.play = () => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 523.25;
      osc.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
      osc.start();
      osc.stop(ctx.currentTime + 0.1);
      return ctx.resume();
    };
    return audio;
  });

  // ============================================================
  // ⚡ SOCKET CONNECTION & MESSAGES
  // ============================================================
 // ============================================================
// ⚡ SOCKET CONNECTION & MESSAGES - FIXED VERSION
// ============================================================
useEffect(() => {
  if (!roomId || !userName) return;

  setConnectionStatus("connecting");

  // Connection events
  socket.on("connect", () => {
    setConnectionStatus("connected");
    socket.emit("join_room", { room_id: roomId, user_name: userName });
  });

  socket.on("disconnect", () => {
    setConnectionStatus("disconnected");
  });

  socket.on("connect_error", () => {
    setConnectionStatus("error");
  });

  // Room events
  socket.on("joined_room", () => {
    setReady(true);
    setConnectionStatus("connected");
    setParticipants(prev => {
      if (!prev.includes(userName)) {
        return [...prev, userName];
      }
      return prev;
    });
  });

  socket.on("chat_history", (data) => {
    setMessages(data.chat_history || []);
    if (data.participants) {
      setParticipants(data.participants);
    } else {
      setParticipants([userName]);
    }
  });

  socket.on("receive_message", (data) => {
    setMessages((prev) => {
      const isDuplicate = prev.length > 0 &&
        prev[prev.length - 1].sender === data.sender &&
        prev[prev.length - 1].message === data.message;
      return isDuplicate ? prev : [...prev, data];
    });
  });

  socket.on("participants_update", (data) => {
    setParticipants(data.participants || []);
  });

  // ✅ FIXED: Session ended handler
  socket.on("session_ended", (data) => {
    console.log("📨 Session ended with data:", data);
    
    // Get feedback directly from data.feedback
    const feedback = data?.feedback || "Session ended. Thank you for participating!";
    
    // Navigate to feedback page
    navigate("/feedback", { 
      state: { 
        feedback: feedback,
        room_id: data?.room_id 
      } 
    });
    
    setIsLoadingFeedback(false);
  });

  // If already connected, join room immediately
  if (socket.connected) {
    socket.emit("join_room", { room_id: roomId, user_name: userName });
  } else {
    socket.connect();
  }

  return () => {
    socket.off("connect");
    socket.off("disconnect");
    socket.off("connect_error");
    socket.off("joined_room");
    socket.off("chat_history");
    socket.off("receive_message");
    socket.off("participants_update");
    socket.off("session_ended");
  };
}, [roomId, userName, navigate]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ============================================================
  // 💬 SEND MESSAGE - TEXT ONLY
  // ============================================================
  const sendMessage = useCallback(() => {
    const trimmed = message.trim();
    if (!trimmed || !ready) return;

    // Play send sound
    sendSound.play().catch(() => {});

    // Add message locally immediately
    setMessages(prev => [...prev, { 
      sender: userName, 
      message: trimmed, 
      timestamp: new Date().toISOString() 
    }]);

    // Send to server
    socket.emit("send_message", {
      room_id: roomId,
      message: trimmed,
      sender: userName,
    });

    // Clear input
    setMessage("");
  }, [message, roomId, userName, ready, sendSound]);

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ============================================================
  // 🏁 END SESSION
  // ============================================================
  const endSession = () => {
    if (window.confirm("Are you sure you want to end this session? All participants will receive feedback.")) {
      setIsLoadingFeedback(true);
      socket.emit("end_session", { room_id: roomId, sender: userName });
    }
  };

  // ============================================================
  // 🎨 UI RENDER - PURE TEXT, NO VOICE BUTTONS
  // ============================================================
  
  // Calculate online count - at least 1 (yourself)
  const onlineCount = Math.max(participants.length, 1);

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      
      {/* 🎪 CLEAN HEADER - NO TTS BUTTONS */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <MdChat className="text-xl" />
            </div>
            <div>
              <h1 className="font-bold text-lg">Collaborative Storytelling</h1>
              <div className="flex items-center gap-2 text-sm opacity-90">
                <span className="font-mono">Room: {roomId.substring(0, 8)}...</span>
                
                {/* ONLINE COUNT - ALWAYS SHOWS AT LEAST 1 */}
                <span className="px-2 py-0.5 bg-green-500/30 rounded-full text-xs flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-green-300 rounded-full"></span>
                  {onlineCount} online
                </span>

                {/* CONNECTION STATUS */}
                {connectionStatus === "disconnected" && (
                  <span className="px-2 py-0.5 bg-red-500/30 rounded-full text-xs">
                    Disconnected
                  </span>
                )}
                {connectionStatus === "connecting" && (
                  <span className="px-2 py-0.5 bg-yellow-500/30 rounded-full text-xs">
                    Connecting...
                  </span>
                )}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            {/* Copy Room ID - ONLY BUTTON IN HEADER */}
            <button
              onClick={() => {
                navigator.clipboard.writeText(roomId);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="flex items-center gap-1 px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded-lg transition-colors text-sm"
            >
              {copied ? <MdCheck size={16} /> : <MdContentCopy size={16} />}
              {copied ? "Copied!" : "Copy ID"}
            </button>
            
            {/* Participants Toggle */}
            <button
              onClick={() => setShowParticipants(!showParticipants)}
              className="p-2 rounded-lg hover:bg-white/20 transition-colors"
              title="View participants"
            >
              <MdPerson size={20} />
            </button>
          </div>
        </div>
      </div>

      {/* 📱 MAIN CONTENT AREA */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* 💬 CHAT MESSAGES */}
        <div className="flex-1 flex flex-col overflow-hidden">
          
          {/* Messages Container */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center max-w-md">
                  <div className="w-20 h-20 rounded-full bg-gradient-to-r from-indigo-100 to-purple-100 flex items-center justify-center mx-auto mb-4">
                    <MdChat className="text-3xl text-indigo-500" />
                  </div>
                  <h2 className="text-2xl font-bold text-gray-800 mb-2">Welcome to the Story!</h2>
                  <p className="text-gray-600">
                    Start writing your part of the story. The AI moderator will guide the narrative.
                  </p>
                  <p className="text-sm text-gray-500 mt-4">
                    Type your message below and press Enter to send.
                  </p>
                </div>
              </div>
            ) : (
              messages.map((msg, index) => {
                const isModerator = msg.sender === "Moderator";
                const isCurrentUser = msg.sender === userName;
                const userColor = !isModerator ? getUserColor(msg.sender, userName) : null;
                const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { 
                  hour: '2-digit', 
                  minute: '2-digit' 
                }) : '';

                return (
                  <div
                    key={`${msg.sender}-${index}-${msg.message.substring(0, 10)}`}
                    className={`flex items-start gap-3 ${isCurrentUser ? 'flex-row-reverse' : ''}`}
                  >
                    {/* Avatar */}
                    <div className="flex-shrink-0">
                      {isModerator ? (
                        <div className="w-10 h-10 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 flex items-center justify-center text-white">
                          <MdChat size={20} />
                        </div>
                      ) : (
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${userColor?.accent || 'bg-gray-500'}`}>
                          {msg.sender.charAt(0)}
                        </div>
                      )}
                    </div>
                    
                    {/* Message Bubble - NO TTS BUTTONS */}
                    <div className={`max-w-xl ${isCurrentUser ? 'text-right' : ''}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`font-semibold text-sm ${isModerator ? 'text-amber-700' : userColor?.text || 'text-gray-700'}`}>
                          {isCurrentUser ? 'You' : msg.sender}
                        </span>
                        <span className="text-xs text-gray-500">{timestamp}</span>
                      </div>
                      
                      <div
                        className={`rounded-2xl px-4 py-3 shadow-sm ${
                          isModerator
                            ? 'bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200'
                            : isCurrentUser
                            ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-br-none'
                            : `${userColor?.bg || 'bg-gray-100'} border ${userColor?.border || 'border-gray-200'} rounded-bl-none`
                        }`}
                      >
                        <p className="whitespace-pre-wrap break-words text-sm">
                          {msg.message}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ✍️ TEXT INPUT - PURE, NO EXTRAS */}
          <div className="border-t bg-white/90 backdrop-blur-sm p-4">
            <div className="max-w-4xl mx-auto">
              <div className="flex gap-3">
                <div className="flex-1 relative">
                  <textarea
                    rows={2}
                    value={message}
                    onChange={(e) => setMessage(e.target.value.substring(0, 1000))}
                    onKeyDown={handleKeyPress}
                    placeholder={ready ? 
                      "Write your part of the story here... (Press Enter to send, Shift+Enter for new line)" : 
                      "Connecting to room..."
                    }
                    disabled={!ready}
                    className="w-full px-4 py-3 bg-white border border-gray-300 rounded-2xl focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100 resize-none transition-all disabled:bg-gray-100 disabled:cursor-not-allowed"
                  />
                  
                  {/* Simple character counter */}
                  <div className="absolute right-3 bottom-3 text-xs text-gray-400">
                    {message.length}/1000
                  </div>
                </div>
                
                {/* Send Button */}
                <button
                  onClick={sendMessage}
                  disabled={!message.trim() || !ready}
                  className="px-6 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-xl hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 font-medium"
                >
                  <MdSend size={20} />
                  Send
                </button>
              </div>
              
              {/* Simple status line */}
              <div className="mt-2 text-xs text-gray-500 flex justify-between">
                <span>
                  {ready ? (
                    <>Connected as: <span className="font-semibold text-indigo-600">{userName}</span></>
                  ) : (
                    <>Establishing connection...</>
                  )}
                </span>
                
                {/* End Session Button */}
                <button
                  onClick={endSession}
                  disabled={isLoadingFeedback}
                  className="text-red-600 hover:text-red-800 font-medium flex items-center gap-1"
                >
                  {isLoadingFeedback ? (
                    <>
                      <div className="w-3 h-3 border-2 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                      Ending...
                    </>
                  ) : (
                    <>
                      <MdExitToApp size={14} />
                      End Session
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 👥 PARTICIPANTS SIDEBAR */}
        {showParticipants && (
          <div className="w-64 border-l bg-white/90 backdrop-blur-sm overflow-y-auto">
            <div className="p-4 border-b">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <MdPerson />
                Participants ({onlineCount})
              </h3>
            </div>
            
            <div className="p-4 space-y-3">
              {/* Always show current user */}
              <div className="flex items-center gap-3 p-2 rounded-lg bg-indigo-50 border border-indigo-100">
                <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 flex items-center justify-center text-white font-bold">
                  {userName.charAt(0)}
                </div>
                <div className="flex-1">
                  <div className="font-medium text-gray-800">
                    {userName}
                    <span className="ml-2 px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">You</span>
                  </div>
                  <div className="text-xs text-gray-500 flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
                    Online
                  </div>
                </div>
              </div>

              {/* Other participants */}
              {participants
                .filter(p => p !== userName)
                .map((participant, index) => {
                  const color = getUserColor(participant, userName);
                  return (
                    <div key={index} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition-colors">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${color.accent}`}>
                        {participant.charAt(0)}
                      </div>
                      <div className="flex-1">
                        <div className="font-medium text-gray-800">{participant}</div>
                        <div className="text-xs text-gray-500 flex items-center gap-1">
                          <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
                          Online
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
            
            <div className="p-4 border-t">
              <div className="text-xs text-gray-500 space-y-2">
                <p className="font-medium text-gray-700">Room Information</p>
                <p className="truncate">ID: <span className="font-mono">{roomId.substring(0, 8)}...</span></p>
                <p>Messages: {messages.length}</p>
                <p className="pt-2 text-indigo-600 font-medium">✨ Pure text collaboration</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}