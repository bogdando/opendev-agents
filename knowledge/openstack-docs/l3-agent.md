# Neutron L3 Agent Architecture

The Neutron L3 agent manages layer-3 networking for OpenStack deployments,
handling router namespaces, floating IP associations, and inter-subnet routing.

## Router Namespaces

Each virtual router is implemented as a Linux network namespace (`qrouter-<uuid>`).
The namespace contains:
- An internal interface connected to each subnet the router serves
- An external gateway interface for traffic leaving the tenant network
- iptables/nftables rules for NAT, floating IP DNAT/SNAT, and security

## Floating IPs

Floating IPs provide 1:1 NAT between a public address and a private instance
address. The L3 agent programs:
- A DNAT rule mapping the floating IP to the instance's fixed IP
- An SNAT rule for return traffic
- A proxy ARP entry on the external interface

## HA Routers (VRRP)

When `l3_ha = True`, routers use VRRP (keepalived) for active/standby failover.
Each HA router runs a keepalived instance inside its namespace. The master router
handles all traffic; on failure, the standby takes over within seconds.

## DVR (Distributed Virtual Router)

DVR moves East-West routing to compute nodes, avoiding the network node bottleneck.
Each compute node hosting instances for a DVR router gets a local router namespace.
North-South traffic for floating IPs is handled locally on the compute node;
SNAT traffic without floating IPs still goes through a centralized SNAT namespace
on the network node.

## Configuration

Key configuration options in `l3_agent.ini`:
- `agent_mode`: `legacy`, `dvr`, or `dvr_snat`
- `external_network_bridge`: deprecated in favor of provider networks
- `ha_vrrp_auth_password`: shared secret for VRRP authentication
- `interface_driver`: typically `openvswitch` or `linuxbridge`
