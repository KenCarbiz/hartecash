"""Message template endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import Lead, Listing, MessageTemplate
from fsbo.templates.render import SEED_TEMPLATES, build_context, render

router = APIRouter(tags=["templates"])


DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


class TemplateIn(BaseModel):
    name: str
    category: str = "outreach"
    body: str
    is_default: bool = False


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    name: str
    category: str
    body: str
    is_default: bool
    created_at: datetime


class RenderedTemplate(BaseModel):
    template_id: int
    rendered: str


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
    category: str | None = None,
) -> list[TemplateOut]:
    _ensure_seeded(db, dealer_id)
    stmt = select(MessageTemplate).where(MessageTemplate.dealer_id == dealer_id)
    if category:
        stmt = stmt.where(MessageTemplate.category == category)
    rows = db.scalars(stmt.order_by(MessageTemplate.category, MessageTemplate.name)).all()
    return [TemplateOut.model_validate(r) for r in rows]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> TemplateOut:
    tpl = MessageTemplate(
        dealer_id=dealer_id,
        name=payload.name,
        category=payload.category,
        body=payload.body,
        is_default=payload.is_default,
    )
    db.add(tpl)
    db.flush()
    return TemplateOut.model_validate(tpl)


class TemplatePatch(BaseModel):
    name: str | None = None
    category: str | None = None
    body: str | None = None
    is_default: bool | None = None


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    payload: TemplatePatch,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> TemplateOut:
    tpl = db.get(MessageTemplate, template_id)
    if not tpl or tpl.dealer_id != dealer_id:
        raise HTTPException(404, "template not found")
    if payload.name is not None:
        tpl.name = payload.name
    if payload.category is not None:
        tpl.category = payload.category
    if payload.body is not None:
        tpl.body = payload.body
    if payload.is_default is not None:
        tpl.is_default = payload.is_default
    db.flush()
    return TemplateOut.model_validate(tpl)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> None:
    tpl = db.get(MessageTemplate, template_id)
    if not tpl or tpl.dealer_id != dealer_id:
        raise HTTPException(404, "template not found")
    db.delete(tpl)


@router.get(
    "/templates/{template_id}/render/{listing_id}", response_model=RenderedTemplate
)
def render_template(
    template_id: int,
    listing_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> RenderedTemplate:
    tpl = db.get(MessageTemplate, template_id)
    if not tpl or tpl.dealer_id != dealer_id:
        raise HTTPException(404, "template not found")
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "listing not found")
    lead = db.scalar(
        select(Lead).where(
            Lead.dealer_id == dealer_id, Lead.listing_id == listing_id
        )
    )
    ctx = build_context(listing, lead)
    return RenderedTemplate(template_id=tpl.id, rendered=render(tpl.body, ctx))


def _ensure_seeded(db: Session, dealer_id: str) -> None:
    """Auto-seed the VAN-baseline templates for a dealer on first access."""
    existing = db.scalar(
        select(MessageTemplate.id).where(MessageTemplate.dealer_id == dealer_id).limit(1)
    )
    if existing:
        return
    for seed in SEED_TEMPLATES:
        db.add(
            MessageTemplate(
                dealer_id=dealer_id,
                name=seed["name"],
                category=seed["category"],
                body=seed["body"],
                is_default=False,
            )
        )
    db.flush()
