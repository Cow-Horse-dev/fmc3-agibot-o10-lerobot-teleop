# Scripts Layout

Scripts are grouped by purpose. The `scripts/` root only contains this README
and category folders.

- `lib/` contains shared shell helpers such as Python environment discovery.
- `o10/` contains daily O10 runtime launchers for control, record, replay, and infer.
- `o10/left_arm/` contains left-arm launchers.
- `o10/right_arm/` contains right-arm launchers.
- `o10/dual_arm/` contains dual-arm launchers.
- `services/` contains HDService and HDWeb lifecycle helpers.
- `tools/` contains one-off utilities for reset poses, tactile checks, dataset conversion, and Docker image export.

O10 launchers live only in the arm-specific folders.

Runtime logs and Python caches are generated artifacts and should not live under
this directory.
