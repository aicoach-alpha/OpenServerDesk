"""Focused rejection checks for retired stopped OSD M1 test cleanup."""
import importlib.util
import unittest
from pathlib import Path

source=Path(__file__).resolve().parents[1]/"tools/staging/reconcile_casaos_legacy_osd_m1.py"
spec=importlib.util.spec_from_file_location("retired_m1",source)
subject=importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def fixture():
    result=[]
    for i,name in enumerate(subject.NAMES):
        ident=("%064x" % (i+11))
        result.append({
            "Name":"/"+name,"Id":ident,"State":{"Status":"exited"},
            "Config":{"Image":"golang:1.26.8","Volumes":None,"Labels":None},
            "HostConfig":{"RestartPolicy":{"Name":"no"},
                          "PortBindings":{},"Privileged":False,
                          "NetworkMode":"none" if i==2 else "container:"+("%064x"%13)},
            "Mounts":[{"Type":"bind","Source":path}
                       for path in sorted(subject.EXPECTED_MOUNTS[name])],
        })
    return result


class OSDM1Cleanup(unittest.TestCase):
    def test_exact_old_stopped_test_names_only(self):
        entries=fixture()
        ids=subject.preflight(entries)
        self.assertEqual(ids,[item["Id"] for item in entries])
        entries.append({"Name":"/nextcloud","Id":"f"*64,
                        "HostConfig":{"NetworkMode":"bridge"}})
        self.assertEqual(subject.preflight(entries),ids)

    def test_running_or_unknown_data_mount_is_denied(self):
        for mutation in (
            lambda e:e[0]["State"].__setitem__("Status","running"),
            lambda e:e[0]["Mounts"].append(
                {"Type":"bind","Source":"/mnt/external-hdd/nextcloud"}),
            lambda e:e[2]["HostConfig"].__setitem__("NetworkMode","host"),
            lambda e:e[1]["Config"].__setitem__("Image","ubuntu:latest"),
        ):
            with self.subTest(mutation=mutation):
                entries=fixture()
                mutation(entries)
                with self.assertRaises(RuntimeError):
                    subject.preflight(entries)

    def test_any_external_container_namespace_dependency_blocks(self):
        entries=fixture()
        entries.append({"Name":"/other-active-service","Id":"f"*64,
                        "HostConfig":{"NetworkMode":"container:"+entries[2]["Id"]}})
        with self.assertRaises(RuntimeError):
            subject.preflight(entries)


if __name__=="__main__":
    unittest.main()
