# ============================================================
# 📦 data_retriever.py — ENHANCED DESERT SURVIVAL SCENARIOS
# ============================================================
from __future__ import annotations
import hashlib
import os
import re
import html
import json
import logging
import random
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("moderator-data")

# ============================================================
# 🏜️ THREE DESERT SURVIVAL SCENARIOS (Still desert themed!)
# ============================================================

SCENARIO_1 = {
    "task_id": "desert_survival_plane_crash",
    "task_name": "Desert Plane Crash Survival",
    "description": """
**BACKGROUND STORY:**

You and your two teammates were passengers on a small charter plane flying over the Arizona desert when the engine failed. The pilot managed to make an emergency landing, but the plane was damaged on impact. The pilot is unconscious and needs help.

It's 2 PM in mid-July. The temperature is 110°F (43°C). You're approximately 80 miles from the nearest town. The plane has a emergency beacon, but it's damaged and not working. You have no cell service.

**YOUR SITUATION:**
• You have moderate injuries - some cuts and bruises, but everyone can walk
• You have about 2-3 hours before sunset
• Nights in the desert can drop to 60°F (15°C)
• There's no water source visible in any direction

**THE ITEMS:**
From the crashed plane, you've managed to salvage the following 12 items:
""",
    "items": [
        "A flashlight (4 batteries included)",
        "A map of the region",
        "A compass",
        "A large plastic sheet (6x8 feet)",
        "A box of matches",
        "A winter coat",
        "A bottle of salt tablets (1000 tablets)",
        "A small hunting knife",
        "2 quarts of water per person (6 quarts total)",
        "A cosmetic mirror",
        "A parachute (red & white, 30ft diameter)",
        "A book - 'Edible Animals of the Desert'"
    ],
    "expert_ranking": {
        "A cosmetic mirror": 1,
        "2 quarts of water per person (6 quarts total)": 2,
        "A flashlight (4 batteries included)": 3,
        "A parachute (red & white, 30ft diameter)": 4,
        "A small hunting knife": 5,
        "A large plastic sheet (6x8 feet)": 6,
        "A box of matches": 7,
        "A winter coat": 8,
        "A compass": 9,
        "A map of the region": 10,
        "A bottle of salt tablets (1000 tablets)": 11,
        "A book - 'Edible Animals of the Desert'": 12
    }
}

SCENARIO_2 = {
    "task_id": "desert_survival_lost_hikers",
    "task_name": "Lost Hikers in the Desert",
    "description": """
**BACKGROUND STORY:**

You and your two friends are experienced hikers who decided to explore a remote canyon in the southwestern desert. You planned a day hike, but took a wrong turn and now you're lost. It's getting late, and you realize you won't make it back to your car before nightfall.

**WHAT HAPPENED:**
You started at 8 AM with plenty of water and snacks. By 2 PM, you realized you were off-trail. You've been trying to find your way back for 3 hours, and now it's 5 PM. You have about 2 hours of daylight left. Temperatures during the day reached 105°F, and nights will drop to 65°F.

**YOUR CURRENT SITUATION:**
• Everyone is tired but in good health
• You have minimal supplies from your day packs
• You told someone your general plans, but not exactly where you were going
• Search and rescue might be dispatched by tomorrow morning if you don't return

**ITEMS IN YOUR PACKS:**
You check your day packs and find the following items:
""",
    "items": [
        "A flashlight (with weak batteries)",
        "A topographic map of the region",
        "A compass",
        "An emergency space blanket (thin plastic sheet)",
        "A lighter (almost out of fuel)",
        "A light windbreaker jacket",
        "A small container of salt tablets (50 tablets)",
        "A multi-tool with knife",
        "Water bottles - 2 quarts total (shared)",
        "A compact mirror",
        "An orange emergency tarp (bright color)",
        "A field guide to desert plants"
    ],
    "expert_ranking": {
        "A compact mirror": 1,
        "Water bottles - 2 quarts total (shared)": 2,
        "A flashlight (with weak batteries)": 3,
        "An orange emergency tarp (bright color)": 4,
        "A multi-tool with knife": 5,
        "An emergency space blanket (thin plastic sheet)": 6,
        "A lighter (almost out of fuel)": 7,
        "A light windbreaker jacket": 8,
        "A compass": 9,
        "A topographic map of the region": 10,
        "A small container of salt tablets (50 tablets)": 11,
        "A field guide to desert plants": 12
    }
}

