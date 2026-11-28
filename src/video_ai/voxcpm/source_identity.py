"""The deployed official checkout is detached at its frozen commit; no system Git needed."""
from pathlib import Path
import re


def source_revision(directory):
    head=(Path(directory)/'.git/HEAD').read_text(encoding='ascii').strip()
    if not re.fullmatch('[0-9a-f]{40}',head):
        raise ValueError('VoxCPM source must be detached at the frozen revision')
    return head
