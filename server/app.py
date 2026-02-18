
from __future__ import annotations

import os
import uuid
import logging
import time
import threading
import sys
import json
import csv
import random
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
)

# ============================================================
# Import Story System
# ============================================================
from data_retriever import (
    get_data,
    format_story_block,
    get_story_intro,
)

# ============================================================
# Import Prompt Functions
# ============================================================
from prompts import (
    generate_moderator_reply,
    generate_passive_chunk,
    get_random_ending,
    generate_engagement_response,
    should_advance_story,
    generate_personalized_feedback,
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
logger.info("🚀 LLM Moderator Server Starting - WITH FIXED FEEDBACK DELIVERY")
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
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()

allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    FRONTEND_URL
]

logger.info(f"🔒 CORS allowed origins: {allowed_origins}")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": allowed_origins}}, supports_credentials=True)

socketio = SocketIO(
    app,
    cors_allowed_origins=allowed_origins,
    async_mode="threading",
    logger=True,
    engineio_logger=True,
    # 👇 CRITICAL FIX: Force polling only
    transports=['polling'],  # Only use polling
    allow_upgrades=False,     # Never upgrade to websocket
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8
)

# ============================================================
# Room State Management
# ============================================================
active_monitors: Dict[str, threading.Thread] = {}
room_sessions: Dict[str, str] = {}  # room_id -> session_id

# ============================================================
# Groq Client Setup
# ============================================================
groq_client = None
try:
    from groq import Groq
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        groq_client = Groq(api_key=groq_api_key)
        logger.info("✅ Groq client initialized")
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
ACTIVE_STORY_STEP = get_setting_value("ACTIVE_STORY_STEP", 1)
PASSIVE_STORY_STEP = get_setting_value("PASSIVE_STORY_STEP", 1)
PASSIVE_SILENCE_SECONDS = get_setting_value("PASSIVE_SILENCE_SECONDS", 10)
ACTIVE_SILENCE_SECONDS = get_setting_value("ACTIVE_SILENCE_SECONDS", 20)
STORY_CHUNK_INTERVAL = get_setting_value("STORY_CHUNK_INTERVAL", 10)
ACTIVE_INTERVENTION_WINDOW_SECONDS = get_setting_value("ACTIVE_INTERVENTION_WINDOW_SECONDS", 20)
PASSIVE_INTERVENTION_WINDOW_SECONDS = get_setting_value("PASSIVE_INTERVENTION_WINDOW_SECONDS", 10)

