"""Analysis routes: generate project overview and file annotations."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.prompts.annotate import build_annotation_prompt
from backend.prompts.overview import build_overview_prompt
from backend.routers.project import get_project_data
from backend.services import cache
from backend.services.llm import call_llm, stream_llm

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])


def _extract_json(text: str) -> dict | list | None:
    """Try to parse JSON from LLM output, handling markdown code fences."""
    text = text.strip()
    # strip ```json ... ``` wrapper
    if text.startswith("```"):
        first_nl = text.find("\n")
        last_fence = text.rfind("```")
        if first_nl != -1 and last_fence > first_nl:
            text = text[first_nl + 1 : last_fence].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # fallback: find first [ or { and extract
    for opener, closer in [("[", "]"), ("{", "}")]:
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


@router.get("/project/{project_id}/overview")
async def get_overview(project_id: str, request: Request):
    """Generate or return cached project overview. Streams SSE."""
    proj = get_project_data(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    # build a cache key from file paths + sizes
    files_sig = "|".join(f"{f['path']}:{f['size']}" for f in proj["files"])
    cache_key = f"overview:{cache.content_hash(files_sig)}"

    # check cache
    cached = await cache.get(cache_key)
    if cached:
        # return cached result as a single SSE event
        async def cached_stream():
            yield f"data: {json.dumps({'result': cached}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # build prompt
    prompt = build_overview_prompt(proj["files"])

    # get api key from header if user provided one (BYOK)
    api_key = request.headers.get("x-api-key")

    # stream response
    async def generate():
        full_response = ""
        async for chunk in stream_llm(prompt, api_key=api_key):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

        # try to parse and cache the full response
        parsed = _extract_json(full_response)
        if parsed and isinstance(parsed, dict):
            await cache.put(cache_key, parsed)
            yield f"data: {json.dumps({'result': parsed}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'raw': full_response}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/project/{project_id}/file/{file_path:path}/annotations")
async def get_annotations(project_id: str, file_path: str, request: Request):
    """Generate or return cached annotations for a file."""
    proj = get_project_data(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    content = proj.get("file_contents", {}).get(file_path)
    if content is None:
        raise HTTPException(404, f"File not found: {file_path}")

    # detect language
    lang = "python"
    for f in proj["files"]:
        if f["path"] == file_path:
            lang = f["language"]
            break

    # cache by file content
    cache_key = f"annotate:{cache.content_hash(content)}"
    cached = await cache.get(cache_key)
    if cached:
        return {"path": file_path, "language": lang, "annotations": cached}

    prompt = build_annotation_prompt(content, lang)
    api_key = request.headers.get("x-api-key")

    result = await call_llm(prompt, api_key=api_key)

    # parse annotations from LLM response
    parsed = _extract_json(result)
    annotations = parsed if isinstance(parsed, list) else []

    if annotations:
        await cache.put(cache_key, annotations)

    return {"path": file_path, "language": lang, "annotations": annotations}
