"""The base of every OSRSClans answer model.

A model reads the camelCase OSRSClans keys and writes snake_case, so the same
model parses the answer, holds the cached copy, and goes out on the Foundry API.
OSRSClans may add fields, so an unknown field is ignored.
"""

from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class OsrsClansModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(validation_alias=to_camel),
        populate_by_name=True,
        frozen=True,
    )
