from pydantic import Field
from pydantic_settings import BaseSettings

from .local_config import load_local_config


class VoiceStackSettings(BaseSettings):
    environment: str = Field(default="dev", description="Environment name, e.g. dev/staging/prod")
    region: str = Field(default="ca-central-1", description="Deployment region identifier")
    redis_url: str = Field(default="redis://redis:6379/0", description="Redis connection URL for transient state")

    voiceagent_base_url: str = Field(default="https://mystore.com", description="Base URL of nopCommerce VoiceAgent endpoint")
    voiceagent_api_key: str = Field(default="CHANGE_ME", description="API key used for server-to-server calls to VoiceAgent")

    asr_service_name: str = Field(default="recepai-asr-service", description="Logical/URL base for ASR service")
    llm_orchestrator_name: str = Field(default="recepai-llm-orchestrator", description="Logical/URL base for LLM orchestrator service")
    tts_service_name: str = Field(default="recepai-tts-service", description="Logical/URL base for TTS service")

    class Config:
        env_prefix = "RECEPAI_"
        extra = "ignore"


# Module-level settings instance
load_local_config()
settings = VoiceStackSettings()
