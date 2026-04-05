# ============================================================
# research_metrics.py - Research Metrics for Desert Survival Study
# ============================================================

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("research_metrics")

# ============================================================
# Participation Equality Metrics
# ============================================================

def calculate_gini_coefficient(shares: List[float]) -> float:
    """
    Calculate Gini coefficient for participation equality
    0 = perfect equality, 1 = perfect inequality
    """
    if not shares or sum(shares) == 0:
        return 0
    
    sorted_shares = sorted(shares)
    n = len(sorted_shares)
    cumulative = 0
    gini = 0
    
    for i, share in enumerate(sorted_shares):
        cumulative += share
        gini += (2*i - n + 1) * share
    
    if sum(sorted_shares) > 0:
        gini = gini / (n * sum(sorted_shares))
    else:
        gini = 0
    
    return max(0, min(gini, 1))  # Clamp between 0 and 1

def calculate_entropy(shares: List[float]) -> float:
    """Calculate Shannon entropy of participation distribution"""
    import math
    if not shares:
        return 0
    
    entropy = 0
    for share in shares:
        if share > 0:
            entropy -= share * math.log2(share)
    
    max_entropy = math.log2(len(shares)) if shares else 1
    return entropy / max_entropy if max_entropy > 0 else 0

def analyze_participation(
    room_id: str,
    messages: List[Dict],
    student_usernames: Optional[List[str]] = None,
) -> Optional[Dict]:
    """
    RQ1/RQ3 participation metrics. If `student_usernames` is provided (enrolled triad),
    includes zeros for silent members so Gini/entropy match end_session.
    """
    try:
        _skip = {"Moderator", "System", None, ""}
        if student_usernames:
            user_counts = {u: 0 for u in student_usernames if u not in _skip}
            for msg in messages:
                username = msg.get("username")
                if username in user_counts:
                    user_counts[username] = user_counts[username] + 1
        else:
            user_counts = {}
            for msg in messages:
                username = msg.get("username")
                if username and username not in _skip:
                    user_counts[username] = user_counts.get(username, 0) + 1
            if not user_counts:
                return None

        counts = list(user_counts.values())
        total = sum(counts)

        if total == 0:
            shares = [0.0 for _ in counts]
        else:
            shares = [c / total for c in counts]

        gini = calculate_gini_coefficient(shares)
        entropy = calculate_entropy(shares)
        max_share = max(shares) if shares else 0.0
        min_share = min(shares) if shares else 0.0
        dominance_gap = max_share - min_share

        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "room_id": room_id,
            "gini_coefficient": gini,
            "entropy": entropy,
            "participation_entropy": entropy,
            "max_share": max_share,
            "min_share": min_share,
            "dominance_gap": dominance_gap,
            "message_counts": user_counts,
            "total_messages": total,
            "dominant_user": sorted_users[0][0] if sorted_users else None,
            "quiet_user": sorted_users[-1][0] if sorted_users else None,
            "shares": dict(zip(user_counts.keys(), shares)),
        }

    except Exception as e:
        logger.error(f"Error analyzing participation: {e}")
        return None


# Strong / interpersonal friction cues for proactive de-escalation (RQ2)
STRONG_TONE_FRAGMENTS: tuple[str, ...] = (
    "you're wrong",
    "youre wrong",
    "you are wrong",
    "shut up",
    "stupid",
    "idiot",
    "ridiculous",
    "nonsense",
    "useless",
    "dumb",
    "moron",
    "not listening",
    "you never",
    "you always",
)


