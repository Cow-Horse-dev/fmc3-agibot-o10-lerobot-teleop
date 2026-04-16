# Copyright (c) 2025, Agibot Co., Ltd.
# OmniHand 2025 SDK is licensed under Mulan PSL v2.

from __future__ import annotations

import importlib
import importlib.util
import sys
import sysconfig
from pathlib import Path


def _load_omnihand_core_module():
    try:
        return importlib.import_module(f"{__name__}.omnihand_2025_core")
    except (ImportError, ModuleNotFoundError) as error:
        expected_names = {
            "omnihand_2025.omnihand_2025_core",
            f"{__name__}.omnihand_2025_core",
        }
        if getattr(error, "name", None) not in expected_names:
            raise

        package_dir = Path(__file__).resolve().parent
        candidate_dirs: list[Path] = []
        seen_dirs: set[Path] = set()

        for entry in [
            sysconfig.get_paths().get("platlib"),
            sysconfig.get_paths().get("purelib"),
            *sys.path,
        ]:
            if not entry:
                continue

            candidate_dir = Path(entry).expanduser().resolve() / "omnihand_2025"
            if candidate_dir == package_dir or candidate_dir in seen_dirs:
                continue
            seen_dirs.add(candidate_dir)
            candidate_dirs.append(candidate_dir)

        module_name = f"{__name__}.omnihand_2025_core"
        last_error: Exception = error
        for candidate_dir in candidate_dirs:
            if not candidate_dir.is_dir():
                continue

            for module_path in sorted(candidate_dir.glob("omnihand_2025_core*.so")):
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None or spec.loader is None:
                    continue

                try:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    return module
                except Exception as candidate_error:  # pragma: no cover
                    last_error = candidate_error
                    sys.modules.pop(module_name, None)

        raise ImportError(
            "Failed to import omnihand_2025_core from the vendored package and "
            "no installed OmniHand wheel could be reused. "
            "Please build/install omnihand_2025_py first."
        ) from last_error


_omnihand_2025_core = _load_omnihand_core_module()

AgibotHandO10 = _omnihand_2025_core.AgibotHandO10
JointMotorErrorReport = _omnihand_2025_core.JointMotorErrorReport
MixCtrl = _omnihand_2025_core.MixCtrl
VendorInfo = _omnihand_2025_core.VendorInfo
Version = _omnihand_2025_core.Version
CommuParams = _omnihand_2025_core.CommuParams
DeviceInfo = _omnihand_2025_core.DeviceInfo

from enum import IntEnum

class EFinger(IntEnum):
    THUMB = 0x01
    INDEX = 0x02
    MIDDLE = 0x03
    RING = 0x04
    LITTLE = 0x05
    PALM = 0x06    
    DORSUM = 0x07  
    UNKNOWN = 0xff

class EControlMode(IntEnum):
    POSITION = 0
    VELOCITY = 1
    TORQUE = 2
    POSITION_TORQUE = 3
    VELOCITY_TORQUE = 4
    POSITION_VELOCITY_TORQUE = 5
    UNKNOWN = 10

class EHandType(IntEnum):
    LEFT = 0
    RIGHT = 1
    UNKNOWN = 10

__all__ = [
    'AgibotHandO10', 
    'EFinger',
    'EHandType',
    'EControlMode',
    'JointMotorErrorReport',
    'MixCtrl',
    'VendorInfo',   
    'Version',       
    'CommuParams',   
    'DeviceInfo'     
]
