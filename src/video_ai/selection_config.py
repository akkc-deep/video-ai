"""Pure, immutable, non-secret image-selection mail settings."""
from dataclasses import dataclass, fields
import math
import re
from typing import Mapping

from .config import ConfigError


CONFIRMED_ADDRESS = '318575094@qq.com'


@dataclass(frozen=True)
class SelectionEmailSettings:
    sender: str = CONFIRMED_ADDRESS
    recipient: str = CONFIRMED_ADDRESS
    smtp_host: str = 'smtp.qq.com'
    smtp_port: int = 465
    smtp_security: str = 'ssl'
    smtp_password_env: str = 'VIDEO_AI_SMTP_AUTH_CODE'
    max_mime_bytes: int = 15 * 1024 * 1024
    timeout_seconds: int | float = 60

    def __post_init__(self):
        if self.sender != CONFIRMED_ADDRESS or self.recipient != CONFIRMED_ADDRESS:
            raise ConfigError('selection_email: sender and recipient must be the confirmed address')
        if self.smtp_security != 'ssl':
            raise ConfigError('selection_email: verified SSL is required')
        if not isinstance(self.smtp_host, str) or not re.fullmatch(
                r'(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', self.smtp_host):
            raise ConfigError('selection_email: invalid SMTP host')
        if type(self.smtp_port) is not int or not 1 <= self.smtp_port <= 65535:
            raise ConfigError('selection_email: invalid SMTP port')
        if not isinstance(self.smtp_password_env, str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_]*', self.smtp_password_env):
            raise ConfigError('selection_email: invalid password environment variable name')
        if type(self.max_mime_bytes) is not int or self.max_mime_bytes <= 0:
            raise ConfigError('selection_email: MIME limit must be a positive integer')
        try:
            valid_timeout = (type(self.timeout_seconds) in (int, float)
                             and math.isfinite(self.timeout_seconds) and self.timeout_seconds > 0)
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ConfigError('selection_email: timeout must be finite and positive')


def parse_selection_email(value) -> SelectionEmailSettings:
    """Parse live dicts or frozen raw mappings; never read credentials here."""
    if value is None:
        return SelectionEmailSettings()
    if not isinstance(value, Mapping):
        raise ConfigError('selection_email: expected object')
    if set(value) - {field.name for field in fields(SelectionEmailSettings)}:
        raise ConfigError('selection_email: unknown field')
    return SelectionEmailSettings(**value)