# Load Groq-specific settings
GROQ_MODEL = get_setting_value("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TEMPERATURE = get_setting_value("GROQ_TEMPERATURE", 0.7)
GROQ_MAX_TOKENS = get_setting_value("GROQ_MAX_TOKENS", 2000)
LLM_PROVIDER = get_setting_value("LLM_PROVIDER", "groq")

logger.info(f"📝 Config: Active Step={ACTIVE_STORY_STEP}, Passive Step={PASSIVE_STORY_STEP}")
logger.info(f"📝 Config: Story Interval={STORY_CHUNK_INTERVAL}s")
logger.info(f"📝 Config: LLM Provider={LLM_PROVIDER}, Model={GROQ_MODEL}")
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
# Helper: Get Room Story Data
# ============================================================
def get_room_story_data(room_id: str) -> Optional[Dict[str, Any]]:
    """Load story data for room"""
    room = get_room(room_id)
    if not room or not room.get('story_id'):
        logger.warning(f"⚠️ No story data for room {room_id}")
        return None

    return get_data(room['story_id'])

# ============================================================
# Helper: Start Story
# ============================================================
def start_story_for_room(room_id: str):
    """Start story for a room when conditions are met"""
    try:
        room = get_room(room_id)
        if not room:
            logger.error(f"❌ Room {room_id} not found")
            return

        participants = get_participants(room_id)
        student_count = len(participants)

        logger.info(f"📊 Room {room_id}: {student_count} students, status={room['status']}")

        if room['status'] == 'active':
            logger.info(f"ℹ️ Room {room_id} already active")
            return
        elif room['status'] == 'completed':
            logger.info(f"ℹ️ Room {room_id} already completed")
            return

        if student_count < 1:
            logger.info(f"ℹ️ Room {room_id} waiting for participants (current: {student_count})")
            return

        logger.info(f"🎬 Starting story for room {room_id} with {student_count} students")

        # Update room status
        update_room_status(room_id, 'active')

        # Create session
        session = create_session(
            room_id=room_id,
            mode=room['mode'],
            participant_count=student_count,
            story_id=room['story_id']
        )
        room_sessions[room_id] = session['id']

        # Send story intro
        story_data = get_room_story_data(room_id)
        if story_data:
            intro = get_story_intro(story_data)
            logger.info(f"📖 Sending story intro to room {room_id}")

            add_message(
                room_id=room_id,
                username="Moderator",
                message=intro,
                message_type="story"
            )

            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": intro},
                room=room_id,
            )

            # Start appropriate mode
            if room['mode'] == 'passive':
                logger.info(f"🔄 Starting passive loop for room {room_id}")
                start_passive_loop(room_id)
            else:  # active mode
                logger.info(f"👁️ Starting silence monitor for room {room_id}")
                start_silence_monitor(room_id)
        else:
            logger.error(f"❌ No story data found for room {room_id}")

    except Exception as e:
        logger.error(f"❌ Error starting story for room {room_id}: {e}", exc_info=True)

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
        # Get random story
        story_data = get_data()
        story_id = story_data.get('story_id', 'default-story')
        logger.info(f"📚 Selected story: {story_id}")

        # Get or create room
        room = get_or_create_room(mode=mode, story_id=story_id)
        room_id = room['id']

        logger.info(f"✅ Room assigned: {room_id} (mode={mode}, participants={room.get('participant_count', 0)})")

        # Generate a proper username
        user_name = f"Student_{random.randint(1000, 9999)}"
        
        # Return username in response
        redirect_url = f"{FRONTEND_URL}/chat/{room_id}?userName={user_name}"

        # Auto-start story for single user
        socketio.start_background_task(lambda: start_story_for_room(room_id))

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
# Passive Story Continuation
# ============================================================
def passive_continue_story(room_id: str):
    """Continue story in passive mode"""
    try:
        room = get_room(room_id)
        if not room or room.get('story_finished') or room['mode'] != 'passive':
            return

        story_data = get_room_story_data(room_id)
        if not story_data:
            return

        sentences = story_data.get("sentences", [])
        total = len(sentences)

        start = room.get('current_chunk_index', 0)
        end = min(start + PASSIVE_STORY_STEP, total)

        next_chunk = " ".join(sentences[start:end])
        is_last = end >= total

        logger.info(f"📖 Passive story chunk {start}→{end}/{total} for room {room_id}")

        msg = generate_passive_chunk(next_chunk, is_last_chunk=is_last)

        add_message(
            room_id=room_id,
            username="Moderator",
            message=msg,
            message_type="story",
            metadata={"story_progress": end, "is_last": is_last}
        )

        socketio.emit(
            "receive_message",
            {"sender": "Moderator", "message": msg},
            room=room_id,
        )

        # Update progress
        supabase.table("rooms").update({
            "current_chunk_index": end
        }).eq("id", room_id).execute()

        if is_last:
            logger.info(f"🏁 Story finished for room {room_id}")
            ending = get_random_ending()

            add_message(
                room_id=room_id,
                username="Moderator",
                message=ending,
                message_type="system"
            )

            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": ending},
                room=room_id,
            )

            end_session(room_id)
            update_room_status(room_id, "completed")

    except Exception as e:
        logger.error(f"❌ Error in passive_continue_story: {e}", exc_info=True)

