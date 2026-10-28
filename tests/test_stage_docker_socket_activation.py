"""User systemd socket activation cannot accidentally bind a new host socket."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as broker


class SocketActivation(unittest.TestCase):
    def test_no_activation_variables_falls_back(self):
        with patch.dict(os.environ,{"LISTEN_FDS":"","LISTEN_PID":""}):
            self.assertIsNone(broker._activated_systemd_socket())

    def test_untrusted_pid_or_fd_count_rejected_without_opening_fd(self):
        for fds,pid in (("2",str(os.getpid())),("1","1"),
                         ("invalid",str(os.getpid()))):
            with self.subTest(fds=fds,pid=pid),patch.dict(
                os.environ,{"LISTEN_FDS":fds,"LISTEN_PID":pid}):
                with self.assertRaises(RuntimeError):
                    broker._activated_systemd_socket()

    def test_unit_declares_stable_rootless_socket(self):
        root=Path(__file__).resolve().parents[1]/"deploy"/"alpha"
        socket_unit=(root/"openserverdesk-stage-docker-broker.socket").read_text()
        service=(root/"openserverdesk-stage-docker-broker.service").read_text()
        self.assertIn("SocketMode=0600",socket_unit)
        self.assertIn("RemoveOnStop=no",socket_unit)
        self.assertIn("ListenStream=/home/andre/projects/openserverdesk/alpha/run/dozzle.sock",socket_unit)
        self.assertIn("Requires=openserverdesk-stage-docker-broker.socket",service)
        self.assertIn("NoNewPrivileges=yes",service)


if __name__=="__main__":
    unittest.main()
