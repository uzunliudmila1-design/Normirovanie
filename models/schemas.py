"""Pydantic-схемы для всех этапов конвейера нормирования."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ─── Метрики LLM-вызовов ────────────────────────────────────────────────────

class LLMCallMetrics(BaseModel):
    """Метрики одного вызова LLM."""

    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0


class StageMetrics(BaseModel):
    """Метрики одного этапа конвейера."""

    stage: str = ""
    duration_ms: int = 0
    llm_calls: list[LLMCallMetrics] = Field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.llm_calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.llm_calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.llm_calls)

    def to_dict(self) -> dict:
        return {
            "этап": self.stage,
            "время_мс": self.duration_ms,
            "входные_токены": self.total_input_tokens,
            "выходные_токены": self.total_output_tokens,
            "стоимость_usd": round(self.total_cost_usd, 6),
            "вызовов_llm": len(self.llm_calls),
        }


class PipelineMetrics(BaseModel):
    """Суммарные метрики конвейера."""

    stages: list[StageMetrics] = Field(default_factory=list)
    total_duration_ms: int = 0

    @property
    def total_input_tokens(self) -> int:
        return sum(s.total_input_tokens for s in self.stages)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.total_output_tokens for s in self.stages)

    @property
    def total_cost_usd(self) -> float:
        return sum(s.total_cost_usd for s in self.stages)

    def to_dict(self) -> dict:
        return {
            "этапы": [s.to_dict() for s in self.stages],
            "итого": {
                "время_мс": self.total_duration_ms,
                "время_сек": round(self.total_duration_ms / 1000, 1),
                "входные_токены": self.total_input_tokens,
                "выходные_токены": self.total_output_tokens,
                "всего_токенов": self.total_input_tokens + self.total_output_tokens,
                "стоимость_usd": round(self.total_cost_usd, 6),
                "вызовов_llm": sum(len(s.llm_calls) for s in self.stages),
            },
        }


# ─── Этап 1: Факты из чертежа ─────────────────────────────────────────────────

class DrawingFacts(BaseModel):
    """Структурированные факты, извлечённые из чертежа/описания."""

    detail_type: str = Field(
        "", description="Тип детали: листовая, труба, профиль, вал, корпус, сборка, металлоконструкция"
    )
    detail_name: str = Field("", description="Название детали из чертежа")
    material: str = Field("", description="Марка материала (Ст3, 09Г2С, 12Х18Н10Т...)")
    mass_kg: Optional[float] = Field(None, description="Масса детали, кг")
    length_mm: Optional[float] = Field(None, description="Длина/габарит, мм")
    width_mm: Optional[float] = Field(None, description="Ширина, мм")
    height_mm: Optional[float] = Field(None, description="Высота, мм")
    thickness_mm: Optional[float] = Field(None, description="Толщина листа/стенки, мм — для правил резки")
    diameter_mm: Optional[float] = Field(None, description="Диаметр (для тел вращения), мм")

    # Признаки наличия операций
    has_cutting: bool = Field(False, description="Есть раскрой/резка листа/трубы")
    has_bending: bool = Field(False, description="Есть гибка")
    has_welding: bool = Field(False, description="Есть сварка")
    has_machining: bool = Field(False, description="Есть мехобработка (токарная, фрезерная, сверлильная...)")
    has_grinding: bool = Field(False, description="Есть шлифование")
    has_painting: bool = Field(False, description="Есть покраска/грунтовка")
    has_heat_treatment: bool = Field(False, description="Есть термообработка")
    has_assembly: bool = Field(False, description="Есть сборка")
    has_cleaning: bool = Field(False, description="Есть очистка (дробемёт, пескоструй)")
    has_straightening: bool = Field(False, description="Есть рихтовка/правка")
    has_holes: bool = Field(False, description="Есть отверстия (сверлильные операции)")
    has_threading: bool = Field(False, description="Есть резьба")
    has_slots: bool = Field(False, description="Есть пазы/шпонки")

    # Параметры точности
    min_tolerance_it: Optional[int] = Field(None, description="Самый точный квалитет (IT6, IT7...)")
    min_roughness_ra: Optional[float] = Field(None, description="Минимальная шероховатость Ra")
    has_geometric_tolerances: bool = Field(False, description="Есть допуски формы/расположения")

    # Сборочный чертёж
    is_assembly: bool = Field(False, description="True если это сборочный чертёж (СБ) — детали приходят готовыми")

    # Рабочий цех (из МК если есть)
    workshop: Optional[str] = Field(None, description="Номер рабочего цеха из МК (1, 2, 3, 4)")

    # Уверенность
    confidence: int = Field(50, description="Общая уверенность модели 0-100")
    confidence_notes: str = Field("", description="Что неоднозначно")


# ─── Этап 2-3: Маршруты ───────────────────────────────────────────────────────

class RouteCandidate(BaseModel):
    """Кандидат-маршрут после фильтрации кодом."""

    route_id: str = Field(..., description="Номер маршрута (M-0001)")
    operations: list[str] = Field(..., description="Список операций")
    score: float = Field(0.0, description="Оценка релевантности (0-1), рассчитанная кодом")
    match_reasons: list[str] = Field(default_factory=list, description="Почему подходит")
    mismatch_reasons: list[str] = Field(default_factory=list, description="Что не совпадает")


class SelectedRoute(BaseModel):
    """Выбранный маршрут (после этапа 3)."""

    route_id: str
    operations: list[str]
    source: str = Field("типовой каталог", description="типовой каталог | маршрутная карта")
    confidence: int = Field(50, description="0-100")
    reasoning: str = Field("", description="Почему выбран именно этот")
    alternatives: list[str] = Field(default_factory=list, description="Альтернативные маршруты")
    suggested_route: list[str] = Field(
        default_factory=list,
        description="Предложенный маршрут на основе фактов чертежа (при confidence < 60)"
    )


# ─── Этап 4: Оборудование ─────────────────────────────────────────────────────

class EquipmentItem(BaseModel):
    """Единица оборудования из базы завода."""

    name: str
    workshop: str = Field("", description="Цех (1, 2, 3, 4, ДорИнвест)")
    department: str = ""
    operations: list[str] = Field(default_factory=list, description="Какие операции выполняет")


class EquipmentChoice(BaseModel):
    """Выбранное оборудование для одной операции."""

    operation: str
    equipment_name: str
    workshop: str
    reasoning: str = ""
    alternatives: list[str] = Field(default_factory=list)


# ─── Этап 5: Результат расчёта одной операции ─────────────────────────────────

class OperationNorm(BaseModel):
    """Результат нормирования одной операции."""

    detail: str = Field("", alias="деталь")
    operation: str = Field(..., alias="операция")
    equipment: str = Field("—", alias="оборудование")
    t_sht: float = Field(..., alias="t_шт_предложено", ge=0)
    t_pz: float = Field(..., alias="t_пз_предложено", ge=0)
    modes: str = Field("—", alias="режимы")
    reasoning: str = Field("", alias="обоснование")

    model_config = {"populate_by_name": True}

    def to_api_dict(self) -> dict:
        return {
            "деталь": self.detail,
            "операция": self.operation,
            "оборудование": self.equipment,
            "t_шт_предложено": self.t_sht,
            "t_пз_предложено": self.t_pz,
            "режимы": self.modes,
            "обоснование": self.reasoning,
        }


# ─── Этап 6: Финальный результат ──────────────────────────────────────────────

class PipelineResult(BaseModel):
    """Полный результат конвейера нормирования."""

    facts: DrawingFacts
    route: SelectedRoute
    equipment_choices: list[EquipmentChoice] = Field(default_factory=list)
    operations: list[OperationNorm] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: Optional[PipelineMetrics] = None

    def to_api_dict(self) -> dict:
        result = {
            "маршрут": {
                "номер": self.route.route_id,
                "операции": " | ".join(self.route.operations),
                "источник": self.route.source,
                "уверенность": self.route.confidence,
                "обоснование": self.route.reasoning,
                "предложенный_маршрут": " | ".join(self.route.suggested_route) if self.route.suggested_route else "",
            },
            "операции": [op.to_api_dict() for op in self.operations],
            "предупреждения": self.warnings,
        }
        if self.metrics:
            result["метрики"] = self.metrics.to_dict()
        return result
