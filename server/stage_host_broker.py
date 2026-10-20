"""Host Integration Broker, stage-only and deny-by-default (v1).

This server-side boundary does not expose a Docker socket, a host file,
a device, network namespace, or a privileged operation. Its *only* currently
enabled interface is read-only OSD-owned staging inventory, available to an
authenticated OSD operator; NOT injected into third-party app containers.

Most CasaOS apps requesting host integration will still need an explicitly
approved capability-specific adapter. Never claim runtime equivalence.
"""
from __future__ import annotations

import re

from appstore_compatibility_matrix import listing as appstore_matrix
from stage_apps import AppError
from stage_unified_inventory import inventory
from stage_host_socket import APPROVED_PILOTS, ADAPTER

IDENTITY=re.compile(r"[a-zA-Z0-9_.:-]{1,115}\Z")
HOST_CAPABILITIES=frozenset((
    "host_docker_or_casaos_api","host_devices_or_kernel",
    "host_system_services","host_security_or_system_files",
    "host_dns_and_network",
))
READONLY_CAPABILITY="stage_container_inventory_readonly"
SAFE_SOURCES=frozenset(("docker","compose","store_pilot","store_general","store_compiled"))


def _host_rows():
    matrix=appstore_matrix()
    if (matrix.get("production_mutation_allowed") is not False or
            not isinstance(matrix.get("apps"),list)):
        raise AppError("host_broker_catalog_integrity_unavailable",503)
    return {
        row["id"]:row for row in matrix["apps"]
        if row.get("install_mode")=="special_host_integration"
        and isinstance(row.get("id"),str)
    }


def _contract(row):
    requested=sorted(set(row.get("requirements") or []) & HOST_CAPABILITIES)
    can_inspect="host_docker_or_casaos_api" in requested
    return {
        "app_id":row["id"],
        "requested_host_capabilities":requested,
        "available_operator_interfaces":(
            [READONLY_CAPABILITY] if can_inspect else []),
        "granted_host_capabilities":[],
        "stage_docker_socket_exposed":False,
        "host_privileged_access":False,
        "external_hdd_user_data_access":False,
        "production_mutation_allowed":False,
        "runtime_compatibility_proven":False,
        "decision":"host_capabilities_denied_stage_inventory_only",
    }


def contracts():
    apps=[_contract(row) for row in _host_rows().values()]
    apps.sort(key=lambda item:item["app_id"])
    return {
        "scope":"authenticated_operator_stage_host_broker_v1",
        "contracts":apps,
        "count":len(apps),
        "curated_stage_socket_pilots":[{
            "app_id":app_id,"adapter":ADAPTER,
            "real_docker_socket_exposed":False,
            "production_mutation_allowed":False,
            "runtime_functionality_proven":False,
        } for app_id in sorted(APPROVED_PILOTS)],
        "stage_inventory_read_interface_count":sum(
            READONLY_CAPABILITY in item["available_operator_interfaces"]
            for item in apps),
        "production_mutation_allowed":False,
        "host_privileged_access":False,
        "external_hdd_user_data_access":False,
        "runtime_compatibility_proven":False,
    }


def inspect(app_id):
    if not isinstance(app_id,str) or not IDENTITY.fullmatch(app_id):
        raise AppError("invalid_host_broker_app_id",400)
    row=_host_rows().get(app_id)
    if row is None:
        raise AppError("host_broker_app_not_eligible",404)
    result=_contract(row)
    # Actual stage metadata read: provenance has already been checked by
    # each contributing stage manager. No caller-supplied Docker API args.
    if READONLY_CAPABILITY in result["available_operator_interfaces"]:
        state=inventory()
        if state.get("production_mutation_allowed") is not False:
            raise AppError("unsafe_host_broker_inventory",503)
        subset=[]
        for item in state.get("applications",[]):
            if item.get("source") not in SAFE_SOURCES:
                raise AppError("unsafe_host_broker_source",503)
            if item.get("lifecycle_writable") is not True:
                continue  # protected/recovery-in-progress stage records
            if not isinstance(item.get("running"),bool):
                raise AppError("unsafe_host_broker_state",503)
            subset.append({
                "source":item["source"],
                "running":item["running"],
                "readiness":str(item.get("readiness","unknown"))[:50],
            })
        result["stage_readonly_inventory"]={
            "total":len(subset),
            "running":sum(item["running"] for item in subset),
            "applications":subset[:40],
            "complete":state.get("complete") is True,
        }
    return result
