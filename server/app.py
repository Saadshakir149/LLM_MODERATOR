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
from typing import Dict, List, Any, Optional, Set
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
    calculate_entropy,
    detect_conflict_episodes,
    message_suggests_interpersonal_conflict,
    recent_multispeaker_tension,
    discussion_appears_off_task,
    intervention_followup_seconds,
)

# ============================================================
# Import Task System (Desert Survival)
# ============================================================
from data_retriever import (
    get_data,
    format_story_block,
    get_story_intro_html,
    get_task_items,
    compare_with_expert_ranking,
    resolve_task_data_from_room,
    pin_task_data_for_room,
    get_pinned_or_resolve_task_data,
    get_canonical_items_for_room,
    clarify_alias_against_list,
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

@socketio.on("disconnect")
def handle_disconnect():
    """Clear socket_id on disconnect so we do not target dead connections; swallow teardown errors."""
    sid = getattr(request, "sid", None) or ""
    try:
        logger.info(f"🔌 Client disconnected: {sid}")
        participant = get_participant_by_socket(sid) if sid else None
        if participant and participant.get("id"):
            supabase.table("participants").update(
                {
                    "socket_id": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", participant["id"]).execute()
    except Exception as e:
        # Avoid noisy tracebacks during WSGI/socket teardown (e.g. write before start_response).
        logger.debug(f"Disconnect cleanup (non-critical): {e}")
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
room_last_expert_tip: Dict[str, float] = {}
room_expert_tip_message_key: Dict[str, str] = {}
room_active_moderator_aux: Dict[str, Dict[str, Any]] = {}
last_item_clarification_at: Dict[str, float] = {}
# One 5-min and one 1-min warning per room across timer + active + passive threads
room_time_warning_5min_claimed: Dict[str, bool] = {}
room_time_warning_1min_claimed: Dict[str, bool] = {}


def claim_session_time_warning(room_id: str, kind: str) -> bool:
    """Return True if this code path may emit that warning (first claimant wins). kind: '5' or '1'."""
    reg = room_time_warning_5min_claimed if kind == "5" else room_time_warning_1min_claimed
    if reg.get(room_id):
        return False
    reg[room_id] = True
    return True


def _active_moderator_student_msg_ratio(
    messages: List[Dict[str, Any]], lookback: int = 100
) -> float:
    """Moderator_msg_count / max(student_msg_count, 1). Target ≤ 0.20 (RQ1)."""
    if not messages:
        return 0.0
    slice_msgs = messages[-lookback:] if len(messages) > lookback else messages
    mod = sum(1 for m in slice_msgs if m.get("username") == "Moderator")
    stu = sum(
        1
        for m in slice_msgs
        if m.get("username") not in ("Moderator", "System", None, "")
    )
    if stu == 0:
        return 0.0
    return mod / stu


_ACTIVE_INVITE_LINES = (
    "{name}, we'd love your take—what's one item you'd rank higher or lower?",
    "{name}, what do you think matters most for survival here?",
    "Jump in when you can, {name}—any item you want the group to weigh?",
    "{name}, a quick thought on the ranking would help the group.",
)

_ACTIVE_FOLLOWUP_LINES = (
    "{name}, still with us? Even a one-line ranking preference helps.",
    "{name}, no pressure—just share whichever item feels strongest to you.",
    "{name}, checking in: any item you want to push back on?",
)


def _pick_phrase(templates: tuple, name: str) -> str:
    return random.choice(templates).format(name=name)


def _room_minutes_elapsed(room: Dict[str, Any], now: Optional[float] = None) -> int:
    """Whole minutes since room creation."""
    if now is None:
        now = time.time()
    created_at_val = room.get("created_at")
    if not created_at_val:
        return 0
    try:
        if isinstance(created_at_val, str):
            cv = created_at_val.replace("Z", "+00:00")
            created_at_dt = datetime.fromisoformat(cv)
            return max(0, int((now - created_at_dt.timestamp()) / 60))
        if isinstance(created_at_val, (int, float)):
            return max(0, int((now - float(created_at_val)) / 60))
    except Exception:
        pass
    return 0


def collect_discussed_canonical_items(
    messages: List[dict], canonical_items: List[str]
) -> set:
    """Distict official item lines explicitly referenced in student chat."""
    out: set = set()
    for m in messages:
        if m.get("username") in ("Moderator", "System"):
            continue
        low = (m.get("message") or "").lower()
        for item in canonical_items:
            il = item.lower()
            if len(il) >= 6 and il in low:
                out.add(item)
    return out


def trailing_student_streak(messages: List[dict]) -> tuple:
    """How many consecutive student messages at the end, same speaker (moderator breaks)."""
    streak_user = None
    streak = 0
    for m in reversed(messages):
        u = m.get("username")
        if u in ("Moderator", "System"):
            break
        if u is None:
            continue
        if streak_user is None:
            streak_user = u
            streak = 1
        elif u == streak_user:
            streak += 1
        else:
            break
    return streak_user, streak


def record_first_mention(
    attribution: Dict[str, str],
    speaker: Optional[str],
    text: str,
    canonical_items: List[str],
) -> None:
    """First speaker to mention an item/topic wins (research attribution)."""
    if not speaker or speaker in ("Moderator", "System"):
        return
    low = (text or "").lower()
    for item in canonical_items:
        il = item.lower()
        if len(il) >= 6 and il in low:
            attribution.setdefault(il[:48], speaker)
            return
    for topic in (
        "water",
        "mirror",
        "flashlight",
        "tarp",
        "compass",
        "map",
        "knife",
        "lighter",
        "jacket",
        "salt",
        "blanket",
        "parachute",
    ):
        if topic in low:
            attribution.setdefault(topic, speaker)
            return


def chat_socket_payload(sender: str, message: str, **extra: Any) -> dict:
    """Stable chat event payload with id (dedup on client)."""
    payload: dict = {
        "id": extra.pop("id", None) or str(uuid.uuid4()),
        "sender": sender,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    payload.update(extra)
    return payload


def get_expert_ranking_opinion(item_label: str) -> Optional[str]:
    """Short expert-style survival perspective for a scenario item (neutral, educational)."""
    low = item_label.lower()
    if "water" in low or "quart" in low:
        return (
            "💧 Water is usually the highest priority in desert heat — even mild dehydration "
            "impairs judgment quickly."
        )
    if "mirror" in low or "cosmetic" in low:
        return (
            "🪞 A mirror is an excellent lightweight signal for aircraft; many expert rankings "
            "place it very high for rescue visibility."
        )
    if "flashlight" in low or "battery" in low:
        return (
            "🔦 Flashlights help at night for signaling and camp tasks, but batteries are finite — "
            "compare that to passive signaling tools."
        )
    if "plastic" in low or "sheet" in low:
        return (
            "🟠 A large plastic sheet can provide shade, collect dew/rain, and improve visibility "
            "depending on color."
        )
    if "match" in low:
        return (
            "🔥 Matches are useful if you have fuel and fire safety; in dry desert conditions "
            "their value depends on what you can burn."
        )
    if "coat" in low or "winter" in low:
        return (
            "🧥 A coat matters for cold desert nights when temperatures can drop sharply after sunset."
        )
    if "salt" in low or "tablet" in low:
        return (
            "🧂 Salt tablets without enough water can worsen dehydration — experts often rank them "
            "lower unless water is abundant."
        )
    if "knife" in low:
        return (
            "🔪 A knife is versatile for gear repair, shelter, and first aid; usefulness is high "
            "but not always above water and rescue signaling."
        )
    if "parachute" in low:
        return (
            "🪂 Parachute fabric can be shelter or signal material; expert lists vary based on "
            "whether rescue or self-extraction is the plan."
        )
    if "book" in low or "edible" in low:
        return (
            "📖 Field guides look helpful, but misidentifying plants is dangerous — many expert "
            "rankings place this lower than water, signaling, and shelter."
        )
    if "compass" in low:
        return (
            "🧭 A compass mainly helps if the group chooses to move; staying put is often safer "
            "when lost and awaiting rescue."
        )
    if "map" in low:
        return (
            "🗺️ Like a compass, a map helps navigation — value drops if the plan is to stay in place "
            "and signal rescuers."
        )
    return None

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
SILENCE_THRESHOLD_SECONDS = 120  # 2 minutes — earlier inclusion (RQ1/RQ3)
SILENCE_FOLLOWUP_SECONDS = 180  # second gentle ping if still quiet after first invite
SILENCE_REINVITE_GAP_SECONDS = 90  # min gap between silence nudges to same person
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
    """Pinned scenario for this room (same item strings everywhere)."""
    room = get_room(room_id)
    if not room:
        logger.warning(f"⚠️ No room found {room_id}")
        return None
    return get_pinned_or_resolve_task_data(room_id)

# ============================================================
# RESEARCH TIMER - 15 Minute Session Timer
# ============================================================
def start_research_timer(room_id: str):
    """15-minute session: 6→2→0 min prompts, force ranking modal, auto end + feedback (RQ4)."""

    def timer_loop():
        # t=9m elapsed → 6 minutes remaining
        time.sleep(9 * 60)
        room = get_room(room_id)
        if room and room.get("status") == "active":
            reminder = (
                "⏰ **6 minutes remaining.** Keep working toward **one agreed ranking of all 12 items** "
                "(1 = most important, 12 = least)."
            )
            add_message(room_id, "Moderator", reminder, "system")
            socketio.emit(
                "receive_message",
                chat_socket_payload("Moderator", reminder),
                room=room_id,
            )

        # t=13m → 2 minutes remaining
        time.sleep(4 * 60)
        room = get_room(room_id)
        if room and room.get("status") == "active":
            urgent = (
                "⚠️ **2 minutes remaining!** Please **submit your final ranking of all 12 items** now."
            )
            add_message(room_id, "Moderator", urgent, "system")
            socketio.emit(
                "receive_message",
                chat_socket_payload("Moderator", urgent),
                room=room_id,
            )
            try:
                socketio.emit(
                    "force_ranking_modal",
                    {"room_id": room_id},
                    room=room_id,
                )
            except Exception as e:
                logger.warning("force_ranking_modal emit failed: %s", e)

        # t=15m → time's up
        time.sleep(2 * 60)
        room = get_room(room_id)
        if room and room.get("status") == "active":
            final_msg = (
                "⏰ **Time's up.** This session is ending—thank you for participating."
            )
            add_message(room_id, "Moderator", final_msg, "system")
            socketio.emit(
                "receive_message",
                chat_socket_payload("Moderator", final_msg),
                room=room_id,
            )
            time.sleep(2)
            try:
                handle_end_session({"room_id": room_id, "sender": "system"})
            except Exception as e:
                logger.error("Auto handle_end_session failed: %s", e)

    thread = threading.Thread(target=timer_loop, daemon=True)
    thread.start()
    research_timers[room_id] = thread
    logger.info(f"⏰ Research timer started for room {room_id} (15 minutes, RQ4 milestones)")

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

        task_data = resolve_task_data_from_room(room)
        pin_task_data_for_room(room_id, task_data)

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
        if task_data:
            intro = get_story_intro_html(task_data)
            logger.info(f"📋 Sending task intro (HTML) to room {room_id}")

            add_message(
                room_id=room_id,
                username="Moderator",
                message=intro,
                message_type="task",
                metadata={"content_format": "html", "kind": "task_intro"},
            )

            socketio.emit(
                "receive_message",
                chat_socket_payload(
                    "Moderator",
                    intro,
                    content_format="html",
                    message_type="task",
                ),
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
        # Per-user cooldown for silence invites (re-invite allowed after gap; avoids one-and-done bug)
        last_silent_invite_at: Dict[str, float] = {}
        silent_followup_sent: Set[str] = set()
        # Track last time we sent a dominance message for each user
        last_dominance_message: Dict[str, float] = {}
        
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
                msgs_for_ratio = get_chat_history(room_id, limit=100)
                mod_ratio = _active_moderator_student_msg_ratio(msgs_for_ratio)
                skip_nonessential = mod_ratio > 0.20
                if skip_nonessential:
                    logger.debug(
                        "Moderator/student msg ratio %.2f — skipping non-essential nudges",
                        mod_ratio,
                    )

                # Get actual participants (excluding Moderator)
                all_participants = get_participants(room_id)
                participant_names = [p['username'] for p in all_participants if p['username'] != 'Moderator']
                
                # If less than 3 participants, skip (shouldn't happen but just in case)
                if len(participant_names) < 3:
                    continue

                td_active = get_pinned_or_resolve_task_data(room_id)
                canonical_items = get_task_items(td_active)
                n_target = len(canonical_items) or 12

                _aux_template = {
                    "last_progress_summary_time": now,
                    "last_summary_discussed_len": 0,
                    "statement_attribution": {},
                    "last_attr_msg_id": None,
                    "last_turn_balance_msg_id": None,
                    "last_conflict_deescalation_id": None,
                    "last_drift_nudge_time": 0.0,
                    "last_at_mod_reply_for_msg_id": None,
                    "last_appreciation_sent": 0.0,
                }
                aux = room_active_moderator_aux.setdefault(room_id, dict(_aux_template))
                for _k, _v in _aux_template.items():
                    aux.setdefault(_k, _v)

                if messages:
                    lm = messages[-1]
                    mid = str(lm.get("id", ""))
                    if mid and mid != str(aux.get("last_attr_msg_id") or ""):
                        if lm.get("username") not in ("Moderator", "System"):
                            record_first_mention(
                                aux["statement_attribution"],
                                lm.get("username"),
                                lm.get("message") or "",
                                canonical_items,
                            )
                        aux["last_attr_msg_id"] = mid

                streak_user, streak = trailing_student_streak(messages)
                last_mid = str(messages[-1].get("id", "")) if messages else ""
                if (
                    not skip_nonessential
                    and streak >= 3
                    and streak_user
                    and last_mid
                    and last_mid != str(aux.get("last_turn_balance_msg_id") or "")
                    and now - last_intervention_time > 45
                ):
                    others = [p for p in participant_names if p != streak_user]
                    if others:
                        force_response = random.choice(
                            [
                                f"{streak_user}, you've made several points—let's hear from "
                                f"{others[0]} on the ranking too.",
                                f"Thanks {streak_user}—{others[0]}, what's your read on the next priorities?",
                            ]
                        )
                        add_message(room_id, "Moderator", force_response, "moderator")
                        socketio.emit(
                            "receive_message",
                            chat_socket_payload("Moderator", force_response),
                            room=room_id,
                        )
                        log_moderator_intervention(
                            room_id, "force_turn_balance", streak_user
                        )
                        aux["last_turn_balance_msg_id"] = last_mid
                        last_intervention_time = now

                # RQ2: Tone / conflict de-escalation (fast, <~1 min after tense exchange)
                last_stu = next(
                    (
                        m
                        for m in reversed(messages)
                        if m.get("username") not in ("Moderator", "System", None, "")
                    ),
                    None,
                )
                if last_stu and now - last_intervention_time > 50:
                    mid_c = str(last_stu.get("id", ""))
                    tense = message_suggests_interpersonal_conflict(
                        last_stu.get("message", "")
                    ) or recent_multispeaker_tension(messages)
                    if tense and mid_c and mid_c != str(
                        aux.get("last_conflict_deescalation_id") or ""
                    ):
                        aux["last_conflict_deescalation_id"] = mid_c
                        line = enforce_response_length(
                            "I'm hearing some friction—let's keep this respectful and collaborative. "
                            "Can each of you offer **one** concrete change to your **12-item** ranking?",
                            55,
                        )
                        add_message(room_id, "Moderator", line, "moderator")
                        socketio.emit(
                            "receive_message",
                            chat_socket_payload("Moderator", line),
                            room=room_id,
                        )
                        log_moderator_intervention(
                            room_id,
                            "conflict_resolution",
                            last_stu.get("username"),
                        )
                        last_intervention_time = now

                # RQ4: Refocus when chat drifts off ranking / items (at most ~every 2 min)
                if (
                    not skip_nonessential
                    and time_elapsed >= 4
                    and discussion_appears_off_task(messages, canonical_items)
                    and now - float(aux.get("last_drift_nudge_time") or 0) > 120
                    and now - last_intervention_time > 55
                ):
                    aux["last_drift_nudge_time"] = now
                    line = enforce_response_length(
                        "Quick refocus: you need **one agreed order for all 12 desert items** (1 = most important). "
                        "Which position is the group most uncertain about?",
                        50,
                    )
                    add_message(room_id, "Moderator", line, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", line),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "discussion_drift", None)
                    last_intervention_time = now
                
                # ===== ACTIVE MODERATOR RULES =====
                
                # RULE 1: Check for dominance (>50% of recent messages)
                if now - last_dominance_check > 30:  # Check every 30 seconds
                    dominant_user = check_dominance(room_id)
                    
                    # Only trigger if:
                    # 1. A dominant user is detected
                    # 2. We haven't intervened in the last 60 seconds (cooldown)
                    # 3. The dominant user is actually in the room
                    # 4. We haven't sent a dominance message to this user in the last 2 minutes
                    if (
                        not skip_nonessential
                        and dominant_user and 
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
                            socketio.emit(
                                "receive_message",
                                chat_socket_payload("Moderator", response),
                                room=room_id,
                            )
                            
                            # Log intervention for research
                            log_moderator_intervention(room_id, "balance_dominance", dominant_user)
                            last_intervention_time = now
                            last_dominance_message[dominant_user] = now
                            
                            logger.info(f"✅ Sent dominance balance message for {dominant_user}")
                    
                    last_dominance_check = now
                
                # RULE 2: Silence (2 min) + optional follow-up (3+ min idle after first ping)
                if now - last_silence_check > 30:
                    silence_handled = False
                    follow = check_silent_followup_candidate(
                        room_id,
                        participant_names,
                        last_silent_invite_at,
                        silent_followup_sent,
                        now,
                    )
                    if (
                        follow
                        and follow in participant_names
                        and (now - last_intervention_time > 45)
                    ):
                        line_fu = _pick_phrase(_ACTIVE_FOLLOWUP_LINES, follow)
                        add_message(room_id, "Moderator", line_fu, "moderator")
                        socketio.emit(
                            "receive_message",
                            chat_socket_payload("Moderator", line_fu),
                            room=room_id,
                        )
                        log_moderator_intervention(
                            room_id, "invite_silent_followup", follow
                        )
                        silent_followup_sent.add(follow)
                        last_intervention_time = now
                        silence_handled = True
                        logger.info("✅ Silence follow-up to %s", follow)

                    if not silence_handled:
                        silent_user = check_silence(room_id)
                        if (
                            not silent_user
                            and len(messages) >= 8
                            and len(participant_names) >= 3
                        ):
                            counts = {p: 0 for p in participant_names}
                            for m in messages:
                                u = m.get("username")
                                if u in counts:
                                    counts[u] += 1
                            if len([u for u in participant_names if counts[u] > 0]) >= 2:
                                lag = min(participant_names, key=lambda u: counts[u])
                                hi, lo = max(counts.values()), counts[lag]
                                if hi - lo >= 3:
                                    last_ts: Optional[float] = None
                                    for m in reversed(messages):
                                        if m.get("username") == lag:
                                            try:
                                                last_ts = datetime.fromisoformat(
                                                    m["created_at"].replace(
                                                        "Z", "+00:00"
                                                    )
                                                ).timestamp()
                                            except Exception:
                                                last_ts = now
                                            break
                                    if last_ts is not None and (now - last_ts) >= 120:
                                        if (
                                            now - last_silent_invite_at.get(lag, 0)
                                        ) > SILENCE_REINVITE_GAP_SECONDS:
                                            silent_user = lag
                                            logger.info(
                                                "🤫 Lagging participant: %s (%s vs %s msgs)",
                                                lag,
                                                lo,
                                                hi,
                                            )

                        if (
                            silent_user
                            and silent_user in participant_names
                            and (now - last_intervention_time > 60)
                            and (
                                now - last_silent_invite_at.get(silent_user, 0)
                                > SILENCE_REINVITE_GAP_SECONDS
                            )
                        ):

                            logger.info("🤫 Silence detected: %s", silent_user)

                            response = generate_active_moderator_response(
                                participants=participant_names,
                                chat_history=[
                                    {
                                        "sender": m["username"],
                                        "message": m["message"],
                                    }
                                    for m in messages
                                ],
                                task_context="Desert survival ranking",
                                time_elapsed=time_elapsed,
                                last_intervention_time=int(
                                    now - last_intervention_time
                                ),
                                dominance_detected=None,
                                silent_user=silent_user,
                            )

                            if not response or len(response) < 10:
                                response = _pick_phrase(
                                    _ACTIVE_INVITE_LINES, silent_user
                                )

                            add_message(room_id, "Moderator", response, "moderator")
                            socketio.emit(
                                "receive_message",
                                chat_socket_payload("Moderator", response),
                                room=room_id,
                            )

                            log_moderator_intervention(
                                room_id, "invite_silent", silent_user
                            )
                            last_silent_invite_at[silent_user] = now
                            last_intervention_time = now
                            logger.info("✅ Sent invitation to %s", silent_user)

                    last_silence_check = now
                
                # RULE 3: Time-based prompts — single 5- and 1-min messages, ALL 12 items (deduped with research timer)
                if (
                    time_remaining <= 5
                    and time_remaining > 4
                    and now - last_intervention_time > 60
                    and claim_session_time_warning(room_id, "5")
                ):
                    response = (
                        f"⚠️ **{int(time_remaining)} minutes remaining!** Please finalize your **complete ranking of all 12 items** "
                        "from most important **(1)** to least important **(12)**."
                    )
                    add_message(room_id, "Moderator", response, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", response),
                        room=room_id,
                    )
                    
                    log_moderator_intervention(room_id, "time_warning", None)
                    last_intervention_time = now
                    logger.info(
                        f"✅ Sent time warning: {time_remaining} minutes remaining"
                    )

                if (
                    time_remaining <= 1
                    and time_remaining > 0
                    and now - last_intervention_time > 30
                    and claim_session_time_warning(room_id, "1")
                ):
                    response = (
                        "⏰ **Last minute!** Please submit your **full ranking of all 12 items** now."
                    )
                    add_message(room_id, "Moderator", response, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", response),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "time_warning_1m", None)
                    last_intervention_time = now
                    logger.info("✅ Sent 1-minute warning (active)")
                    try:
                        socketio.emit(
                            "force_ranking_modal",
                            {"room_id": room_id},
                            room=room_id,
                        )
                    except Exception as fe:
                        logger.warning("force_ranking_modal (1m active): %s", fe)
                
                # RULE 4: Answer questions about the task
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    if last_msg.get('username') != 'Moderator':
                        lm_id_q = str(last_msg.get("id", ""))
                        handled_at_mod = lm_id_q and lm_id_q == str(
                            aux.get("last_at_mod_reply_for_msg_id") or ""
                        )
                        if not handled_at_mod:
                            msg_content = last_msg.get('message', '').lower()

                            # Check if it's a question (contains ? or question words)
                            is_question = False
                            if '?' in msg_content:
                                is_question = True
                            else:
                                question_words = ['what', 'how', 'why', 'when', 'where', 'which', 'who',
                                                 'explain', 'help', 'confused', 'not sure', 'do we', 'should we',
                                                 'can you', 'could you', 'would you', 'tell me', 'guide']
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

                            if is_question and (
                                "@moderator" in msg_content or (now - last_intervention_time > 30)
                            ):
                                logger.info(f"❓ Question detected from {last_msg.get('username')}: {msg_content[:100]}...")

                                response = generate_active_moderator_response(
                                    participants=participant_names,
                                    chat_history=[{"sender": m['username'], "message": m['message']} for m in messages],
                                    task_context="Desert survival ranking",
                                    time_elapsed=time_elapsed,
                                    last_intervention_time=int(now - last_intervention_time),
                                    dominance_detected=None,
                                    silent_user=None
                                )

                                if response and len(response.strip()) > 10:
                                    add_message(room_id, "Moderator", response.strip(), "moderator")
                                    socketio.emit(
                                        "receive_message",
                                        chat_socket_payload("Moderator", response.strip()),
                                        room=room_id,
                                    )

                                    log_moderator_intervention(room_id, "answered_question", last_msg.get('username'))
                                    last_intervention_time = now
                                    logger.info(f"✅ Answered question from {last_msg.get('username')}: {response[:100]}...")
                                else:
                                    fallback = "Your task is to rank the 12 desert survival items from most important (1) to least important (12). Discuss with your group and agree on a final ranking."

                                    if 'time' in msg_content or 'minute' in msg_content:
                                        fallback = f"You have about {time_remaining} minutes remaining to complete the ranking task."
                                    elif 'item' in msg_content or 'rank' in msg_content:
                                        fallback = "You need to rank the 12 items from most important (1) to least important (12) for desert survival. Discuss with your group and reach consensus."

                                    add_message(room_id, "Moderator", fallback, "moderator")
                                    socketio.emit(
                                        "receive_message",
                                        chat_socket_payload("Moderator", fallback),
                                        room=room_id,
                                    )

                                    log_moderator_intervention(room_id, "answered_question_fallback", last_msg.get('username'))
                                    last_intervention_time = now
                                    logger.info(f"✅ Sent fallback answer to {last_msg.get('username')}")

                # RULE 4.25: Brief appreciation for substantive item-focused reasoning (low frequency)
                _app_sub = (
                    "because",
                    "since",
                    "rank",
                    "important",
                    "survival",
                    "mirror",
                    "water",
                    "tarp",
                    "sheet",
                    "compass",
                    "knife",
                    "flashlight",
                    "parachute",
                    "matches",
                    "coat",
                )
                if (
                    not skip_nonessential
                    and messages
                    and messages[-1].get("username") not in ("Moderator", "System", None, "")
                    and now - float(aux.get("last_appreciation_sent") or 0) > 95
                    and now - last_intervention_time > 55
                ):
                    _lm = messages[-1]
                    _lc = (_lm.get("message") or "").lower()
                    if len(_lc) >= 38 and any(s in _lc for s in _app_sub):
                        _resp_ap = generate_active_moderator_response(
                            participants=participant_names,
                            chat_history=[
                                {"sender": m["username"], "message": m["message"]}
                                for m in messages
                            ],
                            task_context="Desert survival ranking",
                            time_elapsed=time_elapsed,
                            last_intervention_time=int(now - last_intervention_time),
                            dominance_detected=None,
                            silent_user=None,
                        )
                        if _resp_ap and len(_resp_ap.strip()) > 12:
                            add_message(
                                room_id, "Moderator", _resp_ap.strip(), "moderator"
                            )
                            socketio.emit(
                                "receive_message",
                                chat_socket_payload("Moderator", _resp_ap.strip()),
                                room=room_id,
                            )
                            log_moderator_intervention(
                                room_id,
                                "appreciation",
                                _lm.get("username"),
                            )
                            aux["last_appreciation_sent"] = now
                            last_intervention_time = now
                            logger.info(
                                "✅ Appreciation nudge after message from %s",
                                _lm.get("username"),
                            )

                # RULE 4.5: Occasional expert survival perspective when a specific item is discussed
                if (
                    not skip_nonessential
                    and messages
                    and len(messages) > 0
                ):
                    tip_msg = messages[-1]
                    if tip_msg.get("username") != "Moderator":
                        raw_tip = tip_msg.get("message", "")
                        low_tip = raw_tip.lower()
                        tip_fingerprint = (
                            f"{tip_msg.get('username')}|{tip_msg.get('created_at', '')}|{raw_tip[:160]}"
                        )
                        if room_expert_tip_message_key.get(room_id) != tip_fingerprint:
                            for item_label in canonical_items:
                                il = item_label.lower()
                                if len(il) >= 6 and il in low_tip:
                                    room_expert_tip_message_key[room_id] = tip_fingerprint
                                    opinion = get_expert_ranking_opinion(item_label)
                                    if opinion and (
                                        now - room_last_expert_tip.get(room_id, 0) > 90
                                    ) and (now - last_intervention_time > 50):
                                        ikey = il[:48]
                                        orig = aux["statement_attribution"].get(ikey)
                                        spk = tip_msg.get("username")
                                        prefix = ""
                                        if orig and orig != spk:
                                            prefix = f"As **{orig}** raised that item, "
                                        response = (
                                            prefix
                                            + f"📚 Expert perspective on “{item_label}”: {opinion}\n\n"
                                            "How does that fit with your group's ranking so far?"
                                        )
                                        add_message(
                                            room_id,
                                            "Moderator",
                                            response,
                                            "moderator",
                                        )
                                        socketio.emit(
                                            "receive_message",
                                            chat_socket_payload("Moderator", response),
                                            room=room_id,
                                        )
                                        log_moderator_intervention(
                                            room_id,
                                            "expert_item_hint",
                                            tip_msg.get("username"),
                                        )
                                        room_last_expert_tip[room_id] = now
                                        last_intervention_time = now
                                        logger.info(
                                            f"📚 Expert hint for item: {item_label[:50]}"
                                        )
                                    break
                
                # RULE 5: Periodic progress recap (every 5 min clock OR 3+ newly discussed items)
                discussed = collect_discussed_canonical_items(messages, canonical_items)
                time_since_recap = now - aux["last_progress_summary_time"]
                new_since_recap = len(discussed) - aux["last_summary_discussed_len"]
                if (
                    not skip_nonessential
                    and (time_since_recap >= 300 or new_since_recap >= 3)
                    and (now - last_intervention_time > 60)
                ):
                    mins = max(1, int(time_since_recap // 60))
                    summary_lines = [
                        "📊 **Progress update** (quick recap):",
                        f"- About **{mins}** min since the last progress check.",
                    ]
                    if discussed:
                        preview = ", ".join(sorted(discussed)[:5])
                        if len(discussed) > 5:
                            preview += "…"
                        summary_lines.append(
                            f"- Items clearly on the table in chat: {preview}"
                        )
                    gap = max(0, n_target - len(discussed))
                    summary_lines.append(
                        f"- Rough gauge: **{gap}** list item(s) not clearly discussed yet."
                    )
                    summary_lines.append(
                        f"- ⏰ About **{int(time_remaining)}** min left in the session."
                    )
                    summary = "\n".join(summary_lines)
                    add_message(room_id, "Moderator", summary, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", summary),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "progress_summary", None)
                    last_intervention_time = now
                    aux["last_progress_summary_time"] = now
                    aux["last_summary_discussed_len"] = len(discussed)
                    logger.info("✅ Sent structured progress summary")
                
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
# PASSIVE MODERATOR — ultra-minimal (research condition)
# ============================================================
def _passive_dedupe_key(msg: Dict[str, Any]) -> str:
    """Stable id for deduping @moderator handling when DB id is missing."""
    mid = msg.get("id")
    if mid is not None and str(mid).strip() and str(mid) != "None":
        return str(mid)
    return "|".join(
        [
            str(msg.get("username") or ""),
            str(msg.get("created_at") or ""),
            (msg.get("message") or "")[:120],
        ]
    )


def start_passive_moderator(room_id: str):
    """Ultra-minimal: only @moderator (dynamic LLM) + one deduped 5-minute warning."""

    def monitor_loop():
        logger.info(f"🔴 PASSIVE moderator (minimal) for room {room_id}")
        # Do not use a single low cap for @moderator + warning — that silenced all pings after a few turns.
        passive_at_mention_replies = 0
        PASSIVE_MAX_AT_MENTIONS = 40
        last_passive_handled_key: Optional[str] = None
        five_min_warning_logged = False

        while True:
            try:
                time.sleep(3)

                room = get_room(room_id)
                if not room or room.get("story_finished") or room.get("status") == "completed":
                    logger.info(f"⏹️ Passive moderator stopped for room {room_id}")
                    break

                now = time.time()
                time_elapsed = 0
                created_at_val = room.get("created_at")
                if created_at_val:
                    try:
                        if isinstance(created_at_val, str):
                            cv = created_at_val.replace("Z", "+00:00")
                            created_at_dt = datetime.fromisoformat(cv)
                            time_elapsed = int((now - created_at_dt.timestamp()) / 60)
                        elif isinstance(created_at_val, (int, float)):
                            time_elapsed = int((now - float(created_at_val)) / 60)
                    except Exception:
                        time_elapsed = 0
                time_elapsed = max(0, time_elapsed)
                time_remaining = max(0, 15 - time_elapsed)

                all_parts = get_participants(room_id)
                participant_names = [
                    p["username"]
                    for p in all_parts
                    if p.get("username") not in ("Moderator", "System", None, "")
                ]

                messages = get_chat_history(room_id, limit=40)
                if messages:
                    last_msg = messages[-1]
                    dkey = _passive_dedupe_key(last_msg)
                    if last_msg.get("username") not in ("Moderator", "System"):
                        body = (last_msg.get("message") or "").lower()
                        if (
                            "@moderator" in body
                            and dkey
                            and dkey != last_passive_handled_key
                        ):
                            if passive_at_mention_replies >= PASSIVE_MAX_AT_MENTIONS:
                                logger.warning(
                                    "⚠️ Passive @moderator cap reached for room %s",
                                    room_id,
                                )
                            else:
                                last_passive_handled_key = dkey
                                passive_at_mention_replies += 1

                                chat_for_llm = [
                                    {
                                        "sender": m.get("username") or "?",
                                        "message": m.get("message") or "",
                                    }
                                    for m in messages
                                    if m.get("username") not in ("Moderator", "System", None, "")
                                ]

                                resp = generate_passive_moderator_response(
                                    participants=participant_names,
                                    chat_history=chat_for_llm,
                                    last_user_message=last_msg.get("message") or "",
                                    time_elapsed=time_elapsed,
                                )
                                if not resp or len(resp.strip()) < 4:
                                    nitems = len(
                                        get_task_items(
                                            get_pinned_or_resolve_task_data(room_id)
                                        )
                                    )
                                    resp = (
                                        f"Rank all **{nitems}** items from most important (**1**) to least "
                                        f"(**{nitems}**). About **{int(time_remaining)}** min left."
                                    )

                                add_message(room_id, "Moderator", resp, "moderator")
                                socketio.emit(
                                    "receive_message",
                                    chat_socket_payload("Moderator", resp),
                                    room=room_id,
                                )
                                log_moderator_intervention(
                                    room_id,
                                    "passive_at_mention",
                                    last_msg.get("username"),
                                )
                                logger.info(
                                    "✅ Passive LLM reply to %s",
                                    last_msg.get("username"),
                                )
                            continue

                if (
                    4 < time_remaining <= 5
                    and not five_min_warning_logged
                    and claim_session_time_warning(room_id, "5")
                ):
                    five_min_warning_logged = True
                    warning = (
                        "⚠️ **5 minutes remaining!** Finalize your **complete ranking of all 12 items** "
                        "(1 = most important, 12 = least)."
                    )
                    add_message(room_id, "Moderator", warning, "system")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", warning),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "time_warning_passive", None)
                    time.sleep(55)

            except Exception as e:
                logger.error(f"❌ Passive moderator error: {e}")
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

def _room_created_timestamp(room: Optional[Dict]) -> float:
    """Unix time for room creation (fallback: now)."""
    if not room:
        return time.time()
    created_at_val = room.get("created_at")
    if not created_at_val:
        return time.time()
    try:
        if isinstance(created_at_val, str):
            return datetime.fromisoformat(
                created_at_val.replace("Z", "+00:00")
            ).timestamp()
        if isinstance(created_at_val, (int, float)):
            return float(created_at_val)
    except Exception:
        pass
    return time.time()


def check_silence(room_id: str) -> Optional[str]:
    """
    Triad rule: invite only if a participant has been quiet for SILENCE_THRESHOLD_SECONDS.
    Per-user idle = time since their last student message; members who never spoke use
    time since room creation until their first message exists.
    """
    participants = get_participants(room_id)
    student_names = [
        p["username"]
        for p in participants
        if p.get("username") and p["username"] not in ("Moderator", "System")
    ]
    if len(student_names) < 3:
        return None

    messages = get_chat_history(room_id, limit=500)
    now = time.time()
    room = get_room(room_id)
    session_start = _room_created_timestamp(room)

    last_student_msg_ts: Dict[str, float] = {}
    for msg in messages:
        u = msg.get("username")
        if u in ("Moderator", "System", None, ""):
            continue
        try:
            ts = datetime.fromisoformat(
                msg["created_at"].replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            continue
        if u not in last_student_msg_ts or ts > last_student_msg_ts[u]:
            last_student_msg_ts[u] = ts

    best_user: Optional[str] = None
    best_idle = -1.0
    for name in student_names:
        last_ts = last_student_msg_ts.get(name)
        if last_ts is None:
            idle = now - session_start
        else:
            idle = now - last_ts
        if idle < SILENCE_THRESHOLD_SECONDS:
            continue
        if idle > best_idle:
            best_idle = idle
            best_user = name

    return best_user


def check_silent_followup_candidate(
    room_id: str,
    participant_names: List[str],
    last_invite_at: Dict[str, float],
    followup_done: Set[str],
    now: float,
) -> Optional[str]:
    """
    Second nudge: person was invited once, still idle ≥ SILENCE_FOLLOWUP_SECONDS,
    ≥75s since last silence message to them, follow-up not yet sent.
    """
    if len(participant_names) < 3:
        return None
    messages = get_chat_history(room_id, limit=500)
    room = get_room(room_id)
    session_start = _room_created_timestamp(room)
    last_student_msg_ts: Dict[str, float] = {}
    for msg in messages:
        u = msg.get("username")
        if u in ("Moderator", "System", None, ""):
            continue
        try:
            ts = datetime.fromisoformat(
                msg["created_at"].replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            continue
        if u not in last_student_msg_ts or ts > last_student_msg_ts[u]:
            last_student_msg_ts[u] = ts

    best: Optional[str] = None
    best_idle = -1.0
    for name in participant_names:
        if name not in last_invite_at or name in followup_done:
            continue
        if now - last_invite_at.get(name, 0) < 75:
            continue
        last_ts = last_student_msg_ts.get(name)
        idle = (now - session_start) if last_ts is None else (now - last_ts)
        if idle < float(SILENCE_FOLLOWUP_SECONDS):
            continue
        if idle > best_idle:
            best_idle = idle
            best = name
    return best


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
        
        td = get_room_task_data(room_id) or get_data()
        comparison = compare_with_expert_ranking(ranking, td)
        logger.info(f"📈 Ranking accuracy: {comparison['accuracy_percentage']:.1f}%")
        # RQ1–RQ5 room-level metrics are persisted in handle_end_session (single canonical row + participant_metrics)
        
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

        task_data = get_data()
        story_id = task_data.get("task_id") or "desert_survival_plane_crash"
        logger.info(f"📚 Using task: {story_id}")

        # Get or create room
        room = get_or_create_room(mode=mode, story_id=story_id)
        room_id = room['id']
        pin_task_data_for_room(room_id, resolve_task_data_from_room(room))

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


@app.route("/api/desert-items")
def get_desert_items_api():
    """Item list for UI; use ?room_id= for the exact strings pinned to that session."""
    room_id = (request.args.get("room_id") or "").strip()
    if room_id:
        bundle = get_canonical_items_for_room(room_id)
        items = bundle["items"]
        return jsonify(
            {
                "items": items,
                "count": len(items),
                "task_id": bundle.get("task_id"),
                "task_name": bundle.get("task_name"),
            }
        )
    items = get_task_items()
    return jsonify({"items": items, "count": len(items)})


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
        story_id = story_data.get("task_id") or "desert_survival_plane_crash"

        from supabase_client import create_room
        room = create_room(mode=mode, story_id=story_id)
        room_id = room['id']
        pin_task_data_for_room(room_id, story_data)

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
                    chat_socket_payload("Moderator", WELCOME_MESSAGE),
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

        pin_task_data_for_room(room_id, resolve_task_data_from_room(room))

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
                "id": str(msg["id"]) if msg.get("id") is not None else None,
                "sender": msg["username"],
                "message": msg["message"],
                "timestamp": msg["created_at"],
                "message_type": mtype,
            }
            if meta.get("flagged"):
                entry["flagged"] = True
            if meta.get("content_format"):
                entry["content_format"] = meta["content_format"]
            if meta.get("flag_reason"):
                entry["flag_reason"] = meta["flag_reason"]
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

            saved_row = add_message(
                room_id=room_id,
                username=sender,
                message=msg,
                message_type="chat_flagged",
                metadata={
                    "word_count": word_count,
                    "flagged": True,
                    "bad_words": bad_words,
                    "severity": severity,
                    "flag_reason": "inappropriate language",
                },
            )

            emit(
                "receive_message",
                chat_socket_payload(
                    sender,
                    msg,
                    id=str(saved_row.get("id", f"{room_id}_{sender}_{int(time.time() * 1000)}")),
                    flagged=True,
                    flag_reason="inappropriate language",
                ),
                room=room_id,
            )
            logger.info(f"✅ Flagged message from {sender} broadcast (severity={severity})")

            if severity == "HIGH":
                resolution = enforce_response_length(
                    "Let's reset tone and refocus on collaboration—which **item** in your **12-item list** "
                    "should the group settle next, and why?",
                    45,
                )
                add_message(room_id, "Moderator", resolution, "moderator")
                socketio.emit(
                    "receive_message",
                    chat_socket_payload("Moderator", resolution),
                    room=room_id,
                )
                log_moderator_intervention(room_id, "conflict_resolution", sender)
            return

        saved_chat = add_message(
            room_id=room_id,
            username=sender,
            message=msg,
            message_type="chat",
            metadata={"word_count": word_count},
        )

        emit(
            "receive_message",
            chat_socket_payload(
                sender,
                msg,
                id=str(saved_chat.get("id", f"{room_id}_{sender}_{int(time.time() * 1000)}")),
            ),
            room=room_id,
        )

        if room.get("mode") == "active" and "@moderator" in msg.lower():
            try:
                te = _room_minutes_elapsed(room)
                participants = get_participants(room_id)
                participant_names = [
                    p["username"]
                    for p in participants
                    if p.get("username") not in ("Moderator", "System", None, "")
                ]
                hist_msgs = get_chat_history(room_id, limit=45)
                chat_history = [
                    {"sender": m["username"], "message": m.get("message", "")}
                    for m in hist_msgs
                ]
                response = generate_active_moderator_response(
                    participants=participant_names,
                    chat_history=chat_history,
                    task_context="Desert survival ranking",
                    time_elapsed=te,
                    last_intervention_time=0,
                    dominance_detected=None,
                    silent_user=None,
                )
                rsp = (response or "").strip()
                if len(rsp) > 8:
                    add_message(room_id, "Moderator", rsp, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", rsp),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "active_at_mention", sender)
                    _aux_inline = room_active_moderator_aux.setdefault(room_id, {})
                    _aux_inline["last_at_mod_reply_for_msg_id"] = str(
                        saved_chat.get("id", "")
                    )
            except Exception as atmod_ex:
                logger.error("Active @moderator inline reply failed: %s", atmod_ex)

        try:
            td = get_pinned_or_resolve_task_data(room_id)
            items = get_task_items(td)
            clar = clarify_alias_against_list(msg, items)
            if clar:
                nowc = time.time()
                if nowc - last_item_clarification_at.get(room_id, 0) > 90:
                    last_item_clarification_at[room_id] = nowc
                    add_message(room_id, "Moderator", clar, "moderator")
                    socketio.emit(
                        "receive_message",
                        chat_socket_payload("Moderator", clar),
                        room=room_id,
                    )
                    log_moderator_intervention(room_id, "item_clarification", sender)
        except Exception as clar_ex:
            logger.debug(f"Item clarification skipped: {clar_ex}")

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
        
        _non_participant = {"Moderator", "System"}
        participant_messages = [
            m for m in full_chat_history if m.get("username") not in _non_participant
        ]
        
        # ===== 3. CALCULATE RESEARCH METRICS =====
        # Include every enrolled student (0 messages if silent) for RQ1/RQ3 inclusion metrics.
        student_usernames = [
            p.get("username")
            for p in participants
            if p.get("username") and p.get("username") not in _non_participant
        ]
        message_counts = {u: 0 for u in student_usernames}
        word_counts = {u: 0 for u in student_usernames}
        for msg in participant_messages:
            username = msg.get("username")
            if username not in message_counts:
                message_counts[username] = 0
                word_counts[username] = 0
            message_counts[username] = message_counts.get(username, 0) + 1
            wc = len(msg.get("message", "").split())
            word_counts[username] = word_counts.get(username, 0) + wc
        
        total_messages = sum(message_counts.values())
        total_words = sum(word_counts.values())
        
        speaking_shares = {}
        if total_messages > 0:
            for user, count in message_counts.items():
                speaking_shares[user] = count / total_messages
        else:
            for user in message_counts:
                speaking_shares[user] = 0.0
        
        # Gini over speaking shares (including zeros for silent members)
        gini_coefficient = 0
        share_list = [speaking_shares[u] for u in sorted(speaking_shares.keys())]
        if len(share_list) >= 2:
            sorted_shares = sorted(share_list)
            n = len(sorted_shares)
            gini = 0.0
            for i, share in enumerate(sorted_shares):
                gini += (2 * i - n + 1) * share
            if sum(sorted_shares) > 0:
                gini_coefficient = gini / (n * sum(sorted_shares))
            gini_coefficient = max(0, min(gini_coefficient, 1))
        
        participation_entropy = calculate_entropy(share_list) if share_list else 0.0
        
        max_share = max(speaking_shares.values()) if speaking_shares else 0
        min_share = min(speaking_shares.values()) if speaking_shares else 0
        dominance_gap = max_share - min_share
        
        conflict_report = detect_conflict_episodes(room_id, full_chat_history)
        repair_times = [
            float(r["time_to_repair"])
            for r in conflict_report.get("repairs", [])
            if r.get("time_to_repair") is not None
        ]
        mean_time_to_repair = (
            sum(repair_times) / len(repair_times) if repair_times else None
        )
        
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
                "condition": room.get("mode"),
                "gini_coefficient": gini_coefficient,
                "participation_entropy": participation_entropy,
                "max_share": max_share,
                "min_share": min_share,
                "dominance_gap": dominance_gap,
                "total_messages": total_messages,
                "total_words": total_words,
                "conflict_count": conflict_report.get("conflict_count", 0),
                "repair_count": conflict_report.get("repair_count", 0),
                "repair_rate": conflict_report.get("repair_rate", 0.0),
                "ranking_submitted": bool(room.get("final_ranking")),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if mean_time_to_repair is not None:
                metrics_data["mean_time_to_repair_seconds"] = mean_time_to_repair
            
            # Add ranking accuracy if available
            if room.get('final_ranking'):
                from data_retriever import compare_with_expert_ranking

                ranking = json.loads(room.get('final_ranking'))
                td = get_room_task_data(room_id) or get_data()
                comparison = compare_with_expert_ranking(ranking, td)
                metrics_data["ranking_accuracy"] = comparison['accuracy_percentage']
            
            # Add time to consensus if available
            if time_to_consensus:
                metrics_data["time_to_consensus"] = time_to_consensus
            
            supabase.table("research_metrics").insert(metrics_data).execute()
            logger.info(f"📊 Saved research metrics for room {room_id}")
            
            metric_users = sorted(message_counts.keys())
            for user in metric_users:
                participant_data = {
                    "room_id": room_id,
                    "username": user,
                    "message_count": message_counts.get(user, 0),
                    "word_count": word_counts.get(user, 0),
                    "share_of_talk": speaking_shares.get(user, 0),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                supabase.table("participant_metrics").insert(participant_data).execute()

            if not metric_users:
                logger.info(
                    f"ℹ️ No enrolled participants in room {room_id} — skipping participant_metrics rows"
                )
            elif total_messages == 0:
                logger.info(
                    f"ℹ️ Room {room_id}: saved participant_metrics for {len(metric_users)} users "
                    f"(0 chat messages; shares and Gini reflect silence)"
                )
            else:
                logger.info(f"👥 Saved participant metrics for {len(metric_users)} users")

            try:
                analyze_conflict_episodes(room_id)
            except Exception as ex:
                logger.debug(f"Optional conflict_episodes persistence skipped: {ex}")

            try:
                inv_r = (
                    supabase.table("moderator_interventions")
                    .select("*")
                    .eq("room_id", room_id)
                    .execute()
                )
                rq5 = intervention_followup_seconds(
                    inv_r.data or [], full_chat_history, window_sec=180.0
                )
                logger.info("RQ5 intervention→student follow-up: %s", rq5)
            except Exception as rq5e:
                logger.debug("RQ5 latency summary skipped: %s", rq5e)
            
        except Exception as e:
            logger.error(f"❌ Failed to save research metrics: {e}")
        
        # ===== 5. GENERATE PERSONALIZED FEEDBACK =====
        chat_history_list = [
            {"sender": msg['username'], "message": msg['message']}
            for msg in full_chat_history
        ]

        def _row_meta(row: dict) -> dict:
            meta = row.get("metadata")
            if isinstance(meta, str):
                try:
                    return json.loads(meta) or {}
                except Exception:
                    return {}
            return meta or {}

        all_participants_data: List[dict] = []
        for participant in participants:
            un = participant.get("username")
            if un in ("Moderator", "System"):
                continue
            flagged_n = sum(
                1
                for m in participant_messages
                if m.get("username") == un and _row_meta(m).get("flagged")
            )
            all_participants_data.append(
                {
                    "name": participant.get("display_name", un),
                    "username": un,
                    "message_count": message_counts.get(un, 0),
                    "word_count": word_counts.get(un, 0),
                    "share_of_talk": speaking_shares.get(un, 0) * 100,
                    "toxic_count": flagged_n,
                }
            )

        all_participants_data.sort(
            key=lambda x: (x.get("message_count", 0), x.get("word_count", 0)),
            reverse=True,
        )

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
                        word_count=word_count,
                        share_of_talk=share_of_talk,
                        response_times=[],
                        story_progress=progress_percent,
                        hint_responses=0,
                        behavior_type=behavior_type,
                        toxic_count=inappropriate_count,
                        off_topic_count=0,
                        chat_history=chat_history_list,
                        story_context=task_context,
                        chat_sender_name=username,
                        all_participants_data=all_participants_data,
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