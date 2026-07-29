"""Processes endpoints — справочник процессов и топология сборки.

Справочник — это перенесённая документация технолога (Решение №86):
пара входящих типов + выход + станок + норматив. Топология пирамиды
выводится отсюда, отдельно не хранится.

API-контракт — Обсидиан → Решения №85-89.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.core.topology import ProcessSpec, build_topology
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.processes import Process

router = APIRouter(prefix="/processes", tags=["processes"])


# === Schemas ===


class ProcessResponse(BaseModel):
    id: UUID
    line_id: UUID | None
    input_type_1: str
    input_type_2: str
    output_type: str
    station_hint: UUID | None
    nominal_duration_sec: int
    anomaly_threshold_pct: int
    valid_from: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateProcessRequest(BaseModel):
    """Одна строка документации технолога."""

    line_id: UUID
    input_type_1: str = Field(min_length=1, max_length=50)
    input_type_2: str = Field(min_length=1, max_length=50)
    output_type: str = Field(min_length=1, max_length=50)
    station_hint: UUID = Field(description="Станок, выполняющий операцию (Решение №87)")
    nominal_duration_sec: int = Field(gt=0, description="Норматив времени, секунды")
    anomaly_threshold_pct: int = Field(default=30, ge=0, le=500)


class UpdateProcessRequest(BaseModel):
    """Частичное обновление. Незаданные поля не меняются."""

    input_type_1: str | None = Field(default=None, min_length=1, max_length=50)
    input_type_2: str | None = Field(default=None, min_length=1, max_length=50)
    output_type: str | None = Field(default=None, min_length=1, max_length=50)
    station_hint: UUID | None = None
    nominal_duration_sec: int | None = Field(default=None, gt=0)
    anomaly_threshold_pct: int | None = Field(default=None, ge=0, le=500)


class TopologyNodeResponse(BaseModel):
    station_id: UUID
    station_name: str
    level: int
    process_ids: list[UUID]
    input_types: list[str]
    output_types: list[str]
    fed_by: list[UUID]
    feeds_into: list[UUID]


class TopologyResponse(BaseModel):
    line_id: UUID
    line_name: str
    nodes: list[TopologyNodeResponse]
    base_part_types: list[str]
    final_output_types: list[str]
    max_level: int
    warnings: list[str]


# === Helpers ===


async def _require_line(session: AsyncSession, line_id: UUID) -> Line:
    line = (
        await session.execute(select(Line).where(Line.id == line_id))
    ).scalar_one_or_none()
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Line {line_id} not found")
    return line


async def _require_station_on_line(
    session: AsyncSession, station_id: UUID, line_id: UUID
) -> Station:
    station = (
        await session.execute(select(Station).where(Station.id == station_id))
    ).scalar_one_or_none()
    if station is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Station {station_id} not found")
    if station.line_id != line_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Station {station.name!r} belongs to another line",
        )
    return station


def _validate_inputs(input_1: str, input_2: str, output: str) -> None:
    """Операция сводит ПАРУ разных деталей в одну (Логика работы, п. 1)."""
    if input_1 == input_2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Входящие типы деталей должны отличаться",
        )
    if output in (input_1, input_2):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Выход операции не может совпадать с её входом",
        )


# === Endpoints ===


@router.get(
    "",
    response_model=list[ProcessResponse],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def list_processes(
    line_id: UUID | None = Query(default=None, description="Фильтр по линии"),
    station_id: UUID | None = Query(default=None, description="Фильтр по станку"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Process]:
    """Справочник процессов с фильтрами."""
    query = select(Process)
    if line_id is not None:
        query = query.where(Process.line_id == line_id)
    if station_id is not None:
        query = query.where(Process.station_hint == station_id)
    query = (
        query.order_by(Process.output_type, Process.valid_from.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(query)).scalars().all())


@router.post(
    "",
    response_model=ProcessResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def create_process(
    body: CreateProcessRequest,
    session: AsyncSession = Depends(get_session),
) -> Process:
    """Добавить операцию в справочник.

    Дубли по (линия, пара входов, выход) не блокируются намеренно: это
    механизм версионирования норматива (Решения №34-35) — новая строка с
    более свежим `valid_from` перекрывает старую, а история сохраняется.
    """
    await _require_line(session, body.line_id)
    await _require_station_on_line(session, body.station_hint, body.line_id)
    _validate_inputs(body.input_type_1, body.input_type_2, body.output_type)

    process = Process(**body.model_dump())
    session.add(process)
    await session.commit()
    await session.refresh(process)
    return process


@router.patch(
    "/{process_id}",
    response_model=ProcessResponse,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def update_process(
    process_id: UUID,
    body: UpdateProcessRequest,
    session: AsyncSession = Depends(get_session),
) -> Process:
    """Правка строки справочника (опечатка, уточнение норматива)."""
    process = (
        await session.execute(select(Process).where(Process.id == process_id))
    ).scalar_one_or_none()
    if process is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Process {process_id} not found")

    patch = body.model_dump(exclude_unset=True)

    if "station_hint" in patch and patch["station_hint"] is not None:
        if process.line_id is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "У процесса не задана линия — станок привязать нельзя",
            )
        await _require_station_on_line(session, patch["station_hint"], process.line_id)

    _validate_inputs(
        patch.get("input_type_1", process.input_type_1),
        patch.get("input_type_2", process.input_type_2),
        patch.get("output_type", process.output_type),
    )

    for key, value in patch.items():
        setattr(process, key, value)

    await session.commit()
    await session.refresh(process)
    return process


@router.delete(
    "/{process_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def delete_process(
    process_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Удалить ошибочно заведённую строку.

    Внимание: watchdog берёт норматив по `valid_from` на момент события,
    поэтому удаление строки меняет трактовку уже случившихся операций.
    Для планового изменения норматива правильнее добавить новую версию.
    """
    process = (
        await session.execute(select(Process).where(Process.id == process_id))
    ).scalar_one_or_none()
    if process is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Process {process_id} not found")
    await session.delete(process)
    await session.commit()


