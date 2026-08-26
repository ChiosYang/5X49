import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Literal

from app.contracts.analysis_v2 import (
    AnalysisV2Input,
    AnalysisV2Output,
    GeneratedAnalysisV2Output,
)

# 加载环境变量
# Fix: Running from 'backend/' directory via uvicorn
load_dotenv(".env.local")

# Import settings service for dynamic model selection
from app.services.settings import get_current_model, get_base_url, get_language

# Initialize OpenAI client with dynamic base URL
def get_client():
    """Get OpenAI client with current base URL"""
    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=get_base_url()
    )


ANALYSIS_PROMPT_VERSION = "genealogy-v2.v2"


@dataclass(frozen=True)
class AnalysisModelConfiguration:
    provider: str
    model: str
    reasoning_effort: Literal["low", "medium", "high", "max"] | None = None
    max_output_tokens: int | None = None


def analysis_prompt_snapshot(configuration: AnalysisModelConfiguration) -> str:
    reasoning = configuration.reasoning_effort or "provider_default"
    maximum = configuration.max_output_tokens or "provider_default"
    return f"{ANALYSIS_PROMPT_VERSION}|reasoning={reasoning}|max={maximum}"


@dataclass(frozen=True)
class AnalysisGenerationResult:
    output: AnalysisV2Output
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None

class FilmHistorian:
    def __init__(self, *, client_factory=None):
        # Production keeps the dynamic client; isolated evaluation can pin a
        # provider endpoint without changing global settings.
        self._client_factory = client_factory or get_client

    def analysis_configuration(self) -> AnalysisModelConfiguration:
        base_url = get_base_url().casefold()
        if "openrouter.ai" in base_url:
            provider = "openrouter"
        elif "api.openai.com" in base_url:
            provider = "openai"
        else:
            provider = "openai_compatible"
        return AnalysisModelConfiguration(provider=provider, model=get_current_model())

    def analyze_v2(
        self,
        analysis_input: AnalysisV2Input,
        *,
        configuration: AnalysisModelConfiguration | None = None,
    ) -> AnalysisGenerationResult:
        configuration = configuration or self.analysis_configuration()
        schema = GeneratedAnalysisV2Output.model_json_schema()
        prompt = (
            "You are a film historian. Return only one JSON object that validates against the "
            "provided Analysis V2 schema. Do not include hidden reasoning. Return no more than eight "
            "high-confidence assertion candidates; fewer is better than speculative coverage. Use "
            "concise, user-visible rationales. Omit qualifiers entirely: explanatory relationship "
            "labels, dates, and direction notes belong in the rationale, not qualifiers. Use "
            "direction=subject_to_target for influences on the subject film and "
            "direction=target_to_subject for later films influenced by the subject. Concept targets "
            "must always use subject_to_target. Reuse an available_concepts entry by entity_id when "
            "it is semantically appropriate; only use a name-only Concept when none of the supplied "
            "options fit. Prefer tmdb.movie identifiers for film targets only when you are certain. "
            "When an external ID is supplied, its display_name and release_year must describe that "
            "same identity; never guess an ID. Otherwise use display_name and release_year so the "
            "reference can enter review. Include at most two Evidence candidates per assertion, and "
            "only use public HTTP(S) URLs that you are confident exist.\n\n"
            f"INPUT:\n{analysis_input.model_dump_json()}\n\n"
            f"OUTPUT JSON SCHEMA:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
        )
        client = self._client_factory()
        request = {
            "model": configuration.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        if configuration.reasoning_effort is not None:
            request["reasoning_effort"] = configuration.reasoning_effort
        if configuration.max_output_tokens is not None:
            request["max_tokens"] = configuration.max_output_tokens
        response = client.chat.completions.create(
            **request,
        )
        raw_content = response.choices[0].message.content
        if not raw_content:
            raise ValueError("Analysis provider returned an empty response")
        output = GeneratedAnalysisV2Output.model_validate_json(raw_content)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        raw_cost = getattr(usage, "cost", None)
        try:
            estimated_cost = float(raw_cost) if raw_cost is not None else None
        except (TypeError, ValueError):
            estimated_cost = None
        if estimated_cost is not None and estimated_cost < 0:
            estimated_cost = None
        return AnalysisGenerationResult(
            output=output,
            input_tokens=input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else None,
            estimated_cost=estimated_cost,
            currency="USD" if estimated_cost is not None else None,
        )
