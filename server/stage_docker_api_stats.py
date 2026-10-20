"""Bounded Docker-compatible stats from a verified stage-owned container.

Read-only Docker CLI uses only an immutable ID authenticated by the stage
registry. No host containers, filesystem paths, network topology, or
actual Docker daemon socket is forwarded to the requesting stage app.
"""
from __future__ import annotations
import datetime
import json
import re
import subprocess

from stage_apps import AppError

CID=re.compile(r"[a-f0-9]{64}\Z")
NUMBER=re.compile(r"([0-9]+(?:\.[0-9]+)?)(B|kB|KB|KiB|MB|MiB|GB|GiB|TB|TiB)\Z")
UNITS={
    "B":1,"kB":1000,"KB":1000,"KiB":1024,
    "MB":1000000,"MiB":1024**2,"GB":1000**3,"GiB":1024**3,
    "TB":1000**4,"TiB":1024**4,
}


def _bytes(text):
    if not isinstance(text,str):
        return 0
    m=NUMBER.fullmatch(text.strip())
    return min(int(float(m.group(1))*UNITS[m.group(2)]),2**48) if m else 0


def _percent(text):
    if not isinstance(text,str) or not re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,2})?%",text):
        return 0.0
    return min(float(text[:-1]),10000.0)


def _safe_cli_stats(ident,runner=subprocess.run):
    if not isinstance(ident,str) or not CID.fullmatch(ident):
        raise AppError("invalid_stage_stats_identity",403)
    args=["docker","stats","--no-stream","--format","{{json .}}",ident]
    try:
        result=runner(args,capture_output=True,text=True,check=False,timeout=7)
    except (OSError,subprocess.TimeoutExpired):
        raise AppError("stage_stats_reader_unavailable",503)
    if result.returncode or len(result.stdout)>7000:
        raise AppError("stage_stats_reader_failed",503)
    try:
        data=json.loads(result.stdout)
    except (ValueError,TypeError):
        raise AppError("stage_stats_invalid_response",503)
    if not isinstance(data,dict):
        raise AppError("stage_stats_invalid_response",503)
    observed=data.get("ID")
    if not isinstance(observed,str) or len(observed)<12 or not ident.startswith(observed):
        raise AppError("stage_stats_identity_changed",403)
    return data


def snapshot(verified_row,runner=subprocess.run):
    """Only accept the redacted already-proven staging registry record."""
    if (not isinstance(verified_row,dict) or
        verified_row.get("Labels",{}).get("osd.stage.scope")!="staging-only" or
        not isinstance(verified_row.get("Id"),str) or
        not CID.fullmatch(verified_row["Id"])):
        raise AppError("unsafe_stage_stats_source",403)
    ident=verified_row["Id"]
    running=verified_row.get("State")=="running"
    raw=_safe_cli_stats(ident,runner) if running else {}
    mem=raw.get("MemUsage","").split("/",1)
    usage=_bytes(mem[0]) if mem else 0
    limit=_bytes(mem[1]) if len(mem)==2 else 256*1024**2
    cpu=_percent(raw.get("CPUPerc","0%"))
    usage_delta=int(cpu/100*1_000_000_000)
    try:
        pids=int(raw.get("PIDs","0"))
    except (TypeError,ValueError):
        pids=0
    pids=max(0,min(pids,64))
    when=datetime.datetime.now(datetime.timezone.utc)
    prev=when-datetime.timedelta(seconds=1)
    iso=lambda moment:moment.isoformat(timespec="milliseconds").replace("+00:00","Z")
    return {
        "read":iso(when),"preread":iso(prev),"id":ident,
        "name":verified_row["Names"][0],
        "pids_stats":{"current":pids},
        "memory_stats":{"usage":usage,"limit":limit,
                        "stats":{"cache":0}},
        "cpu_stats":{
            "cpu_usage":{"total_usage":1_000_000_000+usage_delta,
                         "usage_in_usermode":0,"usage_in_kernelmode":0},
            "system_cpu_usage":2_000_000_000,"online_cpus":1,
            "throttling_data":{"periods":0,"throttled_periods":0,"throttled_time":0},
        },
        "precpu_stats":{
            "cpu_usage":{"total_usage":1_000_000_000,
                         "usage_in_usermode":0,"usage_in_kernelmode":0},
            "system_cpu_usage":1_000_000_000,"online_cpus":1,
        },
        "networks":{},"blkio_stats":{},"storage_stats":{},
        "osd_source":"staging_verified_docker_stats_cli",
        "osd_cpu_percent":cpu,
    }
