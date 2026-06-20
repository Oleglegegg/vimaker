"""Runtime configuration.

Every knob has a sane default so the app works out of the box. Text/vision come from
a local Ollama server; nothing is sent to the cloud. Values can be overridden via
VIMAKER_* environment variables.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VIMAKER_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Local LLM (Ollama) — primary, fully local & free ---
    ollama_host: str = "http://localhost:11434"
    # Single multimodal model does both vision and text (RU/EN desc + hashtags).
    ollama_model: str = "gemma3:12b"
    ollama_text_model: str = "gemma3:12b"
    ollama_timeout: float = 180.0
    use_ollama: bool = True
    adult_mode: bool = True            # phrasing hint for the VLM prompt

    # --- Montage geometry ---
    # Preview length and number of scenes are the user-facing knobs; the per-clip
    # length is derived (clip_len = target_len / num_clips).
    target_len: float = 12.0          # desired preview length, seconds
    num_clips: int = 6                # number of distinct scenes/moments in the preview
    montage_height: int = 720         # output height (width auto, even)
    montage_fps: int = 30
    keep_audio: bool = True           # keep original audio snippets in montage

    # --- Scene detection ---
    scene_threshold: float = 27.0     # PySceneDetect ContentDetector threshold
    min_scenes_for_detect: int = 4    # below this -> motion-based sampling fallback
    motion_sample_fps: float = 2.0    # dense sampling rate (fps) for motion analysis

    # --- Keyframes ---
    # Keyframe count adapts to video length: ~1 frame per `keyframe_secs` seconds,
    # clamped to [keyframe_min, keyframe_max]. Scenes change slowly in long videos,
    # and each frame costs real vision time, so the cap stays modest.
    keyframe_min: int = 6
    keyframe_max: int = 12            # hard cap (vision speed: ~7s/frame)
    keyframe_secs: float = 20.0       # seconds of video per analyzed frame
    keyframe_size: int = 512          # longest side, px (downscaled to save tokens)

    # --- Hashtags ---
    hashtag_count: int = 12           # how many hashtags to generate
    hashtag_words: int = 1            # max words per hashtag (1 = single-word tags)

    # --- Description length (words) ---
    desc_words: int = 45              # target word count for the description
    desc_words_tol: int = 15          # +/- tolerance around the target

    @property
    def clip_len(self) -> float:
        """Length of each moment clip, derived from preview length / scene count."""
        return self.target_len / max(1, self.num_clips)


def load_settings() -> Settings:
    return Settings()
