import pytest

import tests
from tests import master_tests


@pytest.mark.usefixtures("clear_remote")
def test_remove_non_existing():
    master_tests.send_remove_model_request("tensorflow", "removetest")


@pytest.mark.usefixtures("clear_remote")
def test_remove_from_remote():
    test_records = tests.generate_random_test_records(
        5, framework="tensorflow", name="removetest"
    )
    testing_tar_files = tests.make_remote_records(test_records)
    master_tests.send_remove_model_request("tensorflow", "removetest")
    for testing_file in testing_tar_files:
        assert not testing_file.remote_path.exists()
