# v0.6.23 LIVE stage-only authenticated binary file transfer

16 October 2026. OpenServerDesk stage file manager now supports binary
upload/download with strict 64 KiB per-file quota and a 500 file limit.
Only the dedicated app-owned stage file directory is accessed; CasaOS
production applications and Nextcloud uploads on external HDD are not
read, moved or changed.

POST /api/v1/stage/upload consumes application/octet-stream with a
strict stage filename header. It is authorized for administrator and
operator, denied for reader. It uses openat-style directory confinement,
O_NOFOLLOW and O_CREAT|O_EXCL: no traversal, symlink following,
hardlink shenanigans or overwrites. GET /api/v1/stage/download?name=...
returns opaque bytes without decoding as text and permits authorized
reader access. All upload/download bodies are bounded, and binary files
are within the existing stage checkpoint hash/size schema.

The dashboard offers stage-only upload and download controls with
role-dependent enablement. The server remains the sole authority for
access decisions; a forged browser request cannot bypass reader
write denial.

Proof: three isolated HTTP unit tests PASS for arbitrary binary
roundtrip, duplicate rejection, oversized refusal, path traversal
refusal and reader write denial. A separate real LIVE v0.6.23
authenticated test uploaded and downloaded a binary file byte-for-byte,
verified reader POST=403, deleted only the synthetic test object and
confirmed it no longer exists. All six CasaOS production units active.

Limits: no folder hierarchy, no large files, no streaming, no
independent production security assessment. This is an incremental
staging capability, not complete CasaOS functional parity or a
production release authorization. migration_allowed=false.
