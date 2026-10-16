# Signed v0.6.20 staging artifact: verified local release provenance

Artifact SHA256:
99d6b8066b01d354784f182bbc77f169f82f54ccc026fa02c950b648da1bed79

A root-only Ed25519 staging operator key signed a canonical detached manifest
binding exactly this package, its SHA256, size and source Git baseline
ae3e563. The PUBLIC key independently verifies the detached manifest.
The actual final M1 release-decision controller verifies the v0.6.20
signature. The private key remains only on andre-nas and never enters
GitHub or a user-visible chat.

This is staging provenance only, NOT an independently trusted production
signing authority, penetration test, or security acceptance. 18 real CasaOS
Compose app definitions remain unverified for general import parity; no
production migration is allowed.
