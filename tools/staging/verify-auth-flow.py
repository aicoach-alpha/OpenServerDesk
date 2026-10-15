#!/usr/bin/env python3
"""Destructive to a FRESH, disposable staging user DB only. Never target production."""
import json
import secrets
import subprocess

BASE = "http://127.0.0.1:18701"
CONTAINER = "osd-m1-gateway"

def request(method, path, payload=None, token=None):
    cmd = ["docker", "exec", "-i", CONTAINER, "curl", "-sS", "--max-time", "8",
           "-X", method, "-w", "\\n%{http_code}", BASE + path]
    if token:
        cmd += ["-H", "Authorization: " + token]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    done = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                          capture_output=True, text=True, timeout=15, check=True)
    body, code = done.stdout.rsplit(chr(10), 1)
    return int(code), json.loads(body)

def check(ok, what):
    if not ok:
        raise RuntimeError(what + " FAIL")
    print(what + " PASS")

def main():
    mode = subprocess.check_output(["docker", "inspect", CONTAINER,
                                    "--format", "{{.HostConfig.NetworkMode}}"], text=True).strip()
    check(mode == "none", "ISOLATED_NETWORK")
    code, status = request("GET", "/v1/users/status")
    check(code == 200 and status["data"]["initialized"] is False, "FRESH_DB")
    key = status["data"]["key"]
    user = "osd-test-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(25)
    code, result = request("POST", "/v1/users/register",
                           {"username": user, "password": password, "key": key})
    check(code == 200 and result.get("success") == 200, "REGISTER")
    code, result = request("POST", "/v1/users/login",
                           {"username": user, "password": password})
    check(code == 200 and result.get("success") == 200, "LOGIN")
    tokens = result["data"]["token"]
    access = tokens.get("access_token") or tokens.get("accessToken")
    refresh = tokens.get("refresh_token") or tokens.get("refreshToken")
    check(bool(access and refresh), "TOKENS_PRESENT")
    code, result = request("GET", "/v1/users/current", token=access)
    check(code == 200, "PROTECTED_ROUTE")
    code, result = request("POST", "/v1/users/refresh", {"refresh_token": refresh})
    check(code == 200 and result.get("success") == 200, "REFRESH")
    print("AUTH_FLOW_END_TO_END_PASS")

if __name__ == "__main__":
    main()
