import requests
import logging
import pathlib
import pytest
import random
import grpc
import time
import os
import tests
from fcache.cache import FileCache


@pytest.fixture
def clear_node_registry():
    def clear_files():
        registered_config_manager_cache = FileCache(
            ".registered_config_manager_cache", flag="cs"
        )
        registered_remote_model_puller_cache = FileCache(
            ".registered_remote_model_puller_cache", flag="cs"
        )
        registered_config_manager_cache.clear()
        registered_remote_model_puller_cache.clear()

    clear_files()
    yield
    clear_files()


def send_delete_request(framework, model_name, host, port=8000):
    r = requests.delete(
        f"http://{host}:{port}/models/{framework}/{model_name}", timeout=10
    )
    return tests.check_response(r)


def send_register_request(node_type: str, target: str, host="master", port=8000):
    payload = {"node_type": node_type, "target": target}
    r = requests.post(f"http://{host}:{port}/register", json=payload, timeout=10)
    return tests.check_response(r)


def send_delete_register_request(node_type: str, target: str, host="master", port=8000):
    payload = {"node_type": node_type, "target": target}
    r = requests.delete(f"http://{host}:{port}/register", json=payload, timeout=10)
    return tests.check_response(r)


def send_cluster_state_request(host="master", port=8000):
    r = requests.get(f"http://{host}:{port}/report_cluster_state", timeout=10)
    return tests.check_response(r)


def send_set_priority_request(
    framework: str, model_name: str, version: int, host="master", port=8000
):
    payload = {"framework": framework, "name": model_name, "version": version}
    r = requests.post(f"http://{host}:{port}/priority", json=payload, timeout=10)
    return tests.check_response(r)


def send_delete_priority_request(
    framework: str, model_name: str, host="master", port=8000
):
    payload = {"framework": framework, "name": model_name}
    r = requests.delete(f"http://{host}:{port}/priority", json=payload, timeout=10)
    return tests.check_response(r)


def send_remove_model_request(
    frame_work: str, model_name: str, host="master", port=8000
):
    r = requests.delete(
        f"http://{host}:{port}/models/{frame_work}/{model_name}", timeout=10
    )
    return tests.check_response(r)
