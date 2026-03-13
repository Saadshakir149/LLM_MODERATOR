"""
Supabase Client Configuration and Database Operations - COMPLETE FIXED VERSION
========================================================
This module handles all database interactions with Supabase.
Includes ALL functions for admin panel, session summaries, and exports.
"""

import os
import uuid
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("SUPABASE_CLIENT")

# ============================================================
# Supabase Configuration
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
logger.info(f"SUPABASE_URL exists: {bool(SUPABASE_URL)}")
logger.info(f"SUPABASE_KEY exists: {bool(SUPABASE_KEY)}")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env"
    )

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logger.info("✅ Supabase client initialized")

# ============================================================
# Room Operations
# ============================================================

def find_available_room(mode: str) -> Optional[Dict[str, Any]]:
    """
    Find a room with available space for the given mode.
    FIXED: Correctly checks participant_count against max_participants
    """
    try:
        # First get all waiting/active rooms
        response = (
            supabase.table("rooms")
            .select("*")
            .eq("mode", mode)
            .in_("status", ["waiting", "active"])
            .execute()
        )
        
        if not response.data:
            logger.info(f"ℹ️ No rooms found for mode: {mode}")
            return None
        
        # Filter rooms where participant_count < max_participants
        available_rooms = [
            room for room in response.data 
            if room.get('participant_count', 0) < room.get('max_participants', 3)
        ]
        
        if available_rooms:
            # Sort by created_at and return the oldest
            available_rooms.sort(key=lambda x: x.get('created_at', ''))
            room = available_rooms[0]
            logger.info(f"✅ Found available room: {room['id']} (status={room['status']}, participants={room.get('participant_count', 0)}/{room.get('max_participants', 3)})")
            return room

        logger.info(f"ℹ️ No available room found for mode: {mode}, will create new room")
        return None

    except Exception as e:
        logger.error(f"❌ Error finding available room: {e}")
        return None
    
