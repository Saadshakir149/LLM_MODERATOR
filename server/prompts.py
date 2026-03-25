from __future__ import annotations

# ============================================================
# 📦 Imports
# ============================================================
from typing import List, Dict, Any, Optional
import os
import re
import time
import logging
import random
import traceback
from dotenv import load_dotenv

# ============================================================
# 🔧 Environment Setup
# ============================================================
load_dotenv()
logger = logging.getLogger("moderator-prompts")

# ============================================================
# ⚙️ Config Loader
# ============================================================
def get_env(name: str, cast=str, required: bool = False):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        msg = f"[Config] Missing env var: {name}"
        if required:
            raise EnvironmentError(msg)
        logger.warning(msg)
        return None
    try:
        return cast(value)
    except Exception:
        logger.error(f"[Config] Failed to cast {name}")
        return None

# ============================================================
# 🌍 Core Model Configuration
# ============================================================
LLM_PROVIDER = get_env("LLM_PROVIDER", str, False) or "groq"
GROQ_MODEL = get_env("GROQ_MODEL", str, False) or "llama-3.1-8b-instant"
GROQ_TEMPERATURE = get_env("GROQ_TEMPERATURE", float, False) or 0.7
GROQ_MAX_TOKENS = get_env("GROQ_MAX_TOKENS", int, False) or 2000

OPENAI_MODEL = get_env("OPENAI_CHAT_MODEL", str, False) or "gpt-4o-mini"
OPENAI_TEMPERATURE = get_env("OPENAI_TEMPERATURE", float, False) or 0.7
OPENAI_MAX_TOKENS = get_env("OPENAI_MAX_TOKENS", int, False) or 2000

CHAT_HISTORY_LIMIT = get_env("CHAT_HISTORY_LIMIT", int, False) or 50
WELCOME_MESSAGE = get_env("WELCOME_MESSAGE", str, False) or "Welcome everyone! I'm the Moderator."

# ============================================================
# 🧠 LLM Client Initialization
# ============================================================
groq_client = None
openai_client = None

# Try to initialize OpenAI if API key exists
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    logger.info(f"🔑 OPENAI_API_KEY exists: {bool(openai_api_key)}")
    if openai_api_key and openai_api_key.strip():
        logger.info(f"🔑 OPENAI_API_KEY length: {len(openai_api_key)}")
        logger.info(f"🔑 OPENAI_API_KEY starts with: {openai_api_key[:7]}...")
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_api_key)
        logger.info("✅ OpenAI client initialized successfully")
        logger.info("✅ OpenAI client ready for API calls")
    else:
        logger.warning("⚠️ OPENAI_API_KEY not found or empty")
except ImportError:
    logger.warning("⚠️ openai package not installed. Run: pip install openai")
except Exception as e:
    logger.error(f"❌ OpenAI client initialization failed: {e}")
    logger.error(traceback.format_exc())

# Try to initialize Groq as fallback
try:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key and groq_api_key.strip():
        from groq import Groq
        groq_client = Groq(api_key=groq_api_key)
        logger.info("✅ Groq client initialized as fallback")
    else:
        logger.warning("⚠️ GROQ_API_KEY not found")
except ImportError:
    logger.warning("⚠️ groq package not installed")
except Exception as e:
    logger.error(f"❌ Groq client initialization failed: {e}")

