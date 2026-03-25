from __future__ import annotations
import os
import sys

# Eventlet monkey-patching breaks on Python 3.12+ (ssl.wrap_socket removed). Default to threading there.
_socketio_async_mode = os.getenv("SOCKETIO_ASYNC_MODE", "").strip().lower()
if _socketio_async_mode not in ("eventlet", "threading"):
    _socketio_async_mode = (
        "threading" if sys.version_info >= (3, 12) else "eventlet"
    )

if _socketio_async_mode == "eventlet":
    import eventlet

    eventlet.monkey_patch()

# Windows consoles often default to cp1252; keep emoji log lines from crashing stderr.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# LLM Moderator Server with Supabase Integration - RESEARCH VERSION
# WITH DESERT SURVIVAL TASK AND ACTIVE/PASSIVE MODERATION
# Following exact experiment design specifications
# ============================================================

import uuid
import logging
import time
import threading
import json
import csv
import random
import traceback  # Add this line
from io import BytesIO, StringIO
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from flask import Flask, request, send_file, jsonify, make_response
from flask_socketio import SocketIO, join_room, emit
from flask_cors import CORS
from dotenv import load_dotenv

# Optional audio support
try:
    from pydub import AudioSegment
    AUDIO_SUPPORT = True
except ImportError:
    AUDIO_SUPPORT = False

# ============================================================
# Import Supabase Client
# ============================================================
from supabase_client import (
    get_or_create_room,
    get_room,
    update_room_status,
    update_room_participant_count,
    add_participant,
    get_participants,
    get_participant_by_socket,
    get_participant_by_username,
    get_next_participant_name,
    add_message,
    get_chat_history,
    create_session,
    end_session,
    supabase,
    create_room as supabase_create_room,
    analyze_student_behavior,
    save_room_metrics,
    log_moderator_intervention,
    analyze_conflict_episodes
)

# ============================================================
# Import Research Metrics
# ============================================================
from research_metrics import (
    calculate_gini_coefficient,
    analyze_participation,
    detect_conflict_episodes,
)

# ============================================================
# Import Task System (Desert Survival)
# ============================================================
from data_retriever import (
    get_data,
    format_story_block,
    get_story_intro,
    get_task_items,
    compare_with_expert_ranking
)

# ============================================================
# Import Prompt Functions
# ============================================================
from prompts import (
    generate_active_moderator_response,
    generate_passive_moderator_response,
    generate_personalized_feedback,
    get_random_ending,
    check_inappropriate_language,
    get_language_severity,
    get_fallback_feedback,
)

# ============================================================
# Logger Setup
# ============================================================
DEBUG_LOG_FILE = "server_debug.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(DEBUG_LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("LLM_MODERATOR")
logger.info("="*60)
logger.info("🚀 LLM Moderator Research Server Starting")
logger.info("="*60)

# ============================================================
# FFmpeg Configuration (for TTS/STT)
# ============================================================
if AUDIO_SUPPORT:
    try:
        ffmpeg_dir = r"C:\Users\shaima\AppData\Local\ffmpegio\ffmpeg-downloader\ffmpeg\bin"
        if os.path.exists(ffmpeg_dir):
            os.environ["PATH"] += os.pathsep + ffmpeg_dir
            AudioSegment.converter = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            AudioSegment.ffprobe = os.path.join(ffmpeg_dir, "ffprobe.exe")
            logger.info("✅ FFmpeg configured")
    except Exception as e:
        logger.warning(f"⚠️ FFmpeg not configured: {e}")
else:
    logger.warning("⚠️ Audio support disabled (pydub not available)")

# ============================================================
# App Setup
# ============================================================
load_dotenv()

# Get frontend URL first (needed for CORS)
# Override with http://localhost:3000 when running the React app locally.
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://llm-moderator-39gf.vercel.app",
).strip()
if FRONTEND_URL.endswith('/'):
    FRONTEND_URL = FRONTEND_URL[:-1]
allowed_origins = "*"

logger.info(f"🔒 CORS allowed origins: {allowed_origins}")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=_socketio_async_mode,
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)
@socketio.on('connect')
def handle_connect():
    logger.info(f"🔌 SOCKET CONNECTED: {request.sid} from origin: {request.headers.get('Origin', 'Unknown')}")
    emit('connected', {'data': 'Connected successfully'})

@socketio.on('connect_error')
def handle_connect_error(error):
    logger.error(f"❌ SOCKET CONNECT ERROR: {error}")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"🔌 SOCKET DISCONNECTED: {request.sid}")
# Add after your socketio initialization
@socketio.on('ping')
def handle_ping(data):
    """Respond to client pings to keep connection alive"""
    emit('pong', {'timestamp': data.get('timestamp', 0)})

# Add this middleware to keep responses alive
@app.after_request
def add_keep_alive_headers(response):
    response.headers.add('Connection', 'keep-alive')
    response.headers.add('Keep-Alive', 'timeout=60, max=1000')
    return response
# ============================================================
# Room State Management
# ============================================================
active_monitors: Dict[str, threading.Thread] = {}
room_sessions: Dict[str, str] = {}  # room_id -> session_id
research_timers: Dict[str, threading.Thread] = {}  # room_id -> timer thread

# ============================================================
# Groq Client Setup
# ============================================================
groq_client = None
openai_client = None

# Try to initialize OpenAI first
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_api_key)
        logger.info("✅ OpenAI client initialized")
    else:
        logger.warning("⚠️ OPENAI_API_KEY not found")
except ImportError:
    logger.warning("⚠️ openai package not installed")
except Exception as e:
    logger.error(f"❌ Error initializing OpenAI client: {e}")

# Try Groq as fallback
try:
    from groq import Groq
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        groq_client = Groq(api_key=groq_api_key)
        logger.info("✅ Groq client initialized as fallback")
    else:
        logger.warning("⚠️ GROQ_API_KEY not found")
except ImportError:
    logger.warning("⚠️ groq package not installed")
except Exception as e:
    logger.error(f"❌ Error initializing Groq client: {e}")

# ============================================================
# Register Admin API Blueprint
# ============================================================
from admin_api import admin_bp, get_setting_value

app.register_blueprint(admin_bp)
logger.info("✅ Admin API registered at /admin")

# ============================================================
# Configuration - Load from Database
# ============================================================
logger.info("📝 Loading configuration from database...")

