# OpenServerDesk Alpha 0.7.0-alpha.15 — read-only App Store mounts

Implemented safe repair for two long-form CasaOS metadata records with
malformed container targets ending in :ro (Fail2ban and MAME).

- Strip only the invalid :ro suffix from the CONTAINER target.
- Preserve the intended read-only mount in compiled Compose and in the
  single-service Docker stage runtime.
- Allocate an entirely fresh, stage-owned mount source. Original host log
  directories, ROM media, CasaOS data and Nextcloud HDD are never copied.
- Verify read-only capability and provenance for future stage containers.
  Existing stage-owned registry entries remain backwards-compatible.
- Unsafe host mounts and privileged network/device requirements remain gated.
- Static sandbox plans: 672/726. Host-integrated apps: 54.
  Unhandled metadata cases: 0.
- The 672 count proves safe PLAN generation only, NOT end-to-end operation
  of all apps. Empty stage read-only volumes may require operator-provided
  test content for app functionality.
- Original CasaOS production remains unchanged. No production cutover.
- Alpha service: andre uid 1000, LAN 192.168.31.31:18691,
  https://osd.vervue.my.id.
