import os.path
import tempfile
import time
from typing import Union

from jina.clients import Client
from jina.jaml import JAML

from now.deployment import deployment
from now.log import time_profiler
from now.utils.jcloud.helpers import read_flow_file, write_flow_file


@time_profiler
def deploy_flow(flow_yaml: Union[str, dict]):
    """
    Deploy a Flow on JCloud.
    :param flow_yaml: Path to a yaml file or a dict or a Yaml string.

    """
    # TODO create tmpdir top level and pass it down
    with tempfile.TemporaryDirectory() as tmpdir:
        if isinstance(flow_yaml, str) and os.path.exists(flow_yaml):
            flow_file = flow_yaml
            flow_name = read_flow_file(flow_file)['jcloud']['name']
        else:
            if isinstance(flow_yaml, str):
                flow_yaml = JAML.load(flow_yaml)
            flow_name = flow_yaml['jcloud']['name']
            flow_file = os.path.join(tmpdir, 'flow.yml')
            write_flow_file(flow_yaml, flow_file)

        # Now deploy the flow to JCloud
        try:
            flow = deployment.deploy_wolf(path=flow_file)
        except BaseException as e:  # noqa
            print(f'Failed to deploy flow. Deleting flow: `{flow_name}`')
            flows = deployment.list_all_wolf(status='Failed', namespace=flow_name)
            if not flows or len(flows) > 1:
                print(f'Found {len(flows)} `FAILED` flows with name {flow_name}.')
            else:
                flow = deployment.terminate_wolf(flow_id=flows[0]['id'])
                print(f'Successfully deleted flow: `{flows[0]["id"]}`')
            raise e

    time.sleep(10)  # sleep for some time before starting with indexing
    gateway_host_http = flow.endpoints['gateway (http)']
    client = Client(host=gateway_host_http)

    return client, gateway_host_http
