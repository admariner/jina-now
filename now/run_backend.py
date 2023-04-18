import sys
import uuid
from copy import deepcopy
from typing import Dict, Optional

import requests
from docarray import DocumentArray
from jina.clients import Client

from now.admin.update_api_keys import update_api_keys
from now.app.base.app import JinaNOWApp
from now.constants import ACCESS_PATHS
from now.data_loading.data_loading import load_data
from now.deployment.flow import deploy_flow
from now.log import time_profiler
from now.now_dataclasses import UserInput
from now.utils.jcloud.helpers import get_flow_id


@time_profiler
def run(
    app_instance: JinaNOWApp,
    user_input: UserInput,
    **kwargs,
):
    """
    This function will run the backend of the app. Specifically, it will:
    - Load the data
    - Set up the flow dynamically and get the environment variables
    - Deploy the flow
    - Index the data
    :param app_instance: The app instance
    :param user_input: The user input
    :param kwargs: Additional arguments
    :return:
    """
    print_callback = kwargs.get('print_callback', print)

    dataset = load_data(user_input, print_callback)
    print_callback('Data loaded. Deploying the flow...')

    # Set up the app specific flow
    app_instance.setup(user_input=user_input)

    client, gateway_host_http = deploy_flow(flow_yaml=app_instance.flow_yaml)

    # TODO at the moment the scheduler is not working. So we index the data right away
    # if (
    #     user_input.deployment_type == 'remote'
    #     and user_input.dataset_type == DatasetTypes.S3_BUCKET
    #     and 'NOW_CI_RUN' not in os.environ
    # ):
    #     # schedule the trigger which will sync the bucket with the indexer once a day
    #     trigger_scheduler(user_input, gateway_host_internal)
    # else:
    # index data right away
    print_callback('Flow deployed. Indexing the data...')
    index_docs(user_input, dataset, client, print_callback, **kwargs)

    return gateway_host_http


def trigger_scheduler(user_input, host):
    """
    This function will trigger the scheduler which will sync the bucket with the indexer once a day
    """
    print('Triggering scheduler to index data from S3 bucket')
    # check if the api_key exists. If not then create a new one
    if user_input.secured and not user_input.api_key:
        user_input.api_key = uuid.uuid4().hex
        # Also call the bff to update the api key
        for i in range(
            100
        ):  # increase the probability that all replicas get the new key
            update_api_keys(user_input.api_key, host)

    scheduler_params = {
        'flow_id': get_flow_id(host),
        'api_key': user_input.api_key,
    }
    cookies = {'st': user_input.jwt['token']}
    try:
        response = requests.post(
            'https://storefrontapi.nowrun.jina.ai/api/v1/schedule_sync',
            json=scheduler_params,
            cookies=cookies,
        )
        response.raise_for_status()
        print(
            'Scheduler triggered successfully. Scheduler will sync data from S3 bucket once a day.'
        )
    except Exception as e:
        print(f'Error while scheduling indexing: {e}')
        print(f'Indexing will not be scheduled. Please contact Jina AI support.')


def index_docs(user_input, dataset, client, print_callback, **kwargs):
    """
    Index the data right away
    """
    print_callback(f"▶ indexing {len(dataset)} documents")
    params = {'access_paths': ACCESS_PATHS}
    if user_input.secured:
        params['jwt'] = user_input.jwt
    call_flow(
        client=client,
        dataset=dataset,
        max_request_size=user_input.app_instance.max_request_size,
        parameters=deepcopy(params),
        return_results=False,
        **kwargs,
    )
    print_callback('⭐ Success - your data is indexed')


@time_profiler
def call_flow(
    client: Client,
    dataset: DocumentArray,
    max_request_size: int,
    endpoint: str = '/index',
    parameters: Optional[Dict] = None,
    return_results: Optional[bool] = False,
    **kwargs,
):
    request_size = estimate_request_size(dataset, max_request_size)

    # Refer to https://docs.jina.ai/concepts/client/transient-errors/ for more details on parameters
    response = client.post(
        on=endpoint,
        request_size=request_size,
        inputs=dataset,
        show_progress=True,
        parameters=parameters,
        continue_on_error=True,
        prefetch=100,
        max_attempts=10,  # max retries for a single request
        inital_backoff=2,  # start off with higher value, 5 seconds
        max_backoff=30,  # max backoff of 30 seconds
        backoff_multiplier=1.5,  # exponential increase in backoff
        timeout=600,  # timeout of 10 minutes
        on_done=kwargs.get('on_done', None),
        on_error=kwargs.get('on_error', None),
        on_always=kwargs.get('on_always', None),
    )

    if return_results:
        return response


def estimate_request_size(index, max_request_size):
    if len(index) == 0:
        return 1

    # We assume that it is homogeneous multimodal DocumentArray,
    # therefore pick the first document to estimate the size in bytes
    size = sys.getsizeof(index[0].content) + sum(
        [sys.getsizeof(chunk.content) for chunk in index[0].chunks]
    )
    max_size = 5e5  # 0.5 MB
    request_size = max(min(max_request_size, int(max_size / size)), 1)
    return request_size
