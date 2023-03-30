from pytest_mock import MockerFixture

from now.executor.gateway import NOWGateway
from now.executor.gateway.hubble_report import save_cred, start_base_fee_thread


def test_start_base_fee_thread(mocker: MockerFixture):
    mocker.patch(
        'now.executor.gateway.hubble_report.init_payment_client', return_value='PASSED'
    )
    mocker.patch('now.executor.gateway.hubble_report.save_cred', return_value='PASSED')
    mocker.patch(
        'now.executor.gateway.hubble_report.base_fee_thread', return_value='PASSED'
    )
    start_base_fee_thread('test', 'test', 'test')


def test_save_cred():
    save_cred('./')
    save_cred(None)


def test_gateway(mocker: MockerFixture):
    runtime_args = {
        'protocol': [0, 1],
        'port': [8085, 8081],
    }
    mocker.patch('now.deployment.deployment.cmd', return_value=['PASSED', ''])
    NOWGateway({}, runtime_args=runtime_args)
