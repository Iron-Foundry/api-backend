from pydantic import BaseModel


class LootItem(BaseModel):
    item_id: int
    item_name: str
    quantity: int
    ge_price: int | None = None
    total_value: int | None = None