# ============================================================
# 🛠 Helper Functions
# ============================================================
def call_llm(messages, temperature=None, max_tokens=None, system_prompt=None):
    """Make LLM API call (OpenAI preferred, Groq fallback)"""
    
    logger.info("="*50)
    logger.info("📞 call_llm INVOKED")
    logger.info(f"   LLM_PROVIDER setting: {LLM_PROVIDER}")
    logger.info(f"   OpenAI client available: {openai_client is not None}")
    logger.info(f"   Groq client available: {groq_client is not None}")
    logger.info(f"   Temperature: {temperature}")
    logger.info(f"   Max tokens: {max_tokens}")
    logger.info(f"   System prompt provided: {bool(system_prompt)}")
    logger.info(f"   Number of messages: {len(messages) if messages else 0}")
    
    if not openai_client and not groq_client:
        logger.error("❌ No LLM client available - both OpenAI and Groq are None")
        return None
    
    try:
        # ===== OPENAI PATH (Primary) =====
        if LLM_PROVIDER == "openai" and openai_client:
            logger.info("🟢 ATTEMPTING OpenAI API call...")
            
            # Format messages for OpenAI
            openai_messages = []
            
            # Add system prompt if provided
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})
                logger.debug(f"System prompt (first 100 chars): {system_prompt[:100]}...")
            
            # Add conversation messages
            for i, msg in enumerate(messages):
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    openai_messages.append({"role": role, "content": content})
                    logger.debug(f"Message {i}: role={role}, content length={len(content)}")
                else:
                    openai_messages.append({"role": "user", "content": str(msg)})
                    logger.debug(f"Message {i}: (string) content length={len(str(msg))}")
            
            logger.info(f"📤 Sending {len(openai_messages)} messages to OpenAI")
            logger.info(f"   Model: {OPENAI_MODEL}")
            logger.info(f"   Temperature: {temperature or OPENAI_TEMPERATURE}")
            logger.info(f"   Max tokens: {max_tokens or OPENAI_MAX_TOKENS}")
            
            try:
                # Make the API call
                logger.info("⏳ Waiting for OpenAI response...")
                response = openai_client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=openai_messages,
                    temperature=temperature or OPENAI_TEMPERATURE,
                    max_tokens=max_tokens or OPENAI_MAX_TOKENS
                )
                
                content = response.choices[0].message.content
                logger.info(f"✅ OpenAI API call SUCCESSFUL!")
                logger.info(f"   Response length: {len(content)} chars")
                logger.info(f"   Response preview: {content[:150]}...")
                return content
                
            except Exception as openai_error:
                logger.error(f"❌ OpenAI API call FAILED: {openai_error}")
                logger.error(f"   Error type: {type(openai_error).__name__}")
                logger.error(f"   Full traceback: {traceback.format_exc()}")
                
                # Check for specific error types
                error_str = str(openai_error).lower()
                if "authentication" in error_str or "api key" in error_str:
                    logger.error("🔑 This appears to be an API KEY issue. Check your OPENAI_API_KEY in .env")
                elif "rate limit" in error_str:
                    logger.error("⏱️ Rate limit exceeded. Try again later.")
                elif "billing" in error_str or "quota" in error_str:
                    logger.error("💰 Billing issue. Check your OpenAI account credits.")
                elif "connection" in error_str:
                    logger.error("🌐 Network connection issue. Check your internet.")
                
                # Try Groq if OpenAI failed but Groq is available
                if groq_client:
                    logger.info("🟣 Retrying with Groq after OpenAI failure...")
                    groq_messages = []
                    if system_prompt:
                        groq_messages.append({"role": "system", "content": system_prompt})
                    for msg in messages:
                        if isinstance(msg, dict):
                            groq_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
                        else:
                            groq_messages.append({"role": "user", "content": str(msg)})
                    try:
                        response = groq_client.chat.completions.create(
                            model=GROQ_MODEL,
                            messages=groq_messages,
                            temperature=temperature or GROQ_TEMPERATURE,
                            max_tokens=max_tokens or GROQ_MAX_TOKENS,
                            stream=False,
                        )
                        content = response.choices[0].message.content
                        logger.info(f"✅ Groq fallback after OpenAI error ({len(content)} chars)")
                        return content
                    except Exception as groq_retry_err:
                        logger.error(f"❌ Groq fallback also failed: {groq_retry_err}")
                return None
        
        # ===== GROQ PATH (Fallback) =====
        elif groq_client:
            logger.info("🟣 ATTEMPTING Groq API call (fallback)...")
            
            groq_messages = []
            if system_prompt:
                groq_messages.append({"role": "system", "content": system_prompt})
            
            for msg in messages:
                if isinstance(msg, dict):
                    groq_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
                else:
                    groq_messages.append({"role": "user", "content": str(msg)})
            
            try:
                response = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=groq_messages,
                    temperature=temperature or GROQ_TEMPERATURE,
                    max_tokens=max_tokens or GROQ_MAX_TOKENS,
                    stream=False,
                )
                
                content = response.choices[0].message.content
                logger.info(f"✅ Groq response received ({len(content)} chars)")
                return content
            except Exception as groq_error:
                logger.error(f"❌ Groq API call failed: {groq_error}")
                if openai_client and LLM_PROVIDER != "openai":
                    logger.info("🟢 Retrying with OpenAI after Groq failure...")
                    openai_messages = []
                    if system_prompt:
                        openai_messages.append({"role": "system", "content": system_prompt})
                    for i, msg in enumerate(messages):
                        if isinstance(msg, dict):
                            openai_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
                        else:
                            openai_messages.append({"role": "user", "content": str(msg)})
                    try:
                        response = openai_client.chat.completions.create(
                            model=OPENAI_MODEL,
                            messages=openai_messages,
                            temperature=temperature or OPENAI_TEMPERATURE,
                            max_tokens=max_tokens or OPENAI_MAX_TOKENS,
                        )
                        content = response.choices[0].message.content
                        logger.info(f"✅ OpenAI fallback after Groq error ({len(content)} chars)")
                        return content
                    except Exception as oa_retry_err:
                        logger.error(f"❌ OpenAI fallback also failed: {oa_retry_err}")
                return None
        
        else:
            logger.error(f"❌ Requested provider {LLM_PROVIDER} not available")
            logger.error(f"   OpenAI available: {openai_client is not None}")
            logger.error(f"   Groq available: {groq_client is not None}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Unexpected error in call_llm: {e}")
        logger.error(traceback.format_exc())
        return None

