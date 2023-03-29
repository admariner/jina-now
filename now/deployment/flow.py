import os.path
import tempfile

from jina.clients import Client

from now.deployment.deployment import deploy_wolf
from now.log import time_profiler
from now.utils.jcloud.helpers import write_flow_file


@time_profiler
def deploy_flow(
    flow_yaml: str,
):
    """Deploy a Flow on JCloud."""
    # TODO create tmpdir top level and pass it down
    with tempfile.TemporaryDirectory() as tmpdir:
        # hack we don't know if the flow yaml is a path or a string
        if type(flow_yaml) == dict:
            flow_file = os.path.join(tmpdir, 'flow.yml')
            write_flow_file(flow_yaml, flow_file)
            flow_yaml = flow_file

        flow = deploy_wolf(path=flow_yaml)

    gateway_host_http = flow.endpoints['gateway (http)']
    client = Client(host=gateway_host_http)

    return client, gateway_host_http
