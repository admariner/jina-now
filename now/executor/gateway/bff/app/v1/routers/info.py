from collections import defaultdict

from docarray import Document
from fastapi import APIRouter

from now.executor.gateway.bff.app.settings import GlobalUserInput
from now.executor.gateway.bff.app.v1.models.info import (
    CountResponseModel,
    EncoderToDataclassFieldsModsResponseModel,
    FiltersResponseModel,
)
from now.executor.gateway.bff.app.v1.models.shared import BaseRequestModel
from now.executor.gateway.bff.app.v1.routers.helper import jina_client_post
from now.executor.gateway.bff.logger import logger

router = APIRouter()


@router.post(
    '/filters', summary='Get all filters in the indexer and their possible values'
)
async def get_tags(data: BaseRequestModel) -> FiltersResponseModel:
    response = await jina_client_post(
        request_model=data,
        docs=Document(),
        endpoint='/filters',
        target_executor=r'\Aindexer\Z',
    )
    logger.debug(response[0])
    return FiltersResponseModel(filters=response[0].tags.get('filters', []))


@router.post(
    '/count', summary='Get the count of the total number of documents in the indexer'
)
async def get_count(data: BaseRequestModel) -> CountResponseModel:
    response = await jina_client_post(
        request_model=data,
        docs=Document(),
        endpoint='/count',
        target_executor=r'\Aindexer\Z',
    )
    return CountResponseModel(number_of_docs=response[0].tags['count'])


@router.post('/encoder_to_dataclass_fields_mods', include_in_schema=False)
async def get_index_fields_dict() -> EncoderToDataclassFieldsModsResponseModel:
    index_fields_dict = defaultdict(dict)
    user_input_in_bff = GlobalUserInput.user_input_in_bff
    for index_field_raw, encoders in user_input_in_bff.model_choices.items():
        index_field = index_field_raw.replace('_model', '')
        dataclass_field = user_input_in_bff.field_names_to_dataclass_fields[index_field]
        modality = user_input_in_bff.index_field_candidates_to_modalities[index_field]
        for encoder in encoders:
            index_fields_dict[encoder][dataclass_field] = modality
    return EncoderToDataclassFieldsModsResponseModel(
        encoder_to_dataclass_fields_mods=index_fields_dict
    )
