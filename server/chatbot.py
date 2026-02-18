from __future__ import annotations
import os
import time
import random
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class _GroqReply:
    def __init__(self, content: str): 
        self.content = content

class GroqChatbot:
    def __init__(self, system_prompt: str, model_name=None, temperature=None, max_tokens=None):
        self.system_prompt = system_prompt.strip()
        
        # Get Groq API key
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("❌ ERROR: GROQ_API_KEY not found in .env")
            print("ℹ️ Get FREE API key from: https://console.groq.com/keys")
            raise ValueError("GROQ_API_KEY not found")
        
        # Initialize Groq client
        try:
            from groq import Groq
            self.client = Groq(api_key=api_key)
        except ImportError:
            print("❌ Please install groq: pip install groq")
            raise
        
        # Configuration
        self.model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.temperature = float(temperature or os.getenv("GROQ_TEMPERATURE", "0.7"))
        self.max_tokens = int(max_tokens or os.getenv("GROQ_MAX_TOKENS", "2000"))
        self.max_retries = int(os.getenv("GROQ_MAX_RETRIES", "3"))
        
        print(f"✅ Groq chatbot ready: {self.model_name}")
        print(f"📊 Config: temp={self.temperature}, tokens={self.max_tokens}")

    def send_message(self, prompt: str, thread_id: Optional[str] = None):
        """Send message to Groq API"""
        
        # Fallback responses
        fallbacks = [
            "Thanks for sharing! Let's continue with the story.",
            "I appreciate your input. What do others think?",
            "Good point! The story continues...",
            "Interesting observation! Let's see what happens next.",
        ]
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model_name,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False,
                )
                
                content = response.choices[0].message.content
                print(f"✅ Groq response received ({len(content)} chars)")
                return _GroqReply(content)
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    print(f"❌ All retries failed: {e}")
                    # Return fallback response
                    return _GroqReply(random.choice(fallbacks))
                
                wait_time = 1 * (attempt + 1)
                print(f"⚠️ Attempt {attempt + 1} failed, waiting {wait_time}s: {e}")
                time.sleep(wait_time)
        
        return _GroqReply(random.choice(fallbacks))