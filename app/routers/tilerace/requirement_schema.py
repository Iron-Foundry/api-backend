from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class LeafRequirement(BaseModel):
    kind: Literal["item"]
    item_id: int
    quantity: int = 1
    name: str = ""
    icon_url: str = ""


class TextRequirement(BaseModel):
    kind: Literal["text"]
    text: str = ""


class AndRequirement(BaseModel):
    kind: Literal["and"]
    children: list[RequirementNode] = []


class OrRequirement(BaseModel):
    kind: Literal["or"]
    children: list[RequirementNode] = []


class NotRequirement(BaseModel):
    kind: Literal["not"]
    child: RequirementNode


RequirementNode = Annotated[
    LeafRequirement | TextRequirement | AndRequirement | OrRequirement | NotRequirement,
    Field(discriminator="kind"),
]


def requirement_from_items(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    leaves = [
        {
            "kind": "item",
            "item_id": int(i.get("item_id", 0)),
            "quantity": int(i.get("quantity", 1)),
            "name": i.get("name", ""),
            "icon_url": i.get("icon_url", ""),
        }
        for i in items
        if i.get("item_id")
    ]
    if not leaves:
        return None
    if len(leaves) == 1:
        return leaves[0]
    return {"kind": "and", "children": leaves}


AndRequirement.model_rebuild()
OrRequirement.model_rebuild()
NotRequirement.model_rebuild()