def get_fallback_response():
    """Get a simple fallback response"""
    responses = [
        "Thanks for sharing! Let's continue.",
        "I appreciate your input. What do others think?",
        "Good point! Let's keep discussing.",
        "Interesting observation! What do others think?",
        "Let's hear from everyone on this point.",
        "That's an interesting perspective. Any other thoughts?"
    ]
    return random.choice(responses)

# ============================================================
# 🎯 RESEARCH STUDY PROMPTS - DESERT SURVIVAL TASK
# ============================================================
DESERT_ITEMS = [
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
]

def format_items_list():
    """Format items for display in prompts"""
    return "\n".join([f"• {item}" for item in DESERT_ITEMS])

# ============================================================
# 🚫 INAPPROPRIATE LANGUAGE DETECTION (comprehensive, research logging)
# ============================================================
# Multi-word phrases matched by substring. Longer phrases are checked first so
# "shut the fuck up" wins over "shut up". Overlapping hits are reduced by
# blanking matched spans in a working copy before token scans.
#
# NOTE: Bare tokens like "die", "kill", "death" are omitted — desert-survival
# discussions mention risk of death legitimately. Violent/threatening *phrases*
# are still caught (e.g. "kill yourself", "kys", "fuck you").
# ============================================================

_INAPPROPRIATE_PHRASES_RAW = (
    # Aggressive commands / profane phrases
    "shut the fuck up",
    "what the fuck",
    "what the hell",
    "fucking hell",
    "get the fuck out",
    "fuck off",
    "fuck you",
    "fuck u",
    "f u",
    "suck my dick",
    "suck my cock",
    "suck it",
    "eat shit",
    "kiss my ass",
    "go to hell",
    "go die",
    "shut up",
    "shutup",
    "stfuu",
    "stfu",
    "gtfo",
    "son of a bitch",
    "piece of shit",
    "bullshit",
    "horseshit",
    "motherfucker",
    "dick head",
    "cocksucker",
    "jerk off",
    "jerkoff",
    "kill yourself",
    "kys",
    "fuck you up",
    # Urdu / Roman Urdu (phrases)
    "teri maa ki",
    "maa ki",
    "bhen ki",
    "behenchod",
    "behanchod",
    "bhenchod",
    "bhenchood",
    "benchod",
    "madarchod",
    "maderchod",
    "maachod",
    "maa chod",
    "bhosdike",
    "bhosdiwala",
    "bhosri",
    "bhosra",
    "chutiya",
    "chutiye",
    "chutya",
    "choot",
    "haramzada",
    "haramzaada",
    "ullu ka patha",
    "ullu ka pattha",
    "terimaaki",
    "suar ka bacha",
    # Threatening (phrased)
    "beat you",
    "beat u",
    "hit you",
    "hit u",
    "slap you",
    "slap u",
    "punch you",
    "punch u",
    "fight you",
    "fight u",
    "destroy you",
    "end you",
    "ruin you",
    "mess you up",
    "wreck you",
    "hate you",
    "i hate u",
    # Academic / plagiarism insults (phrases)
    "you cheated",
    "you're cheating",
    "youre cheating",
)

INAPPROPRIATE_PHRASES: tuple[str, ...] = tuple(
    sorted(set(_INAPPROPRIATE_PHRASES_RAW), key=len, reverse=True)
)

# Single-token / compact terms: word-boundary match in unscanned portions only.
_INAPPROPRIATE_TOKENS_RAW: frozenset[str] = frozenset(
    {
        # Profanity
        "fuck",
        "fucking",
        "fucked",
        "fucker",
        "shit",
        "shitting",
        "bullshit",
        "shitty",
        "damn",
        "damned",
        "goddamn",
        "goddamned",
        "hell",
        "asshole",
        "asshat",
        "asswipe",
        "assclown",
        "bitch",
        "bitching",
        "bitched",
        "bitchy",
        "dick",
        "dickhead",
        "dickwad",
        "dicksucker",
        "cock",
        "cockhead",
        "pussy",
        "cunt",
        "cunts",
        "cuntface",
        "twat",
        "wanker",
        "bastard",
        # Insults / slurs (use with care: academic / hostile tone)
        "stupid",
        "stoopid",
        "dumbass",
        "dumbfuck",
        "dumb",
        "idiot",
        "idiotic",
        "idiots",
        "moron",
        "moronic",
        "loser",
        "retard",
        "retarded",
        "tard",
        "pathetic",
        "useless",
        "worthless",
        "simp",
        "cuck",
        "nazi",
        "hitler",
        "rapist",
        "pedo",
        "pedophile",
        # Urdu tokens (strong)
        "chut",
        "bhosdike",
        "madarchod",
        "harami",
        "bewakoof",
        "beywaqoof",
        "nalayak",
        "nalaik",
        "kameena",
        "kameeni",
        "lafanga",
        "lafangi",
        "kutta",
        "kutti",
        "kutte",
        "suar",
        "gadha",
        "gadhi",
        "randi",
        "randwa",
        "lauda",
        "laude",
        "loda",
        "lund",
        "lundu",
        "gandu",
        "gand",
        "pagal",
        "paagal",
        "deewana",
        "sala",
        "salaa",
        # Internet / casual (flagged for professional classroom tone)
        "wtf",
        "omfg",
        "omg",
        "lmfao",
        "lmao",
        "rofl",
        "roflmao",
        "lolz",
        "lel",
        "smh",
        "fml",
        # Other
        "jerk",
        "jerks",
        "freakshow",
        "weirdo",
        "psycho",
        "psychotic",
        "garbage",
        "trashy",
        "snowflake",
        "triggered",
        "crybaby",
        "whiner",
        "scrublord",
        "noob",
        "newb",
        "cheater",
        "plagiarism",
        "fraud",
        "poser",
        "wannabe",
        "nerd",
        "dork",
        "dweeb",
        "scrub",
        # Slang insults
        "sucks",
        "suckass",
        # Severe slurs (zero tolerance)
        "nigger",
        "nigga",
        "faggot",
        "fag",
        "chink",
        "spic",
        "kike",
    }
)

