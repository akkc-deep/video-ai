"""Small real-file automatic delivery fixture, without models or media commands."""
from types import SimpleNamespace
from pathlib import Path
from video_ai.runtime.manifest import now
from video_ai.runtime.production_state import ArtifactStamp, write_exclusive
from video_ai.runtime.paths import OUTPUT_ROOT
from unit.test_production_composition_records import payload, report


def delivery_case(runtime_run):
    run, config, paths = runtime_run
    p = payload(run)
    options = dict(output_paths=dict(movie=str(OUTPUT_ROOT/(run.name+'.mp4')),
        subtitle=str(OUTPUT_ROOT/(run.name+'.srt')), receipt=str(OUTPUT_ROOT/(run.name+'.delivery.json'))))
    write_exclusive(run/'production/options.json', options)
    write_exclusive(run/'production/composition.json', report(run,p))
    write_exclusive(run/'logs/production/checkpoints/composition/final.json', dict(payload=p))
    checks = {k:'passed' for k in ('source_text_coverage','audio_samples','frame_mapping','subtitles','final_media')}
    write_exclusive(run/'production/technical-checks.json',dict(schema_version=1,execution_mode='automatic',run_id=run.name,
        created_at=now(),composition_report=ArtifactStamp.read(run/'production/composition.json').to_dict(),
        technical_checks=checks,human_review='unverified'))
    return run, SimpleNamespace(options=options, config=config), paths, p