def start_passive_loop(room_id: str):
    """Start background task for passive story advancement"""
    def loop():
        logger.info(f"🔄 Passive loop started for room {room_id}")
        while True:
            room = get_room(room_id)
            if not room or room.get('story_finished') or room['status'] == 'completed':
                logger.info(f"⏹️ Passive loop stopped for room {room_id}")
                break

            passive_continue_story(room_id)
            socketio.sleep(STORY_CHUNK_INTERVAL)

    socketio.start_background_task(loop)

# ============================================================
# Active Story Advancement
# ============================================================
def advance_story_chunk(room_id: str):
    """Advance story in active mode"""
    try:
        room = get_room(room_id)
        if not room or room.get('story_finished'):
            return

        story_data = get_room_story_data(room_id)
        if not story_data:
            return

        sentences = story_data.get("sentences", [])
        total = len(sentences)

        start = room.get('current_chunk_index', 0)
        end = min(start + ACTIVE_STORY_STEP, total)
        is_last = end >= total

        logger.info(f"📖 Active story chunk {start}→{end}/{total} for room {room_id}")

        context = " ".join(sentences[:end])

        participants = get_participants(room_id)
        student_names = [p['username'] for p in participants]

        history = get_chat_history(room_id)
        chat_history = [
            {"sender": msg['username'], "message": msg['message']}
            for msg in history
        ]

        reply = generate_moderator_reply(
            student_names,
            chat_history,
            context,
            start,
            is_last_chunk=is_last,
        )

        add_message(
            room_id=room_id,
            username="Moderator",
            message=reply,
            message_type="moderator",
            metadata={"story_progress": end, "is_last": is_last}
        )

        socketio.emit(
            "receive_message",
            {"sender": "Moderator", "message": reply},
            room=room_id,
        )

        # Update progress
        supabase.table("rooms").update({
            "current_chunk_index": end
        }).eq("id", room_id).execute()

        if is_last:
            logger.info(f"🏁 Story finished for room {room_id}")
            ending_message = os.getenv("ACTIVE_ENDING_MESSAGE", "✨ We have reached the end of the story.")
            
            add_message(
                room_id=room_id,
                username="Moderator",
                message=ending_message,
                message_type="system"
            )

            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": ending_message},
                room=room_id,
            )

            end_session(room_id)
            update_room_status(room_id, "completed")

    except Exception as e:
        logger.error(f"❌ Error in advance_story_chunk: {e}", exc_info=True)

# ============================================================
# Engagement Response (without advancing story)
# ============================================================
def send_engagement_response(room_id: str):
    """Send an engagement response (question/discussion) without advancing story"""
    try:
        room = get_room(room_id)
        if not room or room.get('story_finished'):
            return

        story_data = get_room_story_data(room_id)
        if not story_data:
            return

        sentences = story_data.get("sentences", [])
        current_progress = room.get('current_chunk_index', 0)

        context = " ".join(sentences[:current_progress])

        participants = get_participants(room_id)
        student_names = [p['username'] for p in participants]

        history = get_chat_history(room_id)
        chat_history = [
            {"sender": msg['username'], "message": msg['message']}
            for msg in history
        ]

        response = generate_engagement_response(
            student_names,
            chat_history,
            context,
            current_progress
        )

        logger.info(f"💭 Engagement response for room {room_id}: {response[:50]}...")

        add_message(
            room_id=room_id,
            username="Moderator",
            message=response,
            message_type="moderator",
            metadata={"type": "engagement", "story_progress": current_progress}
        )

        socketio.emit(
            "receive_message",
            {"sender": "Moderator", "message": response},
            room=room_id,
        )

    except Exception as e:
        logger.error(f"❌ Error in send_engagement_response: {e}", exc_info=True)

