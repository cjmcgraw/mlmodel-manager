from uuid import uuid4 as uuid
from unittest import mock
import random
from google.cloud import storage

import tests

from model_manager_lib import gcs


def make_blob(name):
    random_bucket = uuid().hex
    fake_bucket = mock.MagicMock()
    fake_bucket.name = random_bucket
    return storage.Blob(
        name=name,
        bucket=fake_bucket
    )


@mock.patch("model_manager_lib.gcs.GcsApi.client")
def test_known_remote_records_with_no_records(gcs_client: mock.Mock):
    gcs_client.list_blobs.return_value = []
    records = gcs.get_current_remote_records("gs://some/bucket")
    assert len(records) == 0


@mock.patch("model_manager_lib.gcs.GcsApi.client")
def test_known_remote_records_skips_invalid_records(gcs_client: mock.Mock):
    records = {
        "missing version": "some_env/name/model.tar.gz",
        "not a tar.gz": "some_env/framework/name/123/model",
        "not a gz": "some_env/framework/name/123/model.tar",
        "empty string": "",
        "only valid record": "some_env/framework/name/123456789/model.tar.gz"
    }
    gcs_client.list_blobs.return_value = [make_blob(p) for p in records.values()]
    records = gcs.get_current_remote_records("gs://some/bucket")
    expected_key = gcs.RecordKey(
        framework='framework',
        name='name'
    )
    assert expected_key in records
    assert len(records) == 1
    assert records[expected_key].version == 123456789


@mock.patch("model_manager_lib.gcs.GcsApi.client")
def test_known_remote_records_with_many_records(gcs_client: mock.Mock):
    frameworks = tests.generate_random_strings(n=10)
    names = tests.generate_random_strings(n=10)
    old_versions = tests.generate_versions(n=10, min_val=1, max_val=100)

    non_current_version_remote_data = [
        "/".join(["env_stuff", framework, name, version, "model.tar.gz"])
        for framework in frameworks
        for name in names
        for version in old_versions
    ]

    current_version_remote_data = [
        "/".join(["env_stuff", framework, name, str(101), "model.tar.gz"])
        for framework in frameworks
        for name in names
    ]

    remote_blobs = [
        make_blob(p)
        for p in non_current_version_remote_data + current_version_remote_data
    ]

    random.shuffle(remote_blobs)
    gcs_client.list_blobs.return_value = remote_blobs
    records = gcs.get_current_remote_records("gs://some/bucket")
    assert len(records) == (len(frameworks) * len(names))
    versions = {r.version for r in records.values()}
    assert versions == {101}

