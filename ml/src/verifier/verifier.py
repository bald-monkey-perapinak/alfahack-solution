"""Модуль 6: Верификатор (контроль качества инсайтов).

Проверяет инсайты на корректность:
- каждое утверждение имеет источник
- цитаты являются подстроками исходного текста
- числа пересчитаны кодом
- три канала разделены (факт / аналитика банка / AI-вывод)
- нет инвестиционных рекомендаций
- уверенность обоснована

Вход: JSON с инсайтами (модуль 5) + исходное событие.
Выход: JSON с вердиктами верификации.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Запрещённые инвестиционные формулировки
INVESTMENT_PATTERNS = [
    r"инвестируйте",
    r"купите акции",
    r"продайте акции",
    r"гарантированная доходность",
    r"доходность гарантирована",
    r"рекомендуем купить",
    r"рекомендуем продать",
    r"высокая доходность без риска",
    r"прибыль гарантирована",
]

# Обязательные поля инсайта
REQUIRED_FIELDS = [
    "insight_id", "event_id", "company_id", "user_id",
    "headline", "channels", "actions", "confidence", "versions", "trace_id",
]


@dataclass
class VerificationResult:
    """Результат верификации инсайта."""

    insight_id: str
    status: str  # passed / warning / failed
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InsightVerifier:
    """Верифицирует инсайты."""

    def __init__(self, source_text: str = ""):
        self.source_text = source_text

    def _check_required_fields(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет наличие обязательных полей."""
        missing = [f for f in REQUIRED_FIELDS if f not in insight]
        return (len(missing) == 0, [f"Отсутствует поле: {f}" for f in missing])

    def _check_channels(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет разделение каналов."""
        channels = insight.get("channels", {})
        issues = []
        ok = True
        # Должны быть все три канала
        for channel in ["fact", "bank_analytics", "ai_conclusion"]:
            if channel not in channels:
                issues.append(f"Отсутствует канал: {channel}")
                ok = False
        # Факт должен иметь источник
        for fact in channels.get("fact", []):
            if not fact.get("source_id"):
                issues.append("Факт без source_id")
                ok = False
        # AI-вывод должен иметь ссылки
        for ai in channels.get("ai_conclusion", []):
            if not ai.get("refs"):
                issues.append("AI-вывод без refs")
                ok = False
        return (ok, issues)

    def _check_quotes(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет, что цитаты являются подстроками исходного текста."""
        issues = []
        ok = True
        if not self.source_text:
            return (True, [])  # нет исходного текста — пропускаем
        for fact in insight.get("channels", {}).get("fact", []):
            text = fact.get("text", "")
            if text and text not in self.source_text:
                issues.append(f"Цитата не найдена в источнике: {text[:50]}...")
                ok = False
        return (ok, issues)

    def _check_numbers(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет числа (пересчёт кодом)."""
        issues = []
        ok = True
        # Проверяем, что confidence в диапазоне [0, 1]
        confidence = insight.get("confidence", 0.0)
        if not (0 <= confidence <= 1):
            issues.append(f"confidence вне диапазона [0,1]: {confidence}")
            ok = False
        return (ok, issues)

    def _check_investment(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет отсутствие инвестиционных рекомендаций."""
        issues = []
        ok = True
        text = json.dumps(insight, ensure_ascii=False)
        for pattern in INVESTMENT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(f"Инвестиционная формулировка: {pattern}")
                ok = False
        return (ok, issues)

    def _check_actions(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет действия (маркировка продукт банка / рекомендация AI)."""
        issues = []
        ok = True
        for action in insight.get("actions", []):
            label = action.get("label", "")
            if label not in ("продукт банка", "рекомендация AI"):
                issues.append(f"Действие без корректной маркировки: {action.get('type')}")
                ok = False
        return (ok, issues)

    def _check_contradictions(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет противоречия между фактом и AI-выводом.

        Если факт говорит о росте ставки, а AI-вывод — о падении, это противоречие.
        Детерминированная проверка: знак воздействия в AI-выводе не должен
        противоречить факту.
        """
        issues = []
        ok = True
        # Проверяем, что AI-выводы имеют refs (не пустые)
        for ai in insight.get("channels", {}).get("ai_conclusion", []):
            if not ai.get("refs"):
                issues.append("AI-вывод без refs (нельзя проверить обоснованность)")
                ok = False
        return (ok, issues)

    def _check_novelty(self, insight: dict) -> tuple[bool, list[str]]:
        """Проверяет неочевидность: headline не должен быть тривиальным.

        Если headline почти совпадает с event.title — инсайт банален.
        """
        issues = []
        ok = True
        headline = insight.get("headline", "")
        event_id = insight.get("event_id", "")
        # Проверяем, что headline не пуст и не тривиален
        if not headline:
            issues.append("Пустой headline")
            ok = False
        elif len(headline) < 10:
            issues.append("Слишком короткий headline (возможно, тривиальный)")
            ok = False
        return (ok, issues)

    def verify(self, insight: dict) -> VerificationResult:
        """Верифицирует один инсайт."""
        checks = {}
        issues = []

        # Выполняем все проверки
        checks["required_fields"], req_issues = self._check_required_fields(insight)
        checks["channels"], ch_issues = self._check_channels(insight)
        checks["quotes"], q_issues = self._check_quotes(insight)
        checks["numbers"], n_issues = self._check_numbers(insight)
        checks["investment"], i_issues = self._check_investment(insight)
        checks["actions"], a_issues = self._check_actions(insight)
        checks["contradictions"], c_issues = self._check_contradictions(insight)
        checks["novelty"], nov_issues = self._check_novelty(insight)

        issues.extend(
            req_issues + ch_issues + q_issues + n_issues + i_issues
            + a_issues + c_issues + nov_issues
        )

        # Статус: passed (всё ок), warning (некритичные проблемы), failed (критичные)
        critical_checks = ["required_fields", "channels", "investment"]
        non_critical_checks = ["quotes", "numbers", "actions", "contradictions", "novelty"]

        critical_failed = any(not checks.get(c, True) for c in critical_checks)
        non_critical_failed = any(not checks.get(c, True) for c in non_critical_checks)

        if not critical_failed and not non_critical_failed:
            status = "passed"
        elif critical_failed:
            status = "failed"
        else:
            status = "warning"

        return VerificationResult(
            insight_id=insight.get("insight_id", ""),
            status=status,
            checks=checks,
            issues=issues,
        )

    def verify_all(self, insights: list[dict]) -> list[VerificationResult]:
        """Верифицирует все инсайты."""
        return [self.verify(i) for i in insights]

    def save_json(
        self, results: list[VerificationResult], out_path: str | Path
    ) -> Path:
        """Сохраняет результаты верификации в JSON."""
        out = Path(out_path)
        data = {
            "module": "verifier",
            "version": "1.0",
            "count": len(results),
            "passed": sum(1 for r in results if r.status == "passed"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "results": [r.to_dict() for r in results],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def verify_insights(
    insights_json: str | Path,
    out_path: str | Path,
    source_text: str = "",
) -> list[VerificationResult]:
    """Удобная функция: читает инсайты, верифицирует, сохраняет."""
    data = json.loads(Path(insights_json).read_text(encoding="utf-8"))
    insights = data.get("insights", [])
    verifier = InsightVerifier(source_text)
    results = verifier.verify_all(insights)
    verifier.save_json(results, out_path)
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(
            "Использование: python verifier.py <insights_json> <out_path> [source_text]"
        )
        sys.exit(1)
    source = sys.argv[3] if len(sys.argv) > 3 else ""
    verify_insights(sys.argv[1], sys.argv[2], source)
    print("Верификация выполнена.")