from typing import Dict, List

from pydantic import BaseModel, Field


class FiltersResponseModel(BaseModel):
    filters: Dict[str, List] = Field(
        default={},
        description='Get all the filter fields and their possible values in the index',
        example={
            'price': [1, 2, 3],
            'color': [
                'red',
                'blue',
                'green',
            ],
        },
    )


class CountResponseModel(BaseModel):
    number_of_docs: int = Field(
        default=0,
        description='Get the number of documents in the index',
        example=100,
    )


class EncoderToDataclassFieldsModsResponseModel(BaseModel):
    encoder_to_dataclass_fields_mods: Dict[str, Dict[str, str]] = Field(
        default={},
        description='Dictionary which maps encoder names to the dataclass fields they encode and their modality',
        example={
            'encoderclip': {
                'text_0': 'text',
                'image_0': 'image',
            },
            'encodersbert': {
                'image_0': 'text',
            },
        },
    )
