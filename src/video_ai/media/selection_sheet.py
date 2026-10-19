"""Immutable JPEG mail previews and labelled ffmpeg contact sheets.

The selection coordinator validates the plan and candidate provenance first.
This layer independently decodes the actual media and binds every derivative
to an unchanged original. It never calls an image generation service.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from .images import _command
from ..config import read_json
from ..runtime.manifest import hash_file
from ..runtime.production_state import ProductionRefused, run_path, sync_file


PREVIEW_SIZES = ((960, 540), (640, 360), (320, 180), (160, 90))
_IMAGE_FIELDS = {'kind', 'scene_id', 'candidate_id', 'source_sha256', 'path', 'bytes', 'sha256', 'width', 'height'}
_SHEET_FIELDS = {'path', 'bytes', 'sha256', 'width', 'height', 'sources'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', value):
        raise ProductionRefused(f'safe ASCII {label} required')
    return value


def _source_key(row):
    return row['scene_id'], row['candidate_id'], row['sha256']


def _identity(path):
    identity = hash_file(path)
    return dict(path=str(path), bytes=identity.bytes, sha256=identity.sha256)


def _escaped(path):
    # The filter parser has two escaping layers. Quotes/backslashes in paths
    # are refused rather than placing user-controlled filter syntax in a graph.
    text = str(path).replace('\\', '/')
    if any(c in text for c in "'\n\r,;[]"):
        raise ProductionRefused('unsupported characters in ffmpeg filter path')
    return text.replace(':', r'\:')


class _Media:
    def __init__(self, config, paths, logger):
        self.run = Path(logger.run_dir)
        self.kwargs = dict(config=config, paths=paths, logger=logger, unit_id='selection_media', stage='start_images')
        self.config = config
        self.lock = self.run/'.make-video.lock'
        self.owner = read_json(self.lock) if self.lock.exists() else None

    def owned(self):
        if self.owner is not None and (not self.lock.is_file() or read_json(self.lock) != self.owner):
            raise ProductionRefused('selection media lost held run lock ownership')

    def local(self, path):
        return run_path(self.run, path)

    def command(self, args):
        self.owned()
        result = _command(args, timeout=300, **self.kwargs)
        self.owned()
        return result

    def inspect(self, path):
        identity = _identity(path)
        probe = self.command((self.config.tools['ffprobe'], '-v', 'error', '-count_frames',
                              '-show_streams', '-of', 'json', path))
        streams = read_json(probe.stdout_path).get('streams')
        if (not isinstance(streams, list) or len(streams) != 1 or streams[0].get('codec_type') != 'video'
                or streams[0].get('nb_read_frames') != '1'):
            raise ProductionRefused('single fully decoded still image required')
        stream = streams[0]
        if any(type(stream.get(k)) is not int or stream[k] <= 0 for k in ('width', 'height')):
            raise ProductionRefused('positive integer image dimensions required')
        if stream.get('codec_name') not in {'png', 'mjpeg', 'webp', 'bmp', 'tiff', 'gif', 'jpeg2000', 'targa', 'ppm', 'pgm'}:
            raise ProductionRefused('unsupported still image format')
        self.command((self.config.tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror', '-i', path, '-f', 'null', '-'))
        if _identity(path) != identity:
            raise ProductionRefused('image identity changed during decode')
        return dict(identity, width=stream['width'], height=stream['height'])

    def commit(self, target, raw):
        target = self.local(target)
        self.owned()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != raw:
                raise ProductionRefused('immutable media conflict')
            sync_file(target)
            return
        temporary = self.local(target.with_name(f'.{target.name}.{uuid4().hex}.tmp'))
        try:
            with temporary.open('xb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            self.owned()
            os.rename(temporary, target)
        finally:
            if temporary.exists(): temporary.unlink()

    def render(self, target, args):
        target = self.local(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.local(target.with_name(f'.{target.stem}.{uuid4().hex}.jpg'))
        try:
            self.command((self.config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-xerror',
                          *args, '-frames:v', '1', '-c:v', 'mjpeg', '-q:v', '3', '-pix_fmt', 'yuvj420p', temporary))
            self.inspect(temporary)
            self.commit(target, temporary.read_bytes())
        finally:
            if temporary.exists(): temporary.unlink()
        return self.inspect(target)


def _sources(batch, store):
    current = []
    for scene in batch['scenes']:
        sid = _safe(scene['scene_id'], 'scene ID')
        for candidate in scene['candidates']:
            _safe(candidate['candidate_id'], 'candidate ID')
            current.append(dict(candidate, scene_id=sid))
    if not current or len({_source_key(row)[:2] for row in current}) != len(current):
        raise ProductionRefused('nonempty unique scene/candidate images required')
    baseline = []
    bindings = batch['baseline_bindings']
    for binding in bindings:
        sid = _safe(binding['scene_id'], 'baseline scene ID')
        cid = _safe(binding['candidate_id'], 'baseline candidate ID')
        matches = []
        for accepted_path in sorted((store.run/'production/image-selection').glob('image_batch_*/accepted.json')):
            accepted_path = store.local(accepted_path)
            accepted = read_json(accepted_path)
            if accepted.get('run_id') != batch['run_id'] or accepted.get('schema_version') != 2:
                raise ProductionRefused('accepted baseline run identity differs')
            prior = read_json(store.local(accepted_path.parent/'batch.json'))
            if (prior.get('batch_id') != accepted.get('batch_id') or prior.get('run_id') != batch['run_id']
                    or type(prior.get('batch_index')) is not int or prior['batch_index'] >= batch['batch_index']):
                continue
            if (accepted.get('scene_manifest_sha256') != _digest(prior)
                    or any(accepted.get(k) != batch[k] for k in ('scene_plan_sha256', 'visual_bible_sha256'))):
                raise ProductionRefused('accepted baseline plan identity differs')
            for selection in accepted['selections']:
                if (selection.get('scene_id'), selection.get('candidate_id'), selection.get('sha256')) != (sid, cid, binding['sha256']):
                    continue
                rows = [row for scene in prior['scenes'] if scene['scene_id'] == sid
                        for row in scene['candidates'] if row['candidate_id'] == cid]
                if len(rows) != 1 or any(selection.get(k) != rows[0].get(k)
                                         for k in ('path', 'bytes', 'sha256', 'req_key', 'request_id', 'task_id')):
                    raise ProductionRefused('accepted baseline candidate identity differs')
                matches.append(dict(rows[0], scene_id=sid))
        if len(matches) != 1:
            raise ProductionRefused('baseline has no unique accepted original identity')
        baseline.append(matches[0])
    ordered, seen = [], set()
    for group in (baseline, current):
        for row in sorted(group, key=lambda r: (r['scene_id'], r['candidate_id'])):
            key = _source_key(row)
            if key not in seen:
                ordered.append(row)
                seen.add(key)
    return ordered


def _verify_source(store, row):
    path = store.local(row['path'])
    if any(type(row[k]) is not int or row[k] <= 0 for k in ('bytes', 'width', 'height')):
        raise ProductionRefused('positive integer original metadata required')
    if not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
        raise ProductionRefused('original SHA256 required')
    expected = dict(path=str(path), **{key: row[key] for key in ('bytes', 'sha256', 'width', 'height')})
    if _identity(path) != {key: expected[key] for key in ('path', 'bytes', 'sha256')}:
        raise ProductionRefused('original image identity changed')
    if store.inspect(path) != expected:
        raise ProductionRefused('original image dimensions changed')
    return expected


def prepare_email_media(batch, *, config, paths, logger) -> dict:
    """Persist and return exact schema-2 source/preview/contact-sheet identities.

    The coordinator owns the run lock. A standalone call is also supported;
    when a lock exists, every command and durable commit rechecks its owner.
    """
    store = _Media(config, paths, logger)
    _safe(batch['batch_id'], 'batch ID')
    if batch['run_id'] != store.run.name:
        raise ProductionRefused('media batch run identity differs')
    folder = store.local(store.run/'production/image-selection'/batch['batch_id']/'mail')
    media_path = store.local(folder/'media.json')
    sources = _sources(batch, store)
    originals = [_verify_source(store, row) for row in sources]
    header = dict(schema_version=2, run_id=batch['run_id'], batch_id=batch['batch_id'], scene_manifest_sha256=_digest(batch))
    expected_images = []
    for source, identity in zip(sources, originals):
        base = dict(scene_id=source['scene_id'], candidate_id=source['candidate_id'], source_sha256=source['sha256'])
        expected_images.append(dict(kind='original', **base, **identity))
        for width, height in PREVIEW_SIZES:
            target = folder/'previews'/f'{source["scene_id"]}--{source["candidate_id"]}--{width}x{height}.jpg'
            expected_images.append(dict(kind='preview', **base, path=str(store.local(target)), width=width, height=height))
    pages = [sources[index:index+8] for index in range(0, len(sources), 8)]
    expected_sheets = [dict(path=str(store.local(folder/f'contact_sheet_{index:04d}.jpg')), width=960,
                           height=((len(page)+1)//2)*270,
                           sources=[dict(scene_id=r['scene_id'], candidate_id=r['candidate_id'], sha256=r['sha256']) for r in page])
                       for index, page in enumerate(pages, 1)]
    if media_path.exists():
        saved = read_json(media_path)
        if (set(saved) != set(header)|{'images', 'contact_sheets'} or any(saved[k] != v for k, v in header.items())
                or len(saved['images']) != len(expected_images) or len(saved['contact_sheets']) != len(expected_sheets)):
            raise ProductionRefused('immutable media identity conflict')
        for rows, expected_rows, fields in ((saved['images'], expected_images, _IMAGE_FIELDS),
                                           (saved['contact_sheets'], expected_sheets, _SHEET_FIELDS)):
            for row, expected in zip(rows, expected_rows):
                if set(row) != fields or any(row[k] != v for k, v in expected.items()):
                    raise ProductionRefused('immutable media identity conflict')
                path = store.local(row['path'])
                if _identity(path) != {k: row[k] for k in ('path', 'bytes', 'sha256')}:
                    raise ProductionRefused('saved media identity changed')
                if store.inspect(path) != {k: row[k] for k in ('path', 'bytes', 'sha256', 'width', 'height')}:
                    raise ProductionRefused('saved media dimensions changed')
                sync_file(path)
        store.owned()
        # The manifest and derivative can both have been edited. Re-render
        # from the verified originals below, then let immutable byte comparison
        # prove provenance. Identical published assets retain their timestamps.
    font = Path(config.media.font_file)
    if not font.is_absolute() or not font.is_file():
        raise ProductionRefused('fixed local contact sheet font required')
    images = []
    for expected in expected_images:
        if expected['kind'] == 'original':
            images.append(expected)
            continue
        source = next(r for r in sources if (r['scene_id'], r['candidate_id']) == (expected['scene_id'], expected['candidate_id']))
        width, height = expected['width'], expected['height']
        contain = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
        identity = store.render(expected['path'], ('-i', source['path'], '-vf', contain))
        images.append(dict(expected, **identity))
    sheets = []
    for index, (page, expected) in enumerate(zip(pages, expected_sheets), 1):
        args, filters = [], []
        for cell, source in enumerate(page):
            preview = next(r for r in images if r['kind'] == 'preview' and r['width'] == 960
                           and (r['scene_id'], r['candidate_id']) == (source['scene_id'], source['candidate_id']))
            args.extend(('-i', preview['path']))
            label = f'{source["scene_id"]}={source["candidate_id"]}'
            textfile = folder/'labels'/f'page_{index:04d}_cell_{cell+1:02d}.txt'
            store.commit(textfile, label.encode('ascii'))
            size = min(16, max(4, 750//len(label)))
            filters.append(f"[{cell}:v]scale=480:270,drawbox=x=0:y=ih-26:w=iw:h=26:color=black:t=fill,"
                           f"drawtext=fontfile='{_escaped(font)}':textfile='{_escaped(textfile)}':expansion=none:"
                           f"fontsize={size}:fontcolor=white:x=6:y=h-22[c{cell}]")
        if len(page) == 1:
            filters.append('[c0]pad=960:270:0:0:black[out]')
        else:
            labels = ''.join(f'[c{cell}]' for cell in range(len(page)))
            layout = '|'.join(f'{(cell%2)*480}_{(cell//2)*270}' for cell in range(len(page)))
            filters.append(f'{labels}xstack=inputs={len(page)}:layout={layout}:fill=black,pad=960:{expected["height"]}:0:0:black[out]')
        identity = store.render(expected['path'], (*args, '-filter_complex', ';'.join(filters), '-map', '[out]'))
        sheets.append(dict(expected, **identity))
    # Originals must remain unchanged for the entire derivative transaction.
    for source, identity in zip(sources, originals):
        if _identity(store.local(source['path'])) != {k: identity[k] for k in ('path', 'bytes', 'sha256')}:
            raise ProductionRefused('original image identity changed during preparation')
    media = dict(header, images=images, contact_sheets=sheets)
    store.commit(media_path, _canonical(media))
    return media
