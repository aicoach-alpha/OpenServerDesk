# Alpha 0.7.0-alpha.18 — broker service compatibility correction

The first service unit tried PrivateDevices and ProtectSystem in a user
manager that cannot create the requested system capability sandbox.
The broker failed with 218/CAPABILITIES; no Alpha/CasaOS apps were affected.
The unit now retains UID1000 isolation, NoNewPrivileges, UMask=0077,
CPUQuota=30%, MemoryMax=96M, TasksMax=36, and an eight-client semaphore.
Broker socket file remains owned by UID1000 with mode 0600.
Service tested LIVE with GET stage-only containers (one matching instance);
all POST and DELETE attempts rejected HTTP 403. Production hidden.
The Dozzle image remains absent from cache, so the third-party Dozzle UI
has NOT been verified and cannot be declared functionally compatible.
Static sandbox plans 673/726; 53 host-integrated apps still blocked.
No CasaOS production cutover or Nextcloud external HDD access.