# Very short tokens excluded (too many false positives: "ass" in "class", "fu" as typo)
# "ass" alone is skipped; "asshole" etc. kept.


def _tokens_for_scan(message_lower: str) -> list[str]:
    """Word-boundary token hits on full normalized message."""
    found: list[str] = []
    for tok in _INAPPROPRIATE_TOKENS_RAW:
        if re.search(r"(?<!\w)" + re.escape(tok) + r"(?!\w)", message_lower):
            found.append(tok)
    return found


_CASUAL_SINGLE_OK = frozenset(
    {"lol", "lmao", "lmfao", "rofl", "roflmao", "omg", "wtf", "smh", "fml", "lolz", "lel", "omfg"}
)


def check_inappropriate_language(
    message: str, allow_casual_slang: bool = False
) -> tuple[bool, List[str]]:
    """
    Comprehensive inappropriate-language check for moderated discussions.
    Returns (is_inappropriate, matched_terms) for logging and warnings.

    allow_casual_slang: If True, a single hit that is only casual chat abbreviations
    (e.g. lol, omg) does not count — avoids the AI moderator interrupting on filler.
    """
    if not message or not message.strip():
        return False, []

    message_lower = message.lower()
    work = message_lower
    found: list[str] = []

    for phrase in INAPPROPRIATE_PHRASES:
        if phrase in work:
            found.append(phrase)
            work = work.replace(phrase, " " * len(phrase))

    found.extend(_tokens_for_scan(work))

    seen: set[str] = set()
    found_words: list[str] = []
    for w in found:
        if w not in seen:
            seen.add(w)
            found_words.append(w)

    if not found_words:
        return False, []

    if allow_casual_slang and len(found_words) == 1 and found_words[0] in _CASUAL_SINGLE_OK:
        return False, []

    logger.warning(
        "🚫 Inappropriate language detected: %s in: %.50s...",
        found_words,
        message,
    )
    return True, found_words


_HIGH_SEVERITY_FRAGMENTS: frozenset[str] = frozenset(
    """
    kill yourself kys suicide murder rapist pedo pedophile nazi hitler
    cunt fuck fucking shitter motherfucker cocksucker
    bhenchod madarchod bhosdike chutiya haramzada
    kill u kill you die faggot nigger
    """.split()
)


_MEDIUM_SEVERITY_FRAGMENTS: frozenset[str] = frozenset(
    """
    shit asshole bitch dumbass idiot moron loser retard stupid dumb jerk
    whore slut pussy dick cock cunt twat
    shut stfu gtfo fuck ass wank
    pagal gandu kutta chut lund
    """.split()
)


def get_language_severity(bad_words: List[str]) -> str:
    """HIGH / MEDIUM / LOW from matched terms (worst wins)."""
    if not bad_words:
        return "LOW"
    blob = " ".join(bad_words).lower()
    for w in sorted(_HIGH_SEVERITY_FRAGMENTS, key=len, reverse=True):
        if w in blob:
            return "HIGH"
    for w in sorted(_MEDIUM_SEVERITY_FRAGMENTS, key=len, reverse=True):
        if w in blob:
            return "MEDIUM"
    return "LOW"

