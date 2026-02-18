from __future__ import annotations

# ============================================================
# 📦 Imports
# ============================================================
from typing import List, Dict, Any, Optional
import os
import re
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

OPENAI_MODEL = get_env("OPENAI_CHAT_MODEL", str, False) or "gpt-3.5-turbo"
OPENAI_TEMPERATURE = get_env("OPENAI_TEMPERATURE", float, False) or 0.7
OPENAI_MAX_TOKENS = get_env("OPENAI_MAX_TOKENS", int, False) or 1000

ACTIVE_STORY_STEP = get_env("ACTIVE_STORY_STEP", int, False) or 1
PASSIVE_STORY_STEP = get_env("PASSIVE_STORY_STEP", int, False) or 1
CHAT_HISTORY_LIMIT = get_env("CHAT_HISTORY_LIMIT", int, False) or 50

WELCOME_MESSAGE = get_env("WELCOME_MESSAGE", str, False) or "Welcome everyone! I'm the Moderator."
ACTIVE_ENDING_MESSAGE = get_env("ACTIVE_ENDING_MESSAGE", str, False) or "✨ We have reached the end of the story."
PASSIVE_ENDING_MESSAGE = get_env("PASSIVE_ENDING_MESSAGE", str, False) or "✨ We have reached the end of the story."

# ============================================================
# 🧠 Groq Client Initialization
# ============================================================
groq_client = None
openai_client = None

try:
    if LLM_PROVIDER == "groq":
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if api_key and api_key.strip():
            groq_client = Groq(api_key=api_key)
            logger.info(f"✅ Groq client initialized with {GROQ_MODEL}")
        else:
            logger.error("❌ GROQ_API_KEY not found")
    elif LLM_PROVIDER == "openai":
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and api_key.strip():
            openai_client = OpenAI(api_key=api_key)
            logger.info("✅ OpenAI client initialized")
except Exception as e:
    logger.error(f"❌ LLM client initialization failed: {e}")

# ============================================================
# 🧩 ACTIVE MODE PROMPTS
# ============================================================
ACTIVE_MODE_PROMPTS = {
    "story": """
You are a warm, supportive classroom Moderator guiding students through a FIXED, pre-written story.

Your personality:
- Kind, encouraging, emotionally aware
- You sound like a caring teacher reading a story aloud
- You value student voices and participation

Your responsibility:
- The story already exists and must be followed exactly.
- You guide students through it step by step until its natural ending.
- You do not invent, rewrite, or change story events.

How you treat students:
- You acknowledge their ideas warmly, even when they are incorrect.
- You encourage participation and gently invite quiet students.
- You validate feelings, curiosity, and effort.
- You never shame, criticize, or dismiss students.

Story control:
- The story is the authority; student input is secondary.
- You NEVER change the plot based on student ideas.
- If a student idea conflicts with the story, you kindly redirect.

How to respond:
- 1–2 short sentences only.
- First: a gentle acknowledgment or encouragement.
- Then: continue the NEXT sentence(s) of the story as written.
- Each response advances the story by ONE step only.
"""
}

# ============================================================
# 🛠 Helper Functions
# ============================================================
def call_llm(messages, temperature=None, max_tokens=None, system_prompt=None):
    """Make LLM API call (Groq or OpenAI fallback)"""
    if not groq_client and not openai_client:
        logger.error("No LLM client available")
        return None
    
    try:
        if groq_client:
            groq_messages = []
            if system_prompt:
                groq_messages.append({"role": "system", "content": system_prompt})
            
            for msg in messages:
                groq_messages.append({"role": msg["role"], "content": msg["content"]})
            
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=groq_messages,
                temperature=temperature or GROQ_TEMPERATURE,
                max_tokens=max_tokens or GROQ_MAX_TOKENS,
                stream=False,
            )
            return response.choices[0].message.content
            
        elif openai_client:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=temperature or OPENAI_TEMPERATURE,
                max_tokens=max_tokens or OPENAI_MAX_TOKENS
            )
            return response.choices[0].message.content
            
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return None

def get_fallback_response():
    """Get a simple fallback response"""
    responses = [
        "Thanks for sharing! Let's continue with the story.",
        "I appreciate your input. What do others think?",
        "Good point! The story continues...",
        "Interesting observation! Let's see what happens next.",
    ]
    return random.choice(responses)

