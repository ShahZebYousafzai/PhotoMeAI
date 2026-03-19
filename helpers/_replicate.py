from functools import lru_cache
import sys

from decouple import config

REPLICATE_API_TOKEN = config("REPLICATE_API_TOKEN")
REPLICATE_MODEL = config("REPLICATE_MODEL")
REPLICATE_MODEL_VERSION = config("REPLICATE_MODEL_VERSION")

def _import_replicate():
    """
    Replicate's current dependency stack (pydantic v1) can break on newer Python
    versions. Import lazily so the API can still start for non-Replicate routes.
    """
    try:
        from replicate.client import Client  # type: ignore
        from replicate.exceptions import ReplicateError  # type: ignore
        return Client, ReplicateError
    except Exception as e:
        py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        raise RuntimeError(
            "Failed to import 'replicate'. This is commonly caused by running on "
            f"Python {py} with a Replicate/Pydantic combination that is not compatible. "
            "Recommended fix: use Python 3.12 for this backend (new conda env) or "
            "pin/upgrade 'replicate' to a version that supports your Python."
        ) from e


@lru_cache
def get_replicate_client():
    Client, _ = _import_replicate()
    return Client(api_token=REPLICATE_API_TOKEN)

@lru_cache
def get_replicate_model_version():
    replicate_client = get_replicate_client()
    rep_model = replicate_client.models.get(REPLICATE_MODEL)
    rep_version = rep_model.versions.get(REPLICATE_MODEL_VERSION)
    return rep_version


def generate_image(
    prompt,
    require_trigger_word: bool = True,
    trigger_word: str = "TOK",
    num_outputs: int = 2,
    output_format: str = "jpg",
):
    _import_replicate()  # ensure we fail with a helpful error
    if require_trigger_word:
        if trigger_word not in prompt:
            raise Exception(f"{trigger_word} was not included")
    input_args = {
        "prompt": prompt,
        "num_outputs": num_outputs,
        "output_format": output_format,
    }
    replicate_client = get_replicate_client()
    rep_version = get_replicate_model_version()
    return replicate_client.predictions.create(
        version=rep_version,
        input=input_args
    )

def list_prediction_results(
        model=REPLICATE_MODEL, 
        version=REPLICATE_MODEL_VERSION,
        status=None,
        max_size=500
    ):
    _import_replicate()  # ensure we fail with a helpful error
    replicate_client = get_replicate_client()
    preds = replicate_client.predictions.list()
    results = list(preds.results)
    while preds.next:
        _preds = replicate_client.predictions.list(preds.next)
        results += list(_preds.results)
        if len(results) > max_size:
            break
    results = [x for x in results if x.model==model and x.version==version]
    if status is not None:
        results = [x for x in results if x.status == status]
    return results


def get_prediction_detail(
        prediction_id=None
    ):
    _, ReplicateError = _import_replicate()
    replicate_client = get_replicate_client()
    try:
        pred = replicate_client.predictions.get(prediction_id)
    except ReplicateError:
        return None, 404
    except:
        return None, 500
    return pred, 200