# ============================================================
# 🟢 ACTIVE MODERATOR PROMPTS (Research Version)
# ============================================================
ACTIVE_MODERATOR_SYSTEM_PROMPT = """You are an ACTIVE moderator for a 3-person group discussion.

IMPORTANT - THE ONLY PARTICIPANTS IN THIS ROOM ARE:
{participant_list}

You MUST ONLY address these specific participants by their exact names shown above.
Do NOT invent or use any other names like Rachel, Sarah, Michael, etc.

YOUR ROLE:
- Proactively guide the discussion
- Ensure balanced participation
- Invite quieter members by name
- Gently manage dominant speakers
- Keep discussion on track
- Help group reach consensus within time limit
- Answer questions about the task when asked
- Be helpful and encouraging

BEHAVIOR RULES:
1. If someone hasn't spoken in 3 minutes → invite them by name
2. If one person contributes >50% of messages in last 5 minutes → gently ask others for their views
3. Every 5 minutes → provide a brief summary of progress
4. In last 5 minutes → remind group to finalize ranking
5. Answer questions directly and helpfully
6. Always be polite, encouraging, and neutral

TASK: Desert survival ranking
ITEMS TO RANK:
{items}

Remember: You are ACTIVE - you initiate, guide, and balance.
ONLY use these participant names: {participant_list}
"""

PASSIVE_MODERATOR_SYSTEM_PROMPT = """You are a PASSIVE moderator for a 3-person group discussion.

IMPORTANT - THE ONLY PARTICIPANTS IN THIS ROOM ARE:
{participant_list}

You MUST ONLY address these specific participants by their exact names shown above.
Do NOT invent or use any other names.

YOUR ROLE:
- Only speak when directly addressed by participants
- Provide minimal responses
- Do NOT initiate or guide discussion
- Do NOT balance participation
- Only intervene for clear policy violations

BEHAVIOR RULES:
1. ONLY speak if a participant asks you a direct question
2. If asked, give brief, neutral responses (1-2 sentences max)
3. Do NOT invite quiet members
4. Do NOT summarize unless explicitly asked
5. Do NOT manage turn-taking
6. Answer questions about time or task if asked

TASK: Desert survival ranking
ITEMS TO RANK:
{items}

Remember: You are PASSIVE - wait to be asked, respond minimally.
ONLY use these participant names: {participant_list}
"""

# ============================================================
# 💬 ACTIVE MODERATOR RESPONSE GENERATOR
# ============================================================
def generate_active_moderator_response(
    participants: List[str],
    chat_history: List[Dict[str, Any]],
    task_context: str,
    time_elapsed: int,
    last_intervention_time: int,
    dominance_detected: Optional[str] = None,
    silent_user: Optional[str] = None
) -> str:
    """Generate ACTIVE moderator response based on research rules"""
    try:
        logger.info("="*60)
        logger.info("🎯 GENERATE_ACTIVE_MODERATOR_RESPONSE CALLED")
        logger.info(f"   Participants: {participants}")
        logger.info(f"   Chat history length: {len(chat_history)}")
        logger.info(f"   Time elapsed: {time_elapsed} min")
        logger.info(f"   Last intervention: {last_intervention_time}s ago")
        logger.info(f"   Dominance detected: {dominance_detected}")
        logger.info(f"   Silent user: {silent_user}")
        logger.info(f"   LLM Provider from config: {LLM_PROVIDER}")
        logger.info(f"   OpenAI client available: {openai_client is not None}")
        logger.info(f"   Groq client available: {groq_client is not None}")
        
        # Filter out Moderator from participants list
        actual_participants = [p for p in participants if p != 'Moderator' and p]
        logger.info(f"   Actual participants: {actual_participants}")
        
        if not actual_participants:
            logger.warning("⚠️ No actual participants found, returning welcome message")
            return "Welcome to the desert survival task! Please introduce yourselves."
        
        # Check last message for inappropriate language (but don't block questions)
        if chat_history and len(chat_history) > 0:
            last_msg = chat_history[-1]
            last_sender = last_msg.get('sender', '')
            last_content = last_msg.get('message', '')
            logger.info(f"   Last message from {last_sender}: {last_content[:100]}")
            
            # Only check if it's not a question
            if '?' not in last_content:
                is_inappropriate, bad_words = check_inappropriate_language(
                    last_content, allow_casual_slang=True
                )
                if is_inappropriate:
                    warning_msg = f"{last_sender}, please keep our discussion professional and academic. Let's focus on the desert survival task."
                    logger.info(f"⚠️ Inappropriate language detected from {last_sender}: {bad_words}")
                    return warning_msg
        
        # Format chat history
        trimmed_history = chat_history[-20:] if chat_history else []
        chat_text = ""
        for msg in trimmed_history:
            sender = msg.get('sender', 'Unknown')
            message = msg.get('message', '')
            # Don't include moderator messages in history for context
            if sender != 'Moderator':
                chat_text += f"{sender}: {message}\n"
        
        logger.info(f"📝 Formatted chat history ({len(trimmed_history)} messages)")
        
        # Build context
        time_remaining = max(0, 15 - time_elapsed)
        logger.info(f"⏱️ Time remaining: {time_remaining} minutes")
        
        # Format participant list for prompt
        participant_list_str = ", ".join(actual_participants)
        
        # Determine intervention type
        intervention_type = "normal"
        
        # First, check if the last message was a question that needs answering
        if chat_history and len(chat_history) > 0:
            last_msg = chat_history[-1]
            if last_msg.get('sender') != 'Moderator':
                last_content = last_msg.get('message', '').lower()
                question_phrases = ['what we have to do', 'what to do', 'what next', 'what\'s next', 'whats next', 
                                   'how to', 'what is the task', 'what should we', 'explain', 'how should i start',
                                   'what do we do', 'help', 'confused', 'not sure']
                
                is_question = any(phrase in last_content for phrase in question_phrases) or '?' in last_content
                logger.info(f"❓ Is last message a question? {is_question}")
                
                if is_question:
                    intervention_type = "answer_question"
                    logger.info(f"📝 Detected question, will answer")
        
        # If not a question, check other intervention types
        if intervention_type == "normal":
            if silent_user and time_elapsed > 3:
                intervention_type = "invite_silent"
                logger.info(f"🤫 Will invite silent user: {silent_user}")
            elif dominance_detected:
                intervention_type = "balance_dominance"
                logger.info(f"👑 Will balance dominance for: {dominance_detected}")
            elif time_remaining <= 5:
                intervention_type = "time_warning"
                logger.info(f"⏰ Will give time warning")
            elif time_elapsed > 0 and time_elapsed % 5 == 0:
                intervention_type = "summarize"
                logger.info(f"📊 Will provide summary")
        
        logger.info(f"🎯 Final intervention type: {intervention_type}")
        
        # Create prompt with ACTUAL participant names
        if intervention_type == "answer_question":
            last_question = chat_history[-1].get('message', '') if chat_history else ''
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}

