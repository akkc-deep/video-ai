"""User-facing production: one video number, resume without knowing a run UUID."""
from dataclasses import dataclass
from pathlib import Path
import shutil

from .runtime.storage import (VideoStorage, allocation_scope, managed_location,
                              managed_output)
from .runtime.storage_files import read_record, safe_path, write_record


@dataclass
class ManagedResult:
    result: object
    video_number: str
    video_title: str
    production_directory: Path
    output_directory: Path

    def __getattr__(self, name):
        return getattr(self.result,name)

    def to_dict(self):
        return dict(self.result.to_dict(),video_number=self.video_number,video_title=self.video_title,
            production_directory=str(self.production_directory),output_directory=str(self.output_directory))


def _copy_exact(source, target):
    """Publish a small companion file once; an existing file must match."""
    source, target = Path(source), Path(target)
    if source == target:
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if source.stat().st_size != target.stat().st_size:
            raise ValueError(f'existing delivery companion differs: {target}')
        # Recover an interrupted export by comparing once, without decoding or a size cap.
        with source.open('rb') as original,target.open('rb') as existing:
            while chunk := original.read(1024*1024):
                if chunk != existing.read(len(chunk)):
                    raise ValueError(f'existing delivery companion differs: {target}')
        return
    pending = target.with_name('.'+target.name+'.pending')
    if pending.exists():
        pending.unlink()
    with source.open('rb') as src,pending.open('xb') as dst:
        shutil.copyfileobj(src,dst,1024*1024)
        dst.flush()
        import os
        os.fsync(dst.fileno())
    pending.rename(target)


def export_delivery(storage, video, result):
    run = Path(result.run_dir)
    movie = getattr(result,'movie',None)
    subtitle = getattr(result,'subtitle',None)
    receipt = getattr(result,'receipt_path',None) or getattr(result,'delivery_receipt',None)
    if movie is None:
        options = read_record(run/'production/options.json')
        targets = options['output_paths']
        movie,subtitle = Path(targets['movie']),Path(targets['subtitle'])
        receipt = receipt or Path(targets['receipt'])
    folder = safe_path(managed_output(run).parent,storage.output_dir(video))
    folder.mkdir(parents=True,exist_ok=True)
    for source,name in ((movie,'video.mp4'),(subtitle,'video.srt'),
                        (run/'production/script.txt','script.txt'),(receipt,'video.delivery.json')):
        source = Path(source)
        if not source.is_file():
            raise ValueError(f'published delivery source missing: {source}')
        _copy_exact(source,folder/name)
    # Publication markers generated beside the movie are copied unchanged when present.
    marker = Path(movie).with_suffix('.publication.json')
    if marker.is_file():
        _copy_exact(marker,folder/'video.publication.json')
    names = ('video.mp4','video.srt','script.txt','video.delivery.json')
    manifest = dict(schema_version=1,video=video['number'],title=video['title'],
        version=folder.name,files={n:dict(bytes=(folder/n).stat().st_size) for n in names})
    existing = folder/'delivery.json'
    if existing.exists() and read_record(existing) != manifest:
        raise ValueError('independent delivery manifest changed')
    write_record(existing,manifest)
    storage.record_delivery(video,run,folder)
    return folder


def make_managed_video(config=None, *, video=None, title=None, storage=None, **options):
    """Managed CLI wrapper; the existing Python engine remains backward compatible."""
    from .production import make_video
    from .runtime.production_inputs import read_script
    storage = storage or VideoStorage()
    explicit_run = options.get('run_dir')
    if explicit_run is not None:
        if video is not None or title is not None:
            raise ValueError('--run-dir cannot be combined with --video or --title')
        location = managed_location(explicit_run)
        if location is None:
            return make_video(config,**options)  # Historical frozen run, unchanged.
        if location[0] != storage.runtime_root:
            raise ValueError('run belongs to another storage runtime')
        selected = storage.find(location[1].name)
    elif video is not None:
        if title is not None or options.get('script') is not None or options.get('text') is not None:
            raise ValueError('--video resumes existing input; use a new video for a different script')
        selected = storage.find(video)
        options['run_dir'] = storage.current_run(selected)
    else:
        if any(options.get(key) is not None for key in ('revision','image_selection','clip_observation',
                'continuity_review','final_observation','retry_email')) or options.get('publish'):
            return make_video(config,**options)
        try:
            raw, parsed = read_script(script=options.get('script'),text=options.get('text'))
        except (ValueError,OSError):
            # Preserve the production API's versioned error result without allocating a video.
            return make_video(config,**options)
        title = title or (Path(options['script']).stem if options.get('script') else parsed.text.strip().splitlines()[0][:24])
        selected = storage.create(title)
        source = safe_path(storage.video_dir(selected)/'input/script.txt',storage.production_root)
        source.parent.mkdir(parents=True,exist_ok=True)
        source.write_bytes(raw)
        options['script'],options['text'] = source,None
    with storage.activity(selected), allocation_scope(storage,selected):
        previous = options.get('run_dir')
        result = make_video(config,**options)
        if getattr(result,'run_dir',None) is not None and managed_location(result.run_dir) is None:
            return result  # An injected/historical engine may retain its explicit legacy allocation.
        if options.get('revision') is not None and previous is not None:
            storage.set_current(selected,result.run_dir if getattr(result,'status',None)=='revision_ready' else previous)
        if getattr(result,'status',None) == 'delivered':
            export_delivery(storage,selected,result)
        return ManagedResult(result,selected['number'],selected['title'],
            storage.video_dir(selected),storage.output_dir(selected))
