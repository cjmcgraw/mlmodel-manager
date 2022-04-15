from typing import Tuple
from unittest import mock
import random
import pytest
import re

import tests

from tensorflow_serving.apis import get_model_status_pb2
from google.protobuf import text_format as pbtxt
import grpc

from model_manager_lib import Record, RecordKey
from model_manager_lib import tfserving


def make_mock_config(read_data: str = None, **kwargs) -> mock.MagicMock:
    read_data = read_data or "model_config_list {\n\n}\n"
    file_buffer = mock.mock_open(read_data=read_data, **kwargs)
    return mock.patch("builtins.open", file_buffer)


def check_config_was_saved(expected: str, file_mock: mock.MagicMock):
    first, *rest = file_mock.write.call_args.args

    expected = re.sub(r"\s+", "", expected)
    actual = re.sub(r"\s+", "", first)

    assert expected == actual, f"""
    Expected config to be saved in the same format with the same values
    
    expected:
    {expected}
    
    actual:
    {actual}
    """


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_config_with_empty_file(*args):
    with make_mock_config() as file_mock:
        tfserving.load_config("some/random/path")


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_fails_when_file_contents_invalid(*args):
    invalid_file_contents = f"""
        model_config_list {{
            config {{
                name: "abc-123"
                base_path: "/some/path/to/my/model"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
    """
    with make_mock_config(invalid_file_contents):
        with pytest.raises(pbtxt.ParseError):
            tfserving.load_config("some/path")


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_save_fails_when_crc_is_different(*args):
    initial_file_contents = f"""
        model_config_list {{
            config {{
                name: "abc-123"
                base_path: "/some/path/to/my/model"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}
    """
    with make_mock_config(initial_file_contents):
        config = tfserving.load_config("some/random/path")

    different_file_contents = f"""
            model_config_list {{
            config {{
                name: "abc-123"
                base_path: "/some/path/to/my/model"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
            
             config {{
                name: "efg-456"
                base_path: "/some/other/path/to/my/model"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}           
        }}
    """

    with make_mock_config(different_file_contents):
        with pytest.raises(ValueError):
            config = tfserving.save_config(config)


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_config_with_empty_file_and_add_model(*args):
    config_path = tests.generate_random_path(parts=10)
    with make_mock_config():
        config = tfserving.load_config(config_path)

    record: Record = tests.generate_random_record(framework='tensorflow')
    model_path = tests.generate_random_path()
    with make_mock_config() as file_mock:
        expected = f"""
        model_config_list {{
            config {{
                name: "{record.key.name}"
                base_path: "{model_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}
        """
        new_config = tfserving.add_model(config, record, local_path=model_path)
        opened_file = file_mock()
        opened_file.truncate.assert_called_once()
        check_config_was_saved(expected, opened_file)


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_config_with_model_in_file_add_model(*args):
    initial_record = tests.generate_random_record(framework='tensorflow')
    initial_name = f"{initial_record.key.name}"
    initial_path = tests.generate_random_path()
    initial_file_state = f"""
        model_config_list {{
            config {{
                name: "{initial_name}"
                base_path: "{initial_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}
        """

    config_path = tests.generate_random_path()
    with make_mock_config(read_data=initial_file_state):
        config = tfserving.load_config(config_path)

    assert initial_name in config.known_model_names

    new_record = tests.generate_random_record(framework='tensorflow')
    new_name = f"{new_record.key.name}"
    model_path = tests.generate_random_path()

    with make_mock_config(read_data=initial_file_state) as file_mock:
        new_config = tfserving.add_model(config, new_record, local_path=model_path)
        opened_file = file_mock()
        opened_file.truncate.assert_called_once()
        expected = f"""
         model_config_list {{
            config {{
                name: "{initial_name}"
                base_path: "{initial_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
            config {{
                name: "{new_name}"
                base_path: "{model_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}       
        """
        check_config_was_saved(expected, opened_file)


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_config_with_model_in_file_remove_model(*args):
    initial_record = tests.generate_random_record(framework='tensorflow')
    initial_name = f"{initial_record.key.name}"
    initial_path = tests.generate_random_path()
    initial_file_state = f"""
        model_config_list {{
            config {{
                name: "{initial_name}"
                base_path: "{initial_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}
        """

    config_path = tests.generate_random_path()
    with make_mock_config(read_data=initial_file_state):
        config = tfserving.load_config(config_path)

    assert initial_name in config.known_model_names

    with make_mock_config(read_data=initial_file_state) as file_mock:
        new_config = tfserving.remove_model(config, initial_record.key)
        opened_file = file_mock()
        opened_file.truncate.assert_called_once()
        expected = f"""
         model_config_list {{
        }}       
        """
        check_config_was_saved(expected, opened_file)


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_load_config_with_model_two_models_in_file_remove_model(*args):
    record1 = tests.generate_random_record(framework='tensorflow')
    name1 = f"{record1.key.name}"
    path1 = tests.generate_random_path()

    record2 = tests.generate_random_record(framework='tensorflow')
    name2 = f"{record2.key.name}"
    path2 = tests.generate_random_path()

    initial_file_state = f"""
         model_config_list {{
            config {{
                name: "{name1}"
                base_path: "{path1}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
            config {{
                name: "{name2}"
                base_path: "{path2}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}       
        """

    config_path = tests.generate_random_path()
    with make_mock_config(read_data=initial_file_state):
        config = tfserving.load_config(config_path)

    assert name1 in config.known_model_names
    assert name2 in config.known_model_names

    with make_mock_config(read_data=initial_file_state) as file_mock:
        new_config = tfserving.remove_model(config, record1.key)
        opened_file = file_mock()
        opened_file.truncate.assert_called_once()
        expected = f"""
         model_config_list {{
            config {{
                name: "{name2}"
                base_path: "{path2}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}       
        """
        check_config_was_saved(expected, opened_file)


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
def test_get_known_tensorflow_serving_models_with_empty_file(*args):
    with make_mock_config():
        config = tfserving.load_config("some/path")

    known_tfserving_models = tfserving.get_known_tensorflow_serving_models("localhost:1234", config)
    assert {} == known_tfserving_models