The last user message was: "{last_question}"

Please answer their question helpfully and concisely in 1-2 sentences. 
If they're asking about the task, explain that they need to rank the 12 desert survival items from most important (1) to least important (12).
If they're asking about time, tell them they have {time_remaining} minutes remaining.
ONLY use the actual participant names: {participant_list_str}"""
        
        elif intervention_type == "invite_silent" and silent_user in actual_participants:
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}
{silent_user} hasn't spoken in a while. Politely invite them to share their thoughts on the desert survival ranking in 1 sentence.
ONLY use the actual participant names: {participant_list_str}"""
        
        elif intervention_type == "balance_dominance" and dominance_detected in actual_participants:
            other_participants = [p for p in actual_participants if p != dominance_detected]
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}
{dominance_detected} has been dominating the conversation. Gently ask {', '.join(other_participants)} for their perspective in 1 sentence.
ONLY use the actual participant names: {participant_list_str}"""
        
        elif intervention_type == "time_warning":
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}
Only {time_remaining} minutes left. Remind the group to work towards finalizing their ranking in 1 sentence.
ONLY use the actual participant names: {participant_list_str}"""
        
        elif intervention_type == "summarize":
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}
Based on this chat history: {chat_text[:200]}...
Provide a brief summary of their progress so far in 1-2 sentences.
ONLY use the actual participant names: {participant_list_str}"""
        
        else:
            # Normal facilitation
            prompt = f"""You are an ACTIVE moderator. The participants are: {participant_list_str}
