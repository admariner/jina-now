from pytest_mock import MockerFixture

from now.executor.gateway import NOWGateway
from now.executor.gateway.hubble_report import init_payment_params, save_cred


def test_init_payment_params(mocker: MockerFixture):
    mocker.patch(
        'now.executor.gateway.hubble_report.init_payment_client', return_value='PASSED'
    )
    mocker.patch('now.executor.gateway.hubble_report.save_cred', return_value='PASSED')

    init_payment_params('test', 'test', 'test')


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
