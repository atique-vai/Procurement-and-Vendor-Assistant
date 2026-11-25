"""Model construction and primary/fallback routing for chat workloads."""

from typing import Any, TypeVar

from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.config import get_settings


OutputModel = TypeVar("OutputModel", bound=BaseModel)

_MODEL_REQUEST_TIMEOUT_SECONDS = 20
_MODEL_MAX_RETRIES = 0


def _effective_temperature(model_name: str, temperature: float) -> float:
    normalized_name = model_name.removeprefix("models/").lower()
    if normalized_name.startswith(("gemini-3", "gemini-4")):
        return 1.0
    return temperature


def _structured_output_runnable(
    model: Any,
    output_schema: type[BaseModel],
) -> Runnable:
    """Bind output_schema with explicit tool_choice for Gemini models where
    langchain-google-genai's _supports_tool_choice returns False (e.g. Gemini 3/4).
    """
    if (
        hasattr(model, "bind_tools")
        and hasattr(model, "_supports_tool_choice")
        and not model._supports_tool_choice
    ):
        tool_name = output_schema.__name__
        parser = PydanticToolsParser(tools=[output_schema], first_tool_only=True)

        def _parse_message(message: Any) -> BaseModel | None:
            parsed = parser.invoke(message)
            if parsed is not None:
                return parsed
            content = getattr(message, "content", "")
            text = content.strip() if isinstance(content, str) else ""
            if text and "response" in output_schema.model_fields:
                return output_schema(response=text)
            return None

        return model.bind_tools([output_schema], tool_choice=tool_name) | RunnableLambda(
            _parse_message
        )
    return model.with_structured_output(output_schema)


def _create_model(
    model_name: str,
    *,
    api_key: str,
    temperature: float,
    output_schema: type[BaseModel] | None,
) -> Runnable:
    model = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=_effective_temperature(model_name, temperature),
        timeout=_MODEL_REQUEST_TIMEOUT_SECONDS,
        max_retries=_MODEL_MAX_RETRIES,
    )
    if output_schema is not None:
        return _structured_output_runnable(model, output_schema)
    return model


def _get_model(
    *,
    temperature: float,
    output_schema: type[BaseModel] | None,
) -> Runnable:
    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required to use the Gemini models.")

    model_names = tuple(
        dict.fromkeys(
            name.strip()
            for name in (settings.primary_model, settings.fallback_model)
            if name.strip()
        )
    )
    if not model_names:
        raise ValueError("At least one Gemini model name must be configured.")

    models = [
        _create_model(
            model_name,
            api_key=settings.google_api_key,
            temperature=temperature,
            output_schema=output_schema,
        )
        for model_name in model_names
    ]
    if len(models) == 1:
        return models[0]
    return models[0].with_fallbacks(models[1:])


def get_chat_model(*, temperature: float = 0.0) -> Runnable:
    """Create the configured Gemini chat model with fallback routing."""
    return _get_model(temperature=temperature, output_schema=None)


def get_structured_chat_model(
    output_schema: type[OutputModel],
    *,
    temperature: float = 0.0,
) -> Runnable:
    """Create a Gemini chat model that returns validated structured output."""
    return _get_model(temperature=temperature, output_schema=output_schema)