def create_room(mode: str, story_id: Optional[str] = None, max_participants: int = 3, created_by: str = 'system') -> Dict[str, Any]:
    """Create a new room."""
    try:
        room_id = str(uuid.uuid4())
        
        room_data = {
            "id": room_id,
            "mode": mode,
            "story_id": story_id or "default-story",
            "status": "waiting",
            "participant_count": 0,
            "max_participants": max_participants,
            "current_chunk_index": 0,
            "story_finished": False,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = (
            supabase.table("rooms")
            .insert(room_data)
            .execute()
        )

        room = response.data[0]
        logger.info(f"✅ Created room: {room['id']} (mode: {mode}, max: {max_participants})")
        return room

    except Exception as e:
        logger.error(f"❌ Error creating room: {e}")
        raise

def get_room(room_id: str) -> Optional[Dict[str, Any]]:
    """Get room by ID."""
    try:
        response = (
            supabase.table("rooms")
            .select("*")
            .eq("id", room_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error getting room {room_id}: {e}")
        return None

def update_room_status(room_id: str, status: str):
    """Update room status."""
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if status == 'completed':
            update_data['ended_at'] = datetime.now(timezone.utc).isoformat()
            update_data['story_finished'] = True
        
        supabase.table("rooms").update(update_data).eq("id", room_id).execute()
        logger.info(f"Updated room {room_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating room status: {e}")

def update_room_participant_count(room_id: str, new_count: int):
    """Update participant count in room - FIXED VERSION"""
    try:
        # ✅ FIX: Always get the ACTUAL unique count
        participants = get_participants(room_id)
        actual_count = len(set([p['username'] for p in participants]))
        
        supabase.table("rooms").update({
            "participant_count": actual_count,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", room_id).execute()
        
        logger.info(f"📊 Updated room {room_id} participant count to {actual_count}")
    except Exception as e:
        logger.error(f"Error updating participant count: {e}")


def update_room_chunk_index(room_id: str, chunk_index: int):
    """Update current chunk index for story progress."""
    try:
        supabase.table("rooms").update({
            "current_chunk_index": chunk_index,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", room_id).execute()
        logger.debug(f"Updated room {room_id} chunk index to {chunk_index}")
    except Exception as e:
        logger.error(f"Error updating chunk index: {e}")

# ============================================================
# Participant Operations
# ============================================================

def add_participant(
    room_id: str,
    username: str,
    socket_id: str,
    display_name: Optional[str] = None,
    
) -> Dict[str, Any]:
    """Add participant to room with proper display_name storage - FIXED VERSION"""
    try:
        # ✅ FIX: Check if participant already exists
        existing = get_participant_by_username(room_id, username)
        if existing:
            logger.info(f"👤 Participant {username} already exists, updating socket")
            # Update existing participant
            supabase.table("participants").update({
                'socket_id': socket_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', existing['id']).execute()
            return existing
        
        # Add new participant
        participant_data = {
            "room_id": room_id,
            "username": username,
            "socket_id": socket_id,
            "display_name": display_name or username,
        
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = (
            supabase.table("participants")
            .insert(participant_data)
            .execute()
        )

        participant = response.data[0]
        logger.info(f"✅ Added new participant {username} to room {room_id}")
        
        # ✅ FIX: Get accurate count of UNIQUE participants
        all_participants = get_participants(room_id)
        unique_count = len(set([p['username'] for p in all_participants]))
        
        # Update room participant count with UNIQUE count
        update_room_participant_count(room_id, unique_count)
        
        return participant

    except Exception as e:
        logger.error(f"❌ Error adding participant: {e}")
        raise

def get_next_participant_name(room_id: str) -> str:
    """Generate next available participant name."""
    try:
        response = (
            supabase.table("participants")
            .select("id")
            .eq("room_id", room_id)
            .execute()
        )
        count = len(response.data) if response.data else 0
        return f"Student {count + 1}"
    except Exception as e:
        logger.error(f"Error getting participant count: {e}")
        return "Student 1"

def get_participants(room_id: str) -> List[Dict[str, Any]]:
    """Get all participants in room with display names - FIXED VERSION"""
    try:
        response = (
            supabase.table("participants")
            .select("*")
            .eq("room_id", room_id)
            .order("joined_at", desc=False)
            .execute()
        )
        
        participants = response.data if response.data else []
        
        # ✅ FIX: Deduplicate by username (keep most recent)
        unique_participants = {}
        for p in participants:
            username = p.get('username')
            # Keep the most recent entry
            if username not in unique_participants or \
               p.get('joined_at', '') > unique_participants[username].get('joined_at', ''):
                unique_participants[username] = p
        
        result = list(unique_participants.values())
        
        # Ensure display_name is populated
        for p in result:
            if not p.get('display_name') and p.get('username'):
                p['display_name'] = p['username']
        
        logger.debug(f"📊 Room {room_id}: {len(result)} unique participants")
        return result
        
    except Exception as e:
        logger.error(f"Error getting participants: {e}")
        return []

def get_participants_with_details(room_id: str) -> List[Dict[str, Any]]:
    """Get participants with all details including usernames and display names for admin panel."""
    try:
        response = (
            supabase.table("participants")
            .select("id, username, display_name, socket_id, joined_at, anonymous_id")
            .eq("room_id", room_id)
            .order("joined_at", desc=False)
            .execute()
        )
        
        participants = response.data if response.data else []
        
        # Ensure display_name is populated
        for p in participants:
            if not p.get('display_name') and p.get('username'):
                p['display_name'] = p['username']
        
        logger.info(f"✅ Retrieved {len(participants)} participants with details for room {room_id}")
        return participants
        
    except Exception as e:
        logger.error(f"❌ Error getting participants with details: {e}")
        return []

def get_participant_by_socket(socket_id: str) -> Optional[Dict[str, Any]]:
    """Get participant by Socket.IO ID."""
    try:
        response = (
            supabase.table("participants")
            .select("*")
            .eq("socket_id", socket_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.debug(f"Participant not found for socket {socket_id}")
        return None

def get_participant_by_username(room_id: str, username: str) -> Optional[Dict[str, Any]]:
    """Get participant by username in a room - FIXED VERSION"""
    try:
        # Try exact match first
        response = (
            supabase.table("participants")
            .select("*")
            .eq("room_id", room_id)
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        
        if response.data:
            return response.data
            
        # If not found, try case-insensitive match
        all_participants = get_participants(room_id)
        for p in all_participants:
            if p.get('username', '').lower() == username.lower():
                return p
            if p.get('display_name', '').lower() == username.lower():
                return p
        
        logger.warning(f"⚠️ Participant {username} not found in room {room_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting participant by username: {e}")
        return None

# ============================================================
# Message Operations
# ============================================================

def add_message(
    room_id: str,
    username: str,
    message: str,
    message_type: str = "chat",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Add message to room with metadata support and word count."""
    try:
        # Calculate word count
        word_count = len(message.split())
        
        message_data = {
            "room_id": room_id,
            "username": username,
            "message": message,
            "message_type": message_type,
            "word_count": word_count,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if metadata:
            message_data['metadata'] = metadata
        
        response = (
            supabase.table("messages")
            .insert(message_data)
            .execute()
        )

        msg = response.data[0]
        logger.debug(f"📝 Added message from {username} in room {room_id} ({word_count} words)")
        return msg

    except Exception as e:
        logger.error(f"❌ Error adding message: {e}")
        raise

def get_chat_history(room_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get chat history for room."""
    try:
        query = (
            supabase.table("messages")
            .select("*")
            .eq("room_id", room_id)
            .order("created_at", desc=False)
        )
        if limit:
            query = query.limit(limit)
        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return []

def get_messages_for_export(room_id: str) -> List[Dict[str, Any]]:
    """Get all messages for export (with all fields)."""
    try:
        response = (
            supabase.table("messages")
            .select("id, username, message, message_type, created_at, metadata, word_count")
            .eq("room_id", room_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"❌ Error getting messages for export: {e}")
        return []

# ============================================================
# Session Operations
# ============================================================

def create_session(
    room_id: str,
    mode: str,
    participant_count: int,
    story_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create new session with enhanced data."""
    try:
        session_data = {
            "room_id": room_id,
            "mode": mode,
            "participant_count": participant_count,
            "story_id": story_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
            "message_count": 0,
            "last_activity": datetime.now(timezone.utc).isoformat()
        }
        
        response = (
            supabase.table("sessions")
            .insert(session_data)
            .execute()
        )
        session = response.data[0]
        logger.info(f"Created session {session['id']} for room {room_id}")
        return session
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise

def end_session(room_id: str, ended_by: str = 'system', end_reason: str = 'completed'):
    """End active session for room with details."""
    try:
        response = supabase.table("sessions").select("*").eq("room_id", room_id).is_("ended_at", "null").execute()
        
        if response.data and len(response.data) > 0:
            session = response.data[0]
            started_at = datetime.fromisoformat(session['started_at'].replace('Z', '+00:00'))
            ended_at = datetime.now(timezone.utc)
            duration_seconds = int((ended_at - started_at).total_seconds())
            
            # Get message count
            messages = get_chat_history(room_id)
            message_count = len(messages)
            
            update_data = {
                "ended_at": ended_at.isoformat(),
                "is_active": False,
                "ended_by": ended_by,
                "end_reason": end_reason,
                "duration_seconds": duration_seconds,
                "message_count": message_count
            }
            
            supabase.table("sessions").update(update_data).eq("room_id", room_id).is_("ended_at", "null").execute()
            logger.info(f"Ended session for room {room_id} (duration: {duration_seconds}s, messages: {message_count})")
    except Exception as e:
        logger.error(f"Error ending session: {e}")

def get_session(room_id: str) -> Optional[Dict[str, Any]]:
    """Get active session for room."""
    try:
        response = (
            supabase.table("sessions")
            .select("*")
            .eq("room_id", room_id)
            .is_("ended_at", "null")
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        return None

# ============================================================
# STUDENT BEHAVIOR ANALYSIS - For Personalized Feedback
# ============================================================

def analyze_student_behavior(room_id: str, username: str) -> Dict[str, Any]:
    """
    Analyze student behavior patterns to determine feedback type.
    Detects: passive, toxic, off_topic, constructive, moderate
    """
    try:
        # Get all messages from this student
        messages_response = supabase.table('messages')\
            .select('*')\
            .eq('room_id', room_id)\
            .eq('username', username)\
            .order('created_at')\
            .execute()
        
        messages = messages_response.data if messages_response.data else []
        message_count = len(messages)
        
        # Initialize counters
        toxic_keywords = ['who cares', 'stupid', 'boring', 'useless', 'whatever', 'idiot', 'hate', 'worst']
        off_topic_indicators = ['cat video', 'reminds me of', 'like when i', 'my cat', 'youtube', 'tiktok']
        
        toxic_count = 0
        off_topic_count = 0
        
        for msg in messages:
            content = msg.get('message', '').lower()
            
            for keyword in toxic_keywords:
                if keyword in content:
                    toxic_count += 1
                    break
            
            for indicator in off_topic_indicators:
                if indicator in content:
                    off_topic_count += 1
                    break
        
        # Determine behavior type
        if message_count == 0:
            behavior_type = "passive"
        elif toxic_count >= 2:
            behavior_type = "toxic"
        elif off_topic_count >= message_count * 0.3:
            behavior_type = "off_topic"
        elif message_count >= 3:
            behavior_type = "constructive"
        else:
            behavior_type = "moderate"
        
        # Get response times to hints (if any)
        hint_responses = 0
        response_times = []
        
        # Get all interventions
        interventions_response = supabase.table('messages')\
            .select('*')\
            .eq('room_id', room_id)\
            .eq('message_type', 'intervention')\
            .execute()
        
        interventions = interventions_response.data if interventions_response.data else []
        
        for msg in messages:
            msg_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
            
            for intervention in interventions:
                inter_time = datetime.fromisoformat(intervention['created_at'].replace('Z', '+00:00'))
                time_diff = (msg_time - inter_time).total_seconds()
                
                if 0 < time_diff < 60:
                    hint_responses += 1
                    response_times.append(time_diff)
                    break
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'username': username,
            'message_count': message_count,
            'behavior_type': behavior_type,
            'toxic_count': toxic_count,
            'off_topic_count': off_topic_count,
            'hint_responses': hint_responses,
            'avg_response_time': avg_response_time,
            'response_times': response_times
        }
        
    except Exception as e:
        logger.error(f"Error analyzing student behavior: {e}")
        return {
            'username': username,
            'message_count': 0,
            'behavior_type': 'passive',
            'toxic_count': 0,
            'off_topic_count': 0,
            'hint_responses': 0,
            'avg_response_time': 0,
            'response_times': []
        }

# ============================================================
# Admin Operations
# ============================================================

def create_room_admin(
    mode: str, 
    story_id: str, 
    max_participants: int = 3, 
    created_by: str = 'admin', 
    admin_note: str = ''
) -> Dict[str, Any]:
    """Create a new room with admin options."""
    try:
        room_id = str(uuid.uuid4())
        
        room_data = {
            "id": room_id,
            "mode": mode,
            "story_id": story_id,
            "status": "waiting",
            "participant_count": 0,
            "max_participants": max_participants,
            "current_chunk_index": 0,
            "story_finished": False,
            "created_by": created_by,
            "admin_note": admin_note,
            "condition": mode,  # For research tracking
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = (
            supabase.table("rooms")
            .insert(room_data)
            .execute()
        )

        room = response.data[0]
        logger.info(f"✅ Admin created room: {room['id']} (mode={mode}, max={max_participants})")
        return room

    except Exception as e:
        logger.error(f"❌ Error creating admin room: {e}")
        raise

def get_all_rooms(status: Optional[str] = None, mode: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all rooms with optional filters for admin panel."""
    try:
        query = supabase.table("rooms").select("*").order("created_at", desc=True).limit(limit)
        
        if status:
            query = query.eq("status", status)
        if mode:
            query = query.eq("mode", mode)
        
        response = query.execute()
        rooms = response.data if response.data else []
        
        # Enrich with participant details
        for room in rooms:
            participants = get_participants(room['id'])
            room['participant_list'] = participants
            room['actual_participant_count'] = len(participants)
            room['participant_names'] = [p.get('display_name') or p.get('username', 'User') for p in participants]
        
        logger.info(f"✅ Retrieved {len(rooms)} rooms for admin")
        return rooms
        
    except Exception as e:
        logger.error(f"❌ Error getting all rooms: {e}")
        return []

def get_room_stats(room_id: str) -> Dict[str, Any]:
    """Get statistics for a room for admin panel."""
    try:
        # Get participant count
        participants_response = supabase.table("participants").select("id", count="exact").eq("room_id", room_id).execute()
        participant_count = participants_response.count if hasattr(participants_response, 'count') else 0
        
        # Get message counts
        messages_response = supabase.table("messages").select("*").eq("room_id", room_id).execute()
        messages = messages_response.data if messages_response.data else []
        
        message_count = len(messages)
        chat_messages = len([m for m in messages if m.get('message_type') == 'chat'])
        moderator_messages = len([m for m in messages if m.get('message_type') in ['moderator', 'story', 'system', 'intervention']])
        
        # Get session count
        sessions_response = supabase.table("sessions").select("id", count="exact").eq("room_id", room_id).execute()
        session_count = sessions_response.count if hasattr(sessions_response, 'count') else 0
        
        return {
            "participant_count": participant_count,
            "message_count": message_count,
            "chat_messages": chat_messages,
            "moderator_messages": moderator_messages,
            "session_count": session_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting room stats: {e}")
        return {}

def get_system_stats() -> Dict[str, Any]:
    """Get overall system statistics for admin panel."""
    try:
        # Room stats
        rooms_response = supabase.table("rooms").select("*").execute()
        rooms = rooms_response.data if rooms_response.data else []
        
        # Participant stats
        participants_response = supabase.table("participants").select("*").execute()
        participants = participants_response.data if participants_response.data else []
        
        # Message stats
        messages_response = supabase.table("messages").select("*").execute()
        messages = messages_response.data if messages_response.data else []
        
        # Session stats
        sessions_response = supabase.table("sessions").select("*").execute()
        sessions = sessions_response.data if sessions_response.data else []
        
        # Calculate unique usernames
        unique_usernames = set(p.get('username') for p in participants if p.get('username'))
        
        # Calculate today's date
        today = datetime.now(timezone.utc).date().isoformat()
        
        return {
            "rooms": {
                "total": len(rooms),
                "waiting": len([r for r in rooms if r.get('status') == 'waiting']),
                "active": len([r for r in rooms if r.get('status') == 'active']),
                "completed": len([r for r in rooms if r.get('status') == 'completed']),
                "active_mode": len([r for r in rooms if r.get('mode') == 'active']),
                "passive_mode": len([r for r in rooms if r.get('mode') == 'passive']),
                "avg_participants": sum(r.get('participant_count', 0) for r in rooms) / len(rooms) if rooms else 0,
                "rooms_created_today": len([r for r in rooms if r.get('created_at', '').startswith(today)])
            },
            "participants": {
                "total": len(participants),
                "unique_users": len(unique_usernames),
                "participants_today": len([p for p in participants if p.get('joined_at', '').startswith(today)])
            },
            "messages": {
                "total": len(messages),
                "chat": len([m for m in messages if m.get('message_type') == 'chat']),
                "system": len([m for m in messages if m.get('message_type') == 'system']),
                "moderator": len([m for m in messages if m.get('message_type') == 'moderator']),
                "story": len([m for m in messages if m.get('message_type') == 'story']),
                "intervention": len([m for m in messages if m.get('message_type') == 'intervention']),
                "messages_today": len([m for m in messages if m.get('created_at', '').startswith(today)])
            },
            "sessions": {
                "total": len(sessions),
                "active_mode": len([s for s in sessions if s.get('mode') == 'active']),
                "passive_mode": len([s for s in sessions if s.get('mode') == 'passive']),
                "avg_participants": sum(s.get('participant_count', 0) for s in sessions) / len(sessions) if sessions else 0,
                "avg_messages": sum(s.get('message_count', 0) for s in sessions) / len(sessions) if sessions else 0,
                "avg_duration": sum(s.get('duration_seconds', 0) for s in sessions) / len(sessions) if sessions else 0,
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting system stats: {e}")
        return {}

# ============================================================
# Export Operations
# ============================================================

def create_export_record(
    room_id: str,
    export_type: str,
    format: str,
    exported_by: str = 'admin'
) -> Dict[str, Any]:
    """Create a record of an export."""
    try:
        export_data = {
            "room_id": room_id,
            "export_type": export_type,
            "format": format,
            "exported_by": exported_by,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = supabase.table("room_exports").insert(export_data).execute()
        logger.info(f"✅ Created export record for room {room_id} ({export_type} as {format})")
        return response.data[0] if response.data else {}
        
    except Exception as e:
        logger.error(f"❌ Error creating export record: {e}")
        return {}

def get_room_data_for_export(room_id: str) -> Dict[str, Any]:
    """Get complete room data for export."""
    try:
        # Get room
        room_response = supabase.table("rooms").select("*").eq("id", room_id).single().execute()
        room = room_response.data if room_response.data else {}
        
        # Get participants
        participants = get_participants_with_details(room_id)
        
        # Get messages
        messages = get_messages_for_export(room_id)
        
        # Get sessions
        sessions_response = supabase.table("sessions").select("*").eq("room_id", room_id).execute()
        sessions = sessions_response.data if sessions_response.data else []
        
        return {
            "room": room,
            "participants": participants,
            "messages": messages,
            "sessions": sessions,
            "export_info": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "room_id": room_id,
                "total_participants": len(participants),
                "total_messages": len(messages),
                "total_sessions": len(sessions)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting room data for export: {e}")
        return {}

# ============================================================
# Settings Operations
# ============================================================

def get_setting(key: str, default: Any = None) -> Any:
    """Get setting value from database."""
    try:
        response = (
            supabase.table("settings")
            .select("*")
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        
        if response.data:
            setting = response.data
            value_str = setting.get('value', '')
            data_type = setting.get('data_type', 'string')
            
            if data_type == 'integer':
                return int(value_str) if value_str else default
            elif data_type == 'float':
                return float(value_str) if value_str else default
            elif data_type == 'boolean':
                return value_str.lower() in ('true', '1', 'yes', 'on')
            else:
                return value_str if value_str else default
        
        return default
        
    except Exception as e:
        logger.warning(f"Failed to get setting {key}: {e}")
        return default

def get_all_settings() -> List[Dict[str, Any]]:
    """Get all settings."""
    try:
        response = supabase.table("settings").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return []

def update_setting(key: str, value: str, updated_by: str = 'admin'):
    """Update a setting value."""
    try:
        supabase.table("settings").update({
            "value": str(value),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by
        }).eq("key", key).execute()
        
        logger.info(f"Updated setting {key} = {value}")
        
    except Exception as e:
        logger.error(f"Error updating setting: {e}")

# ============================================================
# Admin Logs Operations
# ============================================================

def log_admin_action(
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    admin_user: str = 'admin',
    ip_address: Optional[str] = None
):
    """Log an admin action."""
    try:
        log_data = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
            "admin_user": admin_user,
            "ip_address": ip_address,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table("admin_logs").insert(log_data).execute()
        logger.info(f"📝 Admin action logged: {action} by {admin_user}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log admin action: {e}")

def get_admin_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Get admin logs."""
    try:
        response = (
            supabase.table("admin_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting admin logs: {e}")
        return []

# ============================================================
# Auto Room Assignment
# ============================================================

def get_or_create_room(mode: str, story_id: Optional[str] = None) -> Dict[str, Any]:
    """Get available room or create new one."""
    room = find_available_room(mode)
    if room:
        return room
    return create_room(mode, story_id)

# ============================================================
# RESEARCH FUNCTIONS
# ============================================================

def calculate_gini_coefficient(message_counts: List[int]) -> float:
    """Calculate Gini coefficient for participation equality"""
    if not message_counts or sum(message_counts) == 0:
        return 0
    
    sorted_counts = sorted(message_counts)
    n = len(sorted_counts)
    gini = 0
    
    for i, count in enumerate(sorted_counts):
        gini += (2*i - n + 1) * count
    
    if sum(sorted_counts) > 0:
        gini = gini / (n * sum(sorted_counts))
    
    return max(0, min(gini, 1))

def save_room_metrics(room_id: str):
    """Calculate and save all research metrics for a room"""
    try:
        # Get room info
        room = get_room(room_id)
        if not room:
            return
        
        # Get all messages
        messages = get_chat_history(room_id)
        
        # Get all participants
        participants = get_participants(room_id)
        
        # Count messages per participant (excluding moderator)
        message_counts = []
        word_counts = []
        participant_data = []
        
        for p in participants:
            if p['username'] == 'Moderator':
                continue
            
            p_messages = [m for m in messages if m.get('username') == p['username']]
            msg_count = len(p_messages)
            word_count = sum(len(m.get('message', '').split()) for m in p_messages)
            
            message_counts.append(msg_count)
            word_counts.append(word_count)
            
            participant_data.append({
                'username': p['username'],
                'message_count': msg_count,
                'word_count': word_count
            })
        
        # Calculate metrics
        total_messages = sum(message_counts)
        total_words = sum(word_counts)
        
        # Speaking shares
        shares = [c/total_messages if total_messages > 0 else 0 for c in message_counts]
        
        # Gini coefficient
        gini = calculate_gini_coefficient(message_counts)
        
        # Dominance metrics
        max_share = max(shares) if shares else 0
        min_share = min(shares) if shares else 0
        dominance_gap = max_share - min_share
        
        # Save to research_metrics table
        metrics_data = {
            "room_id": room_id,
            "condition": room.get('mode'),
            "gini_coefficient": gini,
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
        
        supabase.table("research_metrics").insert(metrics_data).execute()
        
        # Save participant metrics
        for i, p_data in enumerate(participant_data):
            p_metrics = {
                "room_id": room_id,
                "username": p_data['username'],
                "message_count": p_data['message_count'],
                "word_count": p_data['word_count'],
                "share_of_talk": shares[i] if i < len(shares) else 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            supabase.table("participant_metrics").insert(p_metrics).execute()
        
        logger.info(f"✅ Saved research metrics for room {room_id}")
        return metrics_data
        
    except Exception as e:
        logger.error(f"❌ Error saving room metrics: {e}")
        return None

def log_moderator_intervention(room_id: str, intervention_type: str, target_user: Optional[str] = None):
    """Log a moderator intervention for research"""
    try:
        data = {
            "room_id": room_id,
            "intervention_type": intervention_type,
            "target_user": target_user,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table("moderator_interventions").insert(data).execute()
        logger.debug(f"📝 Logged intervention: {intervention_type} in room {room_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log intervention: {e}")

def detect_conflict(message: str) -> tuple[bool, int]:
    """Detect if a message contains conflict and return severity"""
    conflict_keywords = [
        ('disagree', 2), ('wrong', 2), ('no', 1), ('but', 1), 
        ('actually', 1), ("you're wrong", 3), ("that's not", 2),
        ('stupid', 3), ('ridiculous', 3), ('idiot', 3), ('dumb', 3),
        ('nonsense', 2), ('not true', 2), ('incorrect', 2), ('false', 2),
        ('mistake', 1), ('error', 1), ("don't understand", 2),
        ("not getting it", 2)
    ]
    
    message_lower = message.lower()
    severity = 0
    
    for keyword, score in conflict_keywords:
        if keyword in message_lower:
            severity += score
    
    return severity > 0, severity

def detect_repair(message: str) -> bool:
    """Detect if a message is a repair attempt"""
    repair_keywords = [
        'agree', 'okay', 'fair', 'point', 'understand', 'see your',
        'youre right', 'good point', 'makes sense', 'lets move on',
        'compromise', 'both valid', 'i see', 'sorry', 'my bad'
    ]
    
    message_lower = message.lower()
    for keyword in repair_keywords:
        if keyword in message_lower:
            return True
    return False

def analyze_conflict_episodes(room_id: str):
    """Analyze all messages in a room for conflict-repair sequences"""
    try:
        messages = get_chat_history(room_id)
        conflicts = []
        
        for i, msg in enumerate(messages):
            if msg.get('username') == 'Moderator':
                continue
            
            is_conflict, severity = detect_conflict(msg.get('message', ''))
            if is_conflict:
                # Look for repair in next 5 messages
                repair_found = False
                repair_time = None
                repair_user = None
                repair_msg = None
                
                for j in range(i+1, min(i+6, len(messages))):
                    repair_msg = messages[j]
                    if repair_msg.get('username') == 'Moderator':
                        continue
                    
                    if detect_repair(repair_msg.get('message', '')):
                        repair_found = True
                        try:
                            conflict_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
                            repair_time_obj = datetime.fromisoformat(repair_msg['created_at'].replace('Z', '+00:00'))
                            repair_time = int((repair_time_obj - conflict_time).total_seconds())
                        except:
                            repair_time = None
                        repair_user = repair_msg.get('username')
                        break
                
                conflict_data = {
                    "room_id": room_id,
                    "conflict_message_id": msg.get('id'),
                    "conflict_user": msg.get('username'),
                    "conflict_text": msg.get('message'),
                    "severity_score": severity,
                    "repair_message_id": repair_msg.get('id') if repair_found and repair_msg else None,
                    "repair_user": repair_user,
                    "time_to_repair": repair_time,
                    "resolved": repair_found
                }
                
                # Check if table exists before inserting
                try:
                    supabase.table("conflict_episodes").insert(conflict_data).execute()
                except:
                    # Table might not exist yet
                    pass
                
                conflicts.append(conflict_data)
        
        logger.info(f"✅ Analyzed {len(conflicts)} conflicts for room {room_id}")
        return conflicts
        
    except Exception as e:
        logger.error(f"❌ Error analyzing conflicts: {e}")
        return []

# ============================================================
# Cleanup Operations (Optional)
# ============================================================

def cleanup_old_data(days_to_keep: int = 30):
    """Clean up old data (optional)."""
    try:
        cutoff_date = datetime.now(timezone.utc).isoformat()
        
        # Delete old completed rooms
        supabase.table("rooms").delete().eq("status", "completed").lt("ended_at", cutoff_date).execute()
        
        logger.info(f"✅ Cleaned up data older than {days_to_keep} days")
        
    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
