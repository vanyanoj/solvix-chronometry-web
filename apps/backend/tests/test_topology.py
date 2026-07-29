"""Тесты вывода топологии сборки из справочника процессов.

Покрывают `core/topology.py` — Решения №85-89. БД не нужна: функция
чистая, работает на списке `ProcessSpec`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from solvix_chronometry.core.topology import ProcessSpec, build_topology

NOW = datetime.now(timezone.utc)


@pytest.fixture
def stations() -> dict[int, uuid.UUID]:
    """Шесть станков с предсказуемыми номерами."""
    return {n: uuid.uuid4() for n in range(1, 7)}


@pytest.fixture
def names(stations: dict[int, uuid.UUID]) -> dict[uuid.UUID, str]:
    return {sid: f"Станок {n}" for n, sid in stations.items()}


def spec(
    station_id: uuid.UUID | None,
    input_1: str,
    input_2: str,
    output: str,
    *,
    valid_from: datetime = NOW,
) -> ProcessSpec:
    return ProcessSpec(
        id=uuid.uuid4(),
        input_type_1=input_1,
        input_type_2=input_2,
        output_type=output,
        station_id=station_id,
        nominal_duration_sec=120,
        anomaly_threshold_pct=30,
        valid_from=valid_from,
    )


def level_of(topo, station_name: str) -> int:
    return next(n.level for n in topo.nodes if n.station_name == station_name)


def node_of(topo, station_name: str):
    return next(n for n in topo.nodes if n.station_name == station_name)


# === Классическая пирамида ===


def test_pyramid_four_stations_levels(stations, names):
    """Пилотная схема: 4 станка, два входных → промежуточный → финал."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "D", "E", "F"),
            spec(stations[3], "C", "F", "H"),
            spec(stations[4], "H", "G", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert len(topo.nodes) == 4
    assert level_of(topo, "Станок 1") == 0
    assert level_of(topo, "Станок 2") == 0
    assert level_of(topo, "Станок 3") == 1
    assert level_of(topo, "Станок 4") == 2
    assert topo.max_level == 2
    assert topo.warnings == []


def test_pyramid_edges(stations, names):
    """Рёбра идут от производителя к потребителю."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "D", "E", "F"),
            spec(stations[3], "C", "F", "H"),
        ],
        names,
    )

    st3 = node_of(topo, "Станок 3")
    assert set(st3.fed_by) == {stations[1], stations[2]}
    assert st3.feeds_into == []

    st1 = node_of(topo, "Станок 1")
    assert st1.fed_by == []
    assert st1.feeds_into == [stations[3]]


def test_base_and_final_types(stations, names):
    """Листья — что никто не производит, вершина — что никто не потребляет."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "D", "E", "F"),
            spec(stations[3], "C", "F", "H"),
            spec(stations[4], "H", "G", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert topo.base_part_types == ["A", "B", "D", "E", "G"]
    assert topo.final_output_types == ["ИЗДЕЛИЕ"]


# === Несимметричные схемы ===


def test_asymmetric_chain_five_stations(stations, names):
    """Пять станков цепочкой: каждый берёт выход предыдущего + базовую деталь.

    Проверяет ключевое требование Решения №88: укладка не завязана на
    «ровно два потомка», форма дерева произвольная.
    """
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "E"),
            spec(stations[3], "E", "F", "G"),
            spec(stations[4], "G", "H", "I"),
            spec(stations[5], "I", "J", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert [level_of(topo, f"Станок {n}") for n in range(1, 6)] == [0, 1, 2, 3, 4]
    assert topo.max_level == 4
    assert topo.warnings == []


def test_unbalanced_branches_take_longest_path(stations, names):
    """Уровень = ДЛИННЕЙШИЙ путь от базовых деталей, не кратчайший.

    Станок 4 питается от короткой ветки (станок 3, уровень 0) и длинной
    (станок 2, уровень 1) — должен встать на уровень 2, а не 1.
    """
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "E"),
            spec(stations[3], "F", "G", "H"),
            spec(stations[4], "E", "H", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert level_of(topo, "Станок 1") == 0
    assert level_of(topo, "Станок 2") == 1
    assert level_of(topo, "Станок 3") == 0
    assert level_of(topo, "Станок 4") == 2


# === Параллельные станки (Решение №88) ===


def test_parallel_stations_same_operation(stations, names):
    """Два станка делают одну операцию — потребитель питается от обоих."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "E"),
            spec(stations[3], "C", "D", "E"),
            spec(stations[4], "E", "F", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    st4 = node_of(topo, "Станок 4")
    assert set(st4.fed_by) == {stations[2], stations[3]}

    st1 = node_of(topo, "Станок 1")
    assert set(st1.feeds_into) == {stations[2], stations[3]}

    assert level_of(topo, "Станок 2") == 1
    assert level_of(topo, "Станок 3") == 1
    assert level_of(topo, "Станок 4") == 2
    assert topo.warnings == []


def test_station_with_multiple_operations(stations, names):
    """Один станок выполняет несколько разных операций."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[1], "D", "E", "F"),
            spec(stations[2], "C", "F", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    st1 = node_of(topo, "Станок 1")
    assert len(st1.process_ids) == 2
    assert set(st1.input_types) == {"A", "B", "D", "E"}
    assert set(st1.output_types) == {"C", "F"}
    assert len(topo.nodes) == 2


# === Версионирование норматива (Решения №34-35) ===


def test_versioned_process_collapses_to_latest(stations, names):
    """Две версии одной операции схлопываются в одну — берётся свежая."""
    old = NOW - timedelta(days=180)
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C", valid_from=old),
            spec(stations[1], "A", "B", "C", valid_from=NOW),
            spec(stations[2], "C", "D", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert len(node_of(topo, "Станок 1").process_ids) == 1


def test_input_pair_order_does_not_matter(stations, names):
    """`A+B` и `B+A` — одна операция (Решение №17: порядок сканов не важен)."""
    old = NOW - timedelta(days=10)
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C", valid_from=old),
            spec(stations[1], "B", "A", "C", valid_from=NOW),
        ],
        names,
    )

    assert len(node_of(topo, "Станок 1").process_ids) == 1


def test_different_operations_on_same_station_not_collapsed(stations, names):
    """Разные выходы на одном станке — разные операции, не схлопываются."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[1], "A", "B", "D"),
        ],
        names,
    )

    assert len(node_of(topo, "Станок 1").process_ids) == 2


# === Ошибки конфигурации ===


def test_process_without_station_is_skipped_with_warning(stations, names):
    """Операция без станка в топологию не попадает (Решение №87)."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(None, "C", "D", "ИЗДЕЛИЕ"),
        ],
        names,
    )

    assert len(topo.nodes) == 1
    assert any("без указанного станка" in w for w in topo.warnings)


