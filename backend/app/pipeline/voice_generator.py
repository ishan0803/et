"""Voice generation service using ElevenLabs TTS."""

import os
import logging
from pydub import AudioSegment

from elevenlabs import ElevenLabs

from app.config import (
    settings, ELEVENLABS_MODEL,
    MIN_WPM, MAX_WPM, MAX_PAUSE_BETWEEN_SEGMENTS,
)
from app.models import Script, VoiceSegment, VoiceResult
from app.utils.helpers import job_dir, count_words

logger = logging.getLogger(__name__)

# Cache for discovered voice ID
_cached_voice_id: str | None = None


def _get_available_voice_id(client: ElevenLabs) -> str:
    """Get a voice ID that works with the user's plan.

    Queries the API for available voices and picks the best one.
    Free-tier users can only use pre-made voices, not library voices.
    """
    global _cached_voice_id
    if _cached_voice_id:
        return _cached_voice_id

    try:
        response = client.voices.get_all()
        voices = response.voices if hasattr(response, 'voices') else response

        # Prefer pre-made voices (these work on free tier)
        premade = [v for v in voices if getattr(v, 'category', '') == 'premade']
        if premade:
            # Pick a professional-sounding voice
            preferred_names = ['rachel', 'adam', 'sam', 'josh', 'arnold', 'bella', 'domi', 'elli', 'antoni']
            for name in preferred_names:
                for v in premade:
                    if name in v.name.lower():
                        _cached_voice_id = v.voice_id
                        logger.info(f"Selected pre-made voice: {v.name} ({v.voice_id})")
                        return _cached_voice_id

            # Just use the first premade voice
            _cached_voice_id = premade[0].voice_id
            logger.info(f"Selected first pre-made voice: {premade[0].name} ({premade[0].voice_id})")
            return _cached_voice_id

        # Fallback: use any available voice
        if voices:
            _cached_voice_id = voices[0].voice_id
            logger.info(f"Selected fallback voice: {voices[0].name} ({voices[0].voice_id})")
            return _cached_voice_id

    except Exception as e:
        logger.warning(f"Failed to fetch voices: {e}")

    # Last resort hardcoded fallback - "Rachel" pre-made voice
    _cached_voice_id = "21m00Tcm4TlvDq8ikWAM"
    logger.info(f"Using hardcoded fallback voice ID: {_cached_voice_id}")
    return _cached_voice_id


def generate_voice(script: Script, job_id: str,
                   voice_id: str = None) -> VoiceResult:
    """Generate TTS audio for each script segment using ElevenLabs."""
    work_dir = job_dir(job_id)
    audio_dir = os.path.join(work_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    # Auto-discover a working voice if none provided
    vid = voice_id or _get_available_voice_id(client)
    logger.info(f"Using voice ID: {vid}")

    segments: list[VoiceSegment] = []
    audio_clips: list[AudioSegment] = []

    for seg in script.segments:
        seg.text = seg.text.replace("*", "").replace('"', '').replace('\n', ' ')
        seg_path = os.path.join(audio_dir, f"segment_{seg.segment_id}.mp3")

        try:
            # Generate audio
            audio_generator = client.text_to_speech.convert(
                voice_id=vid,
                text=seg.text,
                model_id=ELEVENLABS_MODEL,
                output_format="mp3_44100_128",
            )

            # Write audio bytes
            with open(seg_path, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)

        except Exception as e:
            logger.warning(f"ElevenLabs TTS failed for segment {seg.segment_id} ({e}), falling back to edge-tts...")
            try:
                import subprocess
                clean_text = seg.text.replace("*", "").replace('"', '').replace('\n', ' ')
                cmd = [
                    "edge-tts",
                    "--voice", "en-US-ChristopherNeural",
                    "--text", clean_text,
                    "--write-media", seg_path
                ]
                result = subprocess.run(cmd, check=False, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"edge-tts exit {result.returncode}: {result.stderr}")
            except Exception as fallback_e:
                logger.error(f"Fallback edge-tts also failed: {fallback_e}")
                raise

        # Measure duration from the generated file (whether from ElevenLabs or edge-tts)
        clip = AudioSegment.from_mp3(seg_path)
        duration_sec = len(clip) / 1000.0
        word_count = count_words(seg.text)
        wpm = (word_count / duration_sec) * 60 if duration_sec > 0 else 0

        segments.append(VoiceSegment(
            segment_id=seg.segment_id,
            audio_path=seg_path,
            duration=duration_sec,
            wpm=wpm,
        ))

        audio_clips.append(clip)
        logger.info(
            f"Segment {seg.segment_id}: {duration_sec:.1f}s, "
            f"{wpm:.0f} WPM, {word_count} words"
        )

    # Build combined audio with short gaps between segments
    main_audio = AudioSegment.silent(duration=200)  # Start with 200ms silence
    gap = AudioSegment.silent(duration=int(MAX_PAUSE_BETWEEN_SEGMENTS * 1000))
    
    main_clips = audio_clips[:-1] if len(audio_clips) > 1 else audio_clips
    cta_clip = audio_clips[-1] if len(audio_clips) > 1 else AudioSegment.silent(duration=100)

    for i, clip in enumerate(main_clips):
        main_audio += clip
        if i < len(main_clips) - 1:
            main_audio += gap

    main_audio += AudioSegment.silent(duration=500)  # End with 500ms silence
    
    # CTA clip
    cta_audio = cta_clip
    
    # Legacy combined
    combined = main_audio + gap + cta_audio

    main_path = os.path.join(audio_dir, "main.mp3")
    cta_path = os.path.join(audio_dir, "cta.mp3")
    combined_path = os.path.join(audio_dir, "narration.mp3")
    
    main_audio.export(main_path, format="mp3", bitrate="128k")
    cta_audio.export(cta_path, format="mp3", bitrate="128k")
    combined.export(combined_path, format="mp3", bitrate="128k")

    main_duration = len(main_audio) / 1000.0
    cta_duration = len(cta_audio) / 1000.0
    total_duration = len(combined) / 1000.0
    
    total_words = sum(count_words(seg.text) for seg in script.segments)
    avg_wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0

    result = VoiceResult(
        segments=segments,
        combined_audio_path=combined_path,
        main_audio_path=main_path,
        cta_audio_path=cta_path,
        main_duration=main_duration,
        cta_duration=cta_duration,
        total_duration=total_duration,
        average_wpm=avg_wpm,
    )

    _validate_voice(result)
    return result


def _validate_voice(result: VoiceResult):
    """Validate voice output quality."""
    if result.average_wpm < MIN_WPM * 0.8:
        logger.warning(f"Voice too slow: {result.average_wpm:.0f} WPM")
    if result.average_wpm > MAX_WPM * 1.2:
        logger.warning(f"Voice too fast: {result.average_wpm:.0f} WPM")

    logger.info(
        f"Voice validated: {result.total_duration:.1f}s total, "
        f"{result.average_wpm:.0f} avg WPM, {len(result.segments)} segments"
    )