# ============================================================
# Silence Monitor (Active Mode)
# ============================================================
def start_silence_monitor(room_id: str):
    """Monitor silence and trigger intelligent interventions in active mode"""
    def loop():
        logger.info(f"👁️ Silence monitor started for room {room_id}")
        last_intervention = time.time()
        last_story_advance = time.time()

        while True:
            time.sleep(5)

            room = get_room(room_id)
            if not room or room.get('story_finished') or room['status'] == 'completed':
                logger.info(f"⏹️ Silence monitor stopped for room {room_id}")
                break

            now = time.time()
            time_since_intervention = now - last_intervention
            time_since_advance = now - last_story_advance

            if time_since_intervention >= ACTIVE_INTERVENTION_WINDOW_SECONDS:
                logger.info(f"🔔 Silence detected in room {room_id} ({time_since_intervention:.0f}s)")

                history = get_chat_history(room_id)
                chat_history = [
                    {"sender": msg['username'], "message": msg['message']}
                    for msg in history
                ]

                story_data = get_room_story_data(room_id)
                if story_data:
                    sentences = story_data.get("sentences", [])
                    current_progress = room.get('current_chunk_index', 0)
                    context = " ".join(sentences[:current_progress])

                    should_advance = should_advance_story(
                        chat_history,
                        context,
                        int(time_since_advance)
                    )

                    if should_advance:
                        logger.info(f"📖 AI Decision: ADVANCE story in room {room_id}")
                        advance_story_chunk(room_id)
                        last_story_advance = now
                    else:
                        logger.info(f"💬 AI Decision: ENGAGE students in room {room_id}")
                        send_engagement_response(room_id)

                last_intervention = now

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    active_monitors[room_id] = thread

# ============================================================
# ✅ FIXED: End Session with Guaranteed Feedback Delivery
# ============================================================
@socketio.on("end_session")
def handle_end_session(data):
    """End session and send personalized feedback to each participant - FIXED VERSION"""
    room_id = data.get("room_id")
    sender = data.get("sender", "user")
    
    logger.info(f"🏁 Ending session for room {room_id} initiated by {sender}")
    
    try:
        # Get room info
        room = get_room(room_id)
        if not room:
            emit("error", {"message": "Room not found"})
            return
        
        # Get story info for progress calculation
        story_data = get_room_story_data(room_id)
        
        # Calculate story progress percentage
        progress_percent = 50  # Default
        if story_data and room:
            sentences = story_data.get('sentences', [])
            total_sentences = len(sentences)
            current_progress = room.get('current_chunk_index', 0)
            if total_sentences > 0:
                progress_percent = int((current_progress / total_sentences) * 100)
        
        # Get all participants
        participants = get_participants(room_id)
        
        # Get full chat history for feedback generation
        full_chat_history = get_chat_history(room_id)
        chat_history_list = [
            {"sender": msg['username'], "message": msg['message']}
            for msg in full_chat_history
        ]
        
        # Get story context
        story_context = ""
        if story_data and room:
            sentences = story_data.get("sentences", [])
            current_progress = room.get('current_chunk_index', 0)
            story_context = " ".join(sentences[:current_progress])
        
        # Generate personalized feedback for EACH participant
        feedbacks = {}
        
        for participant in participants:
            username = participant.get('username')
            display_name = participant.get('display_name', username)
            
            # Skip moderator
            if username == 'Moderator' or username == 'System':
                continue
            
            # Analyze this student's behavior
            behavior_data = analyze_student_behavior(room_id, username)
            
            # Generate personalized feedback using LLM
            feedback = generate_personalized_feedback(
                student_name=display_name,
                message_count=behavior_data['message_count'],
                response_times=behavior_data['response_times'],
                story_progress=progress_percent,
                hint_responses=behavior_data['hint_responses'],
                behavior_type=behavior_data['behavior_type'],
                toxic_count=behavior_data['toxic_count'],
                off_topic_count=behavior_data['off_topic_count'],
                chat_history=chat_history_list,
                story_context=story_context
            )
            
            feedbacks[username] = feedback
            
            # === THREE DELIVERY METHODS FOR GUARANTEED FEEDBACK ===
            feedback_sent = False
            
            # METHOD 1: Try direct socket delivery (if participant still connected)
            try:
                participant_record = get_participant_by_username(room_id, username)
                if participant_record and participant_record.get('socket_id'):
                    socketio.emit(
                        "session_ended",
                        {
                            "feedback": feedback, 
                            "room_id": room_id,
                            "username": username
                        },
                        room=participant_record['socket_id']
                    )
                    logger.info(f"📨 Method 1: Sent direct feedback to {username} via socket {participant_record['socket_id']}")
                    feedback_sent = True
            except Exception as e:
                logger.warning(f"⚠️ Method 1 failed for {username}: {e}")
            
            # METHOD 2: Broadcast to entire room (client will filter by username)
            if not feedback_sent:
                try:
                    socketio.emit(
                        "session_ended",
                        {
                            "feedback": feedback, 
                            "room_id": room_id,
                            "username": username,
                            "broadcast": True
                        },
                        room=room_id
                    )
                    logger.info(f"📨 Method 2: Broadcast feedback to room for {username}")
                    feedback_sent = True
                except Exception as e:
                    logger.warning(f"⚠️ Method 2 failed for {username}: {e}")
            
            # METHOD 3: Store in database for retrieval on next page load
            try:
                # Store feedback in a new table
                supabase.table('session_feedback').upsert({
                    'room_id': room_id,
                    'username': username,
                    'feedback': feedback,
                    'created_at': datetime.now().isoformat()
                }).execute()
                logger.info(f"📨 Method 3: Stored feedback in database for {username}")
            except Exception as e:
                logger.error(f"❌ Method 3 failed for {username}: {e}")
        
        # Log summary of feedback types
        feedback_summary = {}
        for username, feedback in feedbacks.items():
            if "dismissive" in feedback.lower() or "harsh" in feedback.lower():
                fb_type = "toxic"
            elif "off-topic" in feedback.lower() or "creative" in feedback.lower():
                fb_type = "off_topic"
            elif "quiet" in feedback.lower() or "passive" in feedback.lower():
                fb_type = "passive"
            elif "model participant" in feedback.lower() or "excellent" in feedback.lower():
                fb_type = "constructive"
            else:
                fb_type = "moderate"
            
            feedback_summary[fb_type] = feedback_summary.get(fb_type, 0) + 1
        
        logger.info(f"📊 Feedback summary for room {room_id}: {feedback_summary}")
        
        # End the session in database
        end_session(room_id, ended_by=sender, end_reason='user_ended')
        
        # Update room status
        update_room_status(room_id, 'completed')
        
        # Stop any running monitors
        if room_id in active_monitors:
            del active_monitors[room_id]
        
        logger.info(f"✅ Session ended for room {room_id}, feedback generated for {len(feedbacks)} participants")
        
    except Exception as e:
        logger.error(f"❌ Error ending session: {e}", exc_info=True)
        emit("error", {"message": "Failed to end session"})