SCENARIO_3 = {
    "task_id": "desert_survival_broken_vehicle",
    "task_name": "Broken Down in the Desert",
    "description": """
**BACKGROUND STORY:**

You and two friends are driving through the desert on a road trip when your SUV overheats and breaks down. There's no cell service, and you haven't seen another car for hours. It's midday, temperature is 108°F, and you're 50 miles from the nearest town.

**WHAT HAPPENED:**
The radiator cracked and all the coolant leaked out. The engine is too hot to touch. You have some basic supplies in the vehicle, but not enough water for a long hike. You have to decide whether to stay with the vehicle (easier for rescue to spot) or try to walk for help.

**YOUR CURRENT SITUATION:**
• Everyone is healthy but worried
• The vehicle provides some shade but will be extremely hot inside
• You have a few hours before sunset
• Nights will be cold (around 55°F)
• You left your travel itinerary with family, so search parties will be looking

**ITEMS IN YOUR VEHICLE:**
Searching your SUV, you find these items:
""",
    "items": [
        "A flashlight (with fresh batteries)",
        "A road map of the state",
        "A compass from the glove box",
        "A tarp for covering luggage",
        "A lighter from the cigarette lighter",
        "Hoodies and jackets (3)",
        "Salt packets from fast food (about 50 packets)",
        "A multi-tool with knife",
        "Water bottles - 3 quarts total",
        "A small mirror from the visor",
        "An orange emergency triangle (reflector)",
        "A desert survival guide book"
    ],
    "expert_ranking": {
        "A small mirror from the visor": 1,
        "Water bottles - 3 quarts total": 2,
        "A flashlight (with fresh batteries)": 3,
        "An orange emergency triangle (reflector)": 4,
        "A multi-tool with knife": 5,
        "A tarp for covering luggage": 6,
        "A lighter from the cigarette lighter": 7,
        "Hoodies and jackets (3)": 8,
        "A compass from the glove box": 9,
        "A road map of the state": 10,
        "Salt packets from fast food (about 50 packets)": 11,
        "A desert survival guide book": 12
    }
}

# Dictionary of all scenarios
ALL_SCENARIOS = {
    "plane_crash": SCENARIO_1,
    "lost_hikers": SCENARIO_2,
    "broken_vehicle": SCENARIO_3,
}

