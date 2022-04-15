import pytest
import tests
from tests import master_tests


@pytest.mark.usefixtures("clear_remote")
def test_priority_non_existing():
    master_tests.send_set_priority_request("tensorflow", "not existing", 1)


@pytest.mark.usefixtures("clear_remote", "clear_tfserving_config")
def test_set_unset_priority():
    test_records = tests.generate_random_test_records(
        3, framework="tensorflow", name="prioritytest", versions=[1, 2, 3]
    )
    testing_tar_files = tests.make_remote_records(test_records)
    master_tests.send_set_priority_request("tensorflow", "prioritytest", 1)
    for testing_file in testing_tar_files:
        if testing_file.test_record.version == 1:
            assert testing_file.remote_path.exists()
            priority_record = testing_file.test_record
            priority_record.is_priority = True
            assert tests.expected_remote_location(
                priority_record
            ).exists(), "priority bucket should exist after set call"
            master_tests.send_delete_priority_request("tensorflow", "prioritytest")
            assert not tests.expected_remote_location(
                priority_record
            ).exists(), "priority bucket should not exist after set call"
