import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, soft_delete
from app.models import File, FileVersion, DatasetType, Dataset, DatasetVersion, DatasetSpatialMetadata, DatasetFile, User
from app.schemas.files import FileCreate, FileUpdate, FileOut, FileVersionCreate, FileVersionOut
from app.schemas.datasets import (
    DatasetTypeOut,
    DatasetCreate, DatasetUpdate, DatasetOut,
    DatasetVersionCreate, DatasetVersionOut,
    DatasetSpatialMetadataUpsert, DatasetSpatialMetadataOut,
    DatasetFileCreate, DatasetFileOut,
)

router = APIRouter(tags=["files-and-datasets"])


@router.post("/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def create_file_record(body: FileCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, File, {**body.model_dump(), "created_by": user.id})


@router.get("/files", response_model=list[FileOut])
async def list_files(
    experiment_id: uuid.UUID | None = None,
    file_type: str | None = None,
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if experiment_id is not None:
        filters.append(File.experiment_id == experiment_id)
    if file_type is not None:
        filters.append(File.file_type == file_type)
    return await list_all(db, File, skip=skip, limit=limit, filters=filters or None)


@router.get("/files/{file_id}", response_model=FileOut)
async def get_file_record(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, File, file_id)


@router.patch("/files/{file_id}", response_model=FileOut)
async def update_file_record(
    file_id: uuid.UUID, body: FileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    file_ = await get_or_404(db, File, file_id)
    return await update_obj(db, file_, body.model_dump(exclude_unset=True))


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_record(file_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    file_ = await get_or_404(db, File, file_id)
    await soft_delete(db, file_)



@router.post("/file-versions", response_model=FileVersionOut, status_code=status.HTTP_201_CREATED)
async def create_file_version(body: FileVersionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    version = await create_obj(db, FileVersion, {**body.model_dump(), "uploaded_by": user.id})
    if body.is_current:
        file_ = await db.get(File, body.file_id)
        file_.current_version_id = version.id
        await db.commit()
    return version


@router.get("/file-versions", response_model=list[FileVersionOut])
async def list_file_versions(file_id: uuid.UUID, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, FileVersion, skip=skip, limit=limit, filters=[FileVersion.file_id == file_id])


@router.get("/file-versions/{version_id}", response_model=FileVersionOut)
async def get_file_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, FileVersion, version_id)


@router.get("/file-versions/{version_id}/content")
async def download_file_version(
    version_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    version = await get_or_404(db, FileVersion, version_id)
    path = storage.full_path(version.storage_key)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File content not found in storage")
    file_ = await get_or_404(db, File, version.file_id)
    return FileResponse(path, media_type=version.mime_type or "application/octet-stream", filename=file_.logical_name)



@router.get("/dataset-types", response_model=list[DatasetTypeOut])
async def list_dataset_types(db: AsyncSession = Depends(get_db)):
    return await list_all(db, DatasetType, limit=500)



@router.post("/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(body: DatasetCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Dataset, {**body.model_dump(), "created_by": user.id})


@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [Dataset.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, Dataset, skip=skip, limit=limit, filters=filters)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Dataset, dataset_id)


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
async def update_dataset(
    dataset_id: uuid.UUID, body: DatasetUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    ds = await get_or_404(db, Dataset, dataset_id)
    return await update_obj(db, ds, body.model_dump(exclude_unset=True))


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ds = await get_or_404(db, Dataset, dataset_id)
    await soft_delete(db, ds)



@router.post("/dataset-versions", response_model=DatasetVersionOut, status_code=status.HTTP_201_CREATED)
async def create_dataset_version(body: DatasetVersionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    version = await create_obj(db, DatasetVersion, {**body.model_dump(), "created_by": user.id})
    if body.is_current:
        ds = await db.get(Dataset, body.dataset_id)
        ds.current_version_id = version.id
        await db.commit()
    return version


@router.get("/dataset-versions", response_model=list[DatasetVersionOut])
async def list_dataset_versions(dataset_id: uuid.UUID, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, DatasetVersion, skip=skip, limit=limit, filters=[DatasetVersion.dataset_id == dataset_id])


@router.get("/dataset-versions/{version_id}", response_model=DatasetVersionOut)
async def get_dataset_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, DatasetVersion, version_id)



@router.put("/dataset-spatial-metadata", response_model=DatasetSpatialMetadataOut)
async def upsert_dataset_spatial_metadata(
    body: DatasetSpatialMetadataUpsert, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    existing = await db.get(DatasetSpatialMetadata, body.dataset_version_id)
    if existing:
        return await update_obj(db, existing, body.model_dump(exclude={"dataset_version_id"}))
    return await create_obj(db, DatasetSpatialMetadata, body.model_dump())


@router.get("/dataset-spatial-metadata/{dataset_version_id}", response_model=DatasetSpatialMetadataOut)
async def get_dataset_spatial_metadata(dataset_version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, DatasetSpatialMetadata, dataset_version_id)



@router.post("/dataset-files", response_model=DatasetFileOut, status_code=status.HTTP_201_CREATED)
async def attach_dataset_file(body: DatasetFileCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, DatasetFile, body.model_dump())


@router.get("/dataset-files", response_model=list[DatasetFileOut])
async def list_dataset_files(dataset_version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await list_all(db, DatasetFile, limit=500, filters=[DatasetFile.dataset_version_id == dataset_version_id])


@router.delete("/dataset-files", status_code=status.HTTP_204_NO_CONTENT)
async def detach_dataset_file(
    dataset_version_id: uuid.UUID, file_version_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    from app.crud.base import hard_delete

    link = await db.get(DatasetFile, (dataset_version_id, file_version_id))
    if link:
        await hard_delete(db, link)