WELCOME_MESSAGE = get_setting_value("WELCOME_MESSAGE", "Welcome everyone! I'm the Moderator.")
LLM_PROVIDER = get_setting_value("LLM_PROVIDER", "groq")
GROQ_MODEL = get_setting_value("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TEMPERATURE = get_setting_value("GROQ_TEMPERATURE", 0.7)
GROQ_MAX_TOKENS = get_setting_value("GROQ_MAX_TOKENS", 2000)

# Research settings - FROM YOUR EXPERIMENT DESIGN
SILENCE_THRESHOLD_SECONDS = 180  # 3 minutes - if someone hasn't spoken for 3 minutes, invite them
DOMINANCE_THRESHOLD = 0.5  # 50% of recent messages - if one person contributes >50%, balance
TIME_WARNING_MINUTES = 5  # Warn when 5 minutes remaining

logger.info(f"📝 Config: LLM Provider={LLM_PROVIDER}, Model={GROQ_MODEL}")
logger.info(f"📝 Research Settings: Silence={SILENCE_THRESHOLD_SECONDS}s, Dominance Threshold={DOMINANCE_THRESHOLD*100}%")
logger.info(f"📝 Frontend URL: {FRONTEND_URL}")

# ============================================================
# Export Data Endpoints
# ============================================================

@app.route("/admin/rooms/<room_id>/export/messages", methods=["GET"])
def export_room_messages(room_id: str):
    """Export room messages in JSON, CSV, or TSV format"""
    try:
        format_type = request.args.get('format', 'json').lower()
        
        # Get messages from database
        messages_response = supabase.table('messages').select('*').eq('room_id', room_id).order('created_at').execute()
        messages = messages_response.data if messages_response.data else []
        
        if not messages:
            return jsonify({"error": "No messages found"}), 404
        
        # Get room info for filename
        room_response = supabase.table('rooms').select('id, created_at').eq('id', room_id).single().execute()
        room = room_response.data if room_response.data else {}
        
        # Format based on requested type
        if format_type == 'json':
            return jsonify({
                "room_id": room_id,
                "exported_at": datetime.now().isoformat(),
                "message_count": len(messages),
                "messages": messages
            })
        
        elif format_type == 'csv':
            output = StringIO()
            if messages:
                all_keys = set()
                for msg in messages:
                    all_keys.update(msg.keys())
                fieldnames = sorted(all_keys)
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(messages)
            
            csv_data = output.getvalue()
            output.close()
            
            response = make_response(csv_data)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=room_{room_id}_messages_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
        
        elif format_type == 'tsv':
            output = StringIO()
            if messages:
                all_keys = set()
                for msg in messages:
                    all_keys.update(msg.keys())
                fieldnames = sorted(all_keys)
                writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(messages)
            
            tsv_data = output.getvalue()
            output.close()
            
            response = make_response(tsv_data)
            response.headers['Content-Type'] = 'text/tab-separated-values'
            response.headers['Content-Disposition'] = f'attachment; filename=room_{room_id}_messages_{datetime.now().strftime("%Y%m%d_%H%M%S")}.tsv'
            return response
        
        else:
            return jsonify({"error": f"Unsupported format: {format_type}. Use json, csv, or tsv"}), 400
    
    except Exception as e:
        logger.error(f"❌ Error exporting messages: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/rooms/<room_id>/export/full", methods=["GET"])
def export_room_full(room_id: str):
    """Export complete room data including participants and sessions"""
    try:
        format_type = request.args.get('format', 'json').lower()
        
        # Get all room data
        room_response = supabase.table('rooms').select('*').eq('id', room_id).single().execute()
        room = room_response.data if room_response.data else {}
        
        participants_response = supabase.table('participants').select('*').eq('room_id', room_id).order('joined_at').execute()
        participants = participants_response.data if participants_response.data else []
        
        messages_response = supabase.table('messages').select('*').eq('room_id', room_id).order('created_at').execute()
        messages = messages_response.data if messages_response.data else []
        
        sessions_response = supabase.table('sessions').select('*').eq('room_id', room_id).execute()
        sessions = sessions_response.data if sessions_response.data else []
        
        data = {
            "room": room,
            "participants": participants,
            "messages": messages,
            "sessions": sessions,
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "room_id": room_id,
                "total_participants": len(participants),
                "total_messages": len(messages),
                "total_sessions": len(sessions)
            }
        }
        
        if format_type == 'json':
            return jsonify(data)
        
        elif format_type == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Room ID', 'Room Status', 'Room Mode', 'Created At', 
                           'Participant Count', 'Message Count', 'Session Count'])
            writer.writerow([
                room.get('id', ''),
                room.get('status', ''),
                room.get('mode', ''),
                room.get('created_at', ''),
                len(participants),
                len(messages),
                len(sessions)
            ])
            
            csv_data = output.getvalue()
            output.close()
            
            response = make_response(csv_data)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=room_{room_id}_full_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
        
        else:
            return jsonify({"error": f"Unsupported format: {format_type}"}), 400
    
    except Exception as e:
        logger.error(f"❌ Error exporting full room data: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# Helper: Get Room Task Data
# ============================================================
def get_room_task_data(room_id: str) -> Optional[Dict[str, Any]]:
    """Load task data for room (always desert survival)"""
    room = get_room(room_id)
    if not room:
        logger.warning(f"⚠️ No room found {room_id}")
        return None

    return get_data()  # Always returns desert survival task

# ============================================================
# RESEARCH TIMER - 15 Minute Session Timer
# ============================================================
def start_research_timer(room_id: str):
    """15-minute timer with warnings for research sessions"""
    
    def timer_loop():
        # Wait 10 minutes (5 minutes remaining warning)
        time.sleep(10 * 60)
        
        room = get_room(room_id)
        if room and room['status'] == 'active':
            # 5 minutes remaining warning - FROM YOUR DESIGN
            warning_msg = "⚠️ **5 minutes remaining!** Please work towards your final ranking. Can you agree on your top 3 items?"
            add_message(
                room_id=room_id,
                username="Moderator",
                message=warning_msg,
                message_type="system"
            )
            
            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": warning_msg},
                room=room_id,
            )
            
            # Wait 4 more minutes
            time.sleep(4 * 60)
            
            # 1 minute remaining
            final_warning = "⏰ **1 minute remaining!** Please submit your final ranking now."
            add_message(
                room_id=room_id,
                username="Moderator",
                message=final_warning,
                message_type="system"
            )
            
            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": final_warning},
                room=room_id,
            )
            
            # Give 1 more minute for submission
            time.sleep(60)
            
            # Auto-end session if not already ended
            room = get_room(room_id)
            if room and room['status'] == 'active':
                handle_end_session({"room_id": room_id, "sender": "system"})
    
    thread = threading.Thread(target=timer_loop, daemon=True)
    thread.start()
    research_timers[room_id] = thread
    logger.info(f"⏰ Research timer started for room {room_id} (15 minutes)")

# ============================================================
# Helper: Start Task
# ============================================================
def start_task_for_room(room_id: str):
    """Start desert survival task for a room when conditions are met"""
    try:
        room = get_room(room_id)
        if not room:
            logger.error(f"❌ Room {room_id} not found")
            return

        participants = get_participants(room_id)
        student_count = len(participants)

        logger.info(f"📊 Room {room_id}: {student_count} students, status={room['status']}")

        # RESEARCH: Only start when EXACTLY 3 participants
        if room['status'] == 'active':
            logger.info(f"ℹ️ Room {room_id} already active")
            return
        elif room['status'] == 'completed':
            logger.info(f"ℹ️ Room {room_id} already completed")
            return

        # RESEARCH: Wait for exactly 3 participants
        if student_count < 3:
            logger.info(f"ℹ️ Room {room_id} waiting for 3 participants (current: {student_count})")
            return

        logger.info(f"🎬 Starting desert survival task for room {room_id} with {student_count} students")

        # Update room status
        update_room_status(room_id, 'active')

        # Create session
        session = create_session(
            room_id=room_id,
            mode=room['mode'],
            participant_count=student_count,
            story_id=room.get('story_id', 'desert_survival')
        )
        room_sessions[room_id] = session['id']

        # Send task intro
        task_data = get_room_task_data(room_id)
        if task_data:
            intro = get_story_intro(task_data)
            logger.info(f"📋 Sending task intro to room {room_id}")

            add_message(
                room_id=room_id,
                username="Moderator",
                message=intro,
                message_type="task"
            )

            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": intro},
                room=room_id,
            )

            # Start research timer
            start_research_timer(room_id)

            # Start appropriate moderator based on condition
            if room['mode'] == 'passive':
                logger.info(f"🔴 Starting PASSIVE moderator for room {room_id}")
                start_passive_moderator(room_id)
            else:  # active mode
                logger.info(f"🟢 Starting ACTIVE moderator for room {room_id}")
                start_active_moderator(room_id)
        else:
            logger.error(f"❌ No task data found for room {room_id}")

    except Exception as e:
        logger.error(f"❌ Error starting task for room {room_id}: {e}", exc_info=True)

