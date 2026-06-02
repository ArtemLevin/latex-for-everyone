from fastapi import APIRouter

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationRequest,
)
from app.services.prompt_builder import build_latex_generation_prompt

router = APIRouter()

PRESETS: list[GenerationPresetResponse] = [
    GenerationPresetResponse(
        id="ege_math_11_hard",
        name="ЕГЭ математика, 11 класс, сложные задачи",
        description="Базовый сценарий для обучающего пособия ЕГЭ по математике с одной сложной тренировочной задачей.",
        defaults={
            "level": "ЕГЭ",
            "alpha_code": 1,
            "beta_code": 1,
            "gamma_code": 4,
            "grade": "11 класс",
            "subject": "математика",
            "priority_method": "нейросеть выбирает самостоятельно по отношению к уровню и классу",
            "graph_analytic": "по ситуации",
        },
    )
]


@router.get("/presets", response_model=list[GenerationPresetResponse])
async def list_generation_presets():
    return PRESETS


@router.post("/prompt", response_model=GenerationPromptResponse)
async def preview_generation_prompt(request: GenerationRequest):
    prompt = build_latex_generation_prompt(request.fields, request.materials)
    warnings = []
    if not request.fields.topic:
        warnings.append("Тема не указана: prompt потребует определить тему по материалам без домыслов.")
    if not request.materials.strip():
        warnings.append("Материалы не переданы: prompt запрещает домысливать исходные задания.")

    return GenerationPromptResponse(
        status="success",
        prompt=prompt,
        warnings=warnings,
        provider=request.provider,
        model=request.model,
    )
