---
name: in-network-filter
description: Fixes search_providers to exclude providers marked as is_in_network=False
metadata:
  type: feedback
---

The `search_providers` function previously joined on the `provider_networks` table but did not filter for `is_in_network == True`. This caused out-of-network providers to be returned in insurance-filtered searches.

**Why:** The join only checked for the existence of a relationship between a provider and a plan, not the actual network status.

**How to apply:** Always include `provider_networks.c.is_in_network == True` when filtering by `plan_id` in `search_providers`.
