from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import subprocess
import uuid
import pytest

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def timeline_run(runtime_run):
    """Real, completed speech evidence and WAVs; no service is involved."""
    import json
    import wave
    from video_ai.planning.segments import SegmentedScript
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw
    from video_ai.runtime.speech_checks import _artifact
    run,config,paths=runtime_run
    source=run/'original.txt'; source.write_bytes(b'\xef\xbb\xbf'+ '树梢，水面倒影。\r\n末尾。\n'.encode())
    (run/'script.txt').write_bytes(source.read_bytes())
    parsed=SegmentedScript.read(source)
    identities={k:hash_file(p) for k,p in {'script':source,'config':config.config_file,'voice':config.voice.config_file}.items()}
    store=create_manifest(run,config,inputs=identities,models={},workflows={})
    store.record_stage('speech','running')
    spans=[]
    for span in parsed.spans:
        item=thaw(span)
        item['status']='skip' if span.kind=='skip' else 'completed'
        if span.kind=='speech':
            folder=run/'audio'/span.unit_id; folder.mkdir(parents=True)
            pcm=folder/'pcm-48000.wav'
            with wave.open(str(pcm),'wb') as f:
                f.setparams((1,2,48000,0,'NONE','')); f.writeframes(b'\0\0'*4800)
            item.update(pcm=_artifact(pcm),samples=4800,sample_rate=48000,channels=1,sample_width=2)
            store.record_unit('speech',span.unit_id,'running')
            store.record_unit('speech',span.unit_id,'completed',artifacts=[item['pcm']])
        spans.append(item)
    data=dict(schema_version=1,status='completed',passed=True,coverage_verified=True,run_dir=str(run),
        source=thaw(identities['script']),script_copy=thaw(hash_file(run/'script.txt')),decoded_text=parsed.text,
        has_bom=parsed.has_bom,spans=spans,total_speech_samples=14400,inputs=thaw(identities))
    (run/'segments.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    store.record_stage('speech','completed',artifacts=[_artifact(run/'segments.json')])
    return run,config,store,data


@pytest.fixture
def runtime_run():
    from video_ai.config import load_config
    from video_ai.runtime.paths import RuntimePaths, create_run
    config = load_config(SOURCE / 'config/production.example.json')
    paths = RuntimePaths.from_config(config)
    return create_run(paths), config, paths


@pytest.fixture
def run_store(runtime_run):
    from video_ai.runtime.manifest import create_manifest
    run, config, paths = runtime_run
    return create_manifest(run, config, inputs={}, models={}, workflows={})


@pytest.fixture
def resource_config(tmp_path):
    from video_ai.config import load_config
    config = load_config(SOURCE / 'config/production.example.json')
    ident = uuid.uuid4().hex
    tools_root = Path('D:/VideoSi/tools/tests') / ident
    model_root = Path('D:/VideoSi/models/tests') / ident
    tools_root.mkdir(parents=True)
    model_root.mkdir(parents=True)
    tools = {}
    for name, original in config.tools.items():
        path = tools_root / name / original.name
        if name.endswith('_root'):
            path.mkdir(parents=True)
            (path / 'entry.py').write_text('# test resource', encoding='utf-8')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'test resource; never executed')
        tools[name] = path
    models = {}
    for name, original in config.models.items():
        path = model_root / original.name
        path.write_bytes(b'test-only model file; never loaded')
        models[name] = path
    voice_paths = {}
    for name in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root'):
        path = model_root / name
        if name.endswith('_root'):
            path.mkdir()
            (path / 'config.json').write_text('{}', encoding='utf-8')
        else:
            path.write_bytes(b'test-only voice weights')
        voice_paths[name] = path
    reference = tmp_path / 'reference.wav'
    reference.write_bytes(b'test-only reference')
    font = tmp_path / 'font.ttc'
    font.write_bytes(b'test-only font')
    voice = replace(config.voice, **voice_paths, reference_audio=reference,
                    reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
    return replace(config, tools=tools, models=models, voice=voice,
                   media=replace(config.media, font_file=font))


@pytest.fixture
def capability_runner():
    def run(args, *, cwd, env, timeout, stdout, stderr, **kwargs):
        assert Path(args[0]).is_absolute()
        assert Path(cwd).is_absolute() and Path(cwd).is_relative_to(Path('D:/VideoSi/cache/video-ai'))
        assert timeout == 30
        assert Path(env['TEMP']).is_relative_to(Path('D:/VideoSi/cache/video-ai'))
        flag = args[-1]
        if flag == '-encoders':
            data = ' V....D h264_nvenc NVIDIA\n V....D libx264 H264\n A..... aac AAC\n'
        elif flag == '-filters':
            data = ' .. subtitles V->V render\n .. scale V->V resize\n .. loudnorm A->A norm\n .. amix N->A mix\n .. xfade VV->V transition\n'
        else:
            data = 'test fixture version; no inference\n'
        stdout.write(data)
        stderr.write('fixture stderr\n')
        return subprocess.CompletedProcess(args, 0)
    return run


@pytest.fixture
def storyboard_run(timeline_run):
    from storyboard_helpers import make_storyboard_run
    return make_storyboard_run(timeline_run)
