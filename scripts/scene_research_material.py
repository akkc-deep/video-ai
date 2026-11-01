"""Explicit, local-only VCO-06 research input operations; bootstrap first."""
import argparse
import json
from pathlib import Path

from video_ai.config import load_config
from video_ai.runtime.paths import RuntimePaths
from video_ai.runtime.research_material_records import verify_wan_material


def _failure(args, request, exc):
    error = dict(kind=type(exc).__name__, message=str(exc) or type(exc).__name__)
    interrupted = isinstance(exc, KeyboardInterrupt)
    if args.command != 'import':
        return dict(status='interrupted' if interrupted else 'blocked', error=error), 130 if interrupted else 2
    from video_ai.runtime.research_material_records import ResearchReader
    from video_ai.runtime._scene_continuity_io import uid, artifact
    run, commit, started = None, None, False
    material_id = request.get('material_id') if isinstance(request, dict) else None
    try:
        uid(material_id)
        registry = Path('D:/VideoSi/projects/video-ai/research-material-imports')/(material_id+'.json')
        if registry.exists():
            binding = ResearchReader().read(registry)
            run = Path(binding['run_dir'])
            started = (run/'research/material/intent.json').is_file()
            if (run/'research/material/commit.json').is_file():
                commit = artifact(run/'research/material/commit.json')
    except (ValueError, OSError, KeyError, TypeError, KeyboardInterrupt):
        pass
    io_failure = isinstance(exc, (OSError, TimeoutError)) and started
    status = 'interrupted' if interrupted else 'failed' if io_failure else 'blocked'
    result = dict(schema_version=1, material_id=material_id, run_dir=str(run) if run else None,
                  status=status, commit=commit, error=error)
    return result, 130 if interrupted else 1 if io_failure else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('verify-source')
    p.add_argument('--index', required=True)
    p.add_argument('--config', required=True)
    p = sub.add_parser('import')
    p.add_argument('--request', required=True)
    p = sub.add_parser('status')
    p.add_argument('--run-dir', required=True)
    p = sub.add_parser('analyze')
    p.add_argument('--run-dir', required=True)
    p.add_argument('--manifest', required=True)
    p = sub.add_parser('baseline')
    p.add_argument('--run-dir', required=True)
    args = parser.parse_args(argv)
    request = None
    try:
        if args.command == 'verify-source':
            result = verify_wan_material(Path(args.index), config=load_config(Path(args.config)))
        elif args.command == 'import':
            from video_ai.runtime.production_research_material import import_research_material
            from video_ai.runtime.research_material_records import ResearchReader
            request = ResearchReader().read(Path(args.request))
            config = load_config(Path(request['config']['path']))
            result = import_research_material(Path(args.request), paths=RuntimePaths.from_config(config))
        elif args.command == 'analyze':
            from video_ai.runtime.production_research_material import analyze_research_material
            result = analyze_research_material(Path(args.run_dir), Path(args.manifest))
        elif args.command == 'baseline':
            from video_ai.runtime.research_material_baseline import measure_research_material
            result = measure_research_material(Path(args.run_dir))
        else:
            from video_ai.runtime.research_material_records import load_research_material_context
            result = load_research_material_context(Path(args.run_dir))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 3 if result.get('status') in ('awaiting_evidence', 'awaiting_qualification', 'awaiting_observation') else 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, ImportError, TimeoutError, KeyboardInterrupt) as exc:
        result, code = _failure(args, request, exc)
        print(json.dumps(result, ensure_ascii=False))
        return code


if __name__ == '__main__':
    raise SystemExit(main())
