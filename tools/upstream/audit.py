"""Generate deterministic read-only integration inventory for upstream source clones."""
import argparse, json, re, subprocess
from pathlib import Path
COMPONENTS=("CasaOS-Gateway","CasaOS-UserService")
def audit(root):
    result={}
    for name in COMPONENTS:
        path=Path(root)/name
        mod=path/"go.mod"
        lic=path/"LICENSE"
        if not mod.is_file() or not lic.is_file():
            raise ValueError(f"missing source or license: {name}")
        content=mod.read_text()
        match=re.search(r"(?m)^go\s+([0-9.]+)$",content)
        if not match: raise ValueError("missing Go version")
        commit=subprocess.check_output(["git","-C",str(path),"rev-parse","HEAD"],text=True).strip()
        result[name]={"go":match.group(1),"commit":commit,"license_present":True,"source_checked":True,"build_tested":False}
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    out=audit(a.root)
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out))