Based on this chat history: {chat_text[:200]}...
Provide a natural, helpful facilitation message to keep the discussion moving in 1 sentence.
ONLY use the actual participant names: {participant_list_str}"""
        
        logger.info(f"📝 Prompt created (type: {intervention_type})")
        logger.info(f"   Prompt preview: {prompt[:150]}...")
        
        # Get system prompt with actual participants
        system_prompt = ACTIVE_MODERATOR_SYSTEM_PROMPT.format(
            participant_list=participant_list_str,
            items=format_items_list()
        )
        logger.info(f"📝 System prompt created, length: {len(system_prompt)} chars")
        
        logger.info(f"📤 About to call call_llm...")
        
        # Call LLM with proper parameters
        response = call_llm(
            messages=[
                {"role": "user", "content": prompt}
            ],
            system_prompt=system_prompt,
            temperature=0.7 if intervention_type == "normal" else 0.5,
            max_tokens=150
        )
        
        if response:
            logger.info(f"✅ Received response from LLM, length: {len(response)} chars")
            text = response.strip()
            # Remove any "Moderator:" prefix if present
            text = re.sub(r"^\s*Moderator[:\-–]?\s*", "", text)
            
            # Final check: ensure no fake names are used
            words = text.split()
            fake_name_detected = False
            for word in words:
                clean_word = word.strip('.,!?\'"()[]{}')
                if clean_word and clean_word[0].isupper() and clean_word not in actual_participants:
                    # Comprehensive list of common English words
                    common_words = [
                        'I', 'We', 'You', 'They', 'He', 'She', 'It', 'The', 'This', 'That', 'These', 'Those',
                        'Let', 'Let\'s', 'Lets', 'Id', 'I\'d', 'Ill', 'I\'ll', 'Im', 'I\'m', 'Ive', 'I\'ve',
                        'We\'re', 'We\'ll', 'We\'ve', 'We\'d', 'You\'re', 'You\'ll', 'You\'ve', 'You\'d',
                        'Please', 'Thanks', 'Thank', 'Good', 'Great', 'Awesome', 'Interesting',
                        'What', 'How', 'Why', 'When', 'Where', 'Which', 'Who', 'Whom',
                        'Next', 'Start', 'Begin', 'Think', 'Thought', 'Help', 'Question', 'Answer',
                        'Point', 'Idea', 'Agree', 'Disagree', 'Hello', 'Hi', 'Hey', 'Welcome',
                        'Everyone', 'All', 'Some', 'Most', 'Few', 'Many', 'Both', 'Each', 'Every',
                        'First', 'Second', 'Third', 'Last', 'Final', 'Important', 'Critical',
                        'Water', 'Desert', 'Survival', 'Item', 'Items', 'Rank', 'Ranking',
                        'Mirror', 'Flashlight', 'Knife', 'Parachute', 'Compass', 'Map', 'Matches',
                        'Coat', 'Plastic', 'Sheet', 'Book', 'Salt', 'Tablets', 'Bottle',
                        'Student', 'Students', 'Group', 'Team', 'Everyone'
                    ]
                    if clean_word not in common_words and len(clean_word) > 2:
                        logger.warning(f"⚠️ Detected potential fake name '{clean_word}', using fallback")
                        fake_name_detected = True
                        break
            
            if fake_name_detected:
                return get_fallback_response()
            
            logger.info(f"✅ Final response: {text[:150]}...")
            return text
        
        logger.warning("⚠️ No response from LLM, using fallback")
        return get_fallback_response()
            
    except Exception as e:
        logger.error(f"❌ [generate_active_moderator_response] Error: {e}")
        logger.error(traceback.format_exc())
        return get_fallback_response()

# ============================================================
# 💬 PASSIVE MODERATOR RESPONSE GENERATOR - ADD THIS FUNCTION
# ============================================================
def generate_passive_moderator_response(
    participants: List[str],
    chat_history: List[Dict[str, Any]],
    last_user_message: Optional[str] = None,
    time_elapsed: int = 0
) -> Optional[str]:
    """Generate PASSIVE moderator response - ONLY when asked directly"""
    try:
        if not last_user_message:
            return None
        
        # Filter out Moderator
        actual_participants = [p for p in participants if p != 'Moderator' and p]
        
        last_msg_lower = last_user_message.lower()
        time_remaining = max(0, 15 - time_elapsed)
        
        # Check if moderator was asked directly
        asked_moderator = any([
            '@moderator' in last_msg_lower,
            'moderator' in last_msg_lower and '?' in last_user_message,
            'what do you think' in last_msg_lower,
            'your opinion' in last_msg_lower,
            'help us' in last_msg_lower,
            'can you help' in last_msg_lower,
            'what should we' in last_msg_lower
        ])
        
        if not asked_moderator:
            return None
        
        # Simple, minimal response based on question type
        if 'time' in last_msg_lower or 'minute' in last_msg_lower:
            return f"You have about {time_remaining} minutes remaining."
        elif 'rank' in last_msg_lower or 'item' in last_msg_lower or 'task' in last_msg_lower:
            return "You need to rank the 12 desert survival items from most important (1) to least important (12)."
        else:
            return "I'm observing the discussion. Continue with your task."
            
    except Exception as e:
        logger.error(f"❌ [generate_passive_moderator_response] Error: {e}")
        return None

# ============================================================
# ✅ FEEDBACK GENERATION
# ============================================================
def format_feedback_response(response: str, student_name: str) -> str:
    """Normalize LLM feedback into the standard UI wrapper."""
    text = (response or "").strip()
    if not text:
        return ""
    if "**Your Feedback**" in text or "📊" in text:
        return "\n" + text if not text.startswith("\n") else text
    return f"\n📊 **Your Feedback**\n\n{text}"


def get_fallback_feedback(
    student_name: str, message_count: int, toxic_count: int = 0
) -> str:
    """Short alias for template feedback when the LLM is unavailable."""
    return generate_detailed_fallback(student_name, message_count, [], toxic_count)


def generate_personalized_feedback(
    student_name: str,
    message_count: int,
    response_times: List[float],
    story_progress: int,
    hint_responses: int = 0,
    behavior_type: str = "moderate",
    toxic_count: int = 0,
    off_topic_count: int = 0,
    chat_history: List[Dict[str, Any]] = None,
    story_context: str = "",
    chat_sender_name: Optional[str] = None,
) -> str:
    """
    Generate personalized feedback via Groq/OpenAI when configured, with template fallback.
    chat_sender_name: username as it appears in chat_history 'sender' (defaults to student_name).
    """
    student_messages: List[str] = []
    sender_key = chat_sender_name if chat_sender_name is not None else student_name

    try:
        if chat_history:
            student_messages = [
                msg.get("message", "")
                for msg in chat_history
                if msg.get("sender") == sender_key
            ]

        inappropriate_from_text = 0
        for msg in student_messages:
            is_bad, _ = check_inappropriate_language(msg, allow_casual_slang=True)
            if is_bad:
                inappropriate_from_text += 1

        effective_toxic = max(toxic_count, inappropriate_from_text)
        total_words = sum(len(m.split()) for m in student_messages)
        share_hint = ""
        if message_count > 0 and total_words > 0:
            share_hint = f"Avg words/message: {total_words / max(message_count, 1):.1f}"

        recent_snippets = [msg[:200] for msg in student_messages[-10:]]
        messages_block = (
            "\n".join(f"- {s}" for s in recent_snippets)
            if recent_snippets
            else "(No messages sent.)"
        )

        context = f"""STUDENT DISPLAY NAME: {student_name}
