from sqlalchemy.orm import Session

from app.models import GenerationHistory
from app.schemas import GenerationCompileCheckResponse, GenerationFields, GenerationTokenUsageResponse


class GenerationHistoryNotFoundError(ValueError):
    pass


class GenerationHistoryService:
    """Persist bounded, privacy-conscious AI generation metadata for observability."""

    def create_success(
        self,
        db: Session,
        *,
        project_id: str | None,
        provider: str,
        model: str | None,
        fields: GenerationFields,
        prompt_hash: str,
        prompt_preview: str,
        raw_output_hash: str,
        latex_code_hash: str,
        latex_code_preview: str,
        validation: dict[str, object],
        compile_check: GenerationCompileCheckResponse,
        token_usage: GenerationTokenUsageResponse,
    ) -> GenerationHistory:
        item = GenerationHistory(
            project_id=project_id,
            provider=provider,
            model=model,
            status="success",
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            raw_output_hash=raw_output_hash,
            latex_code_hash=latex_code_hash,
            latex_code_preview=latex_code_preview,
            fields=fields.model_dump(),
            validation=validation,
            compile_check=compile_check.model_dump(),
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            total_tokens=token_usage.total_tokens,
            token_count_source=token_usage.source,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def create_failure(
        self,
        db: Session,
        *,
        project_id: str | None,
        provider: str,
        model: str | None,
        fields: GenerationFields,
        prompt_hash: str,
        prompt_preview: str,
        error: str,
    ) -> GenerationHistory:
        item = GenerationHistory(
            project_id=project_id,
            provider=provider,
            model=model,
            status="error",
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            fields=fields.model_dump(),
            error=error,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def list_project_history(
        self,
        db: Session,
        project_id: str,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[GenerationHistory]:
        return (
            db.query(GenerationHistory)
            .filter(GenerationHistory.project_id == project_id)
            .order_by(GenerationHistory.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_history_item(self, db: Session, history_id: str) -> GenerationHistory:
        item = db.query(GenerationHistory).filter(GenerationHistory.id == history_id).first()
        if item is None:
            raise GenerationHistoryNotFoundError(f"Generation history item {history_id} not found")
        return item
