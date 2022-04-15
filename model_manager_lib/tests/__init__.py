from uuid import uuid4 as uuid
import pathlib
import random

from model_manager_lib import RecordKey, Record
TEST_ASSETS_DIRECTORY = "./tests/.assets"


def generate_random_strings(n=10):
    return [uuid().hex for _ in range(n)]


def generate_versions(n=10, min_val=1, max_val=1e6):
    sorted_versions = sorted([random.randint(min_val, max_val) for _ in range(n)], reverse=True)
    return [str(x) for x in sorted_versions]


def generate_random_path(parts=5) -> str:
    p = pathlib.Path(TEST_ASSETS_DIRECTORY)
    for _ in range(parts):
        p = p.joinpath(uuid().hex)
    return str(p.absolute())


def generate_random_record_key(framework: str = None, name: str = None) -> RecordKey:
    return RecordKey(
        framework=framework or uuid().hex,
        name=name or uuid().hex,
    )


def generate_random_record(version: str = None, **kwargs) -> Record:
    return Record(
        key=generate_random_record_key(**kwargs),
        version=version or random.randint(1, 1e6)
    )
