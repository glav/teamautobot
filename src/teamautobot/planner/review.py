from __future__ import annotations

from .models import DependencyHandoff, ReviewDecision, ReviewResult


class ReviewContractError(ValueError):
    """Raised when a review task violates the frozen review-gate contract."""


def resolve_review_subject(
    *, task_id: str, dependency_handoffs: tuple[DependencyHandoff, ...]
) -> DependencyHandoff:
    if len(dependency_handoffs) != 1:
        raise ReviewContractError(f"Review task {task_id} requires exactly one dependency handoff.")
    return dependency_handoffs[0]


def validate_review_result(
    *,
    task_id: str,
    dependency_handoffs: tuple[DependencyHandoff, ...],
    review_result: ReviewResult | None,
) -> ReviewResult:
    if review_result is None:
        raise ReviewContractError(f"Review task {task_id} did not return a review result.")

    subject = resolve_review_subject(task_id=task_id, dependency_handoffs=dependency_handoffs)
    if review_result.subject_task_id != subject.task_id:
        raise ReviewContractError(
            f"Review task {task_id} returned subject_task_id={review_result.subject_task_id}, "
            f"expected {subject.task_id}."
        )

    if review_result.decision == ReviewDecision.REJECTED and not review_result.feedback_items:
        raise ReviewContractError(
            f"Rejected review task {task_id} must include at least one feedback item."
        )

    return review_result
