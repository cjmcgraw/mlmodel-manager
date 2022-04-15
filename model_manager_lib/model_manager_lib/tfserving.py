from typing import Tuple, Set, Dict, List
from dataclasses import dataclass
from zlib import crc32
from enum import Enum
import logging as log

import pathlib
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Set, Dict, List
from zlib import crc32

from dataclasses_json import dataclass_json

import tensorflow as tf
from dataclasses_json import dataclass_json

tf.config.threading.set_inter_op_parallelism_threads(0)
tf.config.threading.set_intra_op_parallelism_threads(0)

from tensorflow_serving.apis import model_pb2
from tensorflow_serving.apis import model_service_pb2_grpc
from tensorflow_serving.apis import get_model_status_pb2
from tensorflow_serving.config.model_server_config_pb2 import (
    ModelServerConfig,
    ModelConfig,
)

# this try/catch is really unfortunately but sometimes the file_system_storage_path_source_pb2 is in a different
# location than you expect. So we try both locations and move on with our life.
try:
    from tensorflow_serving.sources.storage_path import (
        file_system_storage_path_source_pb2 as filesystem_pb2,
    )
except ImportError as err:
    from tensorflow_serving.config import (
        file_system_storage_path_source_pb2 as filesystem_pb2,
    )

import google.protobuf.text_format as pbtxt
import grpc

from . import Record, RecordKey, PRIORITY_VERSION


@dataclass()
class TensorflowServingConfig:
    """Represents the TensorflowServing config. This class wraps all functionality
    for

    The expected input of proto is the rawtext written from tensorflow serving.
    This is accessible but contains no autocompletion. This is frustrating and
    means that you'll have to reference documentation to know how to access
    this object.

    Here is a brief example of the structure of the ModelServerConfig:

    TensorflowServingConfig(proto=model_config_list {
          config {
            name: "carls_test0"
            base_path: "/models/carls_test0/"
            model_platform: "tensorflow"
          }
        }
    )

    For more documentation you can find it at:
    https://github.com/tensorflow/serving/blob/master/tensorflow_serving/config/model_server_config.proto
    """

    original_path: pathlib.Path
    original_proto_crc_hash: int
    proto: ModelServerConfig
    known_model_names: Set[str] = None
    model_config_lookup: Dict[str, ModelConfig] = None

    def __post_init__(self):
        self.known_model_names = {
            model_config.name
            for model_config in self._get_model_configs()
            if model_config.name
        }

        self.model_config_lookup = {
            config.name: config for config in self._get_model_configs()
        }

    def _get_model_configs(self) -> List[ModelConfig]:
        return self.proto.model_config_list.config

    def _add(self, model_config: ModelConfig):
        self.proto.model_config_list.config.append(model_config)

    def _remove_name(self, name: str):
        log.info(f"remove  model name {name}")
        if name in self.model_config_lookup:
            model_config = self.model_config_lookup[name]
            log.info(f"remove model config {model_config}")
            self._remove(model_config)

    def _remove(self, model_config: ModelConfig):
        self.proto.model_config_list.config.remove(model_config)


def load_config(tensorflow_serving_config_file: str) -> TensorflowServingConfig:
    config_path = pathlib.Path(tensorflow_serving_config_file)
    with open(config_path, "r") as f:
        data = f.read()
        proto_crc_hash = crc32(data.encode("utf-8"))
        if proto_crc_hash != 0:
            config_proto = pbtxt.Parse(data, ModelServerConfig())
        else:
            config_proto = ModelServerConfig()

    return TensorflowServingConfig(
        original_path=config_path,
        original_proto_crc_hash=proto_crc_hash,
        proto=config_proto,
    )


def save_config(config: TensorflowServingConfig) -> TensorflowServingConfig:
    config_pbtxt = pbtxt.MessageToString(config.proto)
    if len(config_pbtxt) == 0:
        config_pbtxt = "model_config_list {\n\n}\n"
    config_path = config.original_path
    log.info(f"Saving config {config_pbtxt} to path {config_path}")

    with open(config_path, "r+") as f:
        data = f.read()
        current_proto_crc_hash = crc32(data.encode("utf-8"))

        if config.original_proto_crc_hash != current_proto_crc_hash:
            log.error(
                f"attempted to save model config! But it changed underneath us unexpectedly!"
            )
            raise ValueError(
                f"""
                Attempted to save model config! But it changed underneath us unexpectedly!

                original_crc:
                {config.original_proto_crc_hash}
                
                current_crc:
                {current_proto_crc_hash}
                
                data from file: 
                {data}

                current_config:
                {config}
            """
            )
        f.seek(0)
        f.truncate()
        f.write(config_pbtxt)

    return load_config(str(config_path))