def test_cycle_detected_and_reported(stations, names):
    """Цикл в справочнике не роняет расчёт, а даёт предупреждение."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "E"),
            spec(stations[3], "E", "F", "A"),
        ],
        names,
    )

    assert any("циклический" in w.lower() for w in topo.warnings)
    assert len(topo.nodes) == 3


def test_no_final_output_reported(stations, names):
    """Если каждый выход кем-то потребляется — конечного изделия нет."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "A"),
        ],
        names,
    )

    assert topo.final_output_types == []
    assert any("конечное изделие" in w for w in topo.warnings)


def test_self_feeding_station_is_not_an_edge(stations, names):
    """Станок, потребляющий собственный выход, не получает ребро на себя."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[1], "C", "D", "E"),
        ],
        names,
    )

    st1 = node_of(topo, "Станок 1")
    assert stations[1] not in st1.fed_by
    assert stations[1] not in st1.feeds_into
    assert st1.level == 0


def test_unknown_station_name_falls_back(names):
    """Станок, которого нет в справочнике имён, получает заглушку."""
    ghost = uuid.uuid4()
    topo = build_topology([spec(ghost, "A", "B", "C")], names)

    assert topo.nodes[0].station_name == "(удалённый станок)"


# === Граничные случаи ===


def test_empty_processes_gives_empty_topology(names):
    topo = build_topology([], names)

    assert topo.nodes == []
    assert topo.max_level == 0
    assert topo.base_part_types == []
    assert topo.final_output_types == []
    assert topo.warnings == []


def test_only_orphan_processes(names):
    """Все операции без станка — узлов нет, но предупреждение есть."""
    topo = build_topology([spec(None, "A", "B", "C")], names)

    assert topo.nodes == []
    assert any("без указанного станка" in w for w in topo.warnings)


def test_single_station(stations, names):
    topo = build_topology([spec(stations[1], "A", "B", "ИЗДЕЛИЕ")], names)

    assert len(topo.nodes) == 1
    assert topo.nodes[0].level == 0
    assert topo.max_level == 0
    assert topo.base_part_types == ["A", "B"]
    assert topo.final_output_types == ["ИЗДЕЛИЕ"]


def test_disconnected_subgraphs(stations, names):
    """Две независимые ветки на одной линии — обе строятся."""
    topo = build_topology(
        [
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "C", "D", "ИЗДЕЛИЕ-1"),
            spec(stations[3], "X", "Y", "Z"),
            spec(stations[4], "Z", "W", "ИЗДЕЛИЕ-2"),
        ],
        names,
    )

    assert len(topo.nodes) == 4
    assert set(topo.final_output_types) == {"ИЗДЕЛИЕ-1", "ИЗДЕЛИЕ-2"}
    assert level_of(topo, "Станок 2") == 1
    assert level_of(topo, "Станок 4") == 1


def test_nodes_sorted_by_level(stations, names):
    """Узлы отсортированы по уровню — фронт раскладывает ярусами как есть."""
    topo = build_topology(
        [
            spec(stations[4], "H", "G", "ИЗДЕЛИЕ"),
            spec(stations[3], "C", "F", "H"),
            spec(stations[1], "A", "B", "C"),
            spec(stations[2], "D", "E", "F"),
        ],
        names,
    )

    levels = [n.level for n in topo.nodes]
    assert levels == sorted(levels)
