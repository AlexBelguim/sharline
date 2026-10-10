"""Consolidate the existing game feature worktrees without overwriting local edits.

This performs per-file three-way merges in the current checkout, preserves Git
history/index and never changes the source worktrees. Conflicts are written to
tools/_showhome_merge for review; the original target file is retained.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='58acb1d686519d3d8a3294f4b6aa78fd4f9bb7a3'
WORK=ROOT/'tools/_showhome_merge'
SOURCES=[
    ('audio_playtest',ROOT/'.claude/worktrees/integrate-r1','integrate-r1'),
    ('surface_depth',ROOT/'.claude/worktrees/wf_c7bb2a63-cd9-2','worktree-wf_c7bb2a63-cd9-2'),
    ('decals',ROOT/'.claude/worktrees/wf_c7bb2a63-cd9-3','worktree-wf_c7bb2a63-cd9-3'),
]


def git(*args):
    return subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,check=True).stdout


def integrate(label,source,paths):
    report=[]
    for rel in sorted(paths):
        if not rel.startswith('game/'):
            continue
        incoming=source/rel;target=ROOT/rel
        if not incoming.is_file():
            report.append(dict(path=rel,status='source_missing_retained'));continue
        data=incoming.read_bytes()
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            report.append(dict(path=rel,status='LFS_POINTER_NOT_COPIED'));continue
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()==data:
            report.append(dict(path=rel,status='unchanged'));continue
        old=subprocess.run(['git','-C',str(ROOT),'show',BASE+':'+rel],capture_output=True)
        if not target.exists() or old.returncode:
            if target.exists() and target.suffix in ('.rs','.md','.ron','.toml','.wgsl'):
                # A new file from another feature is never blindly overwritten.
                dest=WORK/label/rel
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                report.append(dict(path=rel,status='NEW_FILE_COLLISION',incoming=str(dest)));continue
            shutil.copy2(incoming,target)
            report.append(dict(path=rel,status='added'));continue
        ours=target.read_bytes();base=old.stdout
        if ours==base:
            shutil.copy2(incoming,target);report.append(dict(path=rel,status='updated'));continue
        if target.suffix not in ('.rs','.md','.ron','.toml','.wgsl','.py','.ps1'):
            # Different local binary content belongs to its current author.
            report.append(dict(path=rel,status='LOCAL_BINARY_RETAINED'));continue
        folder=WORK/label/rel.replace('/','_')
        folder.mkdir(parents=True,exist_ok=True)
        for name,content in [('ours',ours),('base',base),('incoming',data)]:
            (folder/name).write_bytes(content)
        merged=subprocess.run(['git','merge-file','-p',str(folder/'ours'),str(folder/'base'),str(folder/'incoming')],capture_output=True)
        if merged.returncode==0:
            target.write_bytes(merged.stdout);report.append(dict(path=rel,status='merged'))
        else:
            (folder/'conflict').write_bytes(merged.stdout)
            report.append(dict(path=rel,status='CONFLICT',review=str(folder/'conflict')))
    return report


def main():
    WORK.mkdir(exist_ok=True)
    report={}
    for label,source,branch in SOURCES:
        paths=git('diff','--name-only',BASE+'..'+branch,'--','game').decode().splitlines()
        report[label]=integrate(label,source,paths)
    foliage=ROOT/'.claude/worktrees/wf_c7bb2a63-cd9-1'
    tracked=git('-C',str(foliage),'diff','--name-only','--','game').decode().splitlines()
    untracked=git('-C',str(foliage),'ls-files','--others','--exclude-standard','--','game').decode().splitlines()
    report['foliage']=integrate('foliage',foliage,set(tracked+untracked))
    (WORK/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    for label,rows in report.items():
        issues=[r for r in rows if r['status'] in ('CONFLICT','NEW_FILE_COLLISION','LFS_POINTER_NOT_COPIED','LOCAL_BINARY_RETAINED')]
        print(label,len(rows),'files',json.dumps(issues))


if __name__=='__main__':main()
