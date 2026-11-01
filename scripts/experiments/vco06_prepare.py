"""Technical preparation v2 for frozen VCO-06 collections; bootstrap first, never generates."""
import argparse
import json
from pathlib import Path

from video_ai.experiments.natural_acquisition import load_collection
from video_ai.experiments.natural_material_preparation import prepare_native_source_v2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--case',required=True)
    args = parser.parse_args(argv)
    try:
        plan = load_collection(args.root)
        selected = [c['case_id'] for c in plan['cases']] if args.case == 'all' else [args.case]
        for case_id in selected:
            print(json.dumps(dict(event='prepare_v2_start',case_id=case_id)),flush=True)
            result = prepare_native_source_v2(args.root,case_id)
            print(json.dumps(dict(event='prepare_v2_done',case_id=case_id,status=result['status'])),flush=True)
        print(json.dumps(dict(status='technical_import_complete',cases=len(selected),ready_for_propose=False)))
        return 0
    except KeyboardInterrupt:
        print(json.dumps(dict(status='interrupted',ready_for_propose=False)))
        return 130
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError) as exc:
        print(json.dumps(dict(status='blocked',ready_for_propose=False,
            error=dict(kind=type(exc).__name__,message=str(exc))),ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
