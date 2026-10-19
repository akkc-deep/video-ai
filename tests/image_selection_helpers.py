"""Offline committed scenes and authentic Jimeng record layouts for selection tests."""
import hashlib
import json
import struct
import zlib

from unit.test_jimeng_config import configured
from unit.test_production_scenes import scene_proposal


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return path


def setup_selection(runtime_run, tmp_path, *, proposal=None):
    from video_ai.config import parse_scene_planning
    from video_ai.planning.production_scenes import build_scene_plan, canonical_digest
    from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ArtifactStamp
    run, original, paths = runtime_run
    config = configured(original, tmp_path)
    frozen = freeze_inputs(config, run, text='湖面很静。白鸟停在石上。它望向远处。\r\n\r\n它飞走了。')
    script = frozen.script
    units = dict(decoded_text=script.text, has_bom=script.has_bom, spans=thaw(script.spans),
                 semantic_specs={s.unit_id: dict(facts={}) for s in script.spans if s.kind == 'speech'})
    audio = {s.unit_id: ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', 96046, 123), 48000, 1, 2, 48001)
             for s in script.spans if s.kind == 'speech'}
    timeline = build_production_timeline(script, audio, settings=config.media.timeline)
    source = frozen.options['execution_policy']['input_identities']['script']['sha256']
    bible, plan = build_scene_plan(script, dict(units, run_id=run.name, source_sha256=source),
                                   timeline, proposal or scene_proposal(), settings=parse_scene_planning(config.raw.get('scene_planning')))
    save(run/'production/visual-bible.json', bible)
    save(run/'production/scene-plan.json', plan)
    commit = {k: plan[k] for k in ('schema_version', 'run_id', 'source_sha256', 'units_sha256',
                                  'timeline_sha256', 'settings', 'visual_bible_sha256')}
    save(run/'production/scene-plan-commit.json', dict(commit, scene_plan_sha256=canonical_digest(plan)))
    return dict(frozen=frozen, run=run, units=units, timeline=timeline, bible=bible, plan=plan,
                paths=paths, config=config)


def candidate_manifest(setup, scene_id, *, count=1):
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.manifest import thaw
    frozen, run = setup['frozen'], setup['run']
    settings = frozen.config.image_generation
    scene = next(row for row in setup['plan']['scenes'] if row['scene_id'] == scene_id)
    folder = run/'production/jimeng'/scene_id
    def chunk(kind, raw):
        return struct.pack('>I', len(raw))+kind+raw+struct.pack('>I', zlib.crc32(kind+raw))
    width, height = settings.output_width, settings.output_height
    png = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
           +chunk(b'IDAT', zlib.compress((b'\0'+b'\x22\x88\xcc'*width)*height))+chunk(b'IEND', b''))
    requests = [dict(schema_version=2, run_id=run.name, scene_id=scene_id, request_id=f'request_{i:02d}',
                     prompt=scene['image_prompt'], image_generation=thaw(settings))
                for i in range(1, settings.candidates_per_scene+1)]
    candidates = []
    for request in requests:
        rid = request['request_id']; directory = folder/rid
        save(directory/'request.json', request)
        identity = canonical_digest(request)
        save(directory/'intent.json', dict(schema_version=2, identity=identity, created_at='2026-10-18T00:00:00+00:00', state='intent'))
        task_id = 'task_'+rid
        save(directory/'accepted.json', dict(schema_version=2, identity=identity, task_id=task_id, request_id='official_'+rid, diagnostic={}))
        save(directory/'outputs.json', dict(schema_version=2, identity=identity, sources=['a'*64]*count))
        rows = []
        for index in range(1, count+1):
            cid = f'{rid}_image_{index:02d}'; path = directory/(cid+'.original')
            path.write_bytes(png)
            sha = hashlib.sha256(png).hexdigest()
            save(directory/(cid+'.download.json'), dict(schema_version=2, identity=identity, candidate_id=cid, bytes=len(png), sha256=sha))
            row = dict(candidate_id=cid, request_id=rid, task_id=task_id, req_key=settings.req_key,
                       path=str(path), bytes=len(png), sha256=sha, width=width, height=height, format='png')
            save(directory/(cid+'.json'), row); rows.append(row)
        save(directory/'result.json', dict(schema_version=2, identity=identity, task_id=task_id, candidates=rows))
        candidates.extend(rows)
    return save(folder/'candidates.json', dict(schema_version=2, run_id=run.name, scene_id=scene_id,
                                               identity=canonical_digest(requests), candidates=candidates))


def notification_receipt(setup, batch):
    """Create actual MIME attachment and accepted transport evidence without sending."""
    from dataclasses import asdict
    from email.message import EmailMessage
    from email import policy
    from pathlib import Path
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.selection_config import parse_selection_email
    run = setup['run']; created_at = '2026-10-18T00:00:00+00:00'
    mail = run/'production/image-selection'/batch['batch_id']/'mail'
    folder = mail/'part_0001/attempt_0001'; folder.mkdir(parents=True,exist_ok=True)
    message_id = f"<{run.name}.{batch['batch_id']}.part_0001.attempt_0001@video-ai.local>"
    message = EmailMessage(policy=policy.SMTP)
    message['From'] = batch['delivery']['sender']; message['To'] = batch['delivery']['recipient']
    message['Subject'] = 'Offline selection fixture'; message['Message-ID'] = message_id
    message.set_content('Offline image selection evidence fixture.')
    attachments = []
    for scene in batch['scenes']:
        for row in scene['candidates']:
            raw = Path(row['path']).read_bytes()
            message.add_attachment(raw,maintype='image',subtype='png',filename=scene['scene_id']+'_'+row['candidate_id']+'.png')
            attachments.append(dict(scene_id=scene['scene_id'], candidate_id=row['candidate_id'],
                                    original_sha256=row['sha256'], attachment_sha256=hashlib.sha256(raw).hexdigest()))
    raw = message.as_bytes(); path = folder/'message.eml'; path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    save(mail/'notification.json', dict(schema_version=2,run_id=run.name,batch_id=batch['batch_id'],
        scene_manifest_sha256=canonical_digest(batch),created_at=created_at,
        parts=[dict(part=1,total=1,message_id=message_id,path=str(path),bytes=len(raw),sha256=sha,attachments=attachments)]))
    intent = dict(schema_version=2,run_id=run.name,batch_id=batch['batch_id'],part=1,attempt=1,
        message_id=message_id,mime_sha256=sha,transport=asdict(parse_selection_email(setup['frozen'].config.raw.get('selection_email'))),
        created_at=created_at)
    save(folder/'intent.json',intent)
    return save(folder/'receipt.json',dict(intent,accepted_at=created_at,smtp_code=250))
