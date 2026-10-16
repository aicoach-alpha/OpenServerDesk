# 18 incumbent Compose topologies — isolated synthetic lifecycle experiment

Experimental tool: tools/staging/verify_synthetic_compose_lifecycle.py

This script never deploys real CasaOS apps. It parses only CasaOS-controlled
Compose YAML configuration files and rebuilds all service structures from
scratch with a cached BusyBox image, network_mode=none, no published ports,
zero host-volume/bind mounts, read-only root FS, all capabilities dropped,
unprivileged user, no image pulling, no building, short-lived stage-only names
and unique ownership labels.

Each generated project is validated with Docker Compose, then its synthetic
containers are started, ownership and isolation checks run, and finally only
containers in the exact synthetic project are brought down. Before and after
container ID inventory is compared; an unexpected change fails the run.

Running such tests DOES NOT establish functional compatibility of Nextcloud,
databases, web servers or any other original application. Real app images,
credentials, ports and user data are NEVER used. No real app is imported.
Do not increase M1 40% accepted gates based on synthetic tests alone.

If the test finishes, its output must explicitly show success and cleanup
before claiming any stage lifecycle PASS. Production migration remains
disabled until complete independent product parity UAT and approval.

## Chunked execution safety

The original full 18-app run exceeded the bounded SentinelX job timeout
after successfully completing 13 one-service application fixture
lifecycles. Two stopped synthetic stage-only containers remained from the
interrupted 14th fixture. An independent, label/owner/image/mount-verified
cleanup removed precisely those two containers; zero synthetic stage-only
containers remained. This interruption is NOT an 18/18 PASS.

The tool was updated to accept explicit --start and --end indexes and
reject batches larger than nine apps. This makes jobs bounded and prevents
a whole-suite timeout from misleading users. Every batch must pass its
own container inventory restoration gate before it may be reported as PASS.

## Observed completion — 16 October 2026

The first job individually completed app fixtures 1-13 before the timeout.
After a strictly stage-only cleanup, a bounded batch for application
fixtures 14-18 PASSED: five fixtures, six services, each independently
started, provenance checked and stopped. The final independent Docker
inventory confirmed ZERO synthetic stage-only containers remaining and
all six original CasaOS production services active.

Across both observations, all 18 incumbent Compose **topologies** had
synthetic fixture lifecycle proof (19 BusyBox synthetic services in total).
The first 18-app command itself did NOT exit successfully; evidence is the
13 individual completed fixture results plus a successful later 5-app batch.

Original application import/runtime parity remains **0/18**. The test
does not reproduce actual app images, ports, networks, credentials, bind
data or application semantics. This may never be marketed as CasaOS parity.
