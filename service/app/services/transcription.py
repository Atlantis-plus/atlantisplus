import httpx
from openai import OpenAI
from app.config import get_settings


async def download_audio_from_storage(storage_path: str, supabase_url: str, service_key: str) -> bytes:
    """Download audio file from Supabase Storage."""
    # Construct the storage URL
    url = f"{supabase_url}/storage/v1/object/voice-notes/{storage_path}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"apikey": service_key}
        )
        response.raise_for_status()
        return response.content


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe audio using OpenAI Whisper API.

    Args:
        audio_bytes: Raw audio file bytes
        filename: Filename with extension for format detection

    Returns:
        Transcribed text
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    # Create a file-like object for the API
    audio_file = (filename, audio_bytes)

    response = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="text"
    )

    return response


async def transcribe_from_storage(storage_path: str) -> str:
    """
    Download audio from Supabase Storage and transcribe it.

    Args:
        storage_path: Path to audio file in voice-notes bucket

    Returns:
        Transcribed text
    """
    settings = get_settings()

    # Download audio
    audio_bytes = await download_audio_from_storage(
        storage_path,
        settings.supabase_url,
        settings.supabase_service_role_key
    )

    # Determine filename from path for format detection
    filename = storage_path.split("/")[-1] if "/" in storage_path else storage_path

    # Transcribe
    return transcribe_audio(audio_bytes, filename)
