from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationProviderStatusResponse,
    GenerationRequest,
    GenerationResultResponse,
    GenerationValidationRequest,
    GenerationValidationResponse,
)
from app.services.ai_generation import AIGenerationError, AIGenerationService, extract_latex_code
from app.services.prompt_builder import build_latex_generation_prompt
from app.services.latex_validator import validate_latex_document

router = APIRouter()

ai_generator = AIGenerationService()

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


def build_generation_prompt_response(request: GenerationRequest) -> GenerationPromptResponse:
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


@router.get("/presets", response_model=list[GenerationPresetResponse])
async def list_generation_presets():
    return PRESETS


@router.post("/prompt", response_model=GenerationPromptResponse)
async def preview_generation_prompt(request: GenerationRequest):
    return build_generation_prompt_response(request)


@router.get("/providers/status", response_model=GenerationProviderStatusResponse)
async def get_generation_provider_status(
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
):
    try:
        status = await ai_generator.get_provider_status(provider=provider, model=model)
    except AIGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return GenerationProviderStatusResponse(**status)


@router.post("/validate", response_model=GenerationValidationResponse)
async def validate_generated_latex(request: GenerationValidationRequest):
    return GenerationValidationResponse(**validate_latex_document(request.latex_code))


@router.post("/generate", response_model=GenerationResultResponse)
async def generate_latex(request: GenerationRequest):
    prompt_response = build_generation_prompt_response(request)

    try:
        raw_output, provider, model = await ai_generator.generate(
            prompt=prompt_response.prompt,
            provider=request.provider,
            model=request.model,
        )
    except AIGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    latex_code = extract_latex_code(raw_output)
    validation = validate_latex_document(latex_code)

    return GenerationResultResponse(
        status="success",
        prompt=prompt_response.prompt,
        warnings=prompt_response.warnings,
        provider=provider,
        model=model,
        latex_code=latex_code,
        raw_output=raw_output,
        validation=GenerationValidationResponse(**validation),
    )
