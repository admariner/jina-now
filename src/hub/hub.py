# from jina.hubble.hubio import HubIO
from datetime import datetime
import subprocess

from yaspin import yaspin


def push_to_hub():
    """
    We need the trained model as hub executor and pushed into the docker registry of hubble.
    Otherwise, there is no possibility to run the executor on Kubernetes.
    In the past, we were saving the trained model in GCP. But the user would not have access to do so.

    Idea 1 create an executor and push the executor+model to hub
    or
    Idea 2 Misuse the Docarray.push() function. Store the model as tensor
    I would prefer Idea 1 since remote Docarrays vanish, and the password has to be part of the k8s config,...
    """
    name = f'linear_head_encoder_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    secret = '93ea59dbd1ee3fe0bdc44252c6e86a87'
    class_name = 'FineTunedLinearHeadEncoder'
    bashCommand = f"jina hub push --private src/hub/head_encoder -t {name} --force-update {class_name} --secret {secret}"
    with yaspin(text="push fine-tuned model to hub", color="green") as spinner:
        with open("NUL", "w") as fh:
            process = subprocess.Popen(bashCommand.split(), stdout=fh)
        output, error = process.communicate()
        spinner.ok('⏫ ')
    return f'FineTunedLinearHeadEncoder:{secret}/{name}'
