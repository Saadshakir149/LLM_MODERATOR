"""
Verify RQ1–RQ5 data collection for one room (run from server/ with .env loaded).

  python verify_rq_room.py <room_uuid>

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY (or project .env).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure server package imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from supabase_client import supabase  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_rq_room.py <room_id>")
        return 1
    room_id = sys.argv[1].strip()

    print(f"--- Room {room_id} ---")
    room = supabase.table("rooms").select("*").eq("id", room_id).maybe_single().execute()
    r = room.data
    if not r:
        print("Room not found.")
        return 2
    print(
        f"status={r.get('status')} mode={r.get('mode')} "
        f"final_ranking={'yes' if r.get('final_ranking') else 'no'}"
    )

    parts = supabase.table("participants").select("*").eq("room_id", room_id).execute()
    print(f"Participants: {len(parts.data or [])}")

    msgs = supabase.table("messages").select("*").eq("room_id", room_id).execute()
    print(f"Messages: {len(msgs.data or [])}")
    for m in (msgs.data or [])[:8]:
        meta = m.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        flagged = meta.get("flagged") or m.get("message_type") == "chat_flagged"
        print(
            f"  [{m.get('message_type')}] {m.get('username')}: "
            f"{(m.get('message') or '')[:48]!r} flagged={flagged}"
        )
    if msgs.data and len(msgs.data) > 8:
        print(f"  ... ({len(msgs.data) - 8} more)")

    iv = (
        supabase.table("moderator_interventions")
        .select("*")
        .eq("room_id", room_id)
        .execute()
    )
    print(f"Moderator interventions: {len(iv.data or [])}")
    for row in iv.data or []:
        print(
            f"  {row.get('intervention_type')} -> "
            f"{row.get('target_user') or 'group'} @ {row.get('timestamp')}"
        )

    rm = supabase.table("research_metrics").select("*").eq("room_id", room_id).execute()
    if rm.data:
        m = rm.data[-1]
        print("Research metrics (latest row):")
        for k in (
            "gini_coefficient",
            "participation_entropy",
            "max_share",
            "min_share",
            "dominance_gap",
            "total_messages",
            "total_words",
            "conflict_count",
            "repair_count",
            "mean_time_to_repair_seconds",
            "repair_rate",
            "ranking_accuracy",
            "time_to_consensus",
            "ranking_submitted",
            "condition",
        ):
            if k in m and m[k] is not None:
                print(f"  {k}: {m[k]}")
    else:
        print("Research metrics: (none — end_session not run yet?)")

    pm = supabase.table("participant_metrics").select("*").eq("room_id", room_id).execute()
    print(f"Participant metrics rows: {len(pm.data or [])}")
    for row in pm.data or []:
        print(
            f"  {row.get('username')}: messages={row.get('message_count')} "
            f"words={row.get('word_count')} share={row.get('share_of_talk')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
