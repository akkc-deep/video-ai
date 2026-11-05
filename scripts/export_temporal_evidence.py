"""Install the pinned core or finalize admission from real production preflight."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from video_ai.adapters.common import strict_json
from video_ai.runtime.production_state import ProductionRefused, object_fields
from video_ai.runtime.temporal_scene_admission import (
    BUNDLE_TOOLS_ROOT, QUALIFICATION_ROOT, finalize_temporal_evidence, install_temporal_bundle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path,
                        default=QUALIFICATION_ROOT/'native16-qualification-assessment.json')
    parser.add_argument('--install-bundle', action='store_true')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--production-preflight', type=Path)
    parser.add_argument('--target', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.install_bundle:
            if any(value is not None for value in (args.runtime, args.production_preflight, args.target)):
                parser.error('bundle installation and production finalization are distinct operations')
            result = install_temporal_bundle(args.qualification, tools_root=BUNDLE_TOOLS_ROOT)
            print(json.dumps(dict(operation='install_core_only', production_ready=False, **result)))
            return 0
        if any(value is None for value in (args.runtime, args.production_preflight, args.target)):
            parser.error('production admission requires --runtime, --production-preflight and --target')
        target = args.target
        if (not target.is_absolute() or not target.is_relative_to(Path('D:/VideoSi'))
                or '..' in target.parts or target.suffix.lower() != '.json'):
            raise ProductionRefused('admission target requires an exact absolute D:/VideoSi JSON path')
        runtime = strict_json(args.runtime.read_bytes())
        object_fields(runtime, ('runtime_bundle', 'native_python', 'package_versions', 'production_worker'), 'production runtime')
        admitted = finalize_temporal_evidence(args.qualification, runtime, args.production_preflight, target=target)
        print(json.dumps(dict(operation='production_admission', evidence=admitted['root'],
                              observed_visual_scope=admitted['value']['observed_visual_scope'],
                              new_video_calls=0, new_text_encoding_calls=0)))
        return 0
    except (ProductionRefused, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps(dict(status='refused', error=str(exc))), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
