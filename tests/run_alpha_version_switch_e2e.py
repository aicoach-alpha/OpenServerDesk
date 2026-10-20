"""Explicitly opt-in ONE isolated MySpeed stage version/rollback E2E.

Runs only as uid 1000 with env OSD_REAL_STAGE_E2E=1. It never touches CasaOS
production projects, uses a fresh random osd-compiled-* project, and removes
its own instance in a finally block. Never run this test on unrelated apps.
"""
import os
import sys
from pathlib import Path

assert os.getuid()==1000, "must run as andre, not root"
assert os.environ.get("OSD_REAL_STAGE_E2E")=="1", "explicit opt-in required"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_store_runtime import operation,listing,_current,_projects
from stage_store_versions import target_image

baseline={a["project"] for a in listing()["apps"]}
if len(baseline)>3:
    raise RuntimeError("too many existing staging projects")
project=None
checks=[]
try:
    result=operation("install",app_id="default:MySpeed")
    project=result["app"]["project"]
    assert project not in baseline and result["app"]["all_running"]
    checks.append("fresh_stage_install")
    print("REAL_E2E_INSTALL",project,flush=True)

    original,_=_current(project,_projects()[project])
    name=next(iter(original["services"]))
    before=original["services"][name]["image"]
    variants={t:target_image("default:MySpeed",t) for t in ("latest","1.0.8")}
    alternative=next((tag for tag,ident in variants.items() if ident!=before),None)
    assert alternative is not None, "two distinct cached digests required"
    print("REAL_E2E_ALTERNATE",alternative,flush=True)

    switched=operation("switch-version",project=project,image_tag=alternative)
    assert switched["operation"]=="switched_version"
    assert switched["app"]["application_data_rollback"]
    new,_=_current(project,_projects()[project])
    assert new["services"][name]["image"]==variants[alternative]
    assert switched["app"]["all_running"]
    checks.append("immutable_image_changed")
    print("REAL_E2E_IMAGE_CHANGED",flush=True)

    reverted=operation("rollback",project=project)
    assert reverted["operation"]=="rollback"
    assert reverted["data_restored"] is True
    old,_=_current(project,_projects()[project])
    assert old["services"][name]["image"]==before
    assert reverted["app"]["all_running"]
    checks.append("image_and_data_rollback")
    print("REAL_E2E_ROLLBACK_PASS",flush=True)
finally:
    if project is not None:
        try:
            removed=operation("uninstall",project=project)
            assert removed["operation"]=="uninstalled"
            checks.append("cleanup_uninstall")
            print("REAL_E2E_CLEANUP_PASS",flush=True)
        except Exception as error:
            print("REAL_E2E_CLEANUP_REQUIRES_RECOVERY",project,
                  type(error).__name__,str(error),flush=True)
            raise
final=listing()
assert {a["project"] for a in final["apps"]}==baseline
assert not final["pending_recovery"]
print("REAL_STAGE_VERSION_CHANGE_E2E_PASS",checks,flush=True)