# ============================================================
# 📂 Load Task Data (Randomly selects a scenario)
# ============================================================
def get_data(story_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns a desert survival scenario.
    If story_id is provided and matches a scenario key, returns that scenario.
    Otherwise returns a random scenario for variety.
    
    Args:
        story_id: Optional scenario key ('plane_crash', 'lost_hikers', 'broken_vehicle')
        
    Returns:
        Desert survival scenario dictionary
    """
    if story_id and story_id in ALL_SCENARIOS:
        scenario = ALL_SCENARIOS[story_id]
        logger.info(f"📖 Selected specific scenario: {scenario['task_name']}")
        return scenario
    
    # Randomly select a scenario for variety
    scenario_key = random.choice(list(ALL_SCENARIOS.keys()))
    scenario = ALL_SCENARIOS[scenario_key]
    logger.info(f"🎲 Randomly selected scenario: {scenario['task_name']}")
    return scenario

# ============================================================
# 🪄 Generate Task Introduction
# ============================================================
def _description_to_markdown_body(description: str) -> str:
    """Turn scenario **bold** segments into readable markdown (no stray asterisks)."""
    if not description:
        return ""
    out: list[str] = []
    for segment in re.split(r"(\*\*.+?\*\*)", description, flags=re.DOTALL):
        if segment.startswith("**") and segment.endswith("**") and len(segment) > 4:
            inner = segment[2:-2].strip()
            out.append(f"**{inner}**")
        else:
            out.append(segment.strip())
    return "\n\n".join(s for s in out if s)


def get_story_intro(task_data: dict) -> str:
    """Markdown task introduction for clients that render markdown (headings + lists)."""
    task_name = task_data.get("task_name", "Desert Survival")
    description = task_data.get("description", "").strip()
    body = _description_to_markdown_body(description)
    items = task_data.get("items", [])
    items_md = "\n".join(f"- {item}" for item in items)

    return f"""### {task_name}

#### Background

{body}

#### Items in your packs

You check your supplies and find:

{items_md}

#### Your task

1. Rank the items from **1** (most important for survival) to **12** (least important).
2. Agree on **one** final group ranking.
3. Be ready to briefly explain your reasoning.

⏰ **You have 15 minutes** to reach consensus.
"""


def _description_to_safe_html(description: str) -> str:
    """Convert **bold** in scenario text to <strong>; escape the rest."""
    if not description:
        return ""
    parts: list[str] = []
    for segment in re.split(r"(\*\*.+?\*\*)", description, flags=re.DOTALL):
        if segment.startswith("**") and segment.endswith("**") and len(segment) > 4:
            inner = html.escape(segment[2:-2].strip())
            parts.append(f'<strong class="font-semibold text-gray-800">{inner}</strong>')
        else:
            parts.append(html.escape(segment).replace("\n", "<br />\n"))
    return "".join(parts)


def get_story_intro_html(task_data: dict) -> str:
    """Sanitized HTML task card for chat (renders with trusted server-only markup)."""
    task_name = html.escape(task_data.get("task_name", "Desert Survival"))
    desc_html = _description_to_safe_html(task_data.get("description", "").strip())
    items = task_data.get("items", [])
    items_html = "".join(
        f'<li class="mb-2 text-gray-700">{html.escape(item)}</li>' for item in items
    )

    return f"""<div class="task-intro text-left">
  <h3 class="text-lg font-bold text-indigo-800 mb-3">{task_name}</h3>
  <div class="mb-3 text-sm leading-relaxed text-gray-700">{desc_html}</div>
  <h4 class="font-semibold text-gray-800 mb-2 text-sm">Items in your packs</h4>
  <ul class="list-disc pl-5 space-y-1 text-sm mb-3">{items_html}</ul>
  <div class="mt-2 p-3 bg-amber-50 rounded-lg border border-amber-200 text-sm">
    <p class="font-semibold text-amber-900 mb-2">Your task</p>
    <ol class="list-decimal pl-5 space-y-1 text-gray-800">
      <li>Rank items 1 (most important)–12 (least important).</li>
      <li>Agree on one final group ranking.</li>
      <li>Be ready to explain your reasoning briefly.</li>
    </ol>
    <p class="text-amber-800 mt-2 font-medium">⏰ 15 minutes to reach consensus.</p>
  </div>
</div>"""

# ============================================================
# 🧱 Format Task Block (for display/debug)
# ============================================================
def format_story_block(task_data: dict, full: bool = False) -> str:
    """Format task for display"""
    name = task_data.get("task_name", "Desert Survival")
    description = task_data.get("description", "").strip()
    items = task_data.get("items", [])
    
    items_text = "\n".join([f"• {item}" for item in items])
    
    if not full:
        return f"Task: {name}\n\n{description[:200]}...\n\nItems:\n{items_text[:200]}..."
    
    return f"""
Task: {name}
{'='*50}

{description}

Items to rank:
{items_text}

Total items: {len(items)}
"""

# ============================================================
# 📋 Get Task Items (for UI display)
# ============================================================
def get_task_items(task_data: Optional[dict] = None) -> list[str]:
    """Return the list of items for the current scenario"""
    if task_data is None:
        task_data = get_data()
    return task_data.get("items", [])

# ============================================================
# 🎯 Compare Ranking with Expert Ranking
# ============================================================
def compare_with_expert_ranking(user_ranking: list, task_data: Optional[dict] = None) -> dict:
    """
    Compare a user's ranking with the expert ranking
    
    Args:
        user_ranking: List of items in ranked order (1 = most important)
        task_data: The scenario data containing expert ranking
        
    Returns:
        Dict with comparison metrics
    """
    if task_data is None:
        task_data = get_data()
    
    expert = task_data.get("expert_ranking", {})
    
    # Calculate score (lower is better - like golf)
    score = 0
    item_scores = {}
    
    for position, item in enumerate(user_ranking, 1):
        expert_pos = expert.get(item, 12)
        diff = abs(position - expert_pos)
        score += diff
        item_scores[item] = {
            "user_rank": position,
            "expert_rank": expert_pos,
            "difference": diff
        }
    
    # Maximum possible difference (for 12 items, max diff is 66)
    max_possible = 66
    
    return {
        "total_score": score,
        "max_possible": max_possible,
        "accuracy_percentage": max(0, 100 - (score / max_possible * 100)),
        "item_scores": item_scores,
        "user_ranking": user_ranking,
        "expert_ranking": sorted(expert.items(), key=lambda x: x[1])
    }

# ============================================================
# 🎲 Get Random Scenario (for admin/research)
# ============================================================
def get_random_scenario() -> Dict[str, Any]:
    """Return a random desert survival scenario"""
    scenario_key = random.choice(list(ALL_SCENARIOS.keys()))
    return ALL_SCENARIOS[scenario_key]

# ============================================================
# 📚 List All Available Scenarios
# ============================================================
def list_scenarios() -> Dict[str, str]:
    """Return a dictionary of scenario keys and names"""
    return {key: scenario["task_name"] for key, scenario in ALL_SCENARIOS.items()}


# ============================================================
# Room-pinned task data (single source of truth per session)
# ============================================================
ROOM_TASK_CACHE: Dict[str, Dict[str, Any]] = {}


def resolve_task_data_from_room(room: Optional[dict]) -> Dict[str, Any]:
    """Map a Supabase room row to the exact scenario dict (stable item strings)."""
    if not room:
        return get_data()
    sid = (room.get("story_id") or "").strip()
    if sid in ALL_SCENARIOS:
        return ALL_SCENARIOS[sid]
    for _key, scen in ALL_SCENARIOS.items():
        if scen.get("task_id") == sid:
            return scen
    low = sid.lower()
    if "plane" in low or "crash" in low:
        return ALL_SCENARIOS["plane_crash"]
    if "hiker" in low or "lost" in low:
        return ALL_SCENARIOS["lost_hikers"]
    if "vehicle" in low or "suv" in low or "car" in low:
        return ALL_SCENARIOS["broken_vehicle"]
    # default-story / missing: deterministic per room id so all clients match
    rid = (room.get("id") or "unknown").encode("utf-8")
    idx = int(hashlib.md5(rid).hexdigest(), 16) % len(ALL_SCENARIOS)
    key = sorted(ALL_SCENARIOS.keys())[idx]
    return ALL_SCENARIOS[key]


def pin_task_data_for_room(room_id: str, task_data: Dict[str, Any]) -> None:
    ROOM_TASK_CACHE[room_id] = task_data


def get_pinned_or_resolve_task_data(room_id: str) -> Dict[str, Any]:
    if room_id in ROOM_TASK_CACHE:
        return ROOM_TASK_CACHE[room_id]
    try:
        from supabase_client import get_room

        room = get_room(room_id)
        td = resolve_task_data_from_room(room)
    except Exception as exc:
        logger.warning("Could not resolve task for room %s: %s", room_id, exc)
        td = get_data()
    ROOM_TASK_CACHE[room_id] = td
    return td


def get_canonical_items_for_room(room_id: str) -> Dict[str, Any]:
    """Identical item list + metadata for every client tied to this room."""
    td = get_pinned_or_resolve_task_data(room_id)
    return {
        "items": list(td.get("items", [])),
        "task_name": td.get("task_name", "Desert Survival"),
        "task_id": td.get("task_id", ""),
    }


# (alias substring, required keywords in canonical line — all must appear in lowercased item text)
_ITEM_ALIAS_QUERIES: List[Tuple[Tuple[str, ...], Tuple[str, ...]]] = [
    (("compact mirror", "small mirror", "visor mirror"), ("mirror",)),
    (("cosmetic mirror",), ("mirror", "cosmetic")),
    (("space blanket", "emergency blanket", "mylar"), ("blanket", "sheet")),
    (("tarp", "orange tarp"), ("tarp",)),
    (("plastic sheet", "large plastic"), ("plastic", "sheet")),
    (("salt packet", "salt tab", "bp tablet"), ("salt",)),
    (("multi-tool", "multitool", "leatherman"), ("multi-tool", "tool")),
    (("hunting knife", "pocket knife"), ("knife",)),
    (
        ("winter coat", "hoodie", "windbreaker", "jacket"),
        ("coat", "jacket", "windbreaker", "hoodie"),
    ),
    (("matches",), ("match",)),
    (("lighter",), ("lighter",)),
    (("parachute", "chute"), ("parachute",)),
    (("field guide", "edible animals", "survival guide"), ("book", "guide")),
    (("road map", "topo", "topographic"), ("map",)),
]


def normalize_item_name(user_phrase: str, canonical_items: List[str]) -> Optional[str]:
    """Map a user fragment to the exact scenario string when unambiguous."""
    if not user_phrase or not canonical_items:
        return None
    low = user_phrase.lower().strip()
    for aliases, need in _ITEM_ALIAS_QUERIES:
        if not any(a in low for a in aliases):
            continue
        candidates = [c for c in canonical_items if all(k in c.lower() for k in need)]
        if len(candidates) == 1:
            return candidates[0]
    best: Optional[str] = None
    best_len = 0
    for c in canonical_items:
        cl = c.lower()
        if len(cl) > 6 and cl in low:
            if len(cl) > best_len:
                best_len = len(cl)
                best = c
    return best


def clarify_alias_against_list(message: str, canonical_items: List[str]) -> Optional[str]:
    """If the message uses a known alias but not the official list wording, return one short line."""
    if not message or not canonical_items:
        return None
    ml = message.lower()
    for aliases, need in _ITEM_ALIAS_QUERIES:
        if not any(a in ml for a in aliases):
            continue
        candidates = [c for c in canonical_items if all(k in c.lower() for k in need)]
        if len(candidates) != 1:
            continue
        canon = candidates[0]
        if canon.lower()[:12] in ml:
            return None
        return f"Quick note: on **our list** that item is: **{canon}**."
    return None