# ============================================================
# 💬 ACTIVE MODERATOR REPLY
# ============================================================
def generate_moderator_reply(
    participants: List[str],
    chat_history: List[Dict[str, Any]],
    story_block: str,
    story_progress: int = 0,
    extra_context: Optional[Dict[str, Any]] = None,
    is_last_chunk: bool = False,
) -> str:
    try:
        if is_last_chunk:
            return ACTIVE_ENDING_MESSAGE
        
        style_prompt = ACTIVE_MODE_PROMPTS.get("story")
        
        trimmed_history = chat_history[-CHAT_HISTORY_LIMIT:] if chat_history else []
        names = ", ".join(participants) if participants else "everyone"
        
        chat_text = ""
        for msg in trimmed_history[-10:]:
            sender = msg.get('sender', 'Unknown')
            message = msg.get('message', '')
            chat_text += f"{sender}: {message}\n"
        
        prompt = f"""
{style_prompt}

Story so far:
{story_block}

Recent chat:
{chat_text}

Participants: {names}

Respond with 1-2 sentences:
1. Acknowledge the last message if relevant
2. Continue the story by one step

Your response:
"""
        
        response = call_llm(
            messages=[
                {"role": "system", "content": "You are a warm classroom story moderator."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        if response:
            text = response.strip()
            text = re.sub(r"^\s*Moderator[:\-–]?\s*", "", text)
            text = " ".join(text.split()[:100])
            return text if text else get_fallback_response()
        else:
            return get_fallback_response()
            
    except Exception as e:
        logger.error(f"[generate_moderator_reply] Error: {e}")
        return get_fallback_response()

# ============================================================
# 🕯 PASSIVE STORYTELLER
# ============================================================
def generate_passive_chunk(
    paragraph: str,
    mode: str = None,
    is_last_chunk: bool = False,
) -> str:
    clean = paragraph.strip()
    if not clean:
        return ""
    
    if is_last_chunk:
        return PASSIVE_ENDING_MESSAGE
    
    return clean

# ============================================================
# 🎯 ENGAGEMENT RESPONSE
# ============================================================
def generate_engagement_response(
    participants: List[str],
    chat_history: List[Dict[str, Any]],
    story_context: str,
    current_progress: int,
) -> str:
    """Generate an engagement response without advancing the story"""
    try:
        trimmed_history = chat_history[-CHAT_HISTORY_LIMIT:] if chat_history else []
        names = ", ".join(participants) if participants else "everyone"
        
        chat_text = ""
        for msg in trimmed_history[-10:]:
            sender = msg.get('sender', 'Unknown')
            message = msg.get('message', '')
            chat_text += f"{sender}: {message}\n"
        
        prompt = f"""
You are a classroom moderator. Students need encouragement to discuss.

Story so far:
{story_context}

Recent conversation:
{chat_text}

Participants: {names}

Generate ONE open-ended question about the story so far.
Do NOT advance the story. Just ask a thoughtful question.
1 sentence only.

Your question:
"""
        
        response = call_llm([
            {"role": "user", "content": prompt}
        ])
        
        if response:
            text = response.strip()
            text = re.sub(r"^\s*Moderator[:\-–]?\s*", "", text)
            return text if text else "What are your thoughts about the story so far?"
        else:
            return "What are your thoughts about the story so far?"
            
    except Exception as e:
        logger.error(f"[generate_engagement_response] Error: {e}")
        return "What are your thoughts about the story so far?"

# ============================================================
# 🎯 SHOULD ADVANCE STORY
# ============================================================
def should_advance_story(
    chat_history: List[Dict[str, Any]],
    story_context: str,
    time_since_last_advance: int,
) -> bool:
    """Determine if it's appropriate to advance the story."""
    try:
        if time_since_last_advance > 60:
            return True
        
        trimmed_history = chat_history[-10:] if chat_history else []
        
        for msg in trimmed_history:
            content = msg.get('message', '').lower()
            if 'what happens next' in content or 'then what' in content:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[should_advance_story] Error: {e}")
        return time_since_last_advance > 60

# ============================================================
# ✅ COMPLETELY FIXED: Generate Personalized Feedback using Groq
# ============================================================

# ============================================================
# ✅ ENHANCED: Generate Detailed Structured Feedback
# ============================================================

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
    story_context: str = ""
) -> str:
    """
    Generate detailed, structured feedback with Strengths, Areas for Improvement, and Next Steps.
    """
    
    try:
        # Extract student's actual messages
        student_messages = []
        if chat_history:
            student_messages = [
                msg.get('message', '') 
                for msg in chat_history 
                if msg.get('sender') == student_name
            ]
        
        # Format student messages for the prompt
        if student_messages:
            messages_text = "\n".join([f"- {msg}" for msg in student_messages[-5:]])  # Last 5 messages
            logger.info(f"📝 Found {len(student_messages)} messages from {student_name}")
            
            # Find the most interesting/creative message to highlight
            interesting_message = student_messages[-1] if student_messages else "your contribution"
        else:
            messages_text = "No messages sent."
            interesting_message = "No messages"
        
        # Create a detailed prompt for structured feedback
        prompt = f"""You are an expert educational facilitator providing personalized feedback to a student.

STUDENT: {student_name}
MESSAGES SENT: {message_count}
STORY PROGRESS: {story_progress}%

STUDENT'S RECENT MESSAGES:
{messages_text}

INSTRUCTIONS:
Write a detailed, encouraging feedback with EXACTLY this structure:

1. Start with "Hi {student_name}," on its own line
2. Then a warm opening sentence acknowledging their specific contribution (mention one specific thing they said)
3. Then create THREE sections with these exact headers:
   **Strengths:**
   **Areas for Improvement:**
   **Next Steps:**

For each section:
- Strengths: List 2-3 specific things they did well, referencing their actual messages
- Areas for Improvement: List 1-2 specific suggestions, based on their participation pattern
- Next Steps: Give 1-2 actionable recommendations for future sessions

End with an encouraging closing sentence.

Make it warm, specific, and constructive. Use bullet points with * or -.

FEEDBACK:
"""
        
        # Call Groq to generate feedback
        response = call_llm(
            messages=[
                {"role": "system", "content": "You are a warm, supportive teacher who gives detailed, structured feedback to students. Always use the exact format requested."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600  # Increased for detailed feedback
        )
        
        if response and len(response.strip()) > 50:
            feedback = response.strip()
            logger.info(f"✅ Generated detailed feedback for {student_name}")
            
            # Format the feedback with the header
            return f"""
📊 **Your Feedback**

{feedback}
"""
        else:
            logger.warning(f"⚠️ Groq returned short response, using fallback for {student_name}")
            return generate_detailed_fallback(student_name, message_count, student_messages)
            
    except Exception as e:
        logger.error(f"❌ Error generating detailed feedback: {e}")
        return generate_detailed_fallback(student_name, message_count, student_messages if 'student_messages' in locals() else [])


def generate_detailed_fallback(student_name: str, message_count: int, student_messages: List[str] = None) -> str:
    """Enhanced fallback with structure when Groq is unavailable"""
    
    student_messages = student_messages or []
    
    if student_messages:
        last_message = student_messages[-1][:100] + "..." if len(student_messages[-1]) > 100 else student_messages[-1]
    else:
        last_message = "participating in our discussion"
    
    if message_count == 0:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for being part of our session today. While you didn't send any messages, your presence was valued.

**Strengths:**
• You showed up and engaged silently with the material
• Your attention to the discussion matters

**Areas for Improvement:**
• Try sharing one small thought next time
• Even a simple question helps the group

**Next Steps:**
• Start with one observation in the next session
• Build confidence by sharing gradually

I look forward to hearing your voice in future discussions!
"""
    
    elif message_count <= 2:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for your contributions today! You shared some thoughtful ideas with us.

**Strengths:**
• You were willing to participate and share your thoughts
• Your message about "{last_message}" showed engagement

**Areas for Improvement:**
• Try to elaborate more on your ideas
• Build on what others say to create dialogue

**Next Steps:**
• In the next session, try to share 2-3 times
• Ask a question to a classmate

Keep up the good work!
"""
    
    else:
        return f"""
📊 **Your Feedback**

Hi {student_name},

Thank you for your active participation today! You contributed {message_count} thoughtful messages to our discussion.

**Strengths:**
• You consistently engaged with the material
• Your message about "{last_message}" showed creative thinking
• You helped move the conversation forward

**Areas for Improvement:**
• Try connecting your ideas to what others have said
• Consider asking questions to invite others into the discussion

**Next Steps:**
• In future sessions, try to build on classmates' ideas
• Challenge yourself to think about character motivations

Great work today! I look forward to hearing more from you.
"""

# ============================================================
# 🍃 RANDOM ENDINGS
# ============================================================
def get_random_ending() -> str:
    endings = [
        "And so the story gently came to an end.",
        "With that, the adventure softly concluded.",
        "The tale settled into a peaceful ending.",
        "And the story rested, complete at last.",
        "The journey ended quietly, leaving smiles behind.",
        "The final moment arrived, soft and warm.",
    ]
    return random.choice(endings)