# ============================================================
# ✅ NEW: Get Stored Feedback Endpoint
# ============================================================
@app.route("/api/feedback/<room_id>/<username>", methods=["GET"])
def get_stored_feedback(room_id: str, username: str):
    """Retrieve stored feedback for a user"""
    try:
        response = supabase.table('session_feedback')\
            .select('feedback')\
            .eq('room_id', room_id)\
            .eq('username', username)\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            return jsonify({
                "success": True,
                "feedback": response.data[0]['feedback']
            })
        else:
            return jsonify({
                "success": False,
                "feedback": None
            }), 404
            
    except Exception as e:
        logger.error(f"❌ Error retrieving feedback: {e}")
        return jsonify({"error": str(e)}), 500

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
        end_type = data.get('type', 'session')
        admin_note = data.get('admin_note', '')
        
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        if end_type == 'story':
            supabase.table('rooms').update({
                'story_finished': True,
                'admin_note': admin_note
            }).eq('id', room_id).execute()
            
            story_end_msg = "📖 The story has reached its conclusion. You may continue discussing."
            add_message(
                room_id=room_id,
                username="Moderator",
                message=story_end_msg,
                message_type="system"
            )
            
            socketio.emit(
                "receive_message",
                {"sender": "Moderator", "message": story_end_msg},
                room=room_id,
            )
            
            action = 'end_story'
            
        else:
            # Trigger the socket event to end session with summaries
            socketio.emit("end_session", {
                "room_id": room_id,
                "sender": f"admin:{data.get('admin_user', 'admin')}"
            }, room=room_id)
            
            action = 'end_session'
        
        log_admin_action(action, 'room', room_id, {
            'end_type': end_type,
            'admin_note': admin_note,
            'previous_status': room.get('status'),
            'story_finished': room.get('story_finished')
        }, data.get('admin_user', 'admin'))
        
        logger.info(f"✅ Admin {action} for room {room_id}")
        
        return jsonify({
            "success": True,
            "message": f"{end_type.capitalize()} ended successfully",
            "room_id": room_id
        })
    
    except Exception as e:
        logger.error(f"❌ Error ending {end_type}: {e}", exc_info=True)
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
# Socket.IO Events
# ============================================================
@socketio.on("connect")
def handle_connect():
    logger.info(f"🔌 Client connected: {request.sid}")

