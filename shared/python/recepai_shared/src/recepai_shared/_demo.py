from recepai_shared import settings, get_logger


def main() -> None:
    logger = get_logger("recepai_demo")
    logger.info("Starting recepai_shared demo")

    logger.info("Environment: %s", settings.environment)
    logger.info("Region: %s", settings.region)
    logger.info("Redis URL: %s", settings.redis_url)
    logger.info("VoiceAgent base URL: %s", settings.voiceagent_base_url)
    # Do NOT log the API key directly
    logger.info("ASR service name: %s", settings.asr_service_name)
    logger.info("LLM orchestrator name: %s", settings.llm_orchestrator_name)
    logger.info("TTS service name: %s", settings.tts_service_name)

    print("Current settings:", settings.model_dump())


if __name__ == "__main__":
    main()
