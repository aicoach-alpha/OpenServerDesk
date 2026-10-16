#!/usr/bin/env python3
"""Synthetic Docker metadata proof: never stat protected user-data paths."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
import m1_platform_scope as scope

assert scope.protected(Path("/mnt/data/nextcloud/files/photo.jpg"))
assert scope.protected(Path("/run/media/usb/dataset"))
assert scope.protected(Path("/home/andre/nextcloud/data/files/doc.txt"))
assert scope.protected(Path("/mnt/unknown_mount"))
assert not scope.protected(Path("/etc/casaos"))
assert not scope.protected(Path("/home/andre/docker/compose.yaml"))

real_file = Path.is_file
real_dir = Path.is_dir
real_symlink = Path.is_symlink

def guard(path, method):
    if scope.protected(path):
        raise AssertionError("protected user-data filesystem accessed")
    return method(path)

fake_id="a"*64
fake=[{"Id":fake_id,"State":{"Running":True},"Config":{"Labels":{
  "com.docker.compose.project":"nextcloud",
  "com.docker.compose.project.config_files":
  "/mnt/data/docker-compose.yml,/home/andre/docker/compose.yaml"
}},"Mounts":[
 {"Type":"bind","Source":"/mnt/data/nextcloud/files","RW":True},
 {"Type":"bind","Source":"/home/andre/nextcloud/data/files","RW":True}
]}]

def docker_stub(*args):
    if args[:3]==("container","ls","--all"):
        return fake_id+"\n"
    if args[:2]==("inspect","--type"):
        return json.dumps(fake)
    raise AssertionError("unapproved docker request")

with patch.object(scope,"docker",side_effect=docker_stub), \
     patch.object(Path,"is_file",lambda self:guard(self,real_file)), \
     patch.object(Path,"is_dir",lambda self:guard(self,real_dir)), \
     patch.object(Path,"is_symlink",lambda self:guard(self,real_symlink)):
    report,selected=scope.select()
    assert report["external_user_data_copied"] is False
    assert report["external_user_data_inspected"] is False
    assert report["protected_bind_references_skipped"]==2
    assert all(not scope.protected(Path(p)) for p in selected)
    assert "/mnt/data/docker-compose.yml" not in selected
print("NEXTCLOUD_USER_HDD_NOT_OPENED_OR_COPIED_PASS")
print("CONFIG_ONLY_SCOPE_WITH_PROTECTED_BINDS_PASS")
