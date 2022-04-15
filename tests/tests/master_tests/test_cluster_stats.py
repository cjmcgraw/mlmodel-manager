import random
import pytest

import tests
from tests import config_manager_tests
from tests import master_tests


@pytest.mark.usefixtures("clear_node_registry", "clear_tfserving_config", "clear_local")
def test_single_model_single_version_is_served():
    # build a model and have it being loaded up
    multiplication_factor = random.random()
    test_record = tests.generate_random_test_record(framework="tensorflow")
    tests.build_local_model(test_record, multiplication_factor, is_tar=False)
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    # send register node on behalf of config_manager and remote_model_puller
    master_tests.send_register_request("config_manager", "config_manager:8002")
    master_tests.send_register_request(
        "remote_model_puller", "remote_model_puller:8001"
    )

    # get cluster_stats
    response = master_tests.send_cluster_state_request().json()
    assert "remote_model_puller" in response
    assert "config_manager" in response
    assert "remote_model_puller:8001" in response["remote_model_puller"]
    assert "config_manager:8002" in response["config_manager"]
    assert (
        "local_filesystem"
        in response["remote_model_puller"]["remote_model_puller:8001"]
    )
    assert "local_filesystem" in response["config_manager"]["config_manager:8002"]
    assert "serving_all" in response["config_manager"]["config_manager:8002"]
