# Nova Scheduler

The Nova scheduler selects a compute host for each instance launch request.
It uses a pipeline of filters and weighers to narrow the candidate list.

## Filter Scheduler Pipeline

1. **Filters** eliminate hosts that cannot fulfill the request
2. **Weighers** rank remaining hosts by preference
3. The top-ranked host wins (or top N for multi-instance requests)

## Common Filters

- `AvailabilityZoneFilter`: match requested AZ
- `ComputeFilter`: host must be alive and enabled
- `RamFilter`: host must have enough free RAM (`ram_allocation_ratio`)
- `DiskFilter`: host must have enough disk space
- `ComputeCapabilitiesFilter`: match flavor extra_specs against host capabilities
- `ImagePropertiesFilter`: match image properties (architecture, hypervisor type)
- `NUMATopologyFilter`: ensure NUMA placement is feasible
- `PciPassthroughFilter`: host must have requested PCI devices
- `AggregateInstanceExtraSpecsFilter`: match against host aggregate metadata

## Weighers

- `RAMWeigher`: prefer hosts with more free RAM (spreader) or less (stacker)
- `DiskWeigher`: prefer hosts with more free disk
- `MetricsWeigher`: custom metrics from compute nodes
- `IoOpsWeigher`: prefer hosts with fewer in-progress operations
- `ServerGroupSoftAffinityWeigher`: prefer hosts already running group members

## Placement Integration

Since Queens, the scheduler queries the Placement service for allocation
candidates before running filters. Placement handles resource provider
inventories (VCPU, MEMORY_MB, DISK_GB) and traits, reducing the filter
set that the scheduler must evaluate.