@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"🔌 Client disconnected: {request.sid}")

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

        add_message(
            room_id=room_id,
            username="Moderator",
            message=WELCOME_MESSAGE,
            message_type="system"
        )

        emit("joined_room", {"room_id": room_id}, to=request.sid)
        emit("room_created", {"room_id": room_id, "mode": mode}, to=request.sid)
        emit(
            "receive_message",
            {"sender": "Moderator", "message": WELCOME_MESSAGE},
            room=room_id,
        )

        socketio.start_background_task(lambda: start_story_for_room(room_id))

    except Exception as e:
        logger.error(f"❌ Error creating room: {e}", exc_info=True)
        emit("error", {"message": "Failed to create room"})

@socketio.on("join_room")
def join_room_handler(data):
    """Handle user joining existing room - FIXED VERSION"""
    room_id = data.get("room_id")
    user_name = data.get("user_name")

    logger.info(f"🚪 Join room request: room={room_id}, user={user_name}, sid={request.sid}")

    try:
        room = get_room(room_id)
        if not room:
            logger.warning(f"⚠️ Room not found: {room_id}")
            emit("error", {"message": "Room not found"})
            return

        # ✅ FIX: Check if participant already exists in this room
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

        # Get chat history
        history = get_chat_history(room_id)
        chat_history = [
            {
                "sender": msg['username'],
                "message": msg['message'],
                "timestamp": msg['created_at']
            }
            for msg in history
        ]

        # Get current participants (deduplicated)
        participants = get_participants(room_id)
        participant_names = list(set([p['username'] for p in participants if p.get('username')]))
        
        # ✅ FIX: Always include the current user
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

        # Try to start story
        socketio.start_background_task(lambda: start_story_for_room(room_id))

    except Exception as e:
        logger.error(f"❌ Error joining room: {e}", exc_info=True)
        emit("error", {"message": "Failed to join room"})

@socketio.on("send_message")
def send_message_handler(data):
    """Handle user message"""
    room_id = data.get("room_id")
    sender = data.get("sender")
    msg = (data.get("message") or "").strip()

    if not msg:
        return

    logger.info(f"💬 Message from {sender} in room {room_id}: {msg[:50]}...")

    try:
        room = get_room(room_id)
        if not room or room.get('story_finished'):
            logger.warning(f"⚠️ Cannot send message - room {room_id} finished or not found")
            return

        add_message(
            room_id=room_id,
            username=sender,
            message=msg,
            message_type="chat"
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
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "llm_provider": LLM_PROVIDER,
        "groq_available": groq_client is not None,
        "audio_support": AUDIO_SUPPORT,
        "session_summaries": True,
        "feedback_delivery": "3-method guaranteed",
        "timestamp": time.time()
    })

# ============================================================
# Server Start
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("="*60)
    logger.info("🚀 Starting Flask-SocketIO server")
    logger.info(f"📍 Host: 0.0.0.0:{port}")
    logger.info(f"🌐 Frontend: {FRONTEND_URL}")
    logger.info(f"🤖 LLM Provider: {LLM_PROVIDER}")
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render sets this
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