def add_model(
    tensorflow_serving_config: TensorflowServingConfig, record: Record, local_path: str
) -> TensorflowServingConfig:
    assert (
        record.key.framework.lower() == "tensorflow"
    ), "cannot add model to tfserving if framework is not tensorflow!"
    if record.key.name in tensorflow_serving_config.known_model_names:
        tensorflow_serving_config._remove_name(record.key.name)

    if not record.is_priority:
        model_config = ModelConfig(
            name=record.key.name,
            base_path=str(local_path),
            model_platform="tensorflow",
            model_version_policy=filesystem_pb2.FileSystemStoragePathSourceConfig.ServableVersionPolicy(
                latest=filesystem_pb2.FileSystemStoragePathSourceConfig.ServableVersionPolicy.Latest(
                    num_versions=1
                )
            ),
        )
    else:
        model_config = ModelConfig(
            name=record.key.name,
            base_path=str(local_path),
            model_platform="tensorflow",
            model_version_policy=filesystem_pb2.FileSystemStoragePathSourceConfig.ServableVersionPolicy(
                specific=filesystem_pb2.FileSystemStoragePathSourceConfig.ServableVersionPolicy.Specific(
                    versions=[PRIORITY_VERSION]
                )
            ),
        )
    tensorflow_serving_config._add(model_config)
    log.warning(
        f"Adding a new model configuration: record={record} config={model_config}"
    )
    return save_config(tensorflow_serving_config)


def remove_model(
    tensorflow_serving_config: TensorflowServingConfig, record_key: RecordKey
) -> TensorflowServingConfig:
    if record_key.name not in tensorflow_serving_config.model_config_lookup:
        log.error(f"Cannot remove a model if it doesn't exit! name={record_key.name}")
        raise ValueError(
            f"""
        Attempting to remove an unknown model! Failed to find the name in
        the know models!

        name:
        {record_key.name}

        current config:
        {tensorflow_serving_config}
        """
        )

    config = tensorflow_serving_config.model_config_lookup[record_key.name]
    tensorflow_serving_config._remove(config)
    return save_config(tensorflow_serving_config)


MODEL_STATE = get_model_status_pb2.ModelVersionStatus.State


class TensorflowServingModelStatus(Enum):
    UNKNOWN = MODEL_STATE.UNKNOWN
    START = MODEL_STATE.START
    LOADING = MODEL_STATE.LOADING
    AVAILABLE = MODEL_STATE.AVAILABLE
    UNLOADING = MODEL_STATE.UNLOADING
    END = MODEL_STATE.END

    def __repr__(self):
        return self.name


@dataclass_json()
@dataclass()
class TensorflowServingModelRecord(Record):
    status: TensorflowServingModelStatus = None


TfServingRecordDict = Dict[RecordKey, Tuple[TensorflowServingModelRecord, ...]]


def get_known_tensorflow_serving_models(
    grpc_target: str, tensorflow_serving_config: TensorflowServingConfig
) -> TfServingRecordDict:
    known_record_keys = [
        RecordKey(framework=model_config.model_platform.lower(), name=model_config.name)
        for model_config in tensorflow_serving_config._get_model_configs()
        if model_config
    ]

    return {
        record_key: _record_key_to_tensorflow_records(grpc_target, record_key)
        for record_key in known_record_keys
    }


def get_current_tensorflow_serving_models(
    grpc_target: str, tensorflow_serving_config: TensorflowServingConfig
) -> Dict[RecordKey, TensorflowServingModelRecord]:
    def get_current_highest_available_model(
        models: Tuple[TensorflowServingModelRecord],
    ) -> TensorflowServingModelRecord:
        current_model = None
        for model in models:
            if model.status == TensorflowServingModelStatus.AVAILABLE:
                if not current_model or (
                    model.is_priority > current_model.is_priority
                    or current_model.version < model.version
                ):
                    current_model = model

        return current_model

    all_known_tfserving_records = get_known_tensorflow_serving_models(
        grpc_target=grpc_target, tensorflow_serving_config=tensorflow_serving_config
    )

    results = {
        key: get_current_highest_available_model(models)
        for key, models in all_known_tfserving_records.items()
    }
    return results


def _record_key_to_tensorflow_records(
    grpc_target: str, record_key: RecordKey
) -> Tuple[TensorflowServingModelRecord, ...]:
    TensorflowServingGrpcConnection.setup_connection(grpc_target)
    record_statuses = TensorflowServingGrpcConnection.get_all_record_statuses(
        record_key
    )
    return tuple(
        TensorflowServingModelRecord(
            key=record_key,
            version=version,
            status=status,
            is_priority=(version == PRIORITY_VERSION),
        )
        for version, status in record_statuses.items()
        if version is not None
    )


class TensorflowServingGrpcConnection:
    target: str = None
    channel: grpc.Channel = None
    stub: model_service_pb2_grpc.ModelServiceStub = None

    @classmethod
    def setup_connection(cls, target: str):
        if not cls.stub:
            cls.target = target
            cls.channel = grpc.insecure_channel(cls.target)
            cls.stub = model_service_pb2_grpc.ModelServiceStub(cls.channel)

    @classmethod
    def get_all_record_statuses(
        cls, record_key: RecordKey
    ) -> Dict[int, TensorflowServingModelStatus]:
        cls.setup_connection(cls.target)
        request = get_model_status_pb2.GetModelStatusRequest(
            model_spec=model_pb2.ModelSpec(name=record_key.name)
        )
        result = {}
        try:
            response = cls.stub.GetModelStatus(request, timeout=0.5)
            log.info(f"name {record_key.name} get response {response}")
            for model_status in response.model_version_status:
                version = model_status.version
                result[version] = (
                    TensorflowServingModelStatus(model_status.state)
                    or TensorflowServingModelStatus.UNKNOWN
                )
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.NOT_FOUND:
                log.warning(
                    "Attempt to retrieve status of a model that doesn't exist! "
                    f"model={record_key}"
                )
            else:
                log.exception(err)
        except Exception as err:
            log.exception(err)
            raise err
        return result
