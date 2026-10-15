# ReCasaOS Go Build Gate (M1)
1. Clone and pin upstream ReCasaOS Gateway and UserService. Inspect licenses and go.mod.
2. Prepare dependencies with explicit network access in a disposable Go container by running `go mod download` while binding a dedicated Go module cache. Checksums are enforced through upstream go.sum during download, but dependency supply-chain review remains pending.
3. Run `tools/upstream/build-staging.sh`: no network, read-only source and root FS, no additional capabilities, bounded memory/CPU/pids, cache read-only.
4. Mark PASS only when both suites succeed and separately built binaries execute successfully in isolated staging, with rollback and security gates.
Do not deploy these services against production CasaOS databases, users, or ports.

## Source code generation (required by UserService)
A fresh ReCasaOS UserService clone intentionally excludes `codegen/`. Before offline build,
run `go generate` in a **separate writable workspace**, with controlled network access.
This generates `codegen/user_service` from the pinned local OpenAPI specification and
`codegen/message_bus` from a tagged remote specification. Pin and verify both
the generator and remote input before release; until then it remains a staging-only build.
Do not generate files against production `/var/lib/casaos`, and do not commit upstream generated source without attribution review.
