"""Qdrant-адаптер: векторное хранилище для новостей, событий, утверждений ЦМИ.

Подключается к Qdrant (если сервер доступен) или использует JSON-fallback
(когда сервер недоступен). Позволяет хранить и искать векторы.

Режимы:
- qdrant: реальное подключение к Qdrant
- json: fallback на JSON-файл (когда Qdrant недоступен)

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class VectorStore:
    """Векторное хранилище (Qdrant или JSON-fallback)."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "news",
        json_path: str | Path | None = None,
    ):
        self.url = url
        self.collection = collection
        self.json_path = Path(json_path) if json_path else None
        self._client = None
        self._qdrant_available = None

    def _check_qdrant(self) -> bool:
        """Проверяет доступность Qdrant."""
        if self._qdrant_available is None:
            try:
                from qdrant_client import QdrantClient
                client = QdrantClient(url=self.url)
                client.get_collections()
                self._qdrant_available = True
            except Exception:
                self._qdrant_available = False
        return self._qdrant_available

    def _get_client(self):
        """Возвращает Qdrant-клиент."""
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(url=self.url)
        return self._client

    def _ensure_collection(self, vector_size: int = 1024):
        """Создаёт коллекцию, если её нет."""
        from qdrant_client.models import Distance, VectorParams
        client = self._get_client()
        collections = [c.name for c in client.get_collections().collections]
        if self.collection not in collections:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    # --- Запись ---

    def upsert(self, points: list[dict]) -> bool:
        """Сохраняет точки (id, vector, payload) в Qdrant (или JSON)."""
        if self._check_qdrant():
            return self._upsert_qdrant(points)
        return self._save_json(points)

    def _upsert_qdrant(self, points: list[dict]) -> bool:
        """Сохраняет точки в Qdrant."""
        from qdrant_client.models import PointStruct
        client = self._get_client()
        # Определяем размерность по первому вектору
        if points:
            vector_size = len(points[0].get("vector", []))
            self._ensure_collection(vector_size)
            structs = [
                PointStruct(
                    id=point.get("id", i),
                    vector=point.get("vector", []),
                    payload=point.get("payload", {}),
                )
                for i, point in enumerate(points)
            ]
            client.upsert(collection_name=self.collection, points=structs)
        return True

    # --- Чтение ---

    def search(self, vector: list[float], top_k: int = 10) -> list[dict]:
        """Ищет ближайшие точки по вектору."""
        if self._check_qdrant():
            return self._search_qdrant(vector, top_k)
        return self._search_json(vector, top_k)

    def _search_qdrant(self, vector: list[float], top_k: int) -> list[dict]:
        """Ищет в Qdrant."""
        client = self._get_client()
        results = client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
        )
        return [
            {"id": r.id, "score": r.score, "payload": r.payload}
            for r in results
        ]

    # --- JSON fallback ---

    def _save_json(self, points: list[dict]) -> bool:
        """Сохраняет точки в JSON-файл (fallback)."""
        if self.json_path is None:
            return False
        existing = []
        if self.json_path.exists():
            try:
                existing = json.loads(self.json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []
        existing.extend(points)
        self.json_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    def _search_json(self, vector: list[float], top_k: int) -> list[dict]:
        """Ищет в JSON-fallback (косинусная близость)."""
        if self.json_path is None or not self.json_path.exists():
            return []
        try:
            points = json.loads(self.json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        scored = []
        for point in points:
            v = point.get("vector", [])
            if len(v) != len(vector):
                continue
            score = self._cosine(vector, v)
            scored.append({"id": point.get("id"), "score": score, "payload": point.get("payload", {})})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _cosine(self, a: list[float], b: list[float]) -> float:
        """Косинусная близость."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def close(self):
        """Закрывает соединение."""
        self._client = None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Использование: python vector_store.py <json_path>")
        sys.exit(1)
    store = VectorStore(json_path=sys.argv[1])
    print(f"Qdrant доступен: {store._check_qdrant()}")
    store.close()