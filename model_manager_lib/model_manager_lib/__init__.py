from dataclasses import dataclass, asdict, is_dataclass
import logging as log
import pathlib
from pydantic import BaseModel
import json_logging
from typing import Optional

PRIORITY_VERSION = 0


class PriorityEndpoint(BaseModel):
    framework: str
    name: str
    version: Optional[int]


@dataclass(frozen=True, eq=True)
class RecordKey:
    framework: str
    name: str


@dataclass(order=False, eq=True)
class Record:
    key: RecordKey
    version: int
    is_priority: bool = False


def records_dict_to_jsonable(records_dict) -> dict:
    results = {}

    for key, record_or_records_list in records_dict.items():
        results.setdefault(key.framework, {})
        framework = results[key.framework]
        framework.setdefault(key.name, [])
        name_list = framework[key.name]

        if is_dataclass(record_or_records_list):
            name_list.append(asdict(record_or_records_list))
        else:
            name_list += [asdict(record) for record in record_or_records_list]

    return results


def load_remote_model_directory(remote_model_directory, environment):
    path = pathlib.Path(remote_model_directory).joinpath(environment)
    return str(path).replace("gs:/", "gs://")
