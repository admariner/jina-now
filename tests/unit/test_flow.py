import pytest
from jcloud.flow import CloudFlow
from jina.jaml import JAML
from pytest_mock import MockerFixture

from now.deployment.flow import deploy_flow
from now.utils.jcloud.helpers import Dumper


@pytest.fixture
def get_dummy_flow(tmpdir, mocker, flow_type):
    flow_str = """
            jtype: Flow
            jcloud:
                name: test
            """
    with open(f'{tmpdir}/test.yml', 'w'):
        flow = CloudFlow(path=f'{tmpdir}/test.yml', flow_id='nowapi-e3fd500bdf')
    flow.endpoints = {'gateway (http)': 'http://somehost:1234'}
    mocker.patch('time.sleep', return_value=None)
    if flow_type == 'str':
        return flow, flow_str
    elif flow_type == 'dict':
        return flow, JAML.load(flow_str)
    else:
        with open(f'{tmpdir}/flow.yml', 'w') as f:
            JAML.dump(
                JAML.load(flow_str), f, indent=2, allow_unicode=True, Dumper=Dumper
            )
        return flow, f'{tmpdir}/flow.yml'


@pytest.mark.parametrize('flow_type', ['str', 'dict', 'file'])
def test_deploy_flow(get_dummy_flow: tuple, flow_type: str, mocker: MockerFixture):
    flow, flow_yaml = get_dummy_flow
    mocker.patch('now.deployment.deployment.deploy_wolf', return_value=flow)
    deploy_flow(flow_yaml)


def test_failed_flow(mocker: MockerFixture):
    mocker.patch(
        'now.deployment.deployment.list_all_wolf',
        return_value=[
            {
                'id': 'nowapi-2133dfs44f4',
                'status': 'Serving',
                'endpoint': 'test',
                'created_at': '2021-01-01',
            }
        ],
    )
    mocker.patch(
        'now.deployment.deployment.terminate_wolf',
        return_value={'id': 'nowapi-2133dfs44f4'},
    )
    mocker.patch('now.deployment.deployment.deploy_wolf', side_effect=ValueError('ts'))
    flow = """
    jtype: Flow
    jcloud:
        name: test
    """
    with pytest.raises(ValueError):
        deploy_flow(flow)
