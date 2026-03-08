from functools import lru_cache

from decouple import config
from replicate.client import Client

REPLICATE_API_TOKEN = config("REPLICATE_API_TOKEN")
REPLICATE_MODEL = config("REPLICATE_MODEL")
REPLICATE_MODEL_VERSION = config("REPLICATE_MODEL_VERSION")

@lru_cache
def get_replicate_client():
    return Client(api_token=REPLICATE_API_TOKEN)

@lru_cache
def get_replicate_model_version():
    replicate_client = get_replicate_client()
    rep_model = replicate_client.models.get(REPLICATE_MODEL)
    rep_version = rep_model.versions.get(REPLICATE_MODEL_VERSION)
    return rep_version

def generate_image(prompt: str, 
                    model: str = REPLICATE_MODEL,
                    model_version: str = REPLICATE_MODEL_VERSION,
                    num_outputs: int = 2, 
                    output_format: str = "jpg",
                    enrich_trigger_word: bool = False, trigger_word: str = "TOK"):
    if enrich_trigger_word:
        if trigger_word not in prompt:
            raise ValueError(f"Trigger word {trigger_word} not found in prompt")
    input_args = {
        "prompt": prompt,
        "num_outputs": 2,
        "output_format": "jpg",
    }
    replicate_client = get_replicate_client()
    rep_version = get_replicate_model_version()

    pred = replicate_client.predictions.create(
                            version=rep_version,
                            input=input_args
                        )
    return {
        "id": pred.id,
        "status": pred.status,
    }

def list_prediction_results(
        model=REPLICATE_MODEL,
        version=REPLICATE_MODEL_VERSION
    ):
    replicate_client = get_replicate_client()
    preds = replicate_client.predictions.list()
    results = list(preds.results)
    return preds