def message_suggests_interpersonal_conflict(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(s in low for s in STRONG_TONE_FRAGMENTS)


def recent_multispeaker_tension(
    messages: List[Dict], *, lookback: int = 10
) -> bool:
    """True if recent window has conflict cues from 2+ different students (RQ2)."""
    recent = messages[-lookback:] if messages else []
    speakers = set()
    for msg in recent:
        u = msg.get("username")
        if u in ("Moderator", "System", None, ""):
            continue
        if message_suggests_interpersonal_conflict(msg.get("message", "")):
            speakers.add(u)
        else:
            hit = sum(1 for k in CONFLICT_KEYWORDS if k in (msg.get("message") or "").lower())
            if hit >= 2:
                speakers.add(u)
    return len(speakers) >= 2


def discussion_appears_off_task(
    messages: List[Dict],
    canonical_items: List[str],
    *,
    min_student_messages: int = 6,
    lookback: int = 24,
) -> bool:
    """Heuristic: last student turns rarely reference items or ranking (RQ4 refocus)."""
    recent = messages[-lookback:] if messages else []
    student_msgs = [
        m
        for m in recent
        if m.get("username") not in ("Moderator", "System", None, "")
    ]
    if len(student_msgs) < min_student_messages:
        return False
    blob = " ".join((m.get("message") or "").lower() for m in student_msgs[-min_student_messages :])
    task_tokens = (
        "rank",
        "ranking",
        "first",
        "second",
        "twelfth",
        "12",
        "item",
        "list",
        "order",
        "priority",
        "most important",
        "least",
        "consensus",
        "agree",
        "water",
        "mirror",
        "knife",
        "compass",
        "map",
        "parachute",
        "flashlight",
    )
    if any(t in blob for t in task_tokens):
        return False
    for item in canonical_items:
        il = item.lower()
        if len(il) >= 8 and il in blob:
            return False
    return True


def intervention_followup_seconds(
    interventions: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    *,
    window_sec: float = 180.0,
) -> Dict[str, Any]:
    """
    RQ5: seconds until the next student message after each moderator intervention.
    `interventions` rows need timestamps (ISO); messages need created_at.
    """
    from datetime import datetime as _dt

    latencies: List[float] = []
    per_type: Dict[str, List[float]] = {}

    def _parse(ts: Any) -> Optional[_dt]:
        if not ts:
            return None
        try:
            if isinstance(ts, str):
                return _dt.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
        return None

    stud_msgs = [
        m
        for m in messages
        if m.get("username") not in ("Moderator", "System", None, "")
    ]

    for inv in sorted(interventions or [], key=lambda x: x.get("timestamp") or ""):
        t0 = _parse(inv.get("timestamp"))
        if not t0:
            continue
        itype = str(inv.get("intervention_type") or "unknown")
        next_t: Optional[_dt] = None
        for m in stud_msgs:
            t1 = _parse(m.get("created_at"))
            if t1 and t1 > t0 and (t1 - t0).total_seconds() <= window_sec:
                next_t = t1
                break
        if next_t is not None:
            delta = (next_t - t0).total_seconds()
            latencies.append(delta)
            per_type.setdefault(itype, []).append(delta)

    def _med(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        s = sorted(xs)
        mid = len(s) // 2
        return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0

    return {
        "count_with_student_followup": len(latencies),
        "median_latency_seconds": _med(latencies),
        "by_type_median": {k: _med(v) for k, v in per_type.items()},
    }

# ============================================================
# Conflict Detection
# ============================================================

CONFLICT_KEYWORDS = [
    'disagree', 'wrong', 'no', 'but', 'however', 'actually',
    "you're wrong", "that's not", 'stupid', 'ridiculous',
    'idiot', 'dumb', 'useless', 'whatever', 'nonsense',
    'not true', 'incorrect', 'false', 'mistake', 'error',
    'you dont understand', 'youre not getting it'
]

REPAIR_KEYWORDS = [
    'lets agree', 'compromise', 'both valid', 'good point',
    'i see your point', 'youre right', 'okay', 'fair enough',
    'lets move on', 'agreed', 'makes sense'
]

def detect_conflict_episodes(room_id: str, messages: List[Dict]) -> Dict:
    """
    Detect conflict episodes and subsequent repairs in conversation
    """
    try:
        conflicts = []
        repairs = []
        
        for i, msg in enumerate(messages):
            if msg.get('username') == 'Moderator':
                continue
            
            text = msg.get('message', '').lower()
            
            # Check for conflict
            conflict_keywords_found = [k for k in CONFLICT_KEYWORDS if k in text]
            if conflict_keywords_found:
                conflicts.append({
                    "time": msg.get('created_at'),
                    "user": msg.get('username'),
                    "message": msg.get('message'),
                    "keywords": conflict_keywords_found,
                    "index": i
                })
            
            # Check for repair (looking back at recent conflicts)
            repair_keywords_found = [k for k in REPAIR_KEYWORDS if k in text]
            if repair_keywords_found:
                # Look for recent conflict to pair with
                for conflict in reversed(conflicts[-5:]):  # Check last 5 conflicts
                    if conflict.get('repaired'):
                        continue
                    
                    # Check if this message is after the conflict
                    try:
                        conflict_time = datetime.fromisoformat(conflict['time'].replace('Z', '+00:00'))
                        msg_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
                        time_diff = (msg_time - conflict_time).total_seconds()
                        
                        if 0 < time_diff < 120:  # Within 2 minutes
                            repairs.append({
                                "conflict": conflict,
                                "repair_message": msg.get('message'),
                                "repair_user": msg.get('username'),
                                "time_to_repair": time_diff,
                                "repair_keywords": repair_keywords_found
                            })
                            conflict['repaired'] = True
                            break
                    except:
                        continue
        
        return {
            "conflict_count": len(conflicts),
            "repair_count": len(repairs),
            "conflicts": conflicts,
            "repairs": repairs,
            "repair_rate": len(repairs) / len(conflicts) if conflicts else 0
        }
    
    except Exception as e:
        logger.error(f"Error detecting conflict: {e}")
        return {
            "conflict_count": 0,
            "repair_count": 0,
            "conflicts": [],
            "repairs": [],
            "repair_rate": 0
        }

# ============================================================
# Moderator Intervention Logging
# ============================================================

def log_moderator_intervention(room_id: str, intervention_type: str, target_user: Optional[str] = None):
    """Log moderator intervention for research analysis"""
    try:
        from supabase_client import supabase
        
        data = {
            "room_id": room_id,
            "intervention_type": intervention_type,
            "target_user": target_user,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table("moderator_interventions").insert(data).execute()
        logger.debug(f"📝 Logged intervention: {intervention_type} in room {room_id}")
    
    except Exception as e:
        logger.error(f"Failed to log intervention: {e}")

# ============================================================
# Turn-taking Analysis
# ============================================================

def analyze_turn_taking(messages: List[Dict]) -> Dict:
    """
    Analyze turn-taking patterns in conversation
    """
    try:
        turns = []
        last_speaker = None
        
        for msg in messages:
            speaker = msg.get('username')
            if speaker == 'Moderator':
                continue
            
            if speaker != last_speaker:
                turns.append({
                    "speaker": speaker,
                    "time": msg.get('created_at'),
                    "message": msg.get('message')
                })
                last_speaker = speaker
        
        # Calculate turn metrics
        if not turns:
            return {
                "total_turns": 0,
                "turns_per_person": {},
                "turn_switches": 0
            }
        
        # Count turns per person
        turns_per_person = {}
        for turn in turns:
            turns_per_person[turn['speaker']] = turns_per_person.get(turn['speaker'], 0) + 1
        
        return {
            "total_turns": len(turns),
            "turns_per_person": turns_per_person,
            "turn_switches": len(turns) - 1,
            "avg_turn_length": sum(len(t['message']) for t in turns) / len(turns) if turns else 0
        }
    
    except Exception as e:
        logger.error(f"Error analyzing turn-taking: {e}")
        return {
            "total_turns": 0,
            "turns_per_person": {},
            "turn_switches": 0
        }

# ============================================================
# Response Time Analysis
# ============================================================

def analyze_response_times(messages: List[Dict]) -> Dict:
    """
    Calculate average response times between participants
    """
    try:
        response_times = []
        last_msg_time = None
        last_speaker = None
        
        for msg in messages:
            speaker = msg.get('username')
            if speaker == 'Moderator':
                continue
            
            try:
                msg_time = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
                
                if last_speaker and last_speaker != speaker and last_msg_time:
                    response_time = (msg_time - last_msg_time).total_seconds()
                    if response_time < 300:  # Only count responses within 5 minutes
                        response_times.append({
                            "from": last_speaker,
                            "to": speaker,
                            "time": response_time
                        })
                
                last_msg_time = msg_time
                last_speaker = speaker
            
            except:
                continue
        
        if not response_times:
            return {
                "avg_response_time": 0,
                "min_response_time": 0,
                "max_response_time": 0,
                "response_count": 0
            }
        
        times = [r['time'] for r in response_times]
        
        return {
            "avg_response_time": sum(times) / len(times),
            "min_response_time": min(times),
            "max_response_time": max(times),
            "response_count": len(response_times),
            "response_times": response_times
        }
    
    except Exception as e:
        logger.error(f"Error analyzing response times: {e}")
        return {
            "avg_response_time": 0,
            "min_response_time": 0,
            "max_response_time": 0,
            "response_count": 0
        }

# ============================================================
# Export All Research Metrics for a Room
# ============================================================

def export_all_metrics(room_id: str, messages: List[Dict]) -> Dict:
    """
    Export ALL research metrics for a room in one dict
    """
    try:
        participation = analyze_participation(room_id, messages)
        conflict = detect_conflict_episodes(room_id, messages)
        turn_taking = analyze_turn_taking(messages)
        response_times = analyze_response_times(messages)
        
        return {
            "room_id": room_id,
            "participation": participation,
            "conflict": conflict,
            "turn_taking": turn_taking,
            "response_times": response_times,
            "total_messages": len(messages),
            "exported_at": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error exporting metrics: {e}")
        return {}