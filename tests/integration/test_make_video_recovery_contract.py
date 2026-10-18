"""Cross-stage recovery through the public coordinator and real HTTP/media.

Reposting an accepted request or regenerating a successful earlier stage must
break this test. Expected request counts are literal for two 0.1-second units.
"""
import json
from pathlib import Path

import pytest

from production_helpers import model_server, config_for_server
from production_visual_helpers import comfy_server, configure_comfy, install_visual_owned
from unit.test_production_inputs import production_config
from unit.test_production_storyboard import visual_handler


@pytest.mark.parametrize('stage', ['source_clips', 'upscale'])
def test_accepted_cross_stage_resume_preserves_original_prompt_and_prefix(
    production_config, runtime_run, monkeypatch, stage
):
    import video_ai.production as production
    import video_ai.runtime.production_upscale as upscale
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.preflight import PreflightReport, PreflightCheck

    run, _, paths = runtime_run
    with model_server(visual_handler) as (planner_url, planner_posts), comfy_server(
        production_config, run, paths, RunLogger(run, production=True)
    ) as (comfy_url, comfy_posts, gets, history):
        config = configure_comfy(config_for_server(production_config, planner_url, run), comfy_url, run)
        raw = json.loads(config.config_file.read_text(encoding='utf-8'))
        raw['media']['timeline'] = dict(sentence_pause_seconds=0, paragraph_pause_seconds=0, opening_seconds=0, closing_seconds=0)
        config.config_file.write_text(json.dumps(raw), encoding='utf-8')
        manager = install_visual_owned(monkeypatch)
        monkeypatch.setattr(upscale, 'ServiceManager', manager)
        monkeypatch.setattr(upscale, 'port_listening', lambda *args: False)
        monkeypatch.setattr(production, 'create_run', lambda *args: run)
        monkeypatch.setattr(production, 'DEFAULT_CONFIG', config.config_file)
        monkeypatch.setattr(production, 'production_preflight', lambda *args: PreflightReport((PreflightCheck('fixture', True, 'local'),)))
        original_wait = ComfyClient.wait_for
        interrupted = []

        def interrupt_after_acceptance(self, submission, **kwargs):
            if submission.stage == stage and not interrupted:
                interrupted.append(submission)
                raise KeyboardInterrupt('accepted original request before checkpoint')
            return original_wait(self, submission, **kwargs)

        monkeypatch.setattr(ComfyClient, 'wait_for', interrupt_after_acceptance)
        first = production.make_video(text='湖水。白鸟。')
        assert first.exit_code == 130 and first.status == 'interrupted'
        assert len(interrupted) == 1
        original_prompt = interrupted[0].prompt_id
        assert original_prompt in history
        prefix = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in run.rglob('*')
                  if p.is_file() and p.suffix in ('.wav', '.png', '.mp4', '.srt', '.ass')}
        earlier_posts = list(planner_posts)
        submitted_clients = [body['client_id'] for body in comfy_posts]
        monkeypatch.setattr(ComfyClient, 'wait_for', original_wait)
        resumed = production.make_video(run_dir=run)
        assert resumed.exit_code == 0 and resumed.status == 'delivered', resumed
        assert planner_posts == earlier_posts and len(planner_posts) == 4
        assert len(comfy_posts) == 8 and len({body['client_id'] for body in comfy_posts}) == 8
        assert [body['client_id'] for body in comfy_posts[:len(submitted_clients)]] == submitted_clients
        assert '/history/' + original_prompt in gets
        state = json.loads((run / 'production/production-state.json').read_text(encoding='utf-8'))
        uid = interrupted[0].unit_id.removesuffix(':attempt_0001')
        assert state['units'][stage][uid]['request']['prompt_id'] == original_prompt
        for name, stamp in prefix.items():
            path = Path(name)
            assert (path.stat().st_size, path.stat().st_mtime_ns) == stamp
        assert all(row['status'] == 'completed' for row in state['stages'].values())
        counts = len(comfy_posts), len(planner_posts), len(gets)
        again = production.make_video(run_dir=run)
        assert again.exit_code == 0
        assert (len(comfy_posts), len(planner_posts), len(gets)) == counts
        assert (again.movie, again.subtitle, again.receipt_path) == (resumed.movie, resumed.subtitle, resumed.receipt_path)


@pytest.mark.parametrize('mode', ['lost_queue_same', 'lost_queue_graph', 'lost_queue_client'])
def test_ambiguous_queue_history_same_id_requires_consistent_identity(
    production_config, runtime_run, monkeypatch, mode
):
    """Ignoring a contradictory queue identity must fail the refusal assertion."""
    from unit.test_production_visuals import full_prefix
    from video_ai.runtime.production_visuals import produce_start_images
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger

    run, _, paths = runtime_run
    with model_server(visual_handler) as (url, planner_posts), comfy_server(
        production_config, run, paths, RunLogger(run, production=True), mode=mode
    ) as (comfy_url, posts, gets, history):
        frozen, state, manifest, logger, timeline, board = full_prefix(
            production_config, run, paths, url, comfy_url, monkeypatch
        )
        with pytest.raises(ProductionRefused):
            produce_start_images(frozen, board, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 1
        original_prompt = next(iter(history))
        original_record = state.record_unit

        def stop_before_next(stage, uid, **kwargs):
            if stage == 'start_images' and uid == 'shot_0002' and kwargs.get('request') is not None:
                if mode != 'lost_queue_same':
                    raise AssertionError('contradictory original prompt was completed and next shot started')
                raise KeyboardInterrupt('stop before new shot POST')
            return original_record(stage, uid, **kwargs)

        monkeypatch.setattr(state, 'record_unit', stop_before_next)
        if mode == 'lost_queue_same':
            with pytest.raises(KeyboardInterrupt):
                produce_start_images(frozen, board, state=state, manifest=manifest, paths=paths, logger=logger)
            record = state.snapshot()['units']['start_images']['shot_0001']
            assert record['status'] == 'completed' and record['request']['prompt_id'] == original_prompt
            assert '/history/' + original_prompt in gets
        else:
            with pytest.raises(ProductionRefused):
                produce_start_images(frozen, board, state=state, manifest=manifest, paths=paths, logger=logger)
            assert state.snapshot()['units']['start_images']['shot_0001']['status'] != 'completed'
            # Cached matching history must not bypass the original contradiction.
            before = len(posts), len(gets)
            with pytest.raises(ProductionRefused):
                produce_start_images(frozen, board, state=state, manifest=manifest, paths=paths, logger=logger)
            assert (len(posts), len(gets)) == before
        assert len(posts) == 1 and '/queue' in gets and '/history' in gets
