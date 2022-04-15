"""
This module is designed for managing all GCS/Remote communications.
It encapsulates all functionality of interacting with the remote data source
of GCS and determining meaning in the file structure/system there.

The main method of interacting is through RemoteRecords which encapsulate GCS
stage, and the GoogleCloudStorage class which encapsulates how to retrieve and
download models to the local file system.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple, List
from uuid import uuid4 as uuid
import subprocess as sp
import tempfile
import tarfile
import pathlib
import logging as log
import shutil
import fnmatch

from google.cloud import storage

from model_manager_lib import RecordKey, Record, PRIORITY_VERSION


class GcsApi:
    client: storage.Client = None

    @classmethod
    def get_client(cls):
        if not cls.client:
            log.info("connecting to GCS client")
            cls.client = storage.Client()
            log.info("successfully connected to GCS client")
        return cls.client


@dataclass(order=False, eq=True)
class RemoteRecord(Record):
    """Container for passing the GCS state around in a sane way"""

    remote_path: pathlib.Path = None


class GcsDownloadException(Exception):
    def __init__(self, remote, message):
        self.remote = remote
        self.message = message
        super().__init__(message)


def get_current_remote_records(
        gcs_model_directory: str, framework=None
) -> Dict[RecordKey, RemoteRecord]:
    """Retrieves the known current remote records from the given gcs directory string. This function will only
    return records that it deems as "current"

    :param gcs_model_directory: str representing the gcs model directory to check
    :param framework: the framework to search, default=* or any
    :return: Tuple[RemoteRecord]
    """
    gcs_api = GcsApi.get_client()
    bucket, env_path = _get_gcs_bucket_and_remaining_path(gcs_model_directory)
    prefix = _format_gcs_search_prefix(env_path, framework=framework)

    remote_records: List[RemoteRecord] = [
        _blob_to_remote_record(gcs_blob)
        for gcs_blob in gcs_api.list_blobs(bucket, prefix=prefix)
        if _is_valid_model(gcs_blob)
    ]

    results: Dict[RecordKey, RemoteRecord] = dict()
    for remote_record in remote_records:
        if remote_record:
            key = remote_record.key
            results[key] = _record_to_keep(
                results.get(key, remote_record), remote_record
            )

    return results


def copy_remote_record_to_priority_bucket(
        gcs_model_directory: str, framework: str, name: str, version: int
):
    assert framework, "framework needs to be set"
    assert name, "model_name needs to be set"
    assert version, "version needs to be set"
    bucket, env_path = _get_gcs_bucket_and_remaining_path(gcs_model_directory)
    prefix = _format_gcs_search_prefix(
        env_path, framework=framework, model_name=name, version=version
    )
    # add / at the end to make sure it is a full match on the model_name
    prefix = prefix.rstrip("/") + "/"
    log.info(f"copy_remote_record_priority_bucket prefix={prefix}")
    blobs = list(bucket.list_blobs(prefix=prefix))
    for blob in list(blobs):
        name = blob.name
        newname = name.replace(f"/{version}/", f"/0/")
        bucket.copy_blob(blob, bucket, newname)


def remove_priority_bucket(gcs_model_directory: str, framework: str, name: str):
    assert framework, "framework needs to be set"
    assert name, "model name needs to be set"
    bucket, env_path = _get_gcs_bucket_and_remaining_path(gcs_model_directory)
    prefix = _format_gcs_search_prefix(
        env_path, framework=framework, model_name=name, is_priority=True
    )
    # add / at the end to make sure it is a full match on the model_name
    prefix = prefix.rstrip("/") + "/"
    log.info(f"remove_priority_bucket prefix={prefix}")
    blobs = list(bucket.list_blobs(prefix=prefix))
    bucket.delete_blobs(blobs)


def download_remote_record_locally(
        remote_record: RemoteRecord,
        local_directory: str,
        temp_directory: str,
):
    """Downloads the given remote record to the local directory.

    This process will download to a temporary directory then untar the result.

    :param remote_record: the record to download
    :param local_directory: a path to the string to download
    :param temp_directory: a path to the temporary directory to use for downloading
    :return: None
    """
    gcs_api = GcsApi.get_client()
    bucket, blob_path = _get_gcs_bucket_and_remaining_path(remote_record.remote_path)
    blob = bucket.get_blob(str(blob_path))
    temp_directory_path = pathlib.Path(temp_directory).joinpath(uuid().hex)
    temp_directory_path.mkdir(parents=True, exist_ok=True)

    log.info(f"downloading record: {remote_record} to location {local_directory}")
    temp_dir = pathlib.Path(tempfile.mkdtemp(dir=str(temp_directory_path.absolute())))

    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_tar_file = temp_dir.joinpath(f"model.tar.gz")
    temp_model_directory = temp_dir.joinpath("untared_model")
    temp_model_directory.mkdir(parents=True, exist_ok=True)
    log.warning(
        f"downloading record: {remote_record} to temporary location {temp_tar_file} for unpacking"
    )
    blob.download_to_filename(temp_tar_file, client=gcs_api)
    if not temp_tar_file.exists():
        log.error(f"""
        Failed to download model blob from remote for unknown reason!

        remote_record:
        {remote_record}

        temp_file:
        {temp_tar_file}
        
        temp_model_directory:
        {temp_model_directory}

        local_directory:
        {local_directory}
        """)
        raise GcsDownloadException(remote=remote_record, message=f'{remote_record} failed to download')

    log.debug(f"extracting tarfile at {temp_tar_file} to {temp_model_directory}")
    with tarfile.open(temp_tar_file, mode="r") as tar:
        for member in tar.getmembers():
            if _tar_member_is_valid(member):
                tar.extract(member, temp_model_directory.absolute())
    try:
        local_path = pathlib.Path(local_directory)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.exists():
            log.error(
                f"Attempt to move directory from {temp_model_directory} to {local_path} "
                "but found race condition! Cowardly ignoring"
            )
        else:
            sp.run(["mv", temp_model_directory.absolute(), local_path.absolute()])
    except Exception as err:
        log.exception(err)
        raise err
    finally:
        shutil.rmtree(temp_directory_path.absolute(), ignore_errors=True)


def remove_model_gcs_bucket(gcs_model_directory: str, framework: str, model_name: str):
    assert framework, "framework needs to be set"
    assert model_name, "model_name needs to be set"
    bucket, env_path = _get_gcs_bucket_and_remaining_path(gcs_model_directory)
    prefix = _format_gcs_search_prefix(
        env_path, framework=framework, model_name=model_name
    )
    # add / at the end to make sure it is a full match on the model_name
    prefix = prefix.rstrip("/") + "/"
    log.info(f"remove_model_gcs_bucket prefix={prefix}")
    blobs = list(bucket.list_blobs(prefix=prefix))
    bucket.delete_blobs(blobs)
    return


def _is_valid_model(blob: storage.Blob) -> bool:
    """Valid models are those that can be handled
    by our system and should be processed

    :param blob: representing the record to consider
    :return: bool
    """
    return blob.name.endswith("model.tar.gz")


def _blob_to_remote_record(blob: storage.Blob) -> RemoteRecord:
    """Translates the given blob into a RemoteRecord class for
    management and processing. This allows us to pass remote state
    in a more sane way

    :param blob: representing the remote data
    :return: RemoteRecord
    """
    blob_path = pathlib.Path(blob.name)
    if len(blob_path.parts) <= 4:
        log.error(
            "failed to process blob! Its format was unexpected! "
            f"skipping blob at {blob.name}"
        )
    else:
        *_, framework, name, version, _ = blob_path.parts
        is_priority = bool(version.lower() == str(PRIORITY_VERSION))
        return RemoteRecord(
            key=RecordKey(
                framework=framework,
                name=name,
            ),
            version=int(version) if not is_priority else 0,
            is_priority=is_priority,
            remote_path=f"gs://{blob.bucket.name}/{blob.name}",
        )


def _record_to_keep(record1: RemoteRecord, record2: RemoteRecord) -> RemoteRecord:
    """Given two records this function is used to determine which
    one should be considered the "current" record.

    Generally that means by using the version, but priority buckets
    kind of throw that all over the place!

    :param record1: the first record, considered the original/default
    :param record2: the second receord, considered the challenger
    :return: RemoteRecord
    """
    if record1.is_priority:
        return record1

    if record2.is_priority:
        return record2

    if record2.version > record1.version:
        return record2

    return record1


def _tar_member_is_valid(member: tarfile.TarInfo) -> bool:
    """Untaring files is complicated stuff. We need to ensure that we
    manage the tar correctly. What I mean by this is that we don't ever
    want to untar something into a root directory or anywhere it is not
    supposed to be.

    This method exists to filter out the tar members so that way we don't
    have a security issue.

    This function tells us if the given tar is valid in our system

    :param member: member to consider
    :return: bool
    """
    member_path = pathlib.Path(member.name)
    if member_path.is_absolute():
        log.error(
            f"attempted to unpack a tar with an absolute path!! Only relative paths are supported"
        )
        return False
    if ".." in member_path.parts:
        log.error(
            f"attempt to unpack a tar with a reference reaching out of the tar!! Only sub paths are supported!"
        )
        return False

    if member.isfile():
        # check here if file is regular file and not executable to be safe!
        # we don't want anyone adding in sockets or anything else weird here!
        ...
    return True


def _get_gcs_bucket_and_remaining_path(
        gcs_directory: str,
) -> Tuple[storage.Bucket, pathlib.Path]:
    assert gcs_directory.startswith(
        "gs://"
    ), f"""
    Expected valid gcs format for given GCS model directory!

    expected:
    stats with 'gs://'

    actual:
    {gcs_directory}
    """
    gcs_path = pathlib.Path(gcs_directory)
    assert (
            len(gcs_path.parts) >= 3
    ), f"""
    Expected gcs bucket path given to have at least three available
    parts. Expected drive/bucket/environment...

    protocol: gs://
    bucket: gcs bucket name
    environment: some set of paths associated with the environment

    expected length:
     >= 3

    found length:
    {len(gcs_path.parts)}

    gcs parts:
    {gcs_path.parts}
    """
    _, bucket, *environment_parts = gcs_path.parts
    assert (
            len(environment_parts) > 0
    ), f"""
    Environment path of the GCS directory must have atleast one valid value in it!

    Found empty or missing environment parts:

    environment parts:
    {environment_parts}
    """
    gcs_api = GcsApi.get_client()
    bucket_str: str = bucket
    environment_path: pathlib.Path = pathlib.Path("/".join(environment_parts))
    bucket: storage.Bucket = gcs_api.get_bucket(bucket_str)
    return bucket, environment_path


def _format_gcs_search_prefix(
        env_path: pathlib.Path,
        framework=None,
        model_name=None,
        version=None,
        is_priority=False,
) -> List[str]:
    if framework:
        env_path = env_path.joinpath(framework)
    if model_name:
        assert framework, "framework needs to be set if model_name is set"
        env_path = env_path.joinpath(model_name)

    if is_priority:
        assert framework, "framework needs to be set if is_priority is set"
        assert model_name, "model_name needs to be set if is_priority is set"
        env_path = env_path.joinpath(str(PRIORITY_VERSION))
    elif version:
        assert framework, "framework needs to be set if version is set"
        assert model_name, "model_name needs to be set if version is set"
        env_path = env_path.joinpath(str(version))

    return str(env_path)
