from typing import Dict, List
import requests
import logging
import pathlib
import pytest
import random
import grpc
import time
import os


os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

log = logging.getLogger(__file__)

import tensorflow as tf
from google.protobuf import wrappers_pb2
from tensorflow_serving.apis import (
    prediction_service_pb2,
    prediction_service_pb2_grpc,
    predict_pb2,
    model_pb2,
)

import tests

TENSORFLOW_SERVING_CONFIG_FILE = pathlib.Path(
    os.environ["TENSORFLOW_SERVING_CONFIG_FILE"]
)
TENSORFLOW_SERVING_GRPC_TARGET = os.environ["TENSORFLOW_SERVING_GRPC_TARGET"]


@pytest.fixture
def clear_tfserving_config():
    def clear_config():
        with open(TENSORFLOW_SERVING_CONFIG_FILE, "w") as f:
            f.write("model_config_list {\n\n}\n")
            f.flush()

    clear_config()
    yield
    clear_config()


def assert_prediction_matches_expected(test_record: tests.TestRecord, factor: float):
    x = random.random()
    y = None

    next_sleep_time = 0.01
    maximum_sleep_time = 0.0
    while not y and next_sleep_time <= 10:
        try:
            y = TFServingClient.predict(test_record, x=x)
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.NOT_FOUND:
                log.error(
                    f"Failed to find model. Beginning sleep for {next_sleep_time} seconds"
                )
                time.sleep(next_sleep_time)
                next_sleep_time += random.random() / 6.0
                maximum_sleep_time += next_sleep_time

                if maximum_sleep_time > 30:
                    raise err

    assert (
        factor * x == y
    ), f"""
    Failed to load record correctly for unknown reason.

    Setting up the initial model versions before remove, and it failed to
    load the model version associated with the record:

    test_record:
    {test_record}

    expected:
    {factor * x}

    actual:
    {y}
    """


class TFServingClient:
    channel: grpc.Channel = None
    prediction_stub: prediction_service_pb2_grpc.PredictionServiceStub = None

    @classmethod
    def predict(cls, test_record: tests.TestRecord, x: float):
        if not cls.prediction_stub:
            channel = grpc.insecure_channel(
                TENSORFLOW_SERVING_GRPC_TARGET, [("wait_for_ready", True)]
            )
            cls.prediction_stub = prediction_service_pb2_grpc.PredictionServiceStub(
                channel
            )
        request = predict_pb2.PredictRequest(
            model_spec=model_pb2.ModelSpec(
                name=test_record.name,
                version=wrappers_pb2.Int64Value(
                    value=test_record.version if not test_record.is_priority else 0
                ),
            ),
            inputs={
                "x": tf.make_tensor_proto(
                    values=x,
                    shape=[
                        1,
                    ],
                    dtype=tf.float64,
                )
            },
        )
        response = cls.prediction_stub.Predict(
            request,
            wait_for_ready=True,
            timeout=30,
            compression=grpc.Compression.Gzip,
        )
        results = response.outputs.get("y").double_val
        assert (
            len(results) > 0
        ), f"""
        Unexpected empty/missing results from tfserving request!
        
        response:
        {response}
        
        found:
        {results}
        """
        return results[0]


def get_config_manager_config():
    r = requests.get("http://config_manager:8002/tensorflow_serving/config", timeout=10)
    tests.check_response(r)
    return r.text()


def get_config_manager_tfserving_models():
    r = requests.get("http://config_manager:8002/tensorflow_serving/all", timeout=10)
    tests.check_response(r)
    return r.json()


def get_config_manager_all_local_models():
    r = requests.get("http://config_manager:8002/local/all", timeout=10)
    tests.check_response(r)
    return r.json()


def get_config_manager_current_local_models():
    r = requests.get("http://config_manager:8002/local/current", timeout=10)
    tests.check_response(r)
    return r.json()


def config_manager_update_tfserving_config_from_local_filesystem():
    r = requests.post(
        "http://config_manager:8002/update_tfserving_config_from_local_filesystem",
        timeout=10,
    )
    tests.check_response(r)
    return r.text


def config_manager_remove_out_of_date_local_models():
    r = requests.post(
        "http://config_manager:8002/clear_out_of_date_local_models", timeout=10
    )
    tests.check_response(r)
    return r.text


def config_manager_send_remove_model_request(frame_work: str, model_name: str):
    response = requests.delete(
        f"http://config_manager:8002/models/{frame_work}/{model_name}", timeout=10
    )
    response.raise_for_status()
    return response.text


def send_delete_priority_request(framework: str, model_name: str):
    payload = {"framework": framework, "name": model_name}
    r = requests.delete(
        f"http://config_manager:8002/priority", json=payload, timeout=10
    )
    return tests.check_response(r)
