from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple
from glob import glob
import logging as log
import pathlib
import shutil

from dataclasses_json import dataclass_json

from . import RecordKey, Record, PRIORITY_VERSION


@dataclass_json()
@dataclass(order=False)
class LocalRecord(Record):
    full_model_path: pathlib.Path = None
    local_model_path: pathlib.Path = None


LocalRecordDict = Dict[RecordKey, Tuple[LocalRecord, ...]]


def get_known_local_models(
    model_directory: str, framework: str = "*", name: str = "*"
) -> LocalRecordDict:
    model_search_path = (
        pathlib.Path(model_directory).joinpath(framework).joinpath(name).absolute()
    )

    results = defaultdict(list)
    for model_path_str in glob(f"{model_search_path}/*"):
        model_path = pathlib.Path(model_path_str)
        local_record = _path_to_local_record(model_path)
        if local_record:
            results[local_record.key].append(local_record)

    return _sort_lists_in_dictionary(results)


def get_current_local_models(
    model_directory: str, framework: str = "*", name: str = "*"
) -> Dict[RecordKey, LocalRecord]:
    return {
        record_key: next(iter(records))
        for record_key, records in get_known_local_models(
            model_directory=model_directory, framework=framework, name=name
        ).items()
        if len(records) > 0
    }


def get_expected_local_path(model_directory: str, record: Record) -> str:
    local_path = (
        pathlib.Path(model_directory)
        .joinpath(record.key.framework)
        .joinpath(record.key.name)
    )

    if record.is_priority:
        local_path = local_path.joinpath(str(PRIORITY_VERSION))
    else:
        local_path = local_path.joinpath(str(record.version))

    return str(local_path.absolute())


def remove_record(record: LocalRecord):
    model_path = str(record.full_model_path.absolute())
    log.warning(f"permanently deleting model at {model_path}")
    shutil.rmtree(model_path, ignore_errors=True)


def get_all_local_records_bykey(
    local_model_directory: str, key: RecordKey
) -> LocalRecordDict:
    all_local_records_lookup = get_known_local_models(local_model_directory)
    return {key: all_local_records_lookup.get(key, [])}


def delete_local_records_bykey(local_model_directory: str, key: RecordKey):
    records_to_delete = get_all_local_records_bykey(local_model_directory, key)

    log.info(f"record_to_delete {records_to_delete}")
    if key in records_to_delete:
        for record in records_to_delete[key]:
            remove_record(record)
    return


def delete_local_priority_record(local_model_directory: str, key: RecordKey):
    records = get_all_local_records_bykey(local_model_directory, key)

    for record in records[key]:
        if record.version == PRIORITY_VERSION:
            remove_record(record)


def _sort_lists_in_dictionary(d: LocalRecordDict) -> LocalRecordDict:
    def sort(records):
        return tuple(
            sorted(records, key=lambda x: (x.is_priority, x.version), reverse=True)
        )

    return {record_key: sort(records) for record_key, records in d.items()}


def _path_to_local_record(model_path: pathlib.Path) -> LocalRecord:
    if len(model_path.parts) < 3:
        log.error(
            "failed to find valid local model path! Missing expected parts "
            f"model_path={model_path} expected parts >= 3"
        )
        return
    *_, framework, name, version = model_path.parts
    is_priority = bool(version.lower() == str(PRIORITY_VERSION))
    return LocalRecord(
        key=RecordKey(
            framework=framework,
            name=name,
        ),
        version=int(version) if not is_priority else 0,
        is_priority=is_priority,
        full_model_path=model_path.absolute(),
        local_model_path=model_path.parent.absolute(),
    )
