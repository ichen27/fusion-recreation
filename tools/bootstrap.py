"""Fetch checksum-locked archives and build OCCT on a user-selected cache volume."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
def checksum(path):
    digest=hashlib.sha256()
    with open(path,"rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()

def verify(path,expected):
    if checksum(path)!=expected:
        raise ValueError("DependencyChecksumMismatch: "+str(path))

def fetch(root):
    lock=json.loads((ROOT/"deps/lock.json").read_text())
    root.mkdir(parents=True,exist_ok=True)
    for name,record in lock["sources"].items():
        archive=root/(name+".tar.gz")
        if not archive.exists():
            temporary=archive.with_suffix(".download")
            urllib.request.urlretrieve(record["url"],temporary)
            verify(temporary,record["sha256"])
            temporary.replace(archive)
        verify(archive,record["sha256"])
        target=root/record["directory"]
        if not target.exists():
            with tarfile.open(archive) as source:
                source.extractall(root,filter="data")
    return lock

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--jobs",type=int,default=6)
    parser.add_argument("--fetch-only",action="store_true")
    args=parser.parse_args()
    lock=fetch(args.root)
    if args.fetch_only:return
    options=["FoundationClasses","ModelingData","ModelingAlgorithms","Visualization","ApplicationFramework","DataExchange","Draw"]
    command=["cmake","-S",str(args.root/lock["sources"]["occt"]["directory"]),"-B",str(args.root/"occt-build"),
             "-G","Ninja","-DCMAKE_BUILD_TYPE=Release","-DINSTALL_DIR="+str(args.root/"occt-install"),
             "-DBUILD_ADDITIONAL_TOOLKITS=TKPrim TKBool TKCAF TKBin TKDESTEP TKXCAF TKBinXCAF TKMesh"]
    # Linux RUNPATH is not inherited from the executable by indirect dependencies.
    # Each installed OCCT library must find its sibling libraries itself.
    if sys.platform.startswith("linux"):
        command += ["-DCMAKE_INSTALL_RPATH=$ORIGIN"]
    command += ["-DBUILD_MODULE_"+name+"=OFF" for name in options]
    command += ["-DUSE_"+name+"=OFF" for name in ("TK","FREETYPE","OPENGL","XLIB")]
    subprocess.run(command,check=True)
    subprocess.run(["cmake","--build",str(args.root/"occt-build"),"-j",str(args.jobs)],check=True)
    subprocess.run(["cmake","--install",str(args.root/"occt-build")],check=True)
if __name__=="__main__":main()
