"""图算法的纯 Python 实现。边一律按无向处理。

weight 是关系强度，越大越近。它不是距离，不能沿路径相加。
加权路径取整条链上最弱的一环，并让这一环尽可能强。
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque


def unique_pairs(edges) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        left, right = edge[0], edge[1]
        if left != right:
            pairs.add(tuple(sorted((left, right))))
    return pairs


def neighbor_sets(nodes, edges) -> dict[str, set[str]]:
    adjacent: dict[str, set[str]] = {node: set() for node in nodes}
    for left, right in unique_pairs(edges):
        adjacent.setdefault(left, set()).add(right)
        adjacent.setdefault(right, set()).add(left)
    return adjacent


def _strength_graph(nodes, edges) -> dict[str, dict[str, float]]:
    adjacent: dict[str, dict[str, float]] = {node: {} for node in nodes}
    for edge in edges:
        left, right, weight = edge[0], edge[1], float(edge[2])
        if left == right:
            continue
        adjacent.setdefault(left, {})
        adjacent.setdefault(right, {})
        if right not in adjacent[left] or weight > adjacent[left][right]:
            adjacent[left][right] = weight
            adjacent[right][left] = weight
    return adjacent


def widest_path(nodes, edges, source: str, target: str):
    """返回 (路径, 最弱环节的强度)。不可达时返回 (None, None)。

    强度相同的两条路径里，保留跳数更少的那条。
    """
    names = set(nodes)
    if source not in names or target not in names:
        return None, None
    if source == target:
        return [source], 0.0
    adjacent = _strength_graph(nodes, edges)
    best_strength = {source: math.inf}
    best_hops = {source: 0}
    parent: dict[str, str | None] = {source: None}
    settled: set[str] = set()
    heap: list[tuple[float, int, str]] = [(-math.inf, 0, source)]
    while heap:
        negative, hops, node = heapq.heappop(heap)
        if node in settled or hops != best_hops.get(node):
            continue
        settled.add(node)
        if node == target:
            break
        strength = best_strength[node]
        for nxt, weight in adjacent.get(node, {}).items():
            if nxt in settled:
                continue
            bottleneck = weight if math.isinf(strength) else min(strength, weight)
            nxt_hops = hops + 1
            old = best_strength.get(nxt, -1.0)
            old_hops = best_hops.get(nxt, 10**9)
            if bottleneck < old or (bottleneck == old and nxt_hops >= old_hops):
                continue
            best_strength[nxt] = bottleneck
            best_hops[nxt] = nxt_hops
            parent[nxt] = node
            heapq.heappush(heap, (-bottleneck, nxt_hops, nxt))
    if target not in parent:
        return None, None
    path: list[str] = []
    cursor: str | None = target
    while cursor is not None:
        path.append(cursor)
        cursor = parent[cursor]
    path.reverse()
    return path, best_strength[target]


def shortest_hops(nodes, edges, source: str, target: str):
    names = set(nodes)
    if source not in names or target not in names:
        return None
    if source == target:
        return 0
    adjacent = neighbor_sets(nodes, edges)
    seen = {source}
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    while queue:
        node, hops = queue.popleft()
        for nxt in adjacent.get(node, ()):
            if nxt in seen:
                continue
            if nxt == target:
                return hops + 1
            seen.add(nxt)
            queue.append((nxt, hops + 1))
    return None


def pagerank(nodes, edges, damping: float = 0.85, iterations: int = 20) -> dict[str, float]:
    """无向无权 PageRank，分数总和为 1。"""
    names = list(dict.fromkeys(nodes))
    count = len(names)
    if count == 0:
        return {}
    adjacent = neighbor_sets(names, edges)
    rank = {name: 1.0 / count for name in names}
    for _ in range(iterations):
        dangling = sum(rank[name] for name in names if not adjacent[name])
        base = (1.0 - damping) / count
        share = damping * dangling / count
        updated = {}
        for name in names:
            incoming = 0.0
            for other in adjacent[name]:
                degree = len(adjacent[other])
                if degree:
                    incoming += rank[other] / degree
            updated[name] = base + share + damping * incoming
        rank = updated
    return rank


def label_propagation(nodes, edges, max_iter: int = 30) -> dict[str, int]:
    """异步标签传播。并列时优先保留自己的标签，否则取较小编号。"""
    names = list(dict.fromkeys(nodes))
    adjacent = neighbor_sets(names, edges)
    labels = {name: index for index, name in enumerate(sorted(names))}
    order = sorted(names)
    for _ in range(max_iter):
        changed = False
        for name in order:
            neighbors = adjacent.get(name, ())
            if not neighbors:
                continue
            counts: dict[int, int] = {}
            for other in neighbors:
                label = labels[other]
                counts[label] = counts.get(label, 0) + 1
            best_count = max(counts.values())
            candidates = [label for label, votes in counts.items() if votes == best_count]
            current = labels[name]
            chosen = current if current in candidates else min(candidates)
            if chosen != current:
                labels[name] = chosen
                changed = True
        if not changed:
            break
    return labels


def clustering_coefficient(nodes, edges) -> float:
    names = list(dict.fromkeys(nodes))
    if not names:
        return 0.0
    adjacent = neighbor_sets(names, edges)
    total = 0.0
    for name in names:
        neighbors = list(adjacent[name])
        degree = len(neighbors)
        if degree < 2:
            continue
        linked = 0
        for index, left in enumerate(neighbors):
            for right in neighbors[index + 1 :]:
                if right in adjacent[left]:
                    linked += 1
        total += linked / (degree * (degree - 1) / 2.0)
    return total / len(names)


def average_path_length(nodes, edges, sample: int | None = None, rng_seed: int = 0) -> float:
    """从若干起点做 BFS，对所有可达的有序点对取平均距离。"""
    names = list(dict.fromkeys(nodes))
    count = len(names)
    if count <= 1:
        return 0.0
    adjacent = neighbor_sets(names, edges)
    ordered = sorted(names)
    width = count if sample is None else min(sample, count)
    if width >= count:
        sources = ordered
    else:
        sources = random.Random(rng_seed).sample(ordered, width)
    total = 0
    pairs = 0
    for source in sources:
        distance = {source: 0}
        queue: deque[str] = deque([source])
        while queue:
            node = queue.popleft()
            for nxt in adjacent.get(node, ()):
                if nxt in distance:
                    continue
                distance[nxt] = distance[node] + 1
                queue.append(nxt)
        for target, hops in distance.items():
            if target == source:
                continue
            total += hops
            pairs += 1
    if pairs == 0:
        return 0.0
    return total / pairs


def small_world(nodes, edges, sample: int = 40) -> dict:
    names = list(dict.fromkeys(nodes))
    count = len(names)
    pairs = unique_pairs(edges)
    edge_count = len(pairs)
    avg_degree = (2.0 * edge_count / count) if count else 0.0
    random_clustering = (avg_degree / count) if count else 0.0
    if count > 1 and avg_degree > 1:
        random_path = math.log(count) / math.log(avg_degree)
    else:
        random_path = None
    used = min(sample, count) if count else 0
    clustering = clustering_coefficient(names, edges)
    path_length = average_path_length(names, edges, sample=used, rng_seed=0)
    clustering_ratio = (clustering / random_clustering) if random_clustering else None
    path_ratio = (
        path_length / random_path if random_path not in (None, 0) else None
    )
    index = (
        clustering_ratio / path_ratio
        if clustering_ratio is not None and path_ratio not in (None, 0)
        else None
    )
    return {
        "nodes": count,
        "edges": edge_count,
        "avg_clustering": clustering,
        "avg_path_length": path_length,
        "random_clustering": random_clustering,
        "random_avg_path_length": random_path,
        "clustering_ratio": clustering_ratio,
        "path_ratio": path_ratio,
        "small_world_index": index,
        "is_small_world": bool(index is not None and index > 1),
        "sample": used,
    }
