import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    hubspot_api_key: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_address: str | None
    imap_host: str | None
    imap_port: int
    imap_username: str | None
    imap_password: str | None
    hubspot_meeting_link: str | None
    database_url: str | None


def load_config() -> Config:
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        hubspot_api_key=os.environ.get("HUBSPOT_API_KEY"),
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_username=os.environ.get("SMTP_USERNAME"),
        smtp_password=os.environ.get("SMTP_PASSWORD"),
        smtp_from_address=os.environ.get("SMTP_FROM_ADDRESS"),
        imap_host=os.environ.get("IMAP_HOST"),
        imap_port=int(os.environ.get("IMAP_PORT", "993")),
        imap_username=os.environ.get("IMAP_USERNAME"),
        imap_password=os.environ.get("IMAP_PASSWORD"),
        hubspot_meeting_link=os.environ.get("HUBSPOT_MEETING_LINK"),
        database_url=os.environ.get("GTM_AGENT_DATABASE_URL"),
    )
