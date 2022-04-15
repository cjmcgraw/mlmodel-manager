import pytest
import tests
from tests import remote_model_puller_tests as remote_tests
import pathy

@pytest.mark.usefixtures("clear_local", "clear_remote")
def test_remove_non_existing_model():
    remote_tests.send_remove_model_request("tensorflow", "model_to_remove")

@pytest.mark.usefixtures("clear_local", "clear_remote")
def test_remove_existing_model():
    framework = "tensorflow"
    model_name = "model_to_remove"
    test_records = tests.generate_random_test_records(5, framework=framework, name=model_name)
    tar_records = tests.make_remote_records(test_records)
    remote_tests.manually_trigger_remote_pull()
    local_state = remote_tests.get_all_local_state()
    assert(local_state[framework][model_name])
    remote_tests.send_remove_model_request(framework, model_name)
    for model in local_state[framework][model_name]:
        assert(not pathy.Pathy(model["full_model_path"]).exists())


