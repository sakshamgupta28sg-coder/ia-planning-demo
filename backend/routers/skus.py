from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from dummy_data import get_new_skus, add_new_sku, delete_sku, HIERARCHIES

router = APIRouter(prefix="/skus", tags=["skus"])


class NewSKURequest(BaseModel):
    l1_name: str
    l2_name: str
    sku: str
    air: float
    auc: float
    launch_week: int
    exit_week: Optional[int] = None
    lifecycle: str = "NEW"


@router.get("/")
def list_skus():
    return {
        "existing": HIERARCHIES,
        "new": get_new_skus(),
    }


@router.post("/")
def create_sku(body: NewSKURequest):
    sku = add_new_sku({
        "l1_name": body.l1_name,
        "l2_name": body.l2_name,
        "sku": body.sku,
        "air": body.air,
        "auc": body.auc,
        "launch_week": body.launch_week,
        "exit_week": body.exit_week,
        "lifecycle": body.lifecycle,
    })
    return sku


@router.delete("/{hierarchy_code}")
def remove_sku(hierarchy_code: int):
    removed = delete_sku(hierarchy_code)
    if not removed:
        raise HTTPException(status_code=404, detail="SKU not found")
    return {"deleted": hierarchy_code}
