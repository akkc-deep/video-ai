"""Submit existing authored clip reviews only; never run a generation pipeline."""
import argparse
import json
from pathlib import Path
from video_ai.runtime.production_inputs import load_frozen_inputs
from video_ai.runtime.production_image_selection import load_prepared_inputs
from video_ai.runtime.production_scene_clips import consume_scene_clip_observations
from video_ai.runtime.production_state import RunLock
from video_ai.runtime.paths import RuntimePaths
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.scene_revision_records import revision_validation, revision_read_transaction
from video_ai.runtime.verification import scene_input_protection

@revision_validation
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('observations', nargs='+', type=Path)
    args = parser.parse_args()
    with revision_read_transaction():
        frozen = load_frozen_inputs(args.run)
    with RunLock(args.run) as lock, scene_input_protection(frozen, review_only=True):
        with revision_read_transaction():
            units, timeline = load_prepared_inputs(frozen)
        result = consume_scene_clip_observations(
            frozen, units, timeline, args.observations,
            paths=RuntimePaths.from_config(frozen.config),
            logger=RunLogger(args.run, production=True), lock=lock)
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        raise SystemExit(result.exit_code)

if __name__ == '__main__':
    main()
