import pytest
import tests
import time
import pathlib
import tempfile
from tests import master_tests
from tests import remote_model_puller_tests as remote_tests
from tests import config_manager_tests
from tests import PRIORITY_VERSION


@pytest.mark.usefixtures("clear_remote", "clear_tfserving_config", "clear_local")
def test_priority():
    framework = "tensorflow"
    model_name = "prioritytest"
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    test_records = tests.generate_random_test_records(
        3, framework=framework, name=model_name, versions=[1, 2, 3]
    )

    for test_record in test_records:
        tests.build_local_model(
            test_record=test_record,
            multiplication_factor=test_record.version,
            output_dir=temp_dir,
            is_tar=True,
        )

    tests.push_local_model_directory_to_remote(temp_dir)

    remote_tests.manually_trigger_remote_pull()
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()
    time.sleep(5)
    current_tfserving_models = (
        config_manager_tests.get_config_manager_tfserving_models()
    )
    assert framework in current_tfserving_models, current_tfserving_models
    assert model_name in current_tfserving_models[framework]
    assert (
        len(current_tfserving_models[framework][model_name])  >= 1
    ), current_tfserving_models
    # there might be multiple entries showing up with different states
    # but one should have status of available
    model_status = [ model["status"] for model in current_tfserving_models[framework][model_name] ]
    assert tests.MODEL_STATE.AVAILABLE in model_status, f"some model should have available state {model_status}"

    versions = [ model["version"] for model in current_tfserving_models[framework][model_name] ]
    assert 3 in versions, f"3 should be in model version list {versions}"

    current_local = remote_tests.get_current_local_state()
    assert (
        current_local[framework][model_name][0]["version"] == 3
    ), "current local has version 3"

    master_tests.send_set_priority_request("tensorflow", model_name, 1)
    remote_tests.manually_trigger_remote_pull()
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()
    time.sleep(5)
    current_local = remote_tests.get_current_local_state()
    assert current_local[framework][model_name][0]["version"] == PRIORITY_VERSION
    current_tfserving_models = (
        config_manager_tests.get_config_manager_tfserving_models()
    )
    versionlist = [
        record["version"] for record in current_tfserving_models[framework][model_name]
    ]
    assert PRIORITY_VERSION in versionlist

    master_tests.send_delete_priority_request("tensorflow", model_name)
    time.sleep(5)
    current_local = remote_tests.get_current_local_state()
    assert current_local[framework][model_name][0]["version"] == 3
    current_tfserving_models = (
        config_manager_tests.get_config_manager_tfserving_models()
    )
    for record in current_tfserving_models[framework][model_name]:
        if record["version"] == PRIORITY_VERSION:
            assert record["status"] != tests.MODEL_STATE.AVAILABLE
