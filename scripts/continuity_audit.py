"""Explicit offline continuity tools. Run through scripts/bootstrap.ps1."""
import argparse
import json
from pathlib import Path
import sys

from video_ai.config import load_config
from video_ai.media.colorimetry import _local_file
from video_ai.media.continuity_analysis import analyze_continuity
from video_ai.media.continuity_calibration import (validate_calibration_catalog,build_annotation_template,calibrate_continuity)
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.paths import RuntimePaths,create_run
from video_ai.runtime.manifest import thaw,hash_file


def _read(path):
    path=_local_file(path)
    if path.stat().st_size>16777216:raise ValueError('resource_limit: JSON')
    identity=thaw(hash_file(path));data=json.loads(path.read_text(encoding='utf-8'))
    if hash_file(path).sha256!=identity['sha256']:raise OSError('input changed while reading')
    return data,identity


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('validate-catalog','annotation-template','calibrate','analyze'):
        p=sub.add_parser(command);p.add_argument('--config',required=True)
        if command=='analyze':p.add_argument('--manifest',required=True)
        else:p.add_argument('--catalog',required=True)
        if command=='calibrate':p.add_argument('--labels',required=True)
    args=parser.parse_args(argv)
    try:
        config=load_config(_local_file(args.config));paths=RuntimePaths.from_config(config)
        if args.command=='analyze':
            manifest,_=_read(args.manifest);logger=RunLogger(create_run(paths))
            report,_=analyze_continuity(manifest,config=config,paths=paths,logger=logger)
            insufficient=report['profile'] is None or not report['profile']['domain_match'] or report['profile']['status']!='ready'
            status='unverified' if insufficient else 'diagnosed'
        else:
            catalog,catalog_identity=_read(args.catalog);validate_calibration_catalog(catalog)
            if args.command=='calibrate':
                _,label_identity=_read(args.labels);logger=RunLogger(create_run(paths))
                profile,_=calibrate_continuity(catalog_identity,label_identity,config=config,paths=paths,logger=logger)
                status=profile['status'];insufficient=status!='ready'
            else:
                logger=RunLogger(create_run(paths));insufficient=False
                if args.command=='annotation-template':
                    logger.save_json('continuity/annotation-template.json',build_annotation_template(catalog));status='template_unverified'
                else:
                    logger.save_json('continuity/catalog-validation.json',dict(schema_version=1,catalog=catalog_identity,status='structure_valid'))
                    status='structure_valid'
        print(json.dumps(dict(audit_run=str(logger.run_dir),status=status),ensure_ascii=False))
        return 3 if insufficient else 0
    except TimeoutError as exc:
        print(json.dumps(dict(status='timeout',error=str(exc))),file=sys.stderr);return 124
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        print(json.dumps(dict(status='rejected',error=str(exc))),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
