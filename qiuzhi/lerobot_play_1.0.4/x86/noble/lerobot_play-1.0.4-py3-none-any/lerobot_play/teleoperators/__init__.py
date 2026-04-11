from lerobot_play._compat import preload_lerobot_processor


preload_lerobot_processor()

from .utils import make_teleoperator_from_config


__all__ = ["make_teleoperator_from_config"]
