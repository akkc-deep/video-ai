"""Read project-local secrets at use time; never include them in frozen config."""
import json
import os
from pathlib import Path

PROJECT_CREDENTIALS_FILE = Path(__file__).resolve().parents[2] / 'config/secrets.local.json'


def read_credentials(*names):
    values = [os.environ.get(name) or None for name in names]
    if all(values):
        return tuple(values)
    try:
        data = json.loads(PROJECT_CREDENTIALS_FILE.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return tuple(values)
    except (OSError, ValueError):
        raise ValueError('Cannot read project config/secrets.local.json; check its JSON format and permissions') from None
    if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
        raise ValueError('Project config/secrets.local.json must contain string values')
    return tuple(value or data.get(name, '').strip() or None for name, value in zip(names, values))
