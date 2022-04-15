import pytest
import logging
from tests import master_tests

log = logging.getLogger(__file__)


@pytest.mark.usefixtures("clear_node_registry")
def test_wrong_node_type():
    with pytest.raises(Exception):
        master_tests.send_register_request("some unkown node", "host1:100")


@pytest.mark.usefixtures("clear_node_registry")
def test_empty_target():
    with pytest.raises(Exception):
        master_tests.send_register_request("config_manager", "")


@pytest.mark.usefixtures("clear_node_registry")
def test_config_manager_register_and_unregister():
    r = master_tests.send_register_request("config_manager", "host1:100")
    assert "host1:100" in r.text
    r = master_tests.send_delete_register_request("config_manager", "host1:100")
    assert "host1:100" not in r.text


@pytest.mark.usefixtures("clear_node_registry")
def test_config_manager_register_and_unregister():
    r = master_tests.send_register_request("remote_model_puller", "host2:200")
    assert "host2:200" in r.text
    r = master_tests.send_delete_register_request("remote_model_puller", "host2:200")
    assert "host2:200" not in r.text
