"""Read-only continuity policy, provenance, playback responses and current admission.

Machine scores are retained verbatim. This module never generates media, runs
the detector, writes receipts, or infers that an author played a video.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import math
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from .manifest import thaw
from ._continuity_byte_guard import observe_inventory, observe_absence
from .production_state import ProductionRefused, object_fields, integer
from ._scene_continuity_io import (SceneContinuityPending, Reader, artifact, verify,
    instant, nonempty, uid, run_for, local)


def load_continuity_policy(frozen):
    raw = getattr(getattr(frozen, 'config', None), 'raw', {})
    config = raw.get('scene_continuity') if 'scene_continuity' in raw else None
    identities = getattr(frozen,'options',{}).get('execution_policy', {}).get('input_identities', {})
    identity = identities.get('scene_continuity_policy')
    if 'scene_continuity' not in raw:
        if identity is not None: raise ProductionRefused('continuity role lacks frozen configuration')
        return None
    from ..config import parse_scene_continuity
    expected = parse_scene_continuity(thaw(config))
    if identity is None: raise ProductionRefused('frozen continuity policy identity missing')
    from ..media._continuity_schema import identity as file_identity
    file_identity(thaw(identity))
    path = run_for(frozen)/'production/scene-continuity/policy.json'
    if identity['path'] != str(path): raise ProductionRefused('continuity policy path differs')
    verify({k: identity[k] for k in ('path', 'bytes', 'sha256')})
    if parse_scene_continuity(Reader().read(path)) != expected: raise ProductionRefused('continuity policy meaning differs')
    return expected


def _schema(value, fields, run=None):
    object_fields(value, fields.split(), 'continuity record')
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ProductionRefused('unsupported continuity record schema')
    if run is not None and value.get('run_id') != run.name:
        raise ProductionRefused('continuity record belongs to another run')
    return value


def _engine(value):
    object_fields(value, 'algorithm parameters_sha256 implementation dependency_fingerprint'.split(), 'continuity Engine')
    if value['algorithm'] != 'continuity_cv_v1': raise ProductionRefused('unsupported continuity engine')
    for key in ('parameters_sha256', 'dependency_fingerprint'):
        if type(value[key]) is not str or len(value[key]) != 64 or any(c not in '0123456789abcdef' for c in value[key]):
            raise ProductionRefused('engine digest malformed')
    if not isinstance(value['implementation'], list) or not value['implementation']:
        raise ProductionRefused('engine implementation missing')
    paths = [v['path'] for v in value['implementation']]
    if paths != sorted(set(paths)): raise ProductionRefused('engine implementation ordering differs')
    return value


def _current_engine():
    from ..media.continuity_report import capture_continuity_engine
    try:return capture_continuity_engine()
    except (ImportError,RuntimeError) as exc:
        raise ProductionRefused('continuity engine unavailable: '+str(exc)) from exc


def _archive(commit, intent, reader):
    value = reader.read(commit['engine_archive'])
    _schema(value, 'schema_version engine_digest versions build_information files')
    if value['engine_digest'] != canonical_digest(intent['engine']): raise ProductionRefused('engine archive digest differs')
    object_fields(value['versions'], 'python numpy opencv'.split(), 'engine versions')
    build = verify(value['build_information'])
    folder = Path(commit['engine_archive']['path']).parent
    if build.parent != folder: raise ProductionRefused('engine build archive escapes epoch')
    originals, archives, total = [], {}, 0
    from ..media._continuity_schema import stable
    from .manifest import _identity
    for row in value['files']:
        object_fields(row, ('original', 'archived'), 'engine archive file')
        _identity(row['original']); original = row['original']; saved = row['archived']
        total += saved['bytes']
        if total > 536870912: raise ProductionRefused('resource_limit: engine archive exceeds 512MiB')
        if (original['bytes'] != saved['bytes'] or original['sha256'] != saved['sha256']
                or not Path(saved['path']).is_relative_to(folder/'files')):
            raise ProductionRefused('engine archive identity differs')
        verify(saved, empty=original['bytes']==0); reader.check()
        originals.append(original); archives[original['path']] = saved
    if [x['path'] for x in originals] != sorted(set(x['path'] for x in originals)):
        raise ProductionRefused('duplicate or unordered engine archive source')
    for source in intent['engine']['implementation']:
        original = next((r for r in originals if r['path'] == source['path']), None)
        if original is None or any(original[k] != source[k] for k in ('bytes', 'sha256')):
            raise ProductionRefused('engine archive lacks implementation')
    text = build.read_text(encoding='utf-8')
    fingerprint = canonical_digest(dict(**value['versions'], build_information=text, package_files=stable(originals)))
    if fingerprint != intent['engine']['dependency_fingerprint']:
        raise ProductionRefused('archived dependency fingerprint differs')
    return dict(engine=intent['engine'], versions=value['versions'], build_information=text,
                files=originals, archives=archives)


def _epochs(frozen, clip_ids, reader, *, current=True):
    run = run_for(frozen); root = run/'production/scene-continuity/epochs'
    commits, intents = {}, {}
    if not root.exists():
        observe_absence(root)
        return [], False
    folders=sorted(root.iterdir())
    observe_inventory(root,'children',folders)
    for folder in folders:
        if not folder.is_dir(): raise ProductionRefused('unexpected continuity epoch entry')
        eid = uid(folder.name); path = folder/'intent.json'
        if not path.is_file(): raise ProductionRefused('epoch lacks intent')
        value = reader.read(path)
        _schema(value, 'schema_version run_id epoch_id previous_commit clip_ids engine reason requested_at', run)
        if value['epoch_id'] != eid or value['clip_ids'] != clip_ids: raise ProductionRefused('epoch plan/ID differs')
        _engine(value['engine']); nonempty(value['reason'])
        if instant(value['requested_at']) > datetime.now(timezone.utc): raise ProductionRefused('future epoch intent')
        intents[eid] = value
        if not (folder/'commit.json').exists():
            observe_absence(folder/'commit.json')
            continue
        commit = reader.read(folder/'commit.json')
        _schema(commit, 'schema_version run_id epoch_id intent engine_archive created_at', run)
        if commit['epoch_id'] != eid or commit['intent'] != artifact(path): raise ProductionRefused('epoch commit intent differs')
        if not instant(value['requested_at'])<=instant(commit['created_at'])<=datetime.now(timezone.utc):
            raise ProductionRefused('epoch commit timestamp outside intent/current time')
        if commit['engine_archive']['path'] != str(folder/'engine/manifest.json'):
            raise ProductionRefused('epoch archive path differs')
        archived = _archive(commit, value, reader)
        commits[eid] = dict(intent=value, commit=commit, artifact=artifact(folder/'commit.json'), archive=archived)
    by_sha = {row['artifact']['sha256']: eid for eid, row in commits.items()}
    children = {}; first = []
    for eid, value in intents.items():
        previous = value['previous_commit']
        if previous is None: first.append(eid); parent = None
        else:
            verify(previous); parent = by_sha.get(previous['sha256'])
            if parent is None or previous != commits[parent]['artifact']: raise ProductionRefused('epoch previous commit unavailable')
        if parent in children: raise ProductionRefused('continuity epoch fork')
        children[parent] = eid
    if intents and len(first) != 1: raise ProductionRefused('continuity epoch root missing or ambiguous')
    chain = []; seen = set(); cursor = children.get(None)
    while cursor is not None:
        if cursor in seen: raise ProductionRefused('continuity epoch cycle')
        seen.add(cursor)
        if cursor in commits: chain.append(commits[cursor])
        cursor = children.get(cursor)
    if seen != set(intents): raise ProductionRefused('disconnected continuity epoch')
    pending = len(intents) != len(commits)
    if len(intents)-len(commits) > 1: raise ProductionRefused('multiple pending continuity epochs')
    if current and chain and not pending:
        if _current_engine() != chain[-1]['intent']['engine']:
            return chain, True
    return chain, pending


def _binding(context, records, clip_id):
    store = context['store']
    budget = next((r['budget'] for r in context['rows'] if r['budget']['clip_id'] == clip_id), None)
    if budget is None: raise ProductionRefused('continuity clip outside committed plan')
    prefix = []
    for row in context['rows']:
        b = row['budget']; cid = b['clip_id']
        if b['scene_id'] != budget['scene_id']: continue
        record = records.get(cid)
        if record is None: raise SceneContinuityPending('technical continuity prefix incomplete')
        # Imported records retain origin paths in the original media declaration.
        folder = _metadata_folder(context['frozen'],cid,record,proof=getattr(store,'revision_context',None))
        prefix.append(dict(clip_id=cid, clip_record=artifact(folder/'clip.json'), request=artifact(folder/'request.json'),
            generated=record['clip']['generated'], source=record['clip']['source'], mapping=artifact(folder/'mapping.json'),
            last_frame=artifact(folder/'last-frame.json'), source_frames=[0,b['retained_frames']],
            output_frames=[b['start_frame'],b['end_frame']]))
        if cid == clip_id: break
    r = records[clip_id]
    return dict(scene_id=budget['scene_id'], clip_id=clip_id, clips=prefix,
        selected_image=deepcopy(r['request']['selected_image']), comparison_images=deepcopy(r['request']['comparison_images']),
        visual_bible_sha256=context['inputs']['visual_bible_sha256'])


def _metadata_folder(frozen,cid,record,*,proof=None):
    """Imported media copies retain their original technical-record provenance."""
    if 'scene_revision' in getattr(frozen,'options',{}):
        from .scene_revision_records import require_scene_revision
        proof=proof or require_scene_revision(frozen)
        if 'clip:'+cid in proof['imports']:
            from .production_inputs import load_frozen_inputs
            from ._scene_revision_origins import source_clip_record
            original=source_clip_record(load_frozen_inputs(proof['source_run']),cid)
            # The verified sidecar pins the original JSON even across multiple imports.
            sidecar=proof['imports']['clip:'+cid][0]
            origin=sidecar.get('origin_artifact')
            if origin is not None:
                verify(origin)
                if Path(origin['path']).name=='clip.json':return Path(origin['path']).parent
            candidate=Path(original['clip']['source']['path']).parent
            if (candidate/'clip.json').is_file():return candidate
            observe_absence(candidate/'clip.json')
            return _metadata_folder(load_frozen_inputs(proof['source_run']),cid,original)
    return Path(record['clip']['source']['path']).parent


def validate_manifest_binding(manifest, binding, *, config, timeout=300, _reader=None):
    """Prove all retained frames, fixed reference and adjacent/join coverage."""
    budget_reader=_reader or Reader(timeout)
    from ..media._continuity_schema import validate_continuity_manifest
    from ..media.colorimetry import load_color_analysis_set
    validate_continuity_manifest(manifest)
    if (manifest['scope'] != 'scene' or manifest['scene_id'] != binding['scene_id']
            or manifest['domain']['source_kind'] != 'generated' or manifest['timeline'] != dict(fps_num=16,fps_den=1)):
        raise ProductionRefused('continuity production domain/scope differs')
    if manifest['domain']['genre'] not in ('people','animals','transport','outdoor','indoor','animation','unspecified'):
        raise ProductionRefused('continuity genre must be explicitly declared')
    if [c['clip_id'] for c in manifest['clips']] != [c['clip_id'] for c in binding['clips']]:
        raise ProductionRefused('manifest does not cover exact retained prefix')
    if len(manifest['references']) != 1: raise ProductionRefused('one independent fixed reference required')
    from ..media._continuity_schema import validate_regions
    input_frames=[f for c in manifest['clips'] for f in c['frames']]+manifest['references']
    regions_value=budget_reader.read({k:manifest['regions'][k] for k in ('path','bytes','sha256')})
    regions=validate_regions(regions_value,{f['record']['path']:f for f in input_frames})
    required_anchors={c['frames'][0]['frame_id'] for c in manifest['clips']}|{manifest['references'][0]['frame_id']}
    if any({a['frame_id'] for a in r['anchors']}!=required_anchors for r in regions):
        raise ProductionRefused('each region requires exact clip starts and independent fixed reference ROI')
    if instant(regions_value['reviewed_at'])>datetime.now(timezone.utc):raise ProductionRefused('future ROI review')
    if manifest['context'] is not None:
        context_value=budget_reader.read({k:manifest['context'][k] for k in ('path','bytes','sha256')})
        if instant(context_value['reviewed_at'])>datetime.now(timezone.utc):raise ProductionRefused('future context review')
    paths = [f['record']['path'] for c in manifest['clips'] for f in c['frames']]+[manifest['references'][0]['record']['path']]
    with load_color_analysis_set(paths, config=config, timeout=timeout) as reader:
        frame_ids = []; first = None
        for clip, expected in zip(manifest['clips'], binding['clips']):
            if len(clip['frames']) != expected['source_frames'][1]: raise ProductionRefused('continuity retained frames incomplete')
            mapping = budget_reader.read(expected['mapping'])
            origin=budget_reader.read(expected['clip_record'])['source']
            for i, frame in enumerate(clip['frames']):
                rec = reader.records[frame['record']['path']] if hasattr(reader, 'records') else reader._records[frame['record']['path']]
                if (rec['source']['sha256'] != expected['source']['sha256'] or rec['source']['path'] not in (expected['source']['path'],origin['path'])
                        or rec['frame_index'] != i): raise ProductionRefused('analysis frame source/index differs')
                if origin['sha256']!=expected['source']['sha256']:raise ProductionRefused('inherited source differs from proven origin')
                mapped = rec['mapping']
                if (not mapped or mapped['clip_id'] != expected['clip_id'] or mapped['retained_frame_index'] != i
                        or mapped['output_frame_index'] != expected['output_frames'][0]+i
                        or mapped['generated_frame_index'] != mapping['retained_to_generated'][i]):
                    raise ProductionRefused('analysis retained/generated/output mapping differs')
                if rec['pts'] is None or Fraction(rec['pts'])*Fraction(rec['time_base']) != Fraction(i,16):
                    raise ProductionRefused('source native PTS differs')
                if first is None: first = rec
                frame_ids.append(frame['frame_id'])
        ref = reader._records[paths[-1]]
        if ref['source']['sha256'] != first['source']['sha256'] or ref['frame_index'] != first['frame_index']:
            raise ProductionRefused('fixed reference not scene first retained frame')
    comparisons = {(r['kind'],r['left'],r['right']) for r in manifest['comparisons']}
    for clip in manifest['clips']:
        ids = [f['frame_id'] for f in clip['frames']]
        if any(('adjacent',a,b) not in comparisons for a,b in zip(ids,ids[1:])):
            raise ProductionRefused('adjacent comparison coverage incomplete')
    for a,b in zip(manifest['clips'],manifest['clips'][1:]):
        if ('parent_join',a['frames'][-1]['frame_id'],b['frames'][0]['frame_id']) not in comparisons:
            raise ProductionRefused('actual parent join not covered')
    rid = manifest['references'][0]['frame_id']
    if any(('reference',rid,fid) not in comparisons for fid in frame_ids[1:]):
        raise ProductionRefused('fixed reference coverage incomplete')
    return manifest


def derive_concerns(report):
    result = {}
    for row in report['detectors']:
        if row['status'] == 'no_candidate': continue
        source = dict(detector_id=row['detector_id'], region_id=row['region_id'], frame_ids=row['frame_ids'],
                      status=row['status'], reasons=row['reasons'])
        key = canonical_digest(source)
        value = dict(concern_id=key, **source, score=row['score'],
            evidence=[{k: e[k] for k in ('path','bytes','sha256')} for e in row['evidence']])
        if key in result and result[key] != value: raise ProductionRefused('conflicting repeated concern')
        result[key] = value
    return list(result.values())


def _prefix(value, expected, video, reviewer, at, reader):
    binding = expected['binding']
    if len(binding['clips']) <= 2:
        if value != expected['video_observation']: raise ProductionRefused('prefix must equal clip observation')
        return video
    prefix = _read_prefix_original(value,expected['run'],reader)
    _schema(prefix, 'schema_version run_id assessment_id assessment review_method reviewer viewed_at playback start_observation process_observation end_observation quality_observation checks verdict issues', expected['run'])
    uid(prefix['assessment_id']); verify(prefix['assessment'])
    if prefix['assessment']==expected.get('assessment_artifact'):
        historical=expected['assessment']
    else:
        loader=expected.get('historical_assessment_loader')
        if loader is None:raise ProductionRefused('prefix lacks verified historical assessment provenance')
        historical=loader(prefix['assessment'])
    if historical['assessment_id'] != prefix['assessment_id'] or _candidate(historical['binding']) != _candidate(binding):
        raise ProductionRefused('prefix playback assessment identity differs')
    if prefix['review_method'] not in ('human_video','agent_video') or prefix['reviewer'] != reviewer:
        raise ProductionRefused('prefix requires same author actual video playback')
    playback = [{k: row[k] for k in ('clip_id','source','source_frames','output_frames')} for row in binding['clips']]
    if prefix['playback'] != playback: raise ProductionRefused('prefix playback coverage incomplete')
    for key in ('start_observation','process_observation','end_observation','quality_observation'): nonempty(prefix[key])
    object_fields(prefix['checks'], 'subject_identity color_lighting motion_process camera_path cumulative_color'.split(), 'prefix checks')
    states = list(prefix['checks'].values())
    if any(s not in ('passed','failed','unverified') for s in states): raise ProductionRefused('invalid prefix check')
    if not isinstance(prefix['issues'],list): raise ProductionRefused('prefix issues must be list')
    for issue in prefix['issues']:
        object_fields(issue, 'check clip_id frames description'.split(), 'prefix issue')
        row = next((c for c in binding['clips'] if c['clip_id'] == issue['clip_id']),None)
        if issue['check'] not in prefix['checks'] or row is None: raise ProductionRefused('prefix issue context differs')
        frames = issue['frames']
        if type(frames) is not list or len(frames)!=2 or any(type(f) is not int for f in frames) or not 0<=frames[0]<frames[1]<=row['source_frames'][1]:
            raise ProductionRefused('prefix issue frames invalid')
        nonempty(issue['description'])
    verdict = 'failed' if 'failed' in states else 'unverified' if 'unverified' in states else 'passed'
    if prefix['verdict'] != verdict or (verdict=='passed' and prefix['issues']) or (verdict=='failed' and not prefix['issues']):
        raise ProductionRefused('prefix verdict differs')
    viewed = instant(prefix['viewed_at'])
    if viewed > at: raise ProductionRefused('prefix playback is in future')
    for clip in binding['clips']:
        if viewed < instant(reader.read(clip['clip_record'])['created_at']): raise ProductionRefused('prefix played before media completed')
    return prefix


def _read_prefix_original(ref,run,reader):
    """Retained author bytes survive removal of the caller's original file.

    An existing changed input still fails identity validation. The deterministic
    SHA-named archive is the only fallback; no arbitrary source is searched.
    """
    path=local(ref['path'],exists=False)
    if path.exists():return reader.read(ref)
    observe_absence(path)
    backup=Path(run)/'production/scene-continuity/prefix-observations'/(ref['sha256']+'.json')
    retained=dict(ref,path=str(backup))
    return reader.read(retained)


def validate_continuity_review(value, expected, *, now):
    reader = expected.get('reader') or Reader()
    _schema(value, 'schema_version run_id assessment_id assessment video_observation prefix_observation reviewer reviewed_at responses', expected['run'])
    assessment = expected['assessment']
    if (value['assessment_id'] != assessment['assessment_id'] or value['assessment'] != expected['assessment_artifact']):
        raise ProductionRefused('review current assessment differs')
    uid(value['assessment_id']); verify(value['assessment'])
    video = reader.read(value['video_observation'])
    from .scene_clip_observations import validate_scene_clip_observation
    video = validate_scene_clip_observation(video, expected['video_expected'], now=now)
    nonempty(value['reviewer'])
    if value['reviewer'] != video['reviewer']: raise ProductionRefused('review author differs from playback author')
    at = instant(value['reviewed_at'])
    if not max(instant(assessment['created_at']),instant(video['viewed_at'])) <= at <= instant(now):
        raise ProductionRefused('review timestamp outside actual evidence window')
    prefix = _prefix(value['prefix_observation'], dict(expected, video_observation=value['video_observation']),
                     video, value['reviewer'],at,reader)
    concerns = {c['concern_id']:c for c in assessment['concerns']}
    responses = value['responses']
    if not isinstance(responses,list) or len(responses)!=len(concerns): raise ProductionRefused('risk responses incomplete')
    seen = set(); states = []
    for response in responses:
        object_fields(response, 'concern_id disposition reason references'.split(), 'continuity response')
        key = response['concern_id']
        if key not in concerns or key in seen: raise ProductionRefused('unknown/duplicate concern response')
        seen.add(key); nonempty(response['reason'])
        disposition = response['disposition']
        if disposition not in ('not_observed_in_full_playback','explained_change','confirmed_issue','unverified'):
            raise ProductionRefused('unsupported concern disposition')
        if not isinstance(response['references'],list): raise ProductionRefused('response references must be list')
        for ref in response['references']: verify(ref)
        if disposition in ('explained_change','not_observed_in_full_playback') and (video['verdict']!='passed' or prefix['verdict']!='passed'):
            raise ProductionRefused('response requires passed complete dynamic playback')
        if disposition == 'explained_change': _explanation(response, concerns[key], assessment, reader)
        states.append(disposition)
    # Return author bytes' meaning without mutating machine states or adding fields.
    return deepcopy(value)


def _explanation(response, concern, assessment, reader):
    manifest = reader.read(assessment['manifest'])
    context_id = manifest['context']
    if context_id is None: raise ProductionRefused('explained change lacks frozen context')
    context_artifact = {k: context_id[k] for k in ('path','bytes','sha256')}
    if context_artifact not in response['references']: raise ProductionRefused('explained change lacks original context reference')
    context = reader.read(context_artifact)
    declarations = context.get('events', [])
    if not any(concern['detector_id'] in d.get('detector_ids',[]) and concern['region_id'] in d.get('region_ids',[])
               and set(concern['frame_ids']) <= set(d.get('frame_ids',[])) for d in declarations):
        raise ProductionRefused('context declaration does not explain this concern')


def _review_state(review, reader):
    video = reader.read(review['video_observation'])
    root=Path(review['assessment']['path']).parents[4]
    prefix = video if review['prefix_observation']==review['video_observation'] else _read_prefix_original(review['prefix_observation'],root,reader)
    dispositions = [r['disposition'] for r in review['responses']]
    if video['verdict']=='failed' or prefix['verdict']=='failed' or 'confirmed_issue' in dispositions: return 'blocked'
    if video['verdict']=='unverified' or prefix['verdict']=='unverified' or 'unverified' in dispositions: return 'awaiting_review'
    return 'ready_for_next_stage'


def _candidate(binding):
    return [(c['source']['sha256'],c['source_frames']) for c in binding['clips']]


def _assessment_header(value,path,epoch,run):
    _schema(value, 'schema_version run_id assessment_id epoch clip_id job attempt binding manifest report closure concerns created_at', run)
    aid = uid(value['assessment_id'])
    if path != run/'production/scene-continuity/jobs'/aid/'assessment.json': raise ProductionRefused('assessment path differs')
    if value['epoch'] != epoch['artifact']: raise ProductionRefused('assessment epoch differs')
    return aid


def _assessment(path, epoch, context, records, reader, *, historical=False):
    run = context['store'].run_dir; value = reader.read(path)
    aid=_assessment_header(value,path,epoch,run)
    successes=[]
    attempts=sorted((path.parent/'attempts').iterdir())
    observe_inventory(path.parent/'attempts','children',attempts)
    for attempt_folder in attempts:
        uid(attempt_folder.name)
        attempt_intent=reader.read(attempt_folder/'intent.json')
        _schema(attempt_intent,'schema_version run_id assessment_id attempt_id audit_run_dir job created_at',run)
        terminal=reader.read(attempt_folder/'terminal.json')
        _schema(terminal,'schema_version run_id assessment_id attempt_id status report outputs failure finished_at',run)
        if (attempt_intent['assessment_id']!=aid or terminal['assessment_id']!=aid
                or attempt_intent['attempt_id']!=attempt_folder.name or terminal['attempt_id']!=attempt_folder.name
                or attempt_intent['job']!=value['job']):
            raise ProductionRefused('assessment attempt history producer differs')
        if not instant(attempt_intent['created_at'])<=instant(terminal['finished_at'])<=datetime.now(timezone.utc):
            raise ProductionRefused('attempt history timestamps invalid')
        if terminal['status']=='completed':successes.append(artifact(attempt_folder/'terminal.json'))
        elif terminal['status']=='interrupted':
            if terminal['report'] is not None:raise ProductionRefused('interrupted attempt claims a report')
            object_fields(terminal['failure'],'kind message evidence'.split(),'interrupted attempt failure')
            nonempty(terminal['failure']['kind']);nonempty(terminal['failure']['message'])
            if terminal['failure']['evidence']!=terminal['outputs']:raise ProductionRefused('interrupted outputs differ from retained failure')
            for ref in terminal['outputs']:verify(ref,empty=ref['bytes']==0)
        else:raise ProductionRefused('completed assessment has a failed or unknown attempt')
    if len(successes)!=1 or successes[0]!=value['attempt']:
        raise ProductionRefused('assessment requires exactly one original successful attempt')
    job = reader.read(value['job'])
    _schema(job, 'schema_version run_id assessment_id epoch clip_id binding manifest created_at', run)
    for key in ('assessment_id','epoch','clip_id','binding','manifest'):
        if job[key] != value[key]: raise ProductionRefused('assessment job binding differs')
    if value['job']['path'] != str(path.parent/'intent.json'): raise ProductionRefused('job path differs')
    terminal = reader.read(value['attempt'])
    _schema(terminal, 'schema_version run_id assessment_id attempt_id status report outputs failure finished_at', run)
    attempt_id = uid(terminal['attempt_id'])
    attempt_path = path.parent/'attempts'/attempt_id
    intent = reader.read(attempt_path/'intent.json')
    _schema(intent, 'schema_version run_id assessment_id attempt_id audit_run_dir job created_at', run)
    if (intent['job'] != value['job'] or intent['assessment_id'] != aid or intent['attempt_id'] != attempt_id
            or value['attempt']['path'] != str(attempt_path/'terminal.json') or terminal['assessment_id'] != aid
            or terminal['status'] != 'completed' or terminal['failure'] is not None or terminal['report'] != value['report']):
        raise ProductionRefused('assessment producer attempt differs')
    report_value=reader.read(value['report'])
    times=[instant(epoch['commit']['created_at']),instant(job['created_at']),instant(intent['created_at']),
           instant(report_value['created_at']),instant(terminal['finished_at']),instant(value['created_at']),datetime.now(timezone.utc)]
    if times!=sorted(times):raise ProductionRefused('assessment/job/attempt/report timestamps out of order or future')
    if value['binding'] != _binding(context,records,value['clip_id']): raise ProductionRefused('assessment production binding drift')
    manifest = reader.read(value['manifest'])
    validate_manifest_binding(manifest,value['binding'],config=context['frozen'].config,_reader=reader,
        timeout=max(.001,reader.deadline-__import__('time').monotonic()))
    from ..media.continuity_report import validate_continuity_report
    verified = validate_continuity_report(value['report'], manifest=value['manifest'], config=context['frozen'].config,_budget=reader,
        expected_engine=epoch['intent']['engine'],
        expected_audit_run_dir=intent['audit_run_dir'], historical_engine=epoch['archive'] if historical else None,
        timeout=max(.001,reader.deadline-__import__('time').monotonic()))
    if derive_concerns(verified['report']) != value['concerns']: raise ProductionRefused('assessment concerns differ from report')
    report_closure=verified['closure']
    archived=epoch['archive']['archives'] if historical else {}
    if historical:
        originals={x['path']:{k:x[k] for k in ('path','bytes','sha256')} for x in epoch['archive']['files']}
        reverse={ref['path']:originals[original] for original,ref in archived.items()}
        report_closure=[reverse.get(ref['path'],ref) for ref in report_closure]
    mandatory = report_closure+[value['manifest']]
    for row in value['binding']['clips']:
        mandatory += [row[k] for k in ('clip_record','request','generated','source','mapping','last_frame')]
        mandatory.append(reader.read(row['last_frame'])['image'])
    closure = sorted({r['path']:r for r in mandatory}.values(),key=lambda r:r['path'])
    if value['closure'] != closure: raise ProductionRefused('assessment evidence closure differs')
    for ref in closure:
        target=archived.get(ref['path'],ref)
        if target['bytes']!=ref['bytes'] or target['sha256']!=ref['sha256']:raise ProductionRefused('archive source identity differs')
        verify(target, runtime=False, empty=target['bytes']==0)
    if len(terminal['outputs']) != len({r['path'] for r in terminal['outputs']}): raise ProductionRefused('duplicate attempt outputs')
    if value['report'] not in terminal['outputs']: raise ProductionRefused('report not owned by attempt outputs')
    for ref in terminal['outputs']:
        if not Path(ref['path']).is_relative_to(Path(intent['audit_run_dir'])): raise ProductionRefused('attempt borrows external output')
        verify(ref, empty=ref['bytes']==0)
    actual_outputs=[artifact(p) for p in sorted((Path(intent['audit_run_dir'])/'logs/continuity').rglob('*')) if p.is_file() and p.stat().st_size>0]
    observe_inventory(Path(intent['audit_run_dir'])/'logs/continuity','nonempty_files',[r['path'] for r in actual_outputs])
    if terminal['outputs']!=actual_outputs:raise ProductionRefused('attempt terminal lacks complete original output inventory')
    instant(value['created_at'])
    return value


def _review_expected(context, records, assessment, path, reader):
    cid = assessment['clip_id']; record = records[cid]
    def historical_loader(ref):
        verify(ref);value=reader.read(ref)
        chain,_=_epochs(context['frozen'],[r['budget']['clip_id'] for r in context['rows']],reader,current=False)
        epoch=next((e for e in chain if e['artifact']==value.get('epoch')),None)
        if epoch is None:raise ProductionRefused('prefix historical assessment has no verified epoch')
        return _assessment(Path(ref['path']),epoch,context,records,reader,historical=True)
    expected_video=dict(template=record['template'],created_at=record['clip']['created_at'])
    if 'scene_revision' in getattr(context['frozen'],'options',{}):
        from .scene_revision_records import require_scene_revision
        proof=require_scene_revision(context['frozen'])
        if 'clip:'+cid in proof['imports']:
            from .production_inputs import load_frozen_inputs
            from ._scene_revision_origins import source_clip_record
            origin=source_clip_record(load_frozen_inputs(proof['source_run']),cid)
            expected_video=dict(template=origin['template'],created_at=origin['clip']['created_at'])
    return dict(run=context['store'].run_dir, assessment=assessment, assessment_artifact=artifact(path),
        binding=assessment['binding'], reader=reader,historical_assessment_loader=historical_loader,
        video_expected=expected_video)


def _reviews(context,records,assessment,path,reader):
    root = context['store'].run_dir/'production/scene-continuity/reviews'
    expected = _review_expected(context,records,assessment,path,reader); valid = {}; states = []
    raws=sorted(root.glob('*.json'))
    observe_inventory(root,'json_direct',raws)
    for raw in raws:
        value = reader.read(raw)
        if value.get('assessment_id') != assessment['assessment_id']: continue
        if raw.stem != artifact(raw)['sha256']: raise ProductionRefused('review raw filename differs from author bytes')
        validate_continuity_review(value, expected, now=datetime.now(timezone.utc))
        state = _review_state(value,reader); states.append(state); valid[str(raw)] = (value,state)
    receipt_path = root/assessment['assessment_id']/'receipt.json'
    receipt = None
    if receipt_path.exists():
        receipt = reader.read(receipt_path)
        _schema(receipt, 'schema_version run_id assessment_id assessment review video_receipt state created_at',context['store'].run_dir)
        if receipt['assessment'] != artifact(path) or receipt['assessment_id'] != assessment['assessment_id']:
            raise ProductionRefused('review receipt assessment differs')
        verify(receipt['review']); item = valid.get(receipt['review']['path'])
        if item is None or item[1] != receipt['state'] or item[1] not in ('blocked','ready_for_next_stage'):
            raise ProductionRefused('review receipt lacks terminal author evidence')
        if instant(receipt['created_at']) < instant(item[0]['reviewed_at']): raise ProductionRefused('receipt precedes review')
        clip = records[assessment['clip_id']]
        name = 'observation-rejected.json' if reader.read(item[0]['video_observation'])['verdict']=='failed' else 'observation-accepted.json'
        actual = _metadata_folder(context.get('frozen'),assessment['clip_id'],clip) if context.get('frozen') is not None else Path(clip['clip']['source']['path']).parent
        if receipt['video_receipt'] != artifact(actual/name): raise ProductionRefused('review original video receipt differs')
        original_video=reader.read(receipt['video_receipt'])
        original_ref=original_video['observation'];review_ref=item[0]['video_observation']
        verify(original_ref);verify(review_ref)
        if any(original_ref[k]!=review_ref[k] for k in ('bytes','sha256')):
            raise ProductionRefused('review video author bytes differ from original receipt')
    else:observe_absence(receipt_path)
    state = 'blocked' if 'blocked' in states else (receipt['state'] if receipt is not None else 'awaiting_review')
    return state, artifact(receipt_path) if receipt else None


def _historical_failures(frozen, units, timeline, binding, *, seen=None, reader=None, context=None, source=None, chain=None):
    """Check same-media historical defects, including explicitly inherited origins."""
    seen = set() if seen is None else seen
    run = run_for(frozen)
    if str(run) in seen: raise ProductionRefused('continuity origin cycle')
    seen.add(str(run))
    from .scene_clip_records import scene_context, collect_progress
    if context is None:context=scene_context(frozen,units,timeline)
    if source is None:_,source=collect_progress(context)
    reader = reader or Reader(); ids = [r['budget']['clip_id'] for r in context['rows']]
    if chain is None:chain,_=_epochs(frozen,ids,reader,current=False)
    for epoch in chain:
        jobs_root=run/'production/scene-continuity/jobs'
        assessments=sorted(jobs_root.glob('*/assessment.json'))
        observe_inventory(jobs_root,'assessment_paths',assessments)
        for path in assessments:
            value = reader.read(path)
            previous=_candidate(value['binding']);current=_candidate(binding)
            if value.get('epoch') != epoch['artifact'] or previous!=current[:len(previous)]: continue
            aid=_assessment_header(value,path,epoch,run)
            root=run/'production/scene-continuity/reviews';authored=False
            raws=sorted(root.glob('*.json'))
            observe_inventory(root,'json_direct',raws)
            for raw in raws:
                if reader.read(raw).get('assessment_id')==aid:authored=True
            # No author consumed this historical report. Its state can only
            # be awaiting_review; it cannot contribute a confirmed defect.
            # Any raw (including unverified/passed) or receipt retains the
            # complete historical report and author validation below.
            if not authored and not (root/aid/'receipt.json').exists():
                observe_absence(root/aid/'receipt.json')
                continue
            value = _assessment(path,epoch,context,source,reader,historical=True)
            if _reviews(context,source,value,path,reader)[0] == 'blocked': return True
    if 'scene_revision' in frozen.options:
        from .scene_revision_records import require_scene_revision
        proof = require_scene_revision(frozen)
        if 'clip:'+binding['clip_id'] in proof['imports']:
            from .production_inputs import load_frozen_inputs
            from ._scene_revision_origins import common
            from ..planning.production_timeline import ProductionTimeline
            source = load_frozen_inputs(proof['source_run']); original = common(source)
            return _historical_failures(source,original['units'],ProductionTimeline.from_dict(original['timeline']),binding,seen=seen,reader=reader)
    return False


def load_scene_continuity_progress(frozen, units, timeline):
    policy = load_continuity_policy(frozen); run = run_for(frozen)
    result = dict(schema_version=1, run_id=run.name, policy=policy, current_epoch=None, clips=[], ready=None)
    if policy is None: return result
    from .scene_clip_records import scene_context, collect_progress
    context = scene_context(frozen, units, timeline); _, records = collect_progress(context)
    ids = [r['budget']['clip_id'] for r in context['rows']]; reader = Reader()
    chain,pending = _epochs(frozen,ids,reader)
    head = chain[-1] if chain else None
    if head: result['current_epoch'] = head['artifact']
    jobs = {}
    jobs_root=run/'production/scene-continuity/jobs'
    intents=sorted(jobs_root.glob('*/intent.json'))
    observe_inventory(jobs_root,'job_intents',intents)
    for path in intents:
        value = reader.read(path)
        _schema(value, 'schema_version run_id assessment_id epoch clip_id binding manifest created_at',run)
        uid(value['assessment_id'])
        if head and value['epoch'] == head['artifact']:
            cid = value['clip_id']
            if cid not in ids or cid in jobs or path.parent.name != value['assessment_id']:
                raise ProductionRefused('multiple jobs for clip or unknown clip')
            jobs[cid] = path.parent
    for cid in ids:
        row = dict(clip_id=cid, assessment=None, review=None, state='awaiting_analysis', reasons=[])
        folder = jobs.get(cid)
        if pending: row.update(state='blocked',reasons=['epoch incomplete or engine changed; explicit reassess required'])
        elif folder and (folder/'assessment.json').exists():
            value = _assessment(folder/'assessment.json',head,context,records,reader)
            row['assessment'] = artifact(folder/'assessment.json')
            row['state'],row['review'] = _reviews(context,records,value,folder/'assessment.json',reader)
            if _historical_failures(frozen,units,timeline,value['binding'],reader=reader,context=context,source=records,chain=chain[:-1]):
                row.update(state='blocked',reasons=['retained confirmed defect for same candidate prefix'])
        elif folder:
            if any(folder.glob('attempts/*/terminal.json')):
                row.update(state='blocked',reasons=['analysis attempt incomplete or failed; explicit recovery/reassess required'])
        result['clips'].append(row)
    result['ready'] = bool(ids) and all(r['state']=='ready_for_next_stage' for r in result['clips'])
    return result


def require_scene_continuity_acceptance(frozen, units, timeline, *, clip_id=None):
    # Legacy low-level writers may carry only their original minimal context.
    if load_continuity_policy(frozen) is None:return None
    progress = load_scene_continuity_progress(frozen,units,timeline)
    if progress['policy'] is None: return None
    if clip_id is None:rows=progress['clips']
    else:
        from .scene_clip_records import scene_context
        context=scene_context(frozen,units,timeline)
        selected=next((r['budget'] for r in context['rows'] if r['budget']['clip_id']==clip_id),None)
        if selected is None:raise ProductionRefused('continuity clip outside committed plan')
        prefix=[]
        for row in context['rows']:
            if row['budget']['scene_id']==selected['scene_id']:prefix.append(row['budget']['clip_id'])
            if row['budget']['clip_id']==clip_id:break
        rows=[r for r in progress['clips'] if r['clip_id'] in prefix]
    if not rows: raise ProductionRefused('continuity clip outside committed plan')
    if any(r['state'] != 'ready_for_next_stage' for r in rows):
        if any(r['state']=='blocked' for r in rows):
            raise ProductionRefused('current continuity evidence is blocked: '+str([(r['clip_id'],r['reasons']) for r in rows]))
        raise SceneContinuityPending('current continuity analysis/playback responses required: '+str([(r['clip_id'],r['state'],r['reasons']) for r in rows]))
    return progress


def _capture_promotion_absences(guard):
    """Retain the absent aliases of promotion receipts actually read above.

    The media validator freezes every receipt it uses. Do not follow declared
    historical manifests or search unrelated receipts. A stage without an
    observed original identity must still be absent, including during capture.
    """
    from dataclasses import replace
    from ._continuity_byte_guard import capture_reads, CaptureLimit
    fields=set('schema_version run_id clip_id operation source staging target recipe evidence created_at'.split())
    captured={row.path for row in guard.files}
    reader=Reader()
    with capture_reads() as extra:
        for row in guard.files:
            path=Path(row.path)
            if (path.parent.name!='media-ready' or path.name not in
                    ('generated.json','source.json','last_frame.json')
                    or path.parent.parent.parent.name!='scene-clips'
                    or path.parent.parent.parent.parent.name!='production'):
                continue
            value=reader.read(dict(path=row.path,bytes=row.bytes,sha256=row.sha256))
            if (not isinstance(value,dict) or set(value)!=fields or type(value['schema_version']) is not int
                    or value['schema_version']!=2 or value['operation']!=path.stem
                    or value['clip_id']!=path.parent.parent.name
                    or value['run_id']!=path.parents[4].name):
                raise ProductionRefused('captured media promotion receipt differs')
            stage=local(value['staging']['path'],exists=False)
            if not stage.is_relative_to(path.parent.parent/'staging'):
                raise ProductionRefused('captured media staging escapes clip')
            if str(stage) not in captured:observe_absence(stage)
    additions=extra.finish()
    absences=tuple(sorted(set(guard.absences)|set(additions.absences)))
    if len(absences)>32768:raise CaptureLimit('byte capture combined absence limit exceeded')
    if set(absences)&captured:raise ProductionRefused('conflicting captured promotion state')
    return replace(guard,absences=absences)


def capture_scene_continuity_guard(frozen, units, timeline):
    """Validate semantics once, then retain only immutable observed dependencies.

    None keeps the caller's original full validator for legacy or unbounded
    contexts. Pending and failed admissions always propagate their refusal.
    """
    from . import _continuity_byte_guard as proof
    import json

    def state():
        value=dict(frozen=thaw(frozen),units=thaw(units),
                   timeline=None if timeline is None else timeline.as_dict())
        return canonical_digest(json.loads(json.dumps(value,allow_nan=False)))

    try: baseline=state()
    except (TypeError,ValueError,AttributeError):
        require_scene_continuity_acceptance(frozen,units,timeline)
        return None
    try:
        with proof.capture_reads() as capture:
            policy=load_continuity_policy(frozen)
            root=Path(__file__).parent.parent/'media'
            if policy is not None:
                observe_inventory(root,'continuity_sources',sorted(root.glob('*continuity*.py')))
            admitted=require_scene_continuity_acceptance(frozen,units,timeline)
            if policy is not None:
                observe_inventory(root,'continuity_sources',sorted(root.glob('*continuity*.py')))
            if state()!=baseline:raise ProductionRefused('continuity admission arguments changed')
        if admitted is None:return None
        guard=_capture_promotion_absences(capture.finish())
        guard.verify()
        from ._protected_continuity_inputs import prepare_continuity_inputs
        run=run_for(frozen)
        prepare_continuity_inputs(guard.files,immutable_roots=(
            run/'production/scene-continuity',run/'production/scene-clips',
            run/'production/scene-revision',run/'production/scene-rendering',
            run/'production/options.json',Path(frozen.options['script_path'])))
        guard.verify()
    except proof.CaptureLimit:
        # A fresh complete admission, outside the failed capture, is required.
        require_scene_continuity_acceptance(frozen,units,timeline)
        return None

    def verify_admitted_bytes():
        if state()!=baseline:raise ProductionRefused('continuity admission arguments changed')
        guard.verify()
        if state()!=baseline:raise ProductionRefused('continuity admission arguments changed')
    if type(guard) is proof.ByteGuard and guard.files:
        from ._scene_media_check_coverage import _tag_ready_continuity_guard
        _tag_ready_continuity_guard(verify_admitted_bytes,guard)
    return verify_admitted_bytes
