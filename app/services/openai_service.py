"""OpenAI service for AI interactions."""

import io
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from openai import AsyncOpenAI
import httpx
from app.config import settings
from app.utils.texts import SYSTEM_PROMPTS

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def moderate_content(text: str) -> Tuple[bool, Optional[str]]:
    """
    Moderate content using OpenAI moderation.
    Returns (is_flagged, reason)
    """
    try:
        response = await openai_client.moderations.create(
            input=text,
            model="omni-moderation-latest"
        )
        
        result = response.results[0]
        if result.flagged:
            # Find which categories were flagged
            flagged_categories = [
                category for category, flagged in result.categories.model_dump().items()
                if flagged
            ]
            reason = f"Flagged categories: {', '.join(flagged_categories)}"
            return True, reason
        
        return False, None
        
    except Exception as e:
        logger.error(f"Moderation error: {e}")
        # In case of error, allow content but log the issue
        return False, None


async def chat_completion(
    messages: List[Dict[str, str]], 
    persona: str = 'default',
    user_id: int = None
) -> str:
    """Generate chat completion using OpenAI."""
    try:
        # Add system prompt based on persona
        system_prompt = SYSTEM_PROMPTS.get(persona, SYSTEM_PROMPTS['default'])
        
        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + messages
        
        response = await openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=full_messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise


async def chat_with_image(image_data: bytes, text: str, persona: str = 'default') -> str:
    """Analyze image with text using OpenAI Vision."""
    try:
        import base64
        
        # Encode image to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        system_prompt = SYSTEM_PROMPTS.get(persona, SYSTEM_PROMPTS['default'])
        
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": system_prompt + " Ты анализируешь изображения."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        raise


async def generate_image(prompt: str) -> str:
    """Generate image using DALL-E."""
    try:
        response = await openai_client.images.generate(
            model=settings.openai_image_model,
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        
        return response.data[0].url
        
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise


async def edit_image(image_data: bytes, prompt: str) -> str:
    """Edit image using DALL-E."""
    try:
        # Create a BytesIO object from image data
        image_file = io.BytesIO(image_data)
        image_file.name = "image.png"
        
        response = await openai_client.images.edit(
            image=image_file,
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        
        return response.data[0].url
        
    except Exception as e:
        logger.error(f"Image editing error: {e}")
        raise


async def transcribe_audio(audio_data: bytes) -> str:
    """Transcribe audio using Whisper."""
    try:
        # Create a BytesIO object from audio data
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.ogg"
        
        response = await openai_client.audio.transcriptions.create(
            model=settings.openai_whisper_model,
            file=audio_file,
            language="ru"
        )
        
        return response.text
        
    except Exception as e:
        logger.error(f"Audio transcription error: {e}")
        raise


async def text_to_speech(text: str, voice: str = "alloy") -> bytes:
    """Convert text to speech using OpenAI TTS."""
    try:
        response = await openai_client.audio.speech.create(
            model=settings.openai_tts_model,
            voice=voice,
            input=text,
            response_format="mp3"
        )
        
        # Read the audio data
        audio_data = b""
        async for chunk in response.iter_bytes():
            audio_data += chunk
        
        return audio_data
        
    except Exception as e:
        logger.error(f"Text-to-speech error: {e}")
        raise


async def download_image(url: str) -> bytes:
    """Download image from URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Image download error: {e}")
        raise


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, max_calls: int = 60, window: int = 60):
        self.max_calls = max_calls
        self.window = window
        self.calls = {}
    
    async def is_allowed(self, user_id: int) -> bool:
        """Check if user is within rate limits."""
        import time
        
        now = time.time()
        if user_id not in self.calls:
            self.calls[user_id] = []
        
        # Remove old calls outside the window
        self.calls[user_id] = [
            call_time for call_time in self.calls[user_id]
            if now - call_time < self.window
        ]
        
        # Check if under limit
        if len(self.calls[user_id]) < self.max_calls:
            self.calls[user_id].append(now)
            return True
        
        return False


# Global rate limiter instance
rate_limiter = RateLimiter(max_calls=30, window=60)  # 30 calls per minute