CHAT USERNAME (for your awareness): {sender_key}
MESSAGES SENT: {message_count}
TOTAL WORDS (their messages): {total_words}
INAPPROPRIATE-LANGUAGE MESSAGES (count): {effective_toxic}
OFF-TOPIC SIGNALS (count): {off_topic_count}
STORY / TASK PROGRESS: {story_progress}%
BEHAVIOR PROFILE: {behavior_type}
HINTS / PROMPTS ANSWERED: {hint_responses}
{share_hint}

THEIR RECENT MESSAGES (newest last, truncated):
{messages_block}

TASK / DISCUSSION CONTEXT:
{story_context or "Desert survival ranking — collaborate and justify item order."}
"""

        system_prompt = """You are an expert educational facilitator providing personalized, constructive feedback.

Generate feedback with:
1. A warm, personalized opening using the student's display name
2. **Strengths:** (2-3 bullet points — cite specific ideas or behaviors from their messages when possible)
3. **Areas for Improvement:** (1-2 bullet points; if inappropriate-language count > 0, mention professional tone respectfully)
4. **Next Steps:** (1-2 concrete, actionable suggestions)
5. A brief encouraging closing

Be specific and professional. Return ONLY the feedback text (no preamble or meta-commentary)."""

        if not openai_client and not groq_client:
            logger.warning("⚠️ No LLM client for feedback; using template fallback")
            return get_fallback_feedback(
                student_name, message_count, effective_toxic
            )

        response = call_llm(
            messages=[{"role": "user", "content": context}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=800,
        )

        if response and len(response.strip()) > 100:
            return format_feedback_response(response, student_name)

        logger.warning("⚠️ LLM feedback missing or too short; using template fallback")
        return get_fallback_feedback(student_name, message_count, effective_toxic)

    except Exception as e:
        logger.error(f"❌ Error generating feedback: {e}")
        logger.error(traceback.format_exc())
        return get_fallback_feedback(
            student_name,
            message_count,
            max(toxic_count, 0),
        )

def generate_detailed_fallback(student_name: str, message_count: int, student_messages: List[str] = None, inappropriate_count: int = 0) -> str:
    """Fallback feedback when LLM is unavailable"""
    student_messages = student_messages or []
    last_message = student_messages[-1][:100] + "..." if student_messages else "participating"
    
    inappropriate_note = ""
    if inappropriate_count > 0:
        inappropriate_note = "\n• Remember to keep language professional and academic"
    
    if message_count == 0:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for being part of our session today.

**Strengths:**
• You showed up and engaged silently

**Areas for Improvement:**
• Try sharing one small thought next time{inappropriate_note}

**Next Steps:**
• Start with one observation next session

I look forward to hearing from you!
"""
    elif message_count <= 2:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for your contributions!

**Strengths:**
• You were willing to participate
• Your message about "{last_message}" showed engagement

**Areas for Improvement:**
• Try to elaborate more on your ideas{inappropriate_note}

**Next Steps:**
• Try to share 2-3 times next session

Keep up the good work!
"""
    else:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for your active participation!

**Strengths:**
• You consistently engaged with the material
• Your message about "{last_message}" showed creative thinking

**Areas for Improvement:**
• Try connecting your ideas to what others said{inappropriate_note}

**Next Steps:**
• Build on classmates' ideas

Great work today!
"""

# ============================================================
# 🍃 RANDOM ENDINGS
# ============================================================
def get_random_ending() -> str:
    """Return a random ending message for sessions"""
    endings = [
        "The discussion has concluded. Thank you for participating!",
        "Great discussion everyone! The session is now complete.",
        "Thank you for your valuable contributions to this session.",
        "Session completed. Great work collaborating with your team!",
        "The desert survival task is now complete. Well done everyone!"
    ]
    return random.choice(endings)