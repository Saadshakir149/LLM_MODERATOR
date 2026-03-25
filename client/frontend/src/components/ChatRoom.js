// ============================================================
// ChatRoom.js - RESEARCH VERSION (Desert Survival Task)
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
  MdChat,
  MdDragHandle,
  MdCheckCircle,
  MdWarning
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
// 🏜️ DESERT SURVIVAL ITEMS (for ranking)
// ============================================================
const DESERT_ITEMS = [
  "A flashlight (4 battery size)",
  "A map of the region",
  "A compass",
  "A large plastic sheet",
  "A box of matches",
  "A winter coat",
  "A bottle of salt tablets (1000 tablets)",
  "A small knife",
  "2 quarts of water per person",
  "A cosmetic mirror",
  "A parachute (red & white)",
  "A book - 'Edible Animals of the Desert'"
];

// ============================================================
// 🎯 MAIN CHATROOM COMPONENT
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
  
  // ============================================================
  // 📊 RESEARCH STUDY STATE
  // ============================================================
  const [showRankingModal, setShowRankingModal] = useState(false);
  const [ranking, setRanking] = useState([]);
  const [rankingSubmitted, setRankingSubmitted] = useState(false);
  const [timeWarning, setTimeWarning] = useState(false);
  const [draggedItem, setDraggedItem] = useState(null);
  const [languageWarning, setLanguageWarning] = useState(null);
  const languageWarningTimerRef = useRef(null);

  const messagesEndRef = useRef(null);

  const dismissLanguageWarning = useCallback(() => {
    if (languageWarningTimerRef.current) {
      window.clearTimeout(languageWarningTimerRef.current);
      languageWarningTimerRef.current = null;
    }
    setLanguageWarning(null);
  }, []);

  const showLanguageWarningBanner = useCallback((text) => {
    if (languageWarningTimerRef.current) {
      window.clearTimeout(languageWarningTimerRef.current);
    }
    setLanguageWarning(text);
    languageWarningTimerRef.current = window.setTimeout(() => {
      setLanguageWarning(null);
      languageWarningTimerRef.current = null;
    }, 8000);
  }, []);

  // ============================================================
  // 🔊 LOCAL SEND SOUND
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
      console.log("📨 RECEIVED MESSAGE:", data);

      setMessages((prev) => {
        const dupIndex = prev.findIndex(
          (msg) =>
            msg.sender === data.sender &&
            msg.message === data.message &&
            Math.abs(new Date(msg.timestamp || 0) - new Date(data.timestamp || 0)) < 4000
        );

        if (dupIndex >= 0) {
          if (data.flagged) {
            const next = [...prev];
            next[dupIndex] = {
              ...next[dupIndex],
              ...data,
              timestamp: next[dupIndex].timestamp || data.timestamp,
            };
            return next;
          }
          console.log("⚠️ Duplicate message ignored");
          return prev;
        }

        const newMessage = {
          ...data,
          timestamp: data.timestamp || new Date().toISOString(),
        };

        return [...prev, newMessage];
      });
    });

    const onLanguageWarningPayload = (data) => {
      if (data?.type === "language_warning" && data.message) {
        showLanguageWarningBanner(data.message);
      }
    };
    socket.on("language_warning", onLanguageWarningPayload);
    socket.on("warning_message", onLanguageWarningPayload);

    socket.on("participants_update", (data) => {
      setParticipants(data.participants || []);
    });

    // ============================================================
    // 📊 RESEARCH STUDY SOCKET EVENTS
    // ============================================================
    socket.on("time_warning", () => {
      setTimeWarning(true);
      setShowRankingModal(true);
    });

    socket.on("ranking_submitted", (data) => {
      if (data.success) {
        setRankingSubmitted(true);
        setShowRankingModal(false);
        // Show success message in chat
        const successMsg = {
          sender: "System",
          message: "✅ Final ranking submitted successfully!",
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, successMsg]);
      } else {
        alert("❌ Failed to submit ranking: " + data.message);
      }
    });

    // Session ended handler
    socket.on("session_ended", (data) => {
      console.log("📨 Session ended with data:", data);
      const feedback = data?.feedback || "Session ended. Thank you for participating!";
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
      if (languageWarningTimerRef.current) {
        window.clearTimeout(languageWarningTimerRef.current);
        languageWarningTimerRef.current = null;
      }
      socket.off("connect");
      socket.off("disconnect");
      socket.off("connect_error");
      socket.off("joined_room");
      socket.off("chat_history");
      socket.off("receive_message");
      socket.off("participants_update");
      socket.off("time_warning");
      socket.off("ranking_submitted");
      socket.off("session_ended");
      socket.off("language_warning", onLanguageWarningPayload);
      socket.off("warning_message", onLanguageWarningPayload);
    };
  }, [roomId, userName, navigate, showLanguageWarningBanner]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ============================================================
  // 💬 SEND MESSAGE
  // ============================================================
  const sendMessage = useCallback(() => {
    const trimmed = message.trim();
    if (!trimmed || !ready) return;

    sendSound.play().catch(() => {});

    setMessages(prev => [...prev, { 
      sender: userName, 
      message: trimmed, 
      timestamp: new Date().toISOString() 
    }]);

    socket.emit("send_message", {
      room_id: roomId,
      message: trimmed,
      sender: userName,
    });

    setMessage("");
  }, [message, roomId, userName, ready, sendSound]);

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ============================================================
  // 📊 RANKING INTERFACE HANDLERS
  // ============================================================
  const handleDragStart = (e, index) => {
    setDraggedItem(index);
    e.dataTransfer.setData("text/plain", index);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e, targetIndex) => {
    e.preventDefault();
    const sourceIndex = draggedItem;
    if (sourceIndex === null || sourceIndex === targetIndex) return;

    const newRanking = [...ranking];
    const [movedItem] = newRanking.splice(sourceIndex, 1);
    newRanking.splice(targetIndex, 0, movedItem);
    setRanking(newRanking);
    setDraggedItem(null);
  };

  const startRanking = () => {
    setRanking([...DESERT_ITEMS]);
  };

  const resetRanking = () => {
    setRanking([]);
  };

  const submitRanking = () => {
    if (ranking.length !== 12) {
      alert("Please rank all 12 items");
      return;
    }

    socket.emit("submit_ranking", {
      room_id: roomId,
      ranking: ranking
    });
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
  // 📊 RANKING MODAL COMPONENT
  // ============================================================
  const RankingModal = () => (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-2xl font-bold text-gray-800">
              {timeWarning ? "⏰ Time's Running Out!" : "Final Ranking"}
            </h3>
            {timeWarning && (
              <span className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-semibold flex items-center gap-1">
                <MdWarning /> 2 minutes left
              </span>
            )}
          </div>
          
          <p className="text-gray-600 mb-4">
            Drag and drop items to rank them from 1 (most important for survival) to 12 (least important).
            Your group must agree on one final ranking.
          </p>
          
          {ranking.length === 0 ? (
            <div className="space-y-2 mb-6">
              {DESERT_ITEMS.map((item, index) => (
                <div
                  key={index}
                  className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-gray-700"
                >
                  {item}
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2 mb-6">
              {ranking.map((item, index) => (
                <div
                  key={index}
                  draggable
                  onDragStart={(e) => handleDragStart(e, index)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, index)}
                  className={`flex items-center gap-3 p-3 bg-white border-2 rounded-lg cursor-move transition-all ${
                    draggedItem === index 
                      ? 'border-indigo-500 bg-indigo-50 shadow-lg' 
                      : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
                  }`}
                >
                  <MdDragHandle className="text-gray-400 text-xl" />
                  <span className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold">
                    {index + 1}
                  </span>
                  <span className="font-medium text-gray-700 flex-1">{item}</span>
                </div>
              ))}
            </div>
          )}
          
          <div className="flex gap-3 mt-6 pt-4 border-t border-gray-200">
            {ranking.length === 0 ? (
              <button
                onClick={startRanking}
                className="flex-1 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors font-medium"
              >
                Start Ranking
              </button>
            ) : (
              <>
                <button
                  onClick={resetRanking}
                  className="flex-1 py-3 border-2 border-gray-300 text-gray-700 rounded-xl hover:bg-gray-50 transition-colors font-medium"
                >
                  Reset
                </button>
                <button
                  onClick={submitRanking}
                  disabled={rankingSubmitted}
                  className="flex-1 py-3 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {rankingSubmitted ? (
                    <>Submitted <MdCheckCircle /></>
                  ) : (
                    'Submit Ranking'
                  )}
                </button>
              </>
            )}
          </div>
          
          {ranking.length === 12 && (
            <p className="text-xs text-gray-500 mt-3 text-center">
              Drag items to reorder. Click Submit when your group agrees.
            </p>
          )}
        </div>
      </div>
    </div>
  );

  // Calculate online count
  const onlineCount = Math.max(participants.length, 1);

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      {languageWarning && (
        <div
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] max-w-lg w-[calc(100%-2rem)] rounded-xl border-l-4 border-amber-500 border border-amber-200 bg-amber-50 px-4 py-3 shadow-lg animate-pulse"
          role="alert"
        >
          <div className="flex items-start gap-3">
            <MdWarning className="text-amber-600 flex-shrink-0 mt-0.5" size={22} />
            <p className="text-sm text-amber-800 flex-1 pr-1">{languageWarning}</p>
            <button
              type="button"
              onClick={dismissLanguageWarning}
              className="flex-shrink-0 text-amber-600 hover:text-amber-900 text-lg leading-none px-1"
              aria-label="Dismiss warning"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* 🎪 HEADER */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <MdChat className="text-xl" />
            </div>
            <div>
              <h1 className="font-bold text-lg">Desert Survival Task</h1>
              <div className="flex items-center gap-2 text-sm opacity-90">
                <span className="font-mono">Room: {roomId.substring(0, 8)}...</span>
                
                <span className="px-2 py-0.5 bg-green-500/30 rounded-full text-xs flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-green-300 rounded-full"></span>
                  {onlineCount}/3 online
                </span>

                {timeWarning && (
                  <span className="px-2 py-0.5 bg-red-500/30 rounded-full text-xs animate-pulse">
                    ⏰ 2 min left
                  </span>
                )}

                {connectionStatus === "disconnected" && (
                  <span className="px-2 py-0.5 bg-red-500/30 rounded-full text-xs">
                    Disconnected
                  </span>
                )}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
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

      {/* 📱 MAIN CONTENT */}
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
                  <h2 className="text-2xl font-bold text-gray-800 mb-2">Desert Survival Task</h2>
                  <p className="text-gray-600 mb-4">
                    Your group must rank 12 items in order of importance for survival.
                    Discuss with your teammates and reach a consensus.
                  </p>
                  <p className="text-sm text-gray-500">
                    You have 15 minutes. A ranking interface will appear when time is running out.
                  </p>
                </div>
              </div>
            ) : (
              messages.map((msg, index) => {
                const isModerator = msg.sender === "Moderator";
                const isSystem = msg.sender === "System";
                const isFlagged = Boolean(msg.flagged);
                const isCurrentUser = msg.sender === userName;
                const userColor = !isModerator && !isSystem ? getUserColor(msg.sender, userName) : null;
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
                      ) : isSystem ? (
                        <div className="w-10 h-10 rounded-full bg-gray-500 flex items-center justify-center text-white">
                          <MdCheckCircle size={20} />
                        </div>
                      ) : (
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${userColor?.accent || 'bg-gray-500'}`}>
                          {msg.sender.charAt(0)}
                        </div>
                      )}
                    </div>
                    
                    {/* Message Bubble */}
                    <div className={`max-w-xl ${isCurrentUser ? 'text-right' : ''}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`font-semibold text-sm ${
                          isModerator ? 'text-amber-700' : 
                          isSystem ? 'text-gray-600' :
                          userColor?.text || 'text-gray-700'
                        }`}>
                          {isCurrentUser ? 'You' : msg.sender}
                        </span>
                        <span className="text-xs text-gray-500">{timestamp}</span>
                        {isFlagged && !isModerator && !isSystem && (
                          <span className="text-xs text-amber-600 flex items-center gap-0.5">
                            <MdWarning className="inline" size={12} />
                            Flagged
                          </span>
                        )}
                      </div>
                      
                      <div
                        className={`rounded-2xl px-4 py-3 shadow-sm ${
                          isModerator
                            ? 'bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200'
                            : isSystem
                            ? 'bg-gray-100 border border-gray-200 text-gray-600'
                            : isCurrentUser
                            ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-br-none'
                            : `${userColor?.bg || 'bg-gray-100'} border ${userColor?.border || 'border-gray-200'} rounded-bl-none`
                        } ${isFlagged && !isModerator && !isSystem ? 'ring-2 ring-amber-400/80 border-amber-300' : ''}`}
                      >
                        {isFlagged && !isModerator && !isSystem && (
                          <p
                            className={`text-xs font-medium mb-1 flex items-center gap-1 ${
                              isCurrentUser ? "text-amber-100" : "text-amber-800"
                            }`}
                          >
                            <MdWarning className="inline" size={14} />
                            Flagged for review
                          </p>
                        )}
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

          {/* ✍️ TEXT INPUT */}
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
                      "Discuss the items with your group... (Press Enter to send)" : 
                      "Connecting to room..."
                    }
                    disabled={!ready}
                    className="w-full px-4 py-3 bg-white border border-gray-300 rounded-2xl focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100 resize-none transition-all disabled:bg-gray-100 disabled:cursor-not-allowed"
                  />
                  <div className="absolute right-3 bottom-3 text-xs text-gray-400">
                    {message.length}/1000
                  </div>
                </div>
                
                <button
                  onClick={sendMessage}
                  disabled={!message.trim() || !ready}
                  className="px-6 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-xl hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 font-medium"
                >
                  <MdSend size={20} />
                  Send
                </button>
              </div>
              
              <div className="mt-2 text-xs text-gray-500 flex justify-between">
                <span>
                  {ready ? (
                    <>Connected as: <span className="font-semibold text-indigo-600">{userName}</span></>
                  ) : (
                    <>Establishing connection...</>
                  )}
                </span>
                
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
                Participants ({onlineCount}/3)
              </h3>
            </div>
            
            <div className="p-4 space-y-3">
              {/* Current user */}
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
              
              {/* Waiting for participants */}
              {participants.length < 3 && (
                <div className="text-center py-4 text-gray-500 text-sm border-t border-gray-100">
                  Waiting for {3 - participants.length} more participant(s)...
                </div>
              )}
            </div>
            
            <div className="p-4 border-t">
              <div className="text-xs text-gray-500 space-y-2">
                <p className="font-medium text-gray-700">Room Information</p>
                <p className="truncate">ID: <span className="font-mono">{roomId.substring(0, 8)}...</span></p>
                <p>Messages: {messages.length}</p>
                <p className="pt-2 text-indigo-600 font-medium">🏜️ Desert Survival Task</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 📊 RANKING MODAL */}
      {showRankingModal && !rankingSubmitted && <RankingModal />}
    </div>
  );
}