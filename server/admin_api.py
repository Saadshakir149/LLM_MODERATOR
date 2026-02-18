"""
Admin API Endpoints - COMPLETE FIXED VERSION
===================
Backend API for admin panel - Fixed room creation with max_participants
"""

import logging
import csv
import json
from io import StringIO
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, make_response
from supabase_client import (
    supabase,
    get_room,
    get_participants,
    get_chat_history,
    get_participants_with_details,
    create_room,
    create_room_admin,  # IMPORT THE ADMIN VERSION WITH max_participants
    update_room_status,
    end_session,
    add_message,
    get_messages_for_export,
    get_all_rooms as get_all_rooms_from_db,
    get_system_stats as get_system_stats_from_db,
    get_room_stats as get_room_stats_from_db,
    log_admin_action,
    create_export_record,
)

logger = logging.getLogger("ADMIN_API")

# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ============================================================
# Helper: Safe datetime parsing
# ============================================================

def safe_datetime_parse(dt_str):
    """Safely parse datetime string to avoid timezone issues"""
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace('Z', '+00:00')
        if '+' in dt_str:
            return datetime.fromisoformat(dt_str)
        else:
            return datetime.fromisoformat(dt_str + '+00:00')
    except:
        try:
            return datetime.strptime(dt_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
        except:
            return datetime.now(timezone.utc)

# ============================================================
# ✅ FIXED: Admin Room Creation - NOW WORKING WITH max_participants
# ============================================================

@admin_bp.route('/rooms', methods=['POST'])
def create_room_admin_endpoint():
    """Admin-only room creation endpoint - FIXED to use create_room_admin"""
    try:
        data = request.json or {}
        
        mode = data.get('mode', 'active')
        story_id = data.get('story_id')
        max_participants = int(data.get('max_participants', 3))
        admin_note = data.get('admin_note', '')
        admin_user = data.get('admin_user', 'admin')
        
        # Validate
        if mode not in ['active', 'passive']:
            return jsonify({"error": "Mode must be 'active' or 'passive'"}), 400
        
        if max_participants < 1 or max_participants > 10:
            return jsonify({"error": "Max participants must be between 1 and 10"}), 400
        
        # Import here to avoid circular imports
        from data_retriever import get_data
        
        # Get story
        if story_id:
            story_data = get_data(story_id)
            if not story_data:
                return jsonify({"error": f"Story {story_id} not found"}), 404
        else:
            story_data = get_data()
            story_id = story_data.get('story_id', 'default-story')
        
        # ✅ FIXED: Use create_room_admin which accepts max_participants
        room = create_room_admin(
            mode=mode,
            story_id=story_id,
            max_participants=max_participants,
            created_by=f'admin:{admin_user}',
            admin_note=admin_note
        )
        
        # Log the creation
        log_admin_action('create_room', 'room', room['id'], {
            'mode': mode,
            'story_id': story_id,
            'max_participants': max_participants,
            'admin_note': admin_note
        }, admin_user)
        
        logger.info(f"✅ Admin created room: {room['id']} (mode={mode}, max_participants={max_participants})")
        
        return jsonify({
            "success": True,
            "room": room,
            "shareable_link": f"/join/{mode}",
            "admin_link": f"/admin/rooms/{room['id']}"
        })
    
    except Exception as e:
        logger.error(f"❌ Error creating room as admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Enhanced Room Details with Usernames
# ============================================================

@admin_bp.route('/rooms/<room_id>', methods=['GET'])
def get_room_details(room_id: str):
    """Get detailed room information including participants and messages"""
    try:
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        # Get participants with proper usernames
        participants = get_participants_with_details(room_id)
        
        # Get messages
        messages = get_messages_for_export(room_id)
        
        # Get session info
        session_response = supabase.table('sessions').select('*').eq('room_id', room_id).execute()
        sessions = session_response.data if session_response.data else []
        
        # Get stats
        stats = get_room_stats_from_db(room_id)
        
        logger.info(f"📊 Admin: Viewed room {room_id} with {len(participants)} participants, {len(messages)} messages")
        
        return jsonify({
            "room": room,
            "participants": participants,
            "messages": messages,
            "sessions": sessions,
            "stats": stats
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting room details: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Chat Export Endpoints
# ============================================================

@admin_bp.route('/rooms/<room_id>/export/chat', methods=['GET'])
def export_room_chat(room_id: str):
    """Export chat messages in various formats"""
    try:
        format_type = request.args.get('format', 'json').lower()
        
        # Get messages
        messages = get_messages_for_export(room_id)
        
        if not messages:
            return jsonify({"error": "No messages found for this room"}), 404
        
        # Get room info for filename
        room = get_room(room_id)
        
        # Export based on format
        if format_type == 'json':
            return jsonify({
                "room_id": room_id,
                "room_mode": room.get('mode') if room else 'unknown',
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "message_count": len(messages),
                "messages": messages
            })
        
        elif format_type == 'csv':
            output = StringIO()
            if messages:
                fieldnames = ['id', 'username', 'message', 'message_type', 'created_at']
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(messages)
            
            csv_data = output.getvalue()
            output.close()
            
            response = make_response(csv_data)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=chat_{room_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            create_export_record(room_id, 'chat', 'csv')
            
            return response
        
        elif format_type == 'tsv':
            output = StringIO()
            if messages:
                fieldnames = ['id', 'username', 'message', 'message_type', 'created_at']
                writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(messages)
            
            tsv_data = output.getvalue()
            output.close()
            
            response = make_response(tsv_data)
            response.headers['Content-Type'] = 'text/tab-separated-values'
            response.headers['Content-Disposition'] = f'attachment; filename=chat_{room_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.tsv'
            
            create_export_record(room_id, 'chat', 'tsv')
            
            return response
        
        else:
            return jsonify({"error": f"Unsupported format: {format_type}. Use json, csv, or tsv"}), 400
    
    except Exception as e:
        logger.error(f"❌ Error exporting chat: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Enhanced Room List
# ============================================================

@admin_bp.route('/rooms', methods=['GET'])
def get_all_rooms():
    """Get all rooms with filters"""
    try:
        # Get query parameters
        status = request.args.get('status')
        mode = request.args.get('mode')
        limit = int(request.args.get('limit', 50))
        search = request.args.get('search', '')
        
        # Use the function from supabase_client
        rooms = get_all_rooms_from_db(status, mode, limit)
        
        # Apply search filter if provided
        if search:
            rooms = [r for r in rooms if 
                    search.lower() in r.get('id', '').lower() or
                    search.lower() in r.get('story_id', '').lower() or
                    any(search.lower() in p.get('username', '').lower() or 
                        search.lower() in p.get('display_name', '').lower() 
                        for p in r.get('participant_list', []))]
        
        logger.info(f"📊 Admin: Retrieved {len(rooms)} rooms (status={status}, mode={mode})")
        return jsonify({
            "rooms": rooms,
            "count": len(rooms),
            "filters": {"status": status, "mode": mode, "search": search},
            "summary": {
                "total": len(rooms),
                "waiting": len([r for r in rooms if r.get('status') == 'waiting']),
                "active": len([r for r in rooms if r.get('status') == 'active']),
                "completed": len([r for r in rooms if r.get('status') == 'completed']),
                "active_mode": len([r for r in rooms if r.get('mode') == 'active']),
                "passive_mode": len([r for r in rooms if r.get('mode') == 'passive'])
            }
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting rooms: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Enhanced Statistics
# ============================================================

@admin_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get overall statistics"""
    try:
        stats = get_system_stats_from_db()
        logger.info(f"📊 Admin: Retrieved enhanced statistics")
        return jsonify(stats)
    
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Room Control Endpoints
# ============================================================

@admin_bp.route('/rooms/<room_id>/end', methods=['POST'])
def end_room_session(room_id: str):
    """End a room session (admin control)"""
    try:
        data = request.json or {}
        admin_user = data.get('admin_user', 'admin')
        
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        # Import socketio to trigger session end with summaries
        from app import socketio as app_socketio
        
        # Trigger the socket event to end session with summaries
        app_socketio.emit("end_session", {
            "room_id": room_id,
            "sender": f"admin:{admin_user}"
        }, room=room_id)
        
        logger.info(f"✅ Admin triggered session end for room {room_id}")
        
        return jsonify({
            "success": True,
            "message": "Session ending, summaries will be sent to participants",
            "room_id": room_id
        })
    
    except Exception as e:
        logger.error(f"❌ Error ending room: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Delete Room Endpoint
# ============================================================

@admin_bp.route('/rooms/<room_id>', methods=['DELETE'])
def delete_room(room_id: str):
    """Delete a room and all associated data"""
    try:
        # Check if room exists
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        # Delete associated data in order
        supabase.table('messages').delete().eq('room_id', room_id).execute()
        supabase.table('participants').delete().eq('room_id', room_id).execute()
        supabase.table('sessions').delete().eq('room_id', room_id).execute()
        
        try:
            supabase.table('room_exports').delete().eq('room_id', room_id).execute()
        except:
            pass
        
        supabase.table('rooms').delete().eq('id', room_id).execute()
        
        log_admin_action('delete_room', 'room', room_id, {'room_mode': room.get('mode')})
        
        logger.info(f"🗑️ Admin: Deleted room {room_id}")
        return jsonify({"success": True, "message": "Room deleted successfully"})
    
    except Exception as e:
        logger.error(f"❌ Error deleting room: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# FIXED: Update Room Status
# ============================================================

@admin_bp.route('/rooms/<room_id>/status', methods=['PUT'])
def update_room_status_admin(room_id: str):
    """Update room status (admin control)"""
    try:
        data = request.json or {}
        status = data.get('status')
        admin_user = data.get('admin_user', 'admin')
        
        if status not in ['waiting', 'active', 'completed']:
            return jsonify({"error": "Invalid status. Use: waiting, active, completed"}), 400
        
        room = get_room(room_id)
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        update_room_status(room_id, status)
        
        if room.get('status') != status:
            add_message(
                room_id=room_id,
                username="System",
                message=f"Room status changed to '{status}' by admin.",
                message_type="system",
                metadata={"admin_action": True, "admin_user": admin_user}
            )
        
        log_admin_action('update_room_status', 'room', room_id, {
            'old_status': room.get('status'),
            'new_status': status
        }, admin_user)
        
        logger.info(f"✅ Admin updated room {room_id} status to {status}")
        
        return jsonify({
            "success": True,
            "message": f"Room status updated to {status}",
            "room_id": room_id,
            "old_status": room.get('status'),
            "new_status": status
        })
    
    except Exception as e:
        logger.error(f"❌ Error updating room status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# Settings Management
# ============================================================

@admin_bp.route('/settings', methods=['GET'])
def get_all_settings():
    """Get all configuration settings grouped by category"""
    try:
        response = supabase.table('settings').select('*').order('category').execute()
        
        settings = response.data if response.data else []
        
        # Group by category
        grouped = {}
        for setting in settings:
            category = setting.get('category', 'general')
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(setting)
        
        logger.info(f"📊 Admin: Retrieved {len(settings)} settings")
        return jsonify({
            "settings": settings,
            "grouped": grouped,
            "count": len(settings)
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting settings: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/settings/<key>', methods=['GET'])
def get_setting(key: str):
    """Get specific setting by key"""
    try:
        response = supabase.table('settings').select('*').eq('key', key).single().execute()
        
        if not response.data:
            return jsonify({"error": "Setting not found"}), 404
        
        return jsonify(response.data)
    
    except Exception as e:
        logger.error(f"❌ Error getting setting {key}: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/settings/<key>', methods=['PUT'])
def update_setting(key: str):
    """Update a setting value"""
    try:
        data = request.json
        new_value = data.get('value')
        
        if new_value is None:
            return jsonify({"error": "Value is required"}), 400
        
        response = supabase.table('settings').update({
            'value': str(new_value),
            'updated_by': data.get('updated_by', 'admin'),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('key', key).execute()
        
        if not response.data:
            return jsonify({"error": "Setting not found"}), 404
        
        log_admin_action('update_setting', 'setting', None, {
            'key': key,
            'old_value': data.get('old_value'),
            'new_value': new_value
        }, data.get('admin_user', 'unknown'))
        
        logger.info(f"✅ Admin: Updated setting {key} = {new_value}")
        return jsonify(response.data[0])
    
    except Exception as e:
        logger.error(f"❌ Error updating setting {key}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ============================================================
# Admin Logs
# ============================================================

@admin_bp.route('/logs', methods=['GET'])
def get_admin_logs():
    """Get admin activity logs"""
    try:
        limit = int(request.args.get('limit', 100))
        
        response = (
            supabase.table('admin_logs')
            .select('*')
            .order('created_at', desc=True)
            .limit(limit)
            .execute()
        )
        
        logs = response.data if response.data else []
        
        return jsonify({
            "logs": logs,
            "count": len(logs)
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting admin logs: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================
# Helper: Get Setting Value
# ============================================================

def get_setting_value(key: str, default=None):
    """Get a setting value from database with type conversion."""
    try:
        response = supabase.table('settings').select('*').eq('key', key).single().execute()
        
        if not response.data:
            return default
        
        setting = response.data
        value_str = setting['value']
        data_type = setting.get('data_type', 'string')
        
        if data_type == 'integer':
            return int(value_str)
        elif data_type == 'float':
            return float(value_str)
        elif data_type == 'boolean':
            return value_str.lower() in ('true', '1', 'yes')
        else:
            return value_str
    
    except Exception as e:
        logger.warning(f"Failed to get setting {key}, using default: {e}")
        return default