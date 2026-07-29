"""Вывод топологии сборки из справочника процессов.

Ноу-хау: топология нигде не хранится явно — она **выводится** из строк
`processes` (перенесённой документации технолога). Ребро возникает там, где
выход одного станка является входом другого.

См. Обсидиан → Решения №85-89:
- изделие / сборочный поток = линия (`Line`);
- `station_hint` обязателен для участия в топологии;
- структура — направленный граф по уровням, НЕ строгое бинарное дерево
  (одну операцию могут выполнять несколько станков параллельно).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ProcessSpec:
    """Строка справочника в виде, достаточном для построения графа."""

    id: UUID
    input_type_1: str
    input_type_2: str
    output_type: str
    station_id: UUID | None
    nominal_duration_sec: int
    anomaly_threshold_pct: int
    valid_from: datetime


@dataclass
class TopologyNode:
    """Станок как узел графа сборки."""

    station_id: UUID
    station_name: str
    level: int = 0
    process_ids: list[UUID] = field(default_factory=list)
    input_types: list[str] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)
    #: станки, чью продукцию потребляет этот узел
    fed_by: list[UUID] = field(default_factory=list)
    #: станки, которые потребляют продукцию этого узла
    feeds_into: list[UUID] = field(default_factory=list)


@dataclass
class Topology:
    nodes: list[TopologyNode] = field(default_factory=list)
    #: типы деталей, которые никто не производит — приходят со склада (листья)
    base_part_types: list[str] = field(default_factory=list)
    #: типы, которые никто не потребляет — выход линии (вершина)
    final_output_types: list[str] = field(default_factory=list)
    #: максимальный уровень (0 — только входные станки)
    max_level: int = 0
    #: проблемы конфигурации, которые стоит показать в UI
    warnings: list[str] = field(default_factory=list)


def _latest_by_valid_from(processes: list[ProcessSpec]) -> list[ProcessSpec]:
    """Оставить актуальную версию каждой операции.

    Версионирование норматива (Решения №34-35): одна и та же операция
    может присутствовать несколькими строками с разными `valid_from`.
    Для топологии берём самую свежую по ключу (станок, входы, выход).
    """
    latest: dict[tuple, ProcessSpec] = {}
    for p in processes:
        # Пара входов неупорядочена: порядок сканирования не важен (Решение №17).
        inputs = tuple(sorted((p.input_type_1, p.input_type_2)))
        key = (p.station_id, inputs, p.output_type)
        current = latest.get(key)
        if current is None or p.valid_from > current.valid_from:
            latest[key] = p
    return list(latest.values())


def build_topology(
    processes: list[ProcessSpec],
    station_names: dict[UUID, str],
) -> Topology:
    """Построить граф сборки из справочника процессов.

    :param processes: строки справочника (уже отфильтрованные по линии)
    :param station_names: id → название станка, для подписи узлов
    """
    topo = Topology()

    actual = _latest_by_valid_from(processes)

    # Процессы без станка в топологию не попадают (Решение №87).
    orphans = [p for p in actual if p.station_id is None]
    if orphans:
        topo.warnings.append(
            f"Процессов без указанного станка: {len(orphans)}. "
            "Они не попали в схему — укажите станок в справочнике."
        )
    bound = [p for p in actual if p.station_id is not None]

    if not bound:
        return topo

    # --- 1. Собираем узлы ---
    nodes: dict[UUID, TopologyNode] = {}
    for p in bound:
        sid = p.station_id
        assert sid is not None  # отфильтровано выше
        node = nodes.get(sid)
        if node is None:
            node = TopologyNode(
                station_id=sid,
                station_name=station_names.get(sid, "(удалённый станок)"),
            )
            nodes[sid] = node
        node.process_ids.append(p.id)
        for t in (p.input_type_1, p.input_type_2):
            if t not in node.input_types:
                node.input_types.append(t)
        if p.output_type not in node.output_types:
            node.output_types.append(p.output_type)

    # --- 2. Кто что производит и потребляет ---
    # Один тип может производиться несколькими станками (Решение №88).
    producers: dict[str, list[UUID]] = {}
    consumers: dict[str, list[UUID]] = {}
    for node in nodes.values():
        for t in node.output_types:
            producers.setdefault(t, []).append(node.station_id)
        for t in node.input_types:
            consumers.setdefault(t, []).append(node.station_id)

    # --- 3. Рёбра: производитель → потребитель ---
    for part_type, consumer_ids in consumers.items():
        for producer_id in producers.get(part_type, []):
            for consumer_id in consumer_ids:
                if producer_id == consumer_id:
                    continue  # станок кормит сам себя — не ребро
                producer = nodes[producer_id]
                consumer = nodes[consumer_id]
                if consumer_id not in producer.feeds_into:
                    producer.feeds_into.append(consumer_id)
                if producer_id not in consumer.fed_by:
                    consumer.fed_by.append(producer_id)

    # --- 4. Листья и вершина ---
    topo.base_part_types = sorted(t for t in consumers if t not in producers)
    topo.final_output_types = sorted(t for t in producers if t not in consumers)

    if not topo.final_output_types:
        topo.warnings.append(
            "Не найдено конечное изделие: каждый выход кем-то потребляется. "
            "Проверьте справочник на замкнутый цикл."
        )

    # --- 5. Уровни: длина самого длинного пути от базовых деталей ---
    _assign_levels(nodes, topo)

    topo.nodes = sorted(nodes.values(), key=lambda n: (n.level, n.station_name))
    topo.max_level = max((n.level for n in topo.nodes), default=0)
    return topo


def _assign_levels(nodes: dict[UUID, TopologyNode], topo: Topology) -> None:
    """Расставить уровни итеративной релаксацией.

    Уровень = 1 + максимальный уровень питающих станков; узел без питающих
    станков (работает только на базовых деталях) получает 0.

    Используется релаксация, а не топологическая сортировка: справочник
    заполняется человеком, и цикл в данных — реальный сценарий ошибки.
    Ограничение по числу проходов гарантирует останов, а недосходимость
    означает цикл — сообщаем о нём вместо падения.
    """
    for node in nodes.values():
        node.level = 0

    max_passes = len(nodes) + 1
    for _ in range(max_passes):
        changed = False
        for node in nodes.values():
            if not node.fed_by:
                continue
            candidate = max(nodes[p].level for p in node.fed_by) + 1
            if candidate > node.level:
                node.level = candidate
                changed = True
        if not changed:
            return

    topo.warnings.append(
        "Обнаружен циклический маршрут в справочнике — уровни станков "
        "рассчитаны приблизительно. Проверьте, что выход операции не "
        "возвращается на её же вход."
    )
