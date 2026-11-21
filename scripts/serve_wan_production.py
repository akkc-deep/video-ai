"""Private owned production service entry. CPU probe never admits weights."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--launch',required=True,type=Path)
    parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--cpu-probe',action='store_true')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('invalid owned port')
    from video_ai.runtime.wan_production_worker import serve
    serve(args.run,args.launch,args.port,cpu=args.cpu_probe)


if __name__=='__main__':main()
