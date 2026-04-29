import argparse
import yaml
from pydantic.v1 import BaseModel, Field, ValidationError
from manifest_schemas import Input
import typing


def get_manifest_types_union():
    # filter down Input typing.Union to types that have a `type` field at the root level
    union_args: list[type[BaseModel]] = []
    for model in typing.get_args(Input):
        if "type" in model.__fields__:
            union_args.append(model)
    return typing.Union[tuple(union_args)]


ManifestTypesUnion = get_manifest_types_union()


class ValidateSchema(BaseModel):
    __root__: ManifestTypesUnion = Field(
        ..., description="Schema to validate", discriminator="type"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-path", type=str, help="Path to the schema file")
    args = parser.parse_args()
    with open(args.file_path, "r") as file:
        schema = yaml.safe_load(file)
    _type = schema.get("type")
    if not _type:
        raise ValueError("Schema does not have a `type` field")
    try:
        ValidateSchema.parse_obj(schema)
        print(f"Schema of type {_type} is valid")
    except ValidationError as e:
        print(f"Schema of type {_type} is invalid:\n{e}")
