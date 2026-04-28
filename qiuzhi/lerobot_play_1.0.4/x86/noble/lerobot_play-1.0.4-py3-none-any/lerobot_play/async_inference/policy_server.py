import logging
import pickle  # nosec
import time
from concurrent import futures
from dataclasses import asdict
from pprint import pformat

import draccus
import grpc

from lerobot.async_inference.configs import PolicyServerConfig
from lerobot.async_inference.constants import SUPPORTED_POLICIES
from lerobot.async_inference.helpers import RemotePolicyConfig
from lerobot.async_inference.policy_server import PolicyServer as BasePolicyServer
from lerobot.async_inference.policy_server import make_pre_post_processors
from lerobot.transport import services_pb2, services_pb2_grpc


def _load_policy(policy_type: str, model_path: str, device: str):
    from lerobot_play.infer import _load_policy as load_policy

    return load_policy(policy_type, model_path, device)


class PolicyServer(BasePolicyServer):
    def SendPolicyInstructions(self, request, context):  # noqa: N802
        """Receive policy instructions and load policies with local PEFT support."""
        if not self.running:
            self.logger.warning("Server is not running. Ignoring policy instructions.")
            return services_pb2.Empty()

        client_id = context.peer()
        policy_specs = pickle.loads(request.data)  # nosec

        if not isinstance(policy_specs, RemotePolicyConfig):
            raise TypeError(
                f"Policy specs must be a RemotePolicyConfig. Got {type(policy_specs)}"
            )

        if policy_specs.policy_type not in SUPPORTED_POLICIES:
            raise ValueError(
                f"Policy type {policy_specs.policy_type} not supported. "
                f"Supported policies: {SUPPORTED_POLICIES}"
            )

        self.logger.info(
            f"Receiving policy instructions from {client_id} | "
            f"Policy type: {policy_specs.policy_type} | "
            f"Pretrained name or path: {policy_specs.pretrained_name_or_path} | "
            f"Actions per chunk: {policy_specs.actions_per_chunk} | "
            f"Device: {policy_specs.device}"
        )

        self.device = policy_specs.device
        self.policy_type = policy_specs.policy_type
        self.lerobot_features = policy_specs.lerobot_features
        self.actions_per_chunk = policy_specs.actions_per_chunk
        self.observation_rename_map = dict(policy_specs.rename_map)

        start = time.perf_counter()
        self.policy = _load_policy(
            self.policy_type,
            policy_specs.pretrained_name_or_path,
            self.device,
        )

        device_override = {"device": self.device}
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            self.policy.config,
            pretrained_path=policy_specs.pretrained_name_or_path,
            preprocessor_overrides={
                "device_processor": device_override,
                "rename_observations_processor": {"rename_map": policy_specs.rename_map},
            },
            postprocessor_overrides={"device_processor": device_override},
        )

        end = time.perf_counter()
        self.logger.info(
            f"Time taken to put policy on {self.device}: {end - start:.4f} seconds"
        )

        return services_pb2.Empty()


@draccus.wrap()
def serve(cfg: PolicyServerConfig):
    logging.info(pformat(asdict(cfg)))

    policy_server = PolicyServer(cfg)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    services_pb2_grpc.add_AsyncInferenceServicer_to_server(policy_server, server)
    server.add_insecure_port(f"{cfg.host}:{cfg.port}")

    policy_server.logger.info(f"PolicyServer started on {cfg.host}:{cfg.port}")
    server.start()
    server.wait_for_termination()

    policy_server.logger.info("Server terminated")


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
