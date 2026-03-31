# Nova Conductor Design Rationale

## Why the Conductor Exists

The Nova conductor was introduced in the Grizzly release to solve the
"database on compute nodes" security problem. Before Grizzly, compute
nodes had direct database access — a compromised compute node could
read or modify any instance record.

## Architecture

The conductor acts as a proxy between compute nodes and the database:

- Compute nodes communicate with the conductor via oslo.messaging RPC
- The conductor performs database operations on behalf of compute nodes
- Compute nodes never connect to the database directly

This provides a security boundary: even if a compute node is compromised,
the attacker cannot directly query or modify the database. They can only
make RPC calls that the conductor validates and executes.

## Task Management

The conductor also handles long-running orchestration tasks:
- Instance build (selecting host, creating network ports, attaching volumes)
- Live migration orchestration
- Resize/cold migration coordination
- Evacuate workflows

These tasks were moved from the compute service to the conductor to
improve reliability — if a compute node crashes mid-operation, the
conductor can detect the failure and clean up.

## RPC Interface

Key conductor RPC methods:
- `build_instances`: orchestrates the full instance launch flow
- `migrate_server`: handles cold migration and resize
- `live_migrate_instance`: coordinates live migration
- `rebuild_instance`: handles evacuate and rebuild
- `object_backport_versions`: version-pins object serialization for rolling upgrades
