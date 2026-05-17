"""CV domain — parsing service.

Extracts structured profile data from uploaded CV documents (PDF, DOCX, TXT)
using the Anthropic Claude API.

PDF files are sent as native document blocks (no extra dependencies required).
DOCX files are unpacked with the stdlib zipfile module.
TXT / plain-text files are decoded directly.
"""
import base64
import io
import json
import zipfile
from xml.etree import ElementTree as ET

import anthropic

from src.core.logging import get_logger
from src.domains.cv.schemas import CvAnalysisResult

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a CV/resume analysis expert.
Extract structured information and return ONLY a valid JSON object with this exact schema — no markdown, no explanation:

{
  "roles": [{"title": "string", "company": "string or null", "duration_months": integer or null}],
  "skills": [{"name": "string", "level": "strong" or "supporting"}],
  "projects": [{"name": "string", "description": "string or null", "impact": "string or null"}],
  "education": [{"degree": "string", "field": "string or null", "institution": "string or null", "year": integer or null}],
  "leadership_signals": integer,
  "years_of_experience": integer,
  "current_role": "most recent job title as string or null",
  "summary": "one sentence professional summary",
  "location": "city and country extracted from the CV, or null if not mentioned",
  "career_path_suggestions": [
    "emoji Short role title (max 6 words)",
    "emoji Short role title (max 6 words)",
    "emoji Short role title (max 6 words)",
    "emoji Short role title (max 6 words)"
  ]
}

Classification rules:
- "strong" skills: clearly primary, demonstrated with achievements or deep experience.
- "supporting" skills: mentioned but not central to the roles.
- leadership_signals: total count of team lead, manager, mentor, or director references.
- years_of_experience: span from earliest to most recent role, rounded to integer.
- location: extract city and/or country if explicitly stated anywhere in the CV (e.g. address, contact section, "Based in London").

career_path_suggestions rules:
- Generate exactly 3–4 suggestions tailored to THIS specific person's background.
- Each suggestion is a plausible NEXT STEP or CAREER TRANSITION — a role the person could realistically aim for.
- Include roles from the same domain (promotion path) AND adjacent/pivot paths (e.g. moving from technical to strategic, or adding a specialism).
- Start each suggestion with a single relevant emoji, then a concise role title (max 6 words).
- Base suggestions entirely on the actual CV content — skills, roles, projects, education, and years of experience.
- Do NOT use generic tech roles (AI Engineer, DevOps, etc.) unless the CV clearly shows those skills.
- Cover diverse career directions so the person has meaningful choices, not four variations of the same path.
- The application serves users worldwide in any career domain — suggestions should reflect that range.
"""

_TEXT_USER_MSG = "Extract the CV information as described. CV text:\n\n{text}"


class CvService:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def parse_upload(self, data: bytes, filename: str) -> CvAnalysisResult:
        """Parse a CV from raw file bytes and return structured analysis."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

        if ext == "pdf":
            return await self._parse_pdf(data)
        if ext == "docx":
            text = self._extract_docx_text(data)
            return await self._parse_text(text)

        # TXT / MD / unknown — decode as UTF-8 with latin-1 fallback
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        return await self._parse_text(text)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _parse_pdf(self, data: bytes) -> CvAnalysisResult:
        pdf_b64 = base64.standard_b64encode(data).decode("utf-8")
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3072,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {"type": "text", "text": "Extract the CV information as described."},
                    ],
                }
            ],
        )
        return self._parse_llm_response(response)

    async def _parse_text(self, text: str) -> CvAnalysisResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3072,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _TEXT_USER_MSG.format(text=text[:14_000]),
                }
            ],
        )
        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: anthropic.types.Message) -> CvAnalysisResult:
        raw = response.content[0].text if response.content else "{}"
        raw = raw.strip()
        # Strip markdown code fences if the model includes them
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            body = parts[1] if len(parts) > 1 else ""
            if body.startswith("json"):
                body = body[4:]
            raw = body.rsplit("```", 1)[0].strip()
        try:
            data = json.loads(raw)
            return CvAnalysisResult.model_validate(data)
        except Exception as exc:
            logger.warning("cv.parse_json_failed", error=str(exc), raw_preview=raw[:200])
            return CvAnalysisResult()

    @staticmethod
    def _extract_docx_text(data: bytes) -> str:
        """Extract plain text from a DOCX file using stdlib zipfile + ElementTree."""
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                with zf.open("word/document.xml") as f:
                    tree = ET.parse(f)
            paragraphs: list[str] = []
            for para in tree.getroot().iter(f"{{{ns}}}p"):
                parts = [t.text for t in para.iter(f"{{{ns}}}t") if t.text]
                if parts:
                    paragraphs.append("".join(parts))
            return "\n".join(paragraphs)
        except Exception as exc:
            logger.warning("cv.docx_extract_failed", error=str(exc))
            return ""


async def get_cv_service() -> CvService:
    from src.config import settings  # noqa: PLC0415

    return CvService(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.default_llm_model,
    )