# ============================================================
# ACTIVE MODERATOR - Complete Implementation
# ============================================================
def start_active_moderator(room_id: str):
    """Active moderator with proactive guidance as per experiment design"""
    
    def monitor_loop():
        logger.info(f"🟢 ACTIVE moderator started for room {room_id}")
        
        last_intervention_time = time.time()
        last_dominance_check = time.time()
        last_silence_check = time.time()
        
        # Track if we've already invited each participant
        invited_users = set()
        # Track last time we sent a dominance message for each user
        last_dominance_message = {}
        
        while True:
            try:
                time.sleep(5)  # Check every 5 seconds
                
                room = get_room(room_id)
                if not room or room.get('story_finished') or room['status'] == 'completed':
                    logger.info(f"⏹️ Active moderator stopped for room {room_id}")
                    break
                
                now = time.time()
                
                # Parse created_at timestamp safely
                time_elapsed = 0
                created_at_val = room.get('created_at')
                
                if created_at_val:
                    try:
                        if isinstance(created_at_val, str):
                            created_at_val = created_at_val.replace('Z', '+00:00')
                            created_at_dt = datetime.fromisoformat(created_at_val)
                            time_elapsed = int((now - created_at_dt.timestamp()) / 60)
                        elif isinstance(created_at_val, (int, float)):
                            time_elapsed = int((now - float(created_at_val)) / 60)
                    except:
                        time_elapsed = 0
                
                time_elapsed = max(0, time_elapsed)
                time_remaining = max(0, 15 - time_elapsed)
                
                # Get recent messages for analysis
                messages = get_chat_history(room_id, limit=50)
                
                # Get actual participants (excluding Moderator)
                all_participants = get_participants(room_id)
                participant_names = [p['username'] for p in all_participants if p['username'] != 'Moderator']
                
                # If less than 3 participants, skip (shouldn't happen but just in case)
                if len(participant_names) < 3:
                    continue
                
                # ===== ACTIVE MODERATOR RULES =====
                
                # RULE 1: Check for dominance (>50% of recent messages)
                if now - last_dominance_check > 30:  # Check every 30 seconds
                    dominant_user = check_dominance(room_id)
                    
                    # Only trigger if:
                    # 1. A dominant user is detected
                    # 2. We haven't intervened in the last 60 seconds (cooldown)
                    # 3. The dominant user is actually in the room
                    # 4. We haven't sent a dominance message to this user in the last 2 minutes
                    if (dominant_user and 
                        dominant_user in participant_names and 
                        (now - last_intervention_time > 60) and
                        (dominant_user not in last_dominance_message or now - last_dominance_message.get(dominant_user, 0) > 120)):
                        
                        logger.info(f"👑 Dominance detected: {dominant_user}")
                        
                        # Get other participants (excluding the dominant one)
                        others = [p for p in participant_names if p != dominant_user]
                        
                        # Use LLM to generate a balanced response
                        if len(others) >= 1:
                            # Let the LLM generate a natural response
                            response = generate_active_moderator_response(
                                participants=participant_names,
                                chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                                task_context="Desert survival ranking",
                                time_elapsed=time_elapsed,
                                last_intervention_time=int(now - last_intervention_time),
                                dominance_detected=dominant_user,
                                silent_user=None
                            )
                            
                            # If LLM fails, use fallback
                            if not response or len(response) < 10:
                                if len(others) >= 2:
                                    response = f"{dominant_user}, thanks for your input. Let's also hear from {others[0]} and {others[1]} - what are your thoughts on the item ranking?"
                                else:
                                    response = f"{dominant_user}, good points. {others[0]}, what do you think about this?"
                            
                            add_message(room_id, "Moderator", response, "moderator")
                            socketio.emit("receive_message", 
                                        {"sender": "Moderator", "message": response},
                                        room=room_id)
                            
                            # Log intervention for research
                            log_moderator_intervention(room_id, "balance_dominance", dominant_user)
                            last_intervention_time = now
                            last_dominance_message[dominant_user] = now
                            
                            logger.info(f"✅ Sent dominance balance message for {dominant_user}")
                    
                    last_dominance_check = now
                
                # RULE 2: Check for silence (3 minutes) - invite quieter members
                if now - last_silence_check > 30:  # Check every 30 seconds
                    silent_user = check_silence(room_id)
                    
                    # Only trigger if:
                    # 1. A silent user is detected
                    # 2. We haven't intervened in the last 60 seconds (cooldown)
                    # 3. The silent user hasn't been invited recently
                    if (silent_user and 
                        silent_user in participant_names and 
                        (now - last_intervention_time > 60) and
                        silent_user not in invited_users):
                        
                        logger.info(f"🤫 Silence detected: {silent_user}")
                        
                        # Use LLM to generate an invitation
                        response = generate_active_moderator_response(
                            participants=participant_names,
                            chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                            task_context="Desert survival ranking",
                            time_elapsed=time_elapsed,
                            last_intervention_time=int(now - last_intervention_time),
                            dominance_detected=None,
                            silent_user=silent_user
                        )
                        
                        # Fallback if LLM fails
                        if not response or len(response) < 10:
                            response = f"{silent_user}, we haven't heard from you yet. What do you think about the desert survival items? Which one would you prioritize?"
                        
                        add_message(room_id, "Moderator", response, "moderator")
                        socketio.emit("receive_message",
                                    {"sender": "Moderator", "message": response},
                                    room=room_id)
                        
                        log_moderator_intervention(room_id, "invite_silent", silent_user)
                        invited_users.add(silent_user)
                        last_intervention_time = now
                        
                        logger.info(f"✅ Sent invitation to {silent_user}")
                    
                    last_silence_check = now
                
                # RULE 3: Time-based prompts (last 5 minutes)
                if time_remaining <= 5 and time_remaining > 4 and now - last_intervention_time > 60:
                    # Use LLM for time warning
                    response = generate_active_moderator_response(
                        participants=participant_names,
                        chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                        task_context="Desert survival ranking",
                        time_elapsed=time_elapsed,
                        last_intervention_time=int(now - last_intervention_time),
                        dominance_detected=None,
                        silent_user=None
                    )
                    
                    # Fallback
                    if not response or len(response) < 10:
                        response = f"⚠️ We have {time_remaining} minutes remaining. Can you agree on your top 3 most important items?"
                    
                    add_message(room_id, "Moderator", response, "moderator")
                    socketio.emit("receive_message",
                                {"sender": "Moderator", "message": response},
                                room=room_id)
                    
                    log_moderator_intervention(room_id, "time_warning", None)
                    last_intervention_time = now
                    logger.info(f"✅ Sent time warning: {time_remaining} minutes remaining")
                
                # RULE 4: Answer questions about the task
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    if last_msg.get('username') != 'Moderator':
                        msg_content = last_msg.get('message', '').lower()
                        
                        # Check if it's a question (contains ? or question words)
                        is_question = False
                        if '?' in msg_content:
                            is_question = True
                        else:
                            question_words = ['what', 'how', 'why', 'when', 'where', 'which', 'who', 
                                             'explain', 'help', 'confused', 'not sure', 'do we', 'should we',
                                             'can you', 'could you', 'would you', 'tell me']
                            for word in question_words:
                                if word in msg_content:
                                    is_question = True
                                    break
                        
                        # Also check for question phrases
                        question_phrases = ['what to do', 'what next', 'how to', 'what is', 'what are',
                                           'what should', 'how do', 'can you help', 'need help']
                        for phrase in question_phrases:
                            if phrase in msg_content:
                                is_question = True
                                break
                        
                        if is_question and (now - last_intervention_time > 30):
                            logger.info(f"❓ Question detected from {last_msg.get('username')}: {msg_content[:100]}...")
                            
                            # Generate response using LLM
                            response = generate_active_moderator_response(
                                participants=participant_names,
                                chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                                task_context="Desert survival ranking",
                                time_elapsed=time_elapsed,
                                last_intervention_time=int(now - last_intervention_time),
                                dominance_detected=None,
                                silent_user=None
                            )
                            
                            # Only send if we got a valid response (not fallback)
                            if response and len(response) > 10 and "Thanks for sharing" not in response:
                                add_message(room_id, "Moderator", response, "moderator")
                                socketio.emit("receive_message", 
                                            {"sender": "Moderator", "message": response},
                                            room=room_id)
                                
                                log_moderator_intervention(room_id, "answered_question", last_msg.get('username'))
                                last_intervention_time = now
                                logger.info(f"✅ Answered question from {last_msg.get('username')}: {response[:100]}...")
                            else:
                                # Fallback answer based on question type
                                fallback = "Your task is to rank the 12 desert survival items from most important (1) to least important (12). Discuss with your group and agree on a final ranking. You have 15 minutes total."
                                
                                # Customize fallback based on question content
                                if 'time' in msg_content or 'minute' in msg_content:
                                    fallback = f"You have about {time_remaining} minutes remaining to complete the ranking task."
                                elif 'item' in msg_content or 'rank' in msg_content:
                                    fallback = "You need to rank the 12 items from most important (1) to least important (12) for desert survival. Discuss with your group and reach consensus."
                                
                                add_message(room_id, "Moderator", fallback, "moderator")
                                socketio.emit("receive_message", 
                                            {"sender": "Moderator", "message": fallback},
                                            room=room_id)
                                
                                log_moderator_intervention(room_id, "answered_question_fallback", last_msg.get('username'))
                                last_intervention_time = now
                                logger.info(f"✅ Sent fallback answer to {last_msg.get('username')}")
                
                # RULE 5: Periodic summaries (every 5 minutes)
                if time_elapsed > 0 and time_elapsed % 5 == 0 and now - last_intervention_time > 60:
                    # Use LLM for summary
                    response = generate_active_moderator_response(
                        participants=participant_names,
                        chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                        task_context="Desert survival ranking",
                        time_elapsed=time_elapsed,
                        last_intervention_time=int(now - last_intervention_time),
                        dominance_detected=None,
                        silent_user=None
                    )
                    
                    # Fallback
                    if not response or len(response) < 10:
                        msg_count = len([m for m in messages if m.get('username') != 'Moderator'])
                        response = f"📊 {time_elapsed} minutes have passed. You've sent {msg_count} messages. Keep discussing to reach consensus on the item ranking."
                    
                    add_message(room_id, "Moderator", response, "moderator")
                    socketio.emit("receive_message",
                                {"sender": "Moderator", "message": response},
                                room=room_id)
                    
                    log_moderator_intervention(room_id, "summary", None)
                    last_intervention_time = now
                    logger.info(f"✅ Sent summary at {time_elapsed} minutes")
                
            except Exception as e:
                logger.error(f"❌ Error in active moderator loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(5)
    
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    active_monitors[room_id] = thread
    logger.info(f"✅ ACTIVE moderator thread started for room {room_id}")
    return thread

# ============================================================
# PASSIVE MODERATOR - FIXED VERSION
# ============================================================
def start_passive_moderator(room_id: str):
    """Passive moderator - only responds when asked, minimal interventions"""
    
    def monitor_loop():
        logger.info(f"🔴 PASSIVE moderator started for room {room_id}")
        
        last_response_time = time.time()
        
        while True:
            try:
                time.sleep(3)  # Check frequently for messages directed at moderator
                
                room = get_room(room_id)
                if not room or room.get('story_finished') or room['status'] == 'completed':
                    logger.info(f"⏹️ Passive moderator stopped for room {room_id}")
                    break
                
                now = time.time()
                
                # ===== SAFE TIME CALCULATION =====
                time_elapsed = 0
                created_at_val = room.get('created_at')
                
                if created_at_val:
                    try:
                        if isinstance(created_at_val, str):
                            created_at_val = created_at_val.replace('Z', '+00:00')
                            created_at_dt = datetime.fromisoformat(created_at_val)
                            time_elapsed = int((now - created_at_dt.timestamp()) / 60)
                        elif isinstance(created_at_val, (int, float)):
                            time_elapsed = int((now - float(created_at_val)) / 60)
                    except Exception as e:
                        logger.warning(f"Could not parse created_at: {e}")
                        time_elapsed = 0
                
                time_elapsed = max(0, time_elapsed)
                time_remaining = max(0, 15 - time_elapsed)
                time_remaining_int = int(time_remaining)
                
                # Check if anyone asked the moderator
                messages = get_chat_history(room_id, limit=10)
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    
                    # Only respond if message is directed at moderator
                    if last_msg.get('username') != 'Moderator':
                        msg_text = last_msg.get('message', '').lower()
                        full_msg = last_msg.get('message', '')
                        
                        # ===== FIXED: Better moderator detection =====
                        asked_moderator = False
                        
                        # Check for @moderator (most explicit)
                        if '@moderator' in msg_text:
                            asked_moderator = True
                            logger.info(f"   ✓ @moderator detected")
                        
                        # Check for "moderator" with question mark
                        elif 'moderator' in msg_text and '?' in full_msg:
                            asked_moderator = True
                            logger.info(f"   ✓ 'moderator' with ? detected")
                        
                        # Check for common question phrases
                        elif any(phrase in msg_text for phrase in [
                            'what do you think', 'your opinion', 'help us', 
                            'can you help', 'what should we', 'tell us'
                        ]):
                            asked_moderator = True
                            logger.info(f"   ✓ question phrase detected")
                        
                        if asked_moderator and (now - last_response_time > 10):
                            logger.info(f"🗣️ Moderator asked directly in room {room_id} by {last_msg.get('username')}")
                            
                            # Get actual participants
                            all_participants = get_participants(room_id)
                            participant_names = [p['username'] for p in all_participants if p['username'] != 'Moderator']
                            
                            # Generate passive response using the dedicated function
                            response = generate_passive_moderator_response(
                                participants=participant_names,
                                chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                                last_user_message=full_msg,
                                time_elapsed=time_elapsed
                            )
                            
                            # Fallback if no response
                            if not response:
                                if 'time' in msg_text or 'minute' in msg_text:
                                    response = f"You have about {time_remaining_int} minutes remaining."
                                elif 'rank' in msg_text or 'item' in msg_text or 'task' in msg_text:
                                    response = "You need to rank the 12 desert survival items from most important (1) to least important (12)."
                                else:
                                    response = "I'm observing the discussion. Continue with your task."
                            
                            add_message(room_id, "Moderator", response, "moderator")
                            socketio.emit("receive_message",
                                        {"sender": "Moderator", "message": response},
                                        room=room_id)
                            
                            log_moderator_intervention(room_id, "responded_to_question", last_msg.get('username'))
                            last_response_time = now
                            logger.info(f"✅ Responded to question from {last_msg.get('username')}: {response[:100]}...")
                
                # ONLY time reminder near the end (5 minutes remaining) - same as active for fairness
                if time_remaining_int == 5 and (now - last_response_time > 60):
                    warning_msg = "⚠️ **5 minutes remaining!** Please work towards your final ranking."
                    add_message(
                        room_id=room_id,
                        username="Moderator",
                        message=warning_msg,
                        message_type="system"
                    )
                    
                    socketio.emit(
                        "receive_message",
                        {"sender": "Moderator", "message": warning_msg},
                        room=room_id,
                    )
                    
                    log_moderator_intervention(room_id, "time_warning", None)
                    last_response_time = now
                    logger.info(f"✅ Sent time warning at 5 minutes")
                
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Error in passive moderator loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(5)
    
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    active_monitors[room_id] = thread
    logger.info(f"✅ PASSIVE moderator thread started for room {room_id}")
    return thread

# ============================================================
# Helper Functions for Research
# ============================================================
def check_dominance(room_id: str) -> Optional[str]:
    """Check if any participant is dominating (>50% of recent messages)"""
    messages = get_chat_history(room_id, limit=20)
    
    if len(messages) < 8:  # Need at least 8 messages to detect dominance
        return None
    
    # Count messages in last 3 minutes
    now = time.time()
    cutoff = now - 180  # 3 minutes
    
    recent_counts = {}
    for msg in messages:
        if msg['username'] == 'Moderator':
            continue
        try:
            msg_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00')).timestamp()
            if msg_time > cutoff:
                recent_counts[msg['username']] = recent_counts.get(msg['username'], 0) + 1
        except:
            continue
    
    if not recent_counts:
        return None
    
    total = sum(recent_counts.values())
    if total < 5:  # Need at least 5 messages in last 3 minutes
        return None
    
    # Find if anyone has >50% AND has at least 3 messages
    for user, count in recent_counts.items():
        share = count / total
        if share > DOMINANCE_THRESHOLD and count >= 3:
            # Check if others have spoken - if only one person has spoken, that's not dominance, that's just low participation
            if len(recent_counts) >= 2:  # At least 2 people have spoken
                return user
    return None

def check_silence(room_id: str) -> Optional[str]:
    """Check if anyone hasn't spoken in 3 minutes"""
    participants = get_participants(room_id)
    if len(participants) < 3:
        return None
    
    messages = get_chat_history(room_id, limit=50)
    
    now = time.time()
    cutoff = now - SILENCE_THRESHOLD_SECONDS  # 3 minutes
    
    recent_speakers = set()
    for msg in messages:
        if msg['username'] == 'Moderator':
            continue
        try:
            msg_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00')).timestamp()
            if msg_time > cutoff:
                recent_speakers.add(msg['username'])
        except:
            continue
    
    # Find who hasn't spoken
    for p in participants:
        if p['username'] != 'Moderator' and p['username'] not in recent_speakers:
            return p['username']
    return None

# ============================================================
# Submit Ranking Endpoint
# ============================================================
@socketio.on("submit_ranking")
def handle_submit_ranking(data):
    """Handle final ranking submission from group"""
    room_id = data.get("room_id")
    ranking = data.get("ranking")  # List of items in ranked order
    
    logger.info(f"📊 Final ranking submitted for room {room_id}")
    
    try:
        # Save to database
        supabase.table("rooms").update({
            "final_ranking": json.dumps(ranking),
            "ranking_submitted_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", room_id).execute()
        
        # Compare with expert ranking
        comparison = compare_with_expert_ranking(ranking)
        logger.info(f"📈 Ranking accuracy: {comparison['accuracy_percentage']:.1f}%")
        
        # Save metrics
        metrics = analyze_participation(room_id, get_chat_history(room_id))
        if metrics:
            supabase.table("research_metrics").insert({
                "room_id": room_id,
                "gini_coefficient": metrics['gini_coefficient'],
                "max_share": metrics['max_share'],
                "min_share": metrics['min_share'],
                "dominance_gap": metrics['dominance_gap'],
                "total_messages": metrics['total_messages'],
                "ranking_accuracy": comparison['accuracy_percentage'],
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        
        # Send confirmation
        socketio.emit("ranking_submitted", {
            "success": True,
            "message": "Ranking submitted successfully!"
        }, room=room_id)
        
    except Exception as e:
        logger.error(f"❌ Error saving ranking: {e}")
        socketio.emit("ranking_submitted", {
            "success": False,
            "message": "Failed to submit ranking"
        }, room=room_id)

# ============================================================
# Auto Room Assignment Endpoint
# ============================================================
@app.route("/join/<mode>")
def auto_join_room(mode: str):
    """Auto-assign user to available room or create new one"""
    logger.info(f"🔗 /join/{mode} - Auto-join request received")

    if mode not in ['active', 'passive']:
        logger.warning(f"⚠️ Invalid mode: {mode}")
        return jsonify({"error": "Invalid mode. Use 'active' or 'passive'"}), 400

    try:
        # DEBUG: List all available rooms
        try:
            rooms_response = supabase.table("rooms").select("*").eq("mode", mode).in_("status", ["waiting", "active"]).execute()
            rooms = rooms_response.data or []
            logger.info(f"📋 Found {len(rooms)} rooms in '{mode}' mode:")
            for room in rooms:
                logger.info(f"   Room {room['id'][:8]}...: {room.get('participant_count', 0)}/3 participants, status={room['status']}")
        except Exception as e:
            logger.error(f"❌ Error listing rooms: {e}")

        # Get desert survival task (always same)
        task_data = get_data()
        story_id = task_data.get('task_id', 'desert_survival')
        logger.info(f"📚 Using task: {story_id}")

        # Get or create room
        room = get_or_create_room(mode=mode, story_id=story_id)
        room_id = room['id']

        logger.info(f"✅ Room assigned: {room_id} (mode={mode}, participants={room.get('participant_count', 0)}/3)")

        # Generate a proper username
        user_name = f"Student_{random.randint(1000, 9999)}"
        
        # Return username in response
        redirect_url = f"{FRONTEND_URL}/chat/{room_id}?userName={user_name}"

        # Auto-start task when room is ready
        socketio.start_background_task(lambda: start_task_for_room(room_id))

        return jsonify({
            "room_id": room_id,
            "mode": room['mode'],
            "user_name": user_name,
            "redirect_url": redirect_url
        })

    except Exception as e:
        logger.error(f"❌ Error in auto_join_room: {e}", exc_info=True)
        return jsonify({"error": "Failed to assign room"}), 500

# ============================================================
# Get Room Info Endpoint
# ============================================================
@app.route("/api/room/<room_id>")
def get_room_info(room_id: str):
    """Get room information"""
    logger.info(f"ℹ️ Room info requested: {room_id}")

    try:
        room = get_room(room_id)
        if not room:
            logger.warning(f"⚠️ Room not found: {room_id}")
            return jsonify({"error": "Room not found"}), 404

        participants = get_participants(room_id)
        logger.info(f"✅ Room {room_id}: {len(participants)} participants")

        return jsonify({
            "room": room,
            "participants": participants,
            "participant_count": len(participants)
        })

    except Exception as e:
        logger.error(f"❌ Error getting room info: {e}", exc_info=True)
        return jsonify({"error": "Failed to get room info"}), 500

# ============================================================
# Socket.IO Events — room lifecycle & messaging
# (connect/disconnect registered near socketio initialization)
# ============================================================
@socketio.on("create_room")
def create_room_handler(data):
    """Handle room creation"""
    user = data.get("user_name", "Student")
    mode = data.get("moderatorMode", "active")

    logger.info(f"🏗️ Creating room: user={user}, mode={mode}, sid={request.sid}")

    try:
        story_data = get_data()
        story_id = story_data.get('story_id', 'default-story')

        from supabase_client import create_room
        room = create_room(mode=mode, story_id=story_id)
        room_id = room['id']

        logger.info(f"✅ Room created: {room_id}")

        participant = add_participant(
            room_id=room_id,
            username=user,
            socket_id=request.sid
        )
        logger.info(f"✅ Participant added: {user} → room {room_id}")

        join_room(room_id)

        # Tell the client immediately — do not block on welcome message DB write + broadcast.
        emit("joined_room", {"room_id": room_id}, to=request.sid)
        emit("room_created", {"room_id": room_id, "mode": mode}, to=request.sid)

        def _welcome_and_start_task():
            try:
                add_message(
                    room_id=room_id,
                    username="Moderator",
                    message=WELCOME_MESSAGE,
                    message_type="system",
                )
                socketio.emit(
                    "receive_message",
                    {"sender": "Moderator", "message": WELCOME_MESSAGE},
                    room=room_id,
                )
            except Exception as wel_exc:
                logger.error(f"❌ Welcome message failed for room {room_id}: {wel_exc}")
            try:
                start_task_for_room(room_id)
            except Exception as task_exc:
                logger.error(f"❌ start_task_for_room failed for {room_id}: {task_exc}")

        socketio.start_background_task(_welcome_and_start_task)

    except Exception as e:
        logger.error(f"❌ Error creating room: {e}", exc_info=True)
        emit("error", {"message": "Failed to create room"})

@socketio.on("join_room")
def join_room_handler(data):
    """Handle user joining existing room"""
    room_id = data.get("room_id")
    user_name = data.get("user_name")

    logger.info(f"🚪 Join room request: room={room_id}, user={user_name}, sid={request.sid}")

    try:
        room = get_room(room_id)
        if not room:
            logger.warning(f"⚠️ Room not found: {room_id}")
            emit("error", {"message": "Room not found"})
            return

        # Check if participant already exists in this room
        existing_participant = get_participant_by_username(room_id, user_name)
        if existing_participant:
            logger.info(f"👤 Participant {user_name} already in room {room_id}, reconnecting")
            # Update their socket ID
            supabase.table('participants').update({
                'socket_id': request.sid,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', existing_participant['id']).execute()
        else:
            # Add new participant
            participant = add_participant(
                room_id=room_id,
                username=user_name,
                socket_id=request.sid,
                display_name=user_name
            )
            logger.info(f"✅ New participant added: {user_name} → room {room_id}")

        join_room(room_id)

        # Get chat history (private warnings only go to the targeted user)
        history = get_chat_history(room_id)
        chat_history = []
        for msg in history:
            mtype = msg.get("message_type") or "chat"
            meta = msg.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            elif meta is None:
                meta = {}
            if (
                msg.get("username") == "Moderator"
                and mtype == "moderator"
                and meta.get("trigger") == "inappropriate_language"
                and meta.get("target_user")
                and meta.get("target_user") != user_name
            ):
                continue
            entry = {
                "sender": msg["username"],
                "message": msg["message"],
                "timestamp": msg["created_at"],
            }
            if meta.get("flagged"):
                entry["flagged"] = True
            chat_history.append(entry)

        # Get current participants (deduplicated)
        participants = get_participants(room_id)
        participant_names = list(set([p['username'] for p in participants if p.get('username')]))
        
        # Always include the current user
        if user_name not in participant_names:
            participant_names.append(user_name)

        logger.info(f"📜 Sending {len(chat_history)} messages to {user_name}")
        logger.info(f"👥 Current participants: {participant_names}")

        emit("joined_room", {"room_id": room_id}, to=request.sid)
        emit("chat_history", {
            "chat_history": chat_history,
            "participants": participant_names
        }, to=request.sid)
        
        emit("participants_update", {
            "participants": participant_names,
            "new_user": user_name
        }, room=room_id)

        # Try to start task
        socketio.start_background_task(lambda: start_task_for_room(room_id))

    except Exception as e:
        logger.error(f"❌ Error joining room: {e}", exc_info=True)
        emit("error", {"message": "Failed to join room"})

@socketio.on("send_message")
def send_message_handler(data):
    """Handle user message (with real-time inappropriate-language warnings)."""
    room_id = data.get("room_id")
    sender = data.get("sender")
    msg = (data.get("message") or "").strip()

    if not msg:
        return

    word_count = len(msg.split())
    logger.info(f"💬 Message from {sender} in room {room_id}: {msg[:50]}... (words: {word_count})")

    try:
        room = get_room(room_id)
        if not room or room.get("story_finished"):
            logger.warning(f"⚠️ Cannot send message - room {room_id} finished or not found")
            return

        is_inappropriate, bad_words = check_inappropriate_language(msg)
        if is_inappropriate:
            severity = get_language_severity(bad_words)
            logger.warning(
                f"⚠️ Inappropriate language from {sender}: {bad_words} (severity: {severity})"
            )
            if severity == "HIGH":
                warning_msg = (
                    "Your message contained inappropriate language. "
                    "Please keep our discussion professional, respectful, and focused on the "
                    "desert survival task. Continued violations may affect your participation."
                )
            elif severity == "MEDIUM":
                warning_msg = (
                    "Please use more professional language. Let's focus on the desert survival task."
                )
            else:
                warning_msg = (
                    "Please keep our discussion professional and focused on the task."
                )
            sample = bad_words[0] if bad_words else ""
            if sample:
                warning_msg += f" (detected: {sample})"

            warning_payload = {
                "message": warning_msg,
                "type": "language_warning",
                "severity": severity,
                "detected_words": bad_words,
            }
            participant_record = get_participant_by_username(room_id, sender)
            if participant_record and participant_record.get("socket_id"):
                sid = participant_record["socket_id"]
                socketio.emit("language_warning", warning_payload, room=sid)
                socketio.emit(
                    "warning_message",
                    {"message": warning_msg, "type": "language_warning"},
                    room=sid,
                )
                logger.info(f"📨 Sent language warning to {sender} (severity={severity})")

            log_moderator_intervention(room_id, "language_warning", sender)

            add_message(
                room_id=room_id,
                username=sender,
                message=msg,
                message_type="chat",
                metadata={
                    "word_count": word_count,
                    "flagged": True,
                    "bad_words": bad_words,
                    "severity": severity,
                },
            )

            emit(
                "receive_message",
                {
                    "id": f"{room_id}_{sender}_{int(time.time() * 1000)}",
                    "sender": sender,
                    "message": msg,
                    "timestamp": datetime.now().isoformat(),
                    "flagged": True,
                    "flag_reason": "inappropriate language",
                },
                room=room_id,
            )
            logger.info(f"✅ Flagged message from {sender} broadcast (severity={severity})")
            return

        add_message(
            room_id=room_id,
            username=sender,
            message=msg,
            message_type="chat",
            metadata={"word_count": word_count},
        )

        emit(
            "receive_message",
            {"sender": sender, "message": msg, "timestamp": datetime.now().isoformat()},
            room=room_id,
        )

        logger.info(f"✅ Message sent to room {room_id}")

    except Exception as e:
        logger.error(f"❌ Error sending message: {e}", exc_info=True)

# ============================================================
# End Session Handler
# ============================================================
@socketio.on("end_session")
def handle_end_session(data):
    """End session, calculate research metrics, and send personalized feedback"""
    room_id = data.get("room_id")
    sender = data.get("sender", "user")
    
    logger.info(f"🏁 Ending session for room {room_id} initiated by {sender}")
    
    try:
        # ===== 1. GET ROOM INFO =====
        room = get_room(room_id)
        if not room:
            emit("error", {"message": "Room not found"})
            return
        
        # Get story info
        story_data = get_room_task_data(room_id)
        progress_percent = 100  # For desert survival, always 100% at end
        task_context = ""
        if story_data:
            task_context = (story_data.get("description") or "").strip()
        if not task_context:
            task_context = (
                "Desert survival task: your group discusses and ranks 12 items from "
                "most to least important for survival, then submits one consensus ranking."
            )
        
        # ===== 2. GET ALL DATA =====
        participants = get_participants(room_id)
        full_chat_history = get_chat_history(room_id)
        
        # Filter out moderator messages for participant analysis
        participant_messages = [m for m in full_chat_history if m.get('username') != 'Moderator']
        
        # ===== 3. CALCULATE RESEARCH METRICS =====
        
        # Message counts per participant
        message_counts = {}
        word_counts = {}
        for msg in participant_messages:
            username = msg.get('username')
            message_counts[username] = message_counts.get(username, 0) + 1
            word_count = len(msg.get('message', '').split())
            word_counts[username] = word_counts.get(username, 0) + word_count
        
        # Calculate total messages and shares
        total_messages = sum(message_counts.values())
        total_words = sum(word_counts.values())
        
        # Calculate speaking shares
        speaking_shares = {}
        if total_messages > 0:
            for user, count in message_counts.items():
                speaking_shares[user] = count / total_messages
        
        # Calculate Gini coefficient
        gini_coefficient = 0
        if len(message_counts) >= 3:  # Need at least 3 participants
            shares = list(speaking_shares.values())
            sorted_shares = sorted(shares)
            n = len(sorted_shares)
            cumulative = 0
            gini = 0
            for i, share in enumerate(sorted_shares):
                cumulative += share
                gini += (2*i - n + 1) * share
            if sum(sorted_shares) > 0:
                gini_coefficient = gini / (n * sum(sorted_shares))
            gini_coefficient = max(0, min(gini_coefficient, 1))
        
        # Calculate dominance metrics
        max_share = max(speaking_shares.values()) if speaking_shares else 0
        min_share = min(speaking_shares.values()) if speaking_shares else 0
        dominance_gap = max_share - min_share
        
        # Calculate time to consensus (if ranking was submitted)
        time_to_consensus = None
        if room.get('ranking_submitted_at') and room.get('created_at'):
            try:
                start_time = datetime.fromisoformat(room['created_at'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(room['ranking_submitted_at'].replace('Z', '+00:00'))
                time_to_consensus = int((end_time - start_time).total_seconds())
            except:
                time_to_consensus = None
        
        # ===== 4. SAVE RESEARCH METRICS TO DATABASE =====
        try:
            # Save room-level metrics
            metrics_data = {
                "room_id": room_id,
                "gini_coefficient": gini_coefficient,
                "max_share": max_share,
                "min_share": min_share,
                "dominance_gap": dominance_gap,
                "total_messages": total_messages,
                "total_words": total_words,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Add ranking accuracy if available
            if room.get('final_ranking'):
                from data_retriever import compare_with_expert_ranking
                ranking = json.loads(room.get('final_ranking'))
                comparison = compare_with_expert_ranking(ranking)
                metrics_data["ranking_accuracy"] = comparison['accuracy_percentage']
            
            # Add time to consensus if available
            if time_to_consensus:
                metrics_data["time_to_consensus"] = time_to_consensus
            
            supabase.table("research_metrics").insert(metrics_data).execute()
            logger.info(f"📊 Saved research metrics for room {room_id}")
            
            # Save individual participant metrics
            for user in message_counts.keys():
                participant_data = {
                    "room_id": room_id,
                    "username": user,
                    "message_count": message_counts.get(user, 0),
                    "word_count": word_counts.get(user, 0),
                    "share_of_talk": speaking_shares.get(user, 0),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                supabase.table("participant_metrics").insert(participant_data).execute()
            
            logger.info(f"👥 Saved participant metrics for {len(message_counts)} users")
            
        except Exception as e:
            logger.error(f"❌ Failed to save research metrics: {e}")
        
        # ===== 5. GENERATE PERSONALIZED FEEDBACK =====
        chat_history_list = [
            {"sender": msg['username'], "message": msg['message']}
            for msg in full_chat_history
        ]
        
        feedbacks = {}
        
        for participant in participants:
            username = participant.get('username')
            display_name = participant.get('display_name', username)
            
            # Skip moderator
            if username == 'Moderator' or username == 'System':
                continue
            
            # Get this participant's metrics
            message_count = message_counts.get(username, 0)
            word_count = word_counts.get(username, 0)
            share_of_talk = speaking_shares.get(username, 0)

            inappropriate_count = 0
            for msg in participant_messages:
                if msg.get('username') == username:
                    is_bad, _ = check_inappropriate_language(
                        msg.get("message", ""), allow_casual_slang=True
                    )
                    if is_bad:
                        inappropriate_count += 1

            if message_count == 0:
                behavior_type = "passive"
            elif inappropriate_count > 0:
                behavior_type = "needs_improvement"
            elif message_count >= 5:
                behavior_type = "active"
            else:
                behavior_type = "moderate"

            logger.info(
                f"📝 Generating dynamic feedback for {username} "
                f"(type: {behavior_type}, inappropriate msgs: {inappropriate_count})"
            )

            feedback = None
            for attempt in range(3):
                try:
                    feedback = generate_personalized_feedback(
                        student_name=display_name,
                        message_count=message_count,
                        response_times=[],
                        story_progress=progress_percent,
                        hint_responses=0,
                        behavior_type=behavior_type,
                        toxic_count=inappropriate_count,
                        off_topic_count=0,
                        chat_history=chat_history_list,
                        story_context=task_context,
                        chat_sender_name=username,
                    )
                    if feedback and len(feedback.strip()) > 100:
                        logger.info(f"✅ Quality feedback for {username} (attempt {attempt + 1})")
                        break
                    logger.warning(f"⚠️ Feedback too short for {username}, retrying...")
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ Feedback attempt {attempt + 1} for {username}: {e}")
                    if attempt == 2:
                        feedback = get_fallback_feedback(
                            display_name, message_count, inappropriate_count
                        )
                    else:
                        time.sleep(1)

            if not feedback or len((feedback or "").strip()) <= 100:
                feedback = get_fallback_feedback(
                    display_name, message_count, inappropriate_count
                )

            feedbacks[username] = feedback
            
            # METHOD 1: Direct socket delivery (most reliable)
            delivery_success = False
            try:
                participant_record = get_participant_by_username(room_id, username)
                if participant_record and participant_record.get('socket_id'):
                    socketio.emit(
                        "session_ended",
                        {
                            "feedback": feedback, 
                            "room_id": room_id,
                            "username": username,
                            "stats": {
                                "message_count": message_count,
                                "word_count": word_count,
                                "share_of_talk": round(share_of_talk * 100, 1)
                            }
                        },
                        room=participant_record['socket_id']
                    )
                    logger.info(f"📨 Sent direct feedback to {username}")
                    delivery_success = True
            except Exception as e:
                logger.warning(f"⚠️ Failed to send direct feedback to {username}: {e}")
            
            # METHOD 2: Broadcast to room as backup (if direct failed)
            if not delivery_success:
                try:
                    socketio.emit(
                        "session_ended",
                        {
                            "feedback": feedback, 
                            "room_id": room_id,
                            "username": username,
                            "stats": {
                                "message_count": message_count,
                                "word_count": word_count,
                                "share_of_talk": round(share_of_talk * 100, 1)
                            },
                            "broadcast": True
                        },
                        room=room_id
                    )
                    logger.info(f"📢 Broadcast feedback for {username} as fallback")
                except Exception as e:
                    logger.error(f"❌ Failed to broadcast feedback for {username}: {e}")
        
        logger.info(f"📊 Feedback generated for {len(feedbacks)} participants")
        
        # ===== 6. END SESSION IN DATABASE =====
        try:
            end_session(room_id, ended_by=sender, end_reason='user_ended')
            logger.info(f"✅ Session ended in database for room {room_id}")
        except Exception as e:
            logger.error(f"❌ Failed to end session in database: {e}")
        
        # ===== 7. UPDATE ROOM STATUS =====
        try:
            update_room_status(room_id, 'completed')
            logger.info(f"✅ Room {room_id} marked as completed")
        except Exception as e:
            logger.error(f"❌ Failed to update room status: {e}")
        
        # ===== 8. STOP MONITORING THREADS =====
        if room_id in active_monitors:
            try:
                del active_monitors[room_id]
                logger.info(f"🛑 Removed active monitor for room {room_id}")
            except:
                pass
        
        if room_id in research_timers:
            try:
                del research_timers[room_id]
                logger.info(f"🛑 Removed research timer for room {room_id}")
            except:
                pass
        
        logger.info(f"✅ Session fully ended for room {room_id}")
        
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR ending session: {e}", exc_info=True)
        try:
            emit("error", {"message": "Failed to end session properly"})
        except:
            pass

# ============================================================
# Admin Room Creation Endpoint
# ============================================================
@app.route("/admin/rooms/create", methods=["POST"])
def admin_create_room():
    """Admin-only room creation endpoint"""
    try:
        data = request.json or {}
        
        mode = data.get('mode', 'active')
        story_id = data.get('story_id')
        max_participants = int(data.get('max_participants', 3))
        admin_note = data.get('admin_note', '')
        
        if mode not in ['active', 'passive']:
            return jsonify({"error": "Mode must be 'active' or 'passive'"}), 400
        
        if story_id:
            story_data = get_data(story_id)
        else:
            story_data = get_data()
            story_id = story_data.get('story_id', 'default-story')
        
        room = supabase_create_room(
            mode=mode,
            story_id=story_id,
            max_participants=max_participants,
            created_by='admin'
        )
        
        if admin_note:
            supabase.table('rooms').update({
                'admin_note': admin_note
            }).eq('id', room['id']).execute()
        
        active_link = f"{FRONTEND_URL}/join/{mode}"
        direct_link = f"{FRONTEND_URL}/chat/{room['id']}"
        
        log_admin_action('create_room_admin', 'room', room['id'], {
            'mode': mode,
            'story_id': story_id,
            'max_participants': max_participants,
            'admin_note': admin_note
        }, 'admin')
        
        logger.info(f"✅ Admin created room: {room['id']} (mode={mode})")
        
        return jsonify({
            "success": True,
            "room": room,
            "links": {
                "shareable": active_link,
                "direct": direct_link
            }
        })
    
    except Exception as e:
        logger.error(f"❌ Error creating room as admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# Admin End Session Endpoint
# ============================================================
@app.route("/admin/rooms/<room_id>/end", methods=["POST"])
def admin_end_session(room_id: str):
    """Admin endpoint to end a session"""
    try:
        data = request.json or {}
        admin_user = data.get('admin_user', 'admin')
        
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        # Trigger the socket event to end session with summaries
        socketio.emit("end_session", {
            "room_id": room_id,
            "sender": f"admin:{admin_user}"
        }, room=room_id)
        
        log_admin_action('end_session', 'room', room_id, {
            'previous_status': room.get('status')
        }, admin_user)
        
        logger.info(f"✅ Admin triggered session end for room {room_id}")
        
        return jsonify({
            "success": True,
            "message": "Session ending, summaries will be sent to participants",
            "room_id": room_id
        })
    
    except Exception as e:
        logger.error(f"❌ Error ending session: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# Helper: Log Admin Action
# ============================================================
def log_admin_action(action: str, entity_type: str = None, entity_id: str = None,
                     details: dict = None, admin_user: str = 'admin'):
    """Log an admin action"""
    try:
        supabase.table('admin_logs').insert({
            'action': action,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'details': details or {},
            'admin_user': admin_user,
            'ip_address': request.remote_addr if request else '127.0.0.1',
            'created_at': datetime.now().isoformat()
        }).execute()
        logger.info(f"📝 Admin action logged: {action} by {admin_user}")
    except Exception as e:
        logger.error(f"❌ Failed to log admin action: {e}")

# ============================================================
# TTS & STT Endpoints
# ============================================================
@app.route("/tts", methods=["POST"])
def tts():
    """Text-to-speech endpoint"""
    text = (request.json.get("text") or "").strip() or "Hello"
    logger.info(f"🔊 TTS request: {text[:30]}...")

    try:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            res = openai_client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=text,
            )
            audio = res.read()
            logger.info(f"✅ TTS generated using OpenAI")
            return send_file(BytesIO(audio), mimetype="audio/mpeg")
        except Exception as openai_error:
            logger.warning(f"OpenAI TTS failed: {openai_error}")
            
            try:
                from gtts import gTTS
                import tempfile
                
                tts = gTTS(text=text, lang='en', slow=False)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                tts.save(temp_file.name)
                
                logger.info(f"✅ TTS generated using gTTS")
                return send_file(temp_file.name, mimetype="audio/mpeg")
            except ImportError:
                logger.warning("gTTS not installed")
                return jsonify({
                    "error": "TTS service unavailable",
                    "fallback_text": text
                }), 503
                
    except Exception as e:
        logger.error(f"❌ TTS error: {e}")
        return {"error": str(e)}, 500

@app.route("/stt", methods=["POST"])
def stt():
    """Speech-to-text endpoint"""
    logger.info(f"🎤 STT request")

    if not AUDIO_SUPPORT:
        logger.warning(f"⚠️ STT not available - pydub not installed")
        return {"error": "STT not available (audio support disabled)"}, 503

    if "file" not in request.files:
        return {"error": "no file"}, 400

    try:
        f = request.files["file"]
        audio = AudioSegment.from_file(
            BytesIO(f.read()),
            format="webm",
        )

        temp_path = os.path.join(os.getcwd(), "temp.wav")
        audio.export(
            temp_path,
            format="wav",
            parameters=["-acodec", "pcm_s16le"],
        )

        with open(temp_path, "rb") as w:
            buf = BytesIO(w.read())
            buf.name = "recording.wav"

        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            res = openai_client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=buf,
            )

            logger.info(f"✅ STT result: {res.text[:50]}...")
            return {"text": res.text.strip()}
        except Exception as openai_error:
            logger.warning(f"OpenAI STT failed: {openai_error}")
            return {"text": "[STT Service Unavailable] Please type your message instead."}

    except Exception as e:
        logger.error(f"❌ STT error: {e}")
        return {"error": str(e)}, 500

# ============================================================
# Health Check Endpoint
# ============================================================
@app.route("/health")
def health_check():
    """Health check with a lightweight Supabase round-trip (skip with ?lite=1 for speed)."""
    lite = request.args.get("lite", "").lower() in ("1", "true", "yes")
    supabase_ok = False
    if not lite:
        try:
            supabase.table("rooms").select("id").limit(1).execute()
            supabase_ok = True
        except Exception as e:
            logger.warning(f"/health Supabase check failed: {e}")
    return jsonify({
        "status": "healthy",
        "llm_provider": LLM_PROVIDER,
        "socketio_async_mode": _socketio_async_mode,
        "openai_available": openai_client is not None,
        "groq_available": groq_client is not None,
        "supabase_connected": supabase_ok if not lite else None,
        "audio_support": AUDIO_SUPPORT,
        "session_summaries": True,
        "feedback_delivery": "direct-with-broadcast-fallback",
        "timestamp": time.time(),
    })

# ============================================================
# Server Start
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("="*60)
    logger.info("🚀 Starting Flask-SocketIO server")
    logger.info(f"⚙️ Socket.IO async_mode: {_socketio_async_mode}")
    logger.info(f"📍 Host: 0.0.0.0:{port}")
    logger.info(f"🌐 Frontend: {FRONTEND_URL}")
    logger.info(f"🤖 LLM Provider: {LLM_PROVIDER}")
    if LLM_PROVIDER == "openai":
        logger.info(f"📊 OpenAI Model: {OPENAI_MODEL}")
    else:
        logger.info(f"📊 Groq Model: {GROQ_MODEL}")
    logger.info(f"📝 Session Summaries: ENABLED")
    logger.info(f"💬 Feedback Delivery: 3-Method Guaranteed")
    logger.info("="*60)
    
    try:
        socketio.run(
            app, 
            host="0.0.0.0", 
            port=port, 
            debug=False, 
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        import traceback
        traceback.print_exc()