@router.get(
    "/topology/{line_id}",
    response_model=TopologyResponse,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def get_topology(
    line_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TopologyResponse:
    """Граф сборки линии, выведенный из справочника (Решение №86).

    Отдаёт узлы с уровнями и связями — фронт раскладывает их ярусами
    и рисует пирамиду. Форма графа произвольная: несимметричные ветки и
    параллельные станки допустимы (Решение №88).
    """
    line = await _require_line(session, line_id)

    processes = list(
        (
            await session.execute(select(Process).where(Process.line_id == line_id))
        ).scalars().all()
    )
    stations = list(
        (
            await session.execute(select(Station).where(Station.line_id == line_id))
        ).scalars().all()
    )
    station_names = {s.id: s.name for s in stations}

    topo = build_topology(
        [
            ProcessSpec(
                id=p.id,
                input_type_1=p.input_type_1,
                input_type_2=p.input_type_2,
                output_type=p.output_type,
                station_id=p.station_hint,
                nominal_duration_sec=p.nominal_duration_sec,
                anomaly_threshold_pct=p.anomaly_threshold_pct,
                valid_from=p.valid_from,
            )
            for p in processes
        ],
        station_names,
    )

    # Станки линии, не задействованные ни в одной операции — тоже сигнал.
    idle_stations = [
        s.name for s in stations if s.id not in {n.station_id for n in topo.nodes}
    ]
    if idle_stations:
        topo.warnings.append(
            "Станки без операций в справочнике: " + ", ".join(sorted(idle_stations))
        )

    return TopologyResponse(
        line_id=line.id,
        line_name=line.name,
        nodes=[
            TopologyNodeResponse(
                station_id=n.station_id,
                station_name=n.station_name,
                level=n.level,
                process_ids=n.process_ids,
                input_types=n.input_types,
                output_types=n.output_types,
                fed_by=n.fed_by,
                feeds_into=n.feeds_into,
            )
            for n in topo.nodes
        ],
        base_part_types=topo.base_part_types,
        final_output_types=topo.final_output_types,
        max_level=topo.max_level,
        warnings=topo.warnings,
    )
