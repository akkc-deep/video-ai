"""Archive a separate development-only human remote viewing record; bootstrap first."""
import argparse
import json
from pathlib import Path

from video_ai.experiments.natural_remote_observation import record_remote_observation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--observation', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = record_remote_observation(args.root, args.observation)
        code = 0
    except KeyboardInterrupt:
        result, code = dict(status='interrupted', ready_for_propose=False), 130
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, ImportError) as exc:
        result, code = dict(status='blocked', ready_for_propose=False,
            error=dict(kind=type(exc).__name__, message=str(exc))), 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