@mock.patch("model_manager_lib.tfserving.TensorflowServingGrpcConnection.stub")
def test_get_known_tensorflow_serving_models_with_single_model_in_file(mock_stub: mock.Mock):
    initial_record = tests.generate_random_record(framework='tensorflow')
    initial_name = f"{initial_record.key.name}"
    initial_path = tests.generate_random_path()

    initial_file = f"""
        model_config_list {{
            config {{
                name: "{initial_name}"
                base_path: "{initial_path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
        }}
    """
    with make_mock_config(initial_file):
        config = tfserving.load_config("some/path")

    versions_to_statuses = {
        int(v): random.choice(list(tfserving.TensorflowServingModelStatus))
        for v in tests.generate_versions(n=20)
    }

    tfserving_response = get_model_status_pb2.GetModelStatusResponse(
        model_version_status=[
            get_model_status_pb2
            .ModelVersionStatus(
                version=version,
                state=status.value
            )
            for version, status in versions_to_statuses.items()
        ]
    )
    mock_stub.GetModelStatus = mock.MagicMock(return_value=tfserving_response)
    known_tfserving_models = tfserving.get_known_tensorflow_serving_models("localhost:1234", config)

    assert {initial_record.key} == set(known_tfserving_models.keys()), f"""
    Expected the initial record key to be the only key present in the known tfserving models.
    
    expected:
    {set(initial_record.key)}
    
    actual:
    {set(known_tfserving_models.keys())}
    """
    actual_versions_to_statuses = {
        m.version: m.status
        for m in known_tfserving_models[initial_record.key]
    }
    assert versions_to_statuses == actual_versions_to_statuses, f"""
    Expected the versions to statuses to all be present in the known tfserving response!
    
    expected:
    {versions_to_statuses}
    
    actual:
    {actual_versions_to_statuses}
    """


@mock.patch("model_manager_lib.tfserving.pathlib.Path.exists")
@mock.patch("model_manager_lib.tfserving.TensorflowServingGrpcConnection.stub")
def test_get_known_tensorflow_serving_models_with_multiple_models_in_file(mock_stub: mock.Mock, *args):

    initial_file = """
        model_config_list { """

    records = [tests.generate_random_record(framework="tensorflow") for _ in range(10)]
    for record in records:
        path = tests.generate_random_path()
        initial_file += f"""
            config {{
                name: "{record.key.name}"
                base_path: "{path}"
                model_platform: "tensorflow"
                model_version_policy {{
                    latest {{
                        num_versions: 1
                    }}
                }}
            }}
         """

    initial_file += "}"
    with make_mock_config(initial_file):
        config = tfserving.load_config("some/path")

    record_keys_to_version_data = {}
    model_names_to_grpc_responses = {}
    for record in records:
        key = record.key
        model_name = f"{record.key.name}"
        record_keys_to_version_data[key] = {
            int(v): random.choice(list(tfserving.TensorflowServingModelStatus))
            for v in tests.generate_versions(n=20)
        }

        model_names_to_grpc_responses[model_name] = get_model_status_pb2.GetModelStatusResponse(
            model_version_status=[
                get_model_status_pb2
                    .ModelVersionStatus(
                        version=version,
                        state=status.value
                    )
                for version, status in record_keys_to_version_data[key].items()
            ]
        )

    def grpc_response_based_on_inputs(request: get_model_status_pb2.GetModelStatusRequest, *args, **kwargs):
        model_name = request.model_spec.name
        return model_names_to_grpc_responses[model_name]

    mock_stub.GetModelStatus = mock.MagicMock(side_effect=grpc_response_based_on_inputs)
    known_tfserving_models = tfserving.get_known_tensorflow_serving_models("localhost:1234", config)
    assert {record.key for record in records} == set(known_tfserving_models.keys())

    for record in records:
        key = record.key
        actual_tfserving_versions = {
            model.version: model.status
            for model in known_tfserving_models[key]
        }

        expected_tfserving_versions = record_keys_to_version_data[key]

        assert expected_tfserving_versions == actual_tfserving_versions


