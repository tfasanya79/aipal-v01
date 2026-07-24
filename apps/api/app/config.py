from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aipal:aipal_dev@localhost:5432/aipal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    jwt_refresh_days: int = 30
    aipal_env: str = "development"
    magic_link_dev_return_token: bool = True
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_timeout_seconds: float = 18.0
    deepseek_max_tokens: int = 220
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 18.0
    openai_max_tokens: int = 220
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_num_predict: int = 72
    ollama_temperature: float = 0.2
    ollama_timeout_seconds: float = 12.0
    # "base" is the minimum production default for accent/noise robustness.
    # Use WHISPER_MODEL=tiny only for low-resource local demos.
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 5
    max_audio_decode_seconds: int = 12
    tts_provider: str = "edge"
    tts_timeout_seconds: float = 6.0
    stt_provider: str = "whisper_stream"
    whisper_stream_partial_interval_ms: int = 150
    stt_min_confidence: float = 0.28
    stt_max_no_speech_probability: float = 0.78
    stt_min_final_chars: int = 2
    semantic_endpointing_provider: str = "multilingual_semantic"
    semantic_endpointing_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    semantic_endpointing_model_source: str = "huggingface:qdrant/fastembed-onnx"
    semantic_endpointing_model_device: str = "cpu"
    semantic_endpointing_model_cache_path: str = ".cache/endpointing"
    semantic_endpointing_supported_languages: str = "en,pcm,fr"
    semantic_endpointing_fallback_mode: str = "language_agnostic"
    semantic_endpointing_inference_timeout_seconds: float = 0.10
    semantic_endpointing_latency_slo_seconds: float = 0.02
    semantic_endpointing_min_confidence: float = 0.55
    semantic_endpointing_code_switch_threshold: float = 0.65
    semantic_endpointing_production_fallback_policy: str = "fail_closed"
    semantic_endpointing_min_wait_ms: int = 240
    semantic_endpointing_max_wait_ms: int = 1_400
    neural_vad_provider: str = "silero_v6"
    neural_vad_model_version: str = "silero-v6-faster-whisper"
    neural_vad_device: str = "cpu"
    neural_vad_sample_rate: int = 16_000
    neural_vad_frame_ms: int = 40
    neural_vad_start_threshold: float = 0.55
    neural_vad_end_threshold: float = 0.35
    neural_vad_start_min_ms: int = 64
    neural_vad_thinking_pause_ms: int = 320
    neural_vad_preroll_ms: int = 320
    neural_vad_max_utterance_ms: int = 20_000
    neural_vad_inference_timeout_seconds: float = 0.02
    neural_vad_fallback_mode: str = "adaptive_energy_development_only"
    neural_vad_production_fallback_policy: str = "fail_closed"
    neural_vad_echo_suppression_enabled: bool = True
    neural_vad_echo_start_threshold: float = 0.72
    neural_vad_diagnostics_enabled: bool = True
    topic_classifier_provider: str = "semantic_local"
    topic_classifier_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    topic_classifier_model_version: str = "topic-transition-v1"
    topic_classifier_device: str = "cpu"
    topic_classifier_min_confidence: float = 0.62
    topic_classifier_ambiguity_threshold: float = 0.12
    topic_classifier_timeout_seconds: float = 0.10
    topic_classifier_latency_slo_seconds: float = 0.025
    topic_classifier_max_paused_topics: int = 5
    topic_classifier_topic_expiry_seconds: int = 86_400
    topic_classifier_confirmation_expiry_seconds: int = 1_800
    topic_classifier_same_topic_similarity: float = 0.62
    topic_classifier_related_similarity: float = 0.42
    topic_classifier_unrelated_similarity: float = 0.30
    topic_classifier_resume_similarity: float = 0.58
    topic_classifier_fallback_mode: str = "safe_ambiguous"
    topic_classifier_production_fallback_policy: str = "fail_closed"
    topic_classifier_diagnostics_enabled: bool = True
    live_voice_v2: bool = True
    live_voice_transport: str = "websocket_pcm"
    realtime_voice_provider: str = ""
    live_turns_per_minute: int = 20
    mem0_enabled: bool = False
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_timeout_seconds: float = 8.0
    ai_reasoning_enabled: bool = True
    ai_reasoning_max_tokens: int = 384
    ai_reasoning_timeout_seconds: float = 90.0
    ai_streaming_enabled: bool = True
    ai_stream_segment_min_chars: int = 28
    ai_stream_segment_max_chars: int = 120
    ai_tts_queue_size: int = 4
    redis_url: str = ""
    context_cache_ttl_seconds: int = 180
    notification_dispatcher_enabled: bool = True
    notification_dispatcher_interval_seconds: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@aipal.local"
    smtp_use_tls: bool = True
    email_notifications_provider: str = "smtp"
    cors_origins: str = "*"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "aipal://spotify-callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
