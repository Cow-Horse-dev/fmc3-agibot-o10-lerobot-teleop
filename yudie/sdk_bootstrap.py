from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_OMNIHAND_PKG = PROJECT_ROOT / "omnihand_2025"
LOCAL_VENDOR_SDK = PROJECT_ROOT / "vendor_sdk" / "Omnihand-2025-SDK-dev_xuqigui"
LOCAL_USBCANFD_SDK = PROJECT_ROOT / "vendor_sdk" / "usbcanfd_libusb_x64_1.0.13_260316"


def configure_local_sdk_paths():
    """
    Prefer SDK artifacts vendored inside the project over copies installed into
    the conda environment, so the repo is more portable and self-contained.
    """
    project_root = str(PROJECT_ROOT)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault("YUDIE_PROJECT_ROOT", project_root)
    if LOCAL_VENDOR_SDK.exists():
        os.environ.setdefault("YUDIE_OMNIHAND_SDK_ROOT", str(LOCAL_VENDOR_SDK))
    if LOCAL_USBCANFD_SDK.exists():
        os.environ.setdefault("YUDIE_USBCANFD_SDK_ROOT", str(LOCAL_USBCANFD_SDK))


configure_local_sdk_paths()
