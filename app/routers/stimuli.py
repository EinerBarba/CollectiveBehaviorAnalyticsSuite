import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, hard_delete
from app.models import StimulusType, Stimulus, StimulusEvent, User
from app.schemas.stimuli import (
    StimulusTypeOut,
    StimulusCreate, StimulusUpdate, StimulusOut,
    StimulusEventCreate, StimulusEventUpdate, StimulusEventOut,
)

router = APIRouter(tags=["stimuli"])



@router.get("/stimulus-types", response_model=list[StimulusTypeOut])
async def list_stimulus_types(db: AsyncSession = Depends(get_db)):
    return await list_all(db, StimulusType, limit=500)



@router.post("/stimuli", response_model=StimulusOut, status_code=status.HTTP_201_CREATED)
async def create_stimulus(body: StimulusCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Stimulus, body.model_dump())


@router.get("/stimuli", response_model=list[StimulusOut])
async def list_stimuli(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [Stimulus.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, Stimulus, skip=skip, limit=limit, filters=filters)


@router.get("/stimuli/{stimulus_id}", response_model=StimulusOut)
async def get_stimulus(stimulus_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Stimulus, stimulus_id)


@router.patch("/stimuli/{stimulus_id}", response_model=StimulusOut)
async def update_stimulus(
    stimulus_id: uuid.UUID, body: StimulusUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    stim = await get_or_404(db, Stimulus, stimulus_id)
    return await update_obj(db, stim, body.model_dump(exclude_unset=True))


@router.delete("/stimuli/{stimulus_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stimulus(stimulus_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stim = await get_or_404(db, Stimulus, stimulus_id)
    await hard_delete(db, stim)



@router.post("/stimulus-events", response_model=StimulusEventOut, status_code=status.HTTP_201_CREATED)
async def create_stimulus_event(body: StimulusEventCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, StimulusEvent, body.model_dump())


@router.get("/stimulus-events", response_model=list[StimulusEventOut])
async def list_stimulus_events(stimulus_id: uuid.UUID, skip: int = 0, limit: int = 500, db: AsyncSession = Depends(get_db)):
    return await list_all(db, StimulusEvent, skip=skip, limit=limit, filters=[StimulusEvent.stimulus_id == stimulus_id])


@router.get("/stimulus-events/{event_id}", response_model=StimulusEventOut)
async def get_stimulus_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, StimulusEvent, event_id)


@router.patch("/stimulus-events/{event_id}", response_model=StimulusEventOut)
async def update_stimulus_event(
    event_id: uuid.UUID, body: StimulusEventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    event = await get_or_404(db, StimulusEvent, event_id)
    return await update_obj(db, event, body.model_dump(exclude_unset=True))


@router.delete("/stimulus-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stimulus_event(event_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await get_or_404(db, StimulusEvent, event_id)
    await hard_delete(db, event)
