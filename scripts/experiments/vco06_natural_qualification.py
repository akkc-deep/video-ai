"""Read-only qualification evidence audit; this command does not fit or render a candidate."""
import argparse
import json
from pathlib import Path

from video_ai.runtime.natural_qualification_audit import write_qualification_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    audit = commands.add_parser('audit')
    audit.add_argument('--delivery', required=True)
    audit.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        result = write_qualification_audit(Path(args.delivery), Path(args.output))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 3
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, ImportError) as exc:
        print(json.dumps(dict(status='blocked', error=dict(kind=type(exc).__name__, message=str(exc))), ensure_ascii=False))
        return 2
    except KeyboardInterrupt:
        print(json.dumps(dict(status='interrupted', ready_for_propose=False)))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
