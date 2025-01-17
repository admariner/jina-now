import hubble
import pytest
import requests
from jina import Client
from tests.integration.local.conftest import BASE_URL, SEARCH_URL, get_request_body
from tests.integration.remote.assertions import assert_search

from now.constants import ACCESS_PATHS, Models

API_KEY = 'my_key'
update_api_keys_url = f'{BASE_URL}/admin/updateApiKeys'
update_emails_url = f'{BASE_URL}/admin/updateUserEmails'


@pytest.mark.parametrize(
    'get_flow',
    [
        (
            {
                'admin_emails': [
                    hubble.Client(
                        token=get_request_body(secured=True)['jwt']['token'],
                        max_retries=None,
                        jsonify=True,
                    )
                    .get_user_info()['data']
                    .get('email')
                ]
            },
            {
                'admin_emails': [
                    hubble.Client(
                        token=get_request_body(secured=True)['jwt']['token'],
                        max_retries=None,
                        jsonify=True,
                    )
                    .get_user_info()['data']
                    .get('email')
                ],
                'document_mappings': [[Models.CLIP_MODEL, 512, ['text_field']]],
            },
        ),
    ],
    indirect=True,
)
def test_add_key(get_flow, simple_data, setup_service_running, random_index_name):
    client = Client(host='http://localhost:8081')

    client.index(
        simple_data,
        parameters={
            'access_paths': ACCESS_PATHS,
            'jwt': get_request_body(secured=True)['jwt'],
        },
    )
    request_body = get_request_body(secured=True)
    # Test adding user email
    request_body['user_emails'] = ['florian.hoenicke@jina.ai']
    response = requests.post(
        update_emails_url,
        json=request_body,
    )
    assert response.status_code == 200

    # test api keys
    # search with invalid api key
    request_body = get_request_body(secured=True)
    request_body['query'] = [
        {'name': 'text', 'value': 'girl on motorbike', 'modality': 'text'}
    ]
    del request_body['jwt']
    request_body['api_key'] = API_KEY
    request_body['limit'] = 9
    assert_search(SEARCH_URL, request_body, expected_status_code=401)

    print('# add api key')
    request_body_update_keys = get_request_body(secured=True)
    request_body_update_keys['api_keys'] = [API_KEY]
    response = requests.post(
        update_api_keys_url,
        json=request_body_update_keys,
    )
    if response.status_code != 200:
        print(response.text)
        print(response.json()['message'])
        raise Exception(f'Response status is {response.status_code}')
    print('# the same search should work now')
    assert_search(SEARCH_URL, request_body)
