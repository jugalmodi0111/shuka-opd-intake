import datetime
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    sarvam_api_key: str = ""
    intake_mode: str = "mock"                  # mock | live
    asr_model: str = "saaras:v3"
    tts_model: str = "bulbul:v3"
    llm_model: str = "sarvam-m"
    vision_confidence_threshold: float = 0.6
    encounter_date: str = "2026-06-11"         # ISO; injectable for temporal-anchor tests
    region: str = "IN-generic"
    fixtures_dir: Path = Path("fixtures")
    lexicon_dir: Path = Path(__file__).parent / "lexicons"
    speakers: dict[str, str] = {"hi-IN": "anushka", "ta-IN": "anushka"}

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def encounter_date_parsed(self) -> datetime.date:
        return datetime.date.fromisoformat(self.encounter_date)


settings = Settings()
