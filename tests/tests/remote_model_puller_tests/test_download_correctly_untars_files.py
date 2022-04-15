import pytest

import tests
from tests import remote_model_puller_tests as remote_tests


@pytest.mark.usefixtures("clear_remote", "clear_local")
@pytest.mark.parametrize(
    argnames=["num_of_models"],
    argvalues=[[_] for _ in range(5, 25, 5)],
)
def test_many_models_is_correctly_untared(num_of_models):
    test_records = tests.generate_random_test_records(num_of_models)
    tar_records = tests.make_remote_records(test_records)

    remote_tests.manually_trigger_remote_pull()
    for tar_record in tar_records:
        test_record = tar_record.test_record
        local_path = tests.expected_local_location(test_record)
        tar_record.assert_unpacked_tar_matches(local_path)
