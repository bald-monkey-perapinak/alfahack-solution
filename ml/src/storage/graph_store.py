"""Neo4j-адаптер: граф факторов, компаний, событий.

Подключается к Neo4j (если сервер доступен) или использует JSON-fallback
(когда сервер недоступен). Позволяет хранить и запрашивать граф.

Режимы:
- neo4j: реальное подключение к Neo4j
- json: fallback на JSON-файл (когда Neo4j недоступен)

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GraphStore:
    """Хранилище графа (Neo4j или JSON-fallback)."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        json_path: str | Path | None = None,
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.json_path = Path(json_path) if json_path else None
        self._driver = None
        self._neo4j_available = None

    def _check_neo4j(self) -> bool:
        """Проверяет доступность Neo4j."""
        if self._neo4j_available is None:
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    self.uri, auth=(self.user, self.password)
                )
                driver.verify_connectivity()
                driver.close()
                self._neo4j_available = True
            except Exception:
                self._neo4j_available = False
        return self._neo4j_available

    def _get_driver(self):
        """Возвращает драйвер Neo4j."""
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
        return self._driver

    # --- Запись ---

    def save_factor_graph(self, factor_graph: dict, version: str = "v1") -> bool:
        """Сохраняет граф факторов в Neo4j (или JSON)."""
        if self._check_neo4j():
            return self._save_factor_graph_neo4j(factor_graph, version)
        return self._save_json({"type": "factor_graph", "version": version, "data": factor_graph})

    def _save_factor_graph_neo4j(self, factor_graph: dict, version: str) -> bool:
        """Сохраняет граф факторов в Neo4j."""
        driver = self._get_driver()
        with driver.session() as session:
            # Очищаем старые узлы факторов
            session.run("MATCH (f:Factor) DETACH DELETE f")
            for source, edges in factor_graph.items():
                session.run(
                    "MERGE (f:Factor {name: $name})",
                    name=source,
                )
                for target, edge in edges.items():
                    session.run(
                        """
                        MATCH (a:Factor {name: $source})
                        MERGE (b:Factor {name: $target})
                        MERGE (a)-[r:INFLUENCES {version: $version}]->(b)
                        SET r.sign = $sign, r.strength = $strength
                        """,
                        source=source,
                        target=target,
                        version=version,
                        sign=edge["sign"],
                        strength=edge["strength"],
                    )
        return True

    def save_company(self, company: dict) -> bool:
        """Сохраняет компанию в Neo4j (или JSON)."""
        if self._check_neo4j():
            return self._save_company_neo4j(company)
        return self._save_json({"type": "company", "data": company})

    def _save_company_neo4j(self, company: dict) -> bool:
        """Сохраняет компанию в Neo4j."""
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (c:Company {id: $id})
                SET c.revenue = $revenue, c.region = $region
                """,
                id=company.get("company_id", ""),
                revenue=company.get("observed", {}).get("revenue"),
                region=company.get("observed", {}).get("region"),
            )
        return True

    def save_event(self, event: dict) -> bool:
        """Сохраняет событие в Neo4j (или JSON)."""
        if self._check_neo4j():
            return self._save_event_neo4j(event)
        return self._save_json({"type": "event", "data": event})

    def _save_event_neo4j(self, event: dict) -> bool:
        """Сохраняет событие в Neo4j."""
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (e:Event {id: $id})
                SET e.type = $type, e.title = $title
                """,
                id=event.get("event_id", ""),
                type=event.get("event_type", ""),
                title=event.get("title", ""),
            )
        return True

    # --- Чтение ---

    def get_factor_graph(self) -> dict:
        """Возвращает граф факторов."""
        if self._check_neo4j():
            return self._get_factor_graph_neo4j()
        return self._load_json("factor_graph")

    def _get_factor_graph_neo4j(self) -> dict:
        """Возвращает граф факторов из Neo4j."""
        driver = self._get_driver()
        graph: dict[str, dict] = {}
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Factor)-[r:INFLUENCES]->(b:Factor)
                RETURN a.name AS source, b.name AS target, r.sign AS sign, r.strength AS strength
                """
            )
            for record in result:
                source = record["source"]
                target = record["target"]
                if source not in graph:
                    graph[source] = {}
                graph[source][target] = {
                    "sign": record["sign"],
                    "strength": record["strength"],
                }
        return graph

    # --- JSON fallback ---

    def _save_json(self, data: dict) -> bool:
        """Сохраняет данные в JSON-файл (fallback)."""
        if self.json_path is None:
            return False
        # Загружаем существующие данные
        existing = {}
        if self.json_path.exists():
            try:
                existing = json.loads(self.json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        # Добавляем/обновляем
        key = data.get("type", "data")
        existing[key] = data.get("data", data)
        self.json_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    def _load_json(self, key: str) -> dict:
        """Загружает данные из JSON-файла (fallback)."""
        if self.json_path is None or not self.json_path.exists():
            return {}
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
            return data.get(key, {})
        except json.JSONDecodeError:
            return {}

    def close(self):
        """Закрывает соединение."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Использование: python graph_store.py <json_path>")
        sys.exit(1)
    store = GraphStore(json_path=sys.argv[1])
    print(f"Neo4j доступен: {store._check_neo4j()}")
    store.close()