"""Create a NEW sanitized directory snapshot. Source backups are never overwritten."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.deletion_backup import sanitize_snapshot

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('--deletion-registry',type=Path,required=True)
    args=parser.parse_args()
    result=sanitize_snapshot(args.source,args.target,args.deletion_registry)
    print('Sanitized COPY created; original backups remain. Registry revision '+str(result['registry_revision']))
