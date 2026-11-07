"""Restore a reward archive to a NEW directory with an independent CURRENT deletion registry.
Never restores account files or signing keys; never replaces a live DATA_DIR.
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.deletion_backup import restore_rewards


def restore(archive: Path, target: Path, *, deletion_registry: Path):
    return restore_rewards(archive,target,deletion_registry)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('--deletion-registry',type=Path,required=True)
    args=parser.parse_args()
    report=restore(args.archive,args.target,deletion_registry=args.deletion_registry)
    print('Sanitized offline copy verified. Source and live storage unchanged; registry revision '+str(report['registry_revision']))
