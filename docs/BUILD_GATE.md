# Upstream build gate — M1
Use the isolated script `tools/upstream/build-staging.sh` only after pinning and examining upstream sources.

The initial script enforces a read-only root, no container privileges, no network, read-only source mounts, and temporary writable disk. This will **not** be sufficient if dependencies have not been cached; in that case use a separately controlled dependency preparation step. Never install Go on the production host solely for a staging build. No upstream binary has passed build/runtime integration yet.

Passing a Go test suite is not authorization to migrate CasaOS users or databases; require separate auth migration, application state restore, rollback and penetration testing.
