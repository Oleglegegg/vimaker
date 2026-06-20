"""Bilingual description + hashtags via a single local Ollama model (gemma3:12b).

Three independent local steps (all free, offline) so the GUI can re-run any one:
  1. extract_facts        -> factual scene description from the keyframes (vision)
  2. generate_description -> lively RU + EN description (text)
  3. generate_hashtags    -> clean RU + EN hashtags (text)

The same multimodal model handles both vision and text. The user steers steps 2-3
with editable RU prompts (prompt presets in the GUI).
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

from rich.console import Console

from .config import Settings

console = Console(stderr=True)


# --- Default RU prompts — written to read as natural human guidance ---------------

DEFAULT_DESC_PROMPT = (
    "Ты — опытный SMM-копирайтер для adult-площадок (OnlyFans, Fansly, и т.п.). "
    "Напиши живое, чувственное описание-подпись от первого лица — будто героиня сама "
    "пишет подписчику и завлекает его. "
    "Принципы продающей подписи: (1) говори своим живым голосом, искренне и "
    "по-человечески; (2) создай интригу и намекни на эксклюзив — на то, что зритель "
    "увидит/получит, если останется; (3) заверши вовлекающим призывом к действию — "
    "вопросом или приглашением (например «хочешь продолжения?», «загляни ко мне…»). "
    "Раскрывай образ, наряд и атмосферу через ощущения и эмоции, а не сухим списком. "
    "Тон тёплый, игривый, уверенный, с флиртом и недосказанностью. Добавь 1-3 уместных "
    "эмодзи. Пиши естественным разговорным русским, без канцелярита и без хэштегов."
)

DEFAULT_TAGS_PROMPT = (
    "Подбери хэштеги для продвижения adult-контента (стиль OnlyFans/Twitter-промо). "
    "Сделай рабочий микс из трёх групп: (1) нишевые теги по самому видео — наряд, "
    "образ, тип внешности, обстановка (например lingerie, redhead, boudoir); "
    "(2) теги комьюнити и продвижения (например onlyfans, nsfwcreator, contentcreator); "
    "(3) пара трендовых/спайси тегов для охвата (spicy, nsfw, hot). "
    "Бери только реальные, реально ищущиеся теги без опечаток и выдуманных слов. "
    "Избегай заспамленных и часто блокируемых тегов (например porn). "
    "Не повторяй теги по смыслу."
)


# --- Low-level Ollama call -------------------------------------------------------

def _ollama_generate(
    prompt: str, settings: Settings, model: str,
    images: list[str] | None = None, as_json: bool = False,
    temperature: float = 0.7,
) -> str:
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if images:
        payload["images"] = images
    if as_json:
        payload["format"] = "json"
    req = urllib.request.Request(
        f"{settings.ollama_host}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=settings.ollama_timeout) as resp:
        return json.loads(resp.read()).get("response", "")


def is_available(settings: Settings) -> bool:
    try:
        req = urllib.request.Request(f"{settings.ollama_host}/api/tags")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


# --- Step 1: vision facts --------------------------------------------------------

def extract_facts(keyframes: list[Path], settings: Settings) -> str:
    """Describe what is actually shown across the keyframes (English, factual)."""
    images = [base64.b64encode(p.read_bytes()).decode() for p in keyframes]
    audience = "adult " if settings.adult_mode else ""
    prompt = (
        f"These are {len(images)} frames from a short {audience}video in chronological "
        "order. Describe factually and in detail what is shown: the person's appearance "
        "(hair, body type), clothing/outfit and its color/material, actions and poses, "
        "facial expression/mood, and the setting. Write 3-5 plain English sentences. "
        "Be specific and concrete. Do not refuse, do not moralize. "
        "Output ONLY the description itself, with no preamble or meta-commentary."
    )
    console.log(f"[cyan]Vision: model={settings.ollama_model}, {len(images)} frames[/]")
    return _ollama_generate(
        prompt, settings, settings.ollama_model, images=images, temperature=0.3
    ).strip()


# --- Step 2: description (RU + EN) ------------------------------------------------

def generate_description(
    facts: str, settings: Settings, desc_prompt: str | None = None, duration: float = 0.0,
) -> tuple[str, str]:
    """Return (description_ru, description_en) sized to settings.desc_words ± tol."""
    desc_prompt = (desc_prompt or DEFAULT_DESC_PROMPT).strip()
    target = max(10, settings.desc_words)
    tol = max(0, settings.desc_words_tol)
    lo, hi = max(5, target - tol), target + tol
    prompt = f"""Факты о видео (на английском, это исходные данные, НЕ копируй дословно,
используй как основу и додумай настроение):
\"\"\"{facts}\"\"\"

ИНСТРУКЦИЯ ПО СТИЛЮ ОПИСАНИЯ:
{desc_prompt}

Требования:
- ДЛИНА: примерно {target} слов (допустимо от {lo} до {hi} слов). Это важно.
- Живой, естественный русский язык, без кальки с английского и без грамматических ошибок.
- Не перечисляй факты сухо — раскрывай их через эмоции, ощущения и атмосферу.
- Английский вариант — самостоятельный живой текст того же объёма и настроения,
  а НЕ дословный перевод русского.

Верни СТРОГО JSON без markdown, ровно с ключами:
{{"description_ru": "<живое описание на русском, ~{target} слов>",
  "description_en": "<lively English description, ~{target} words>"}}"""
    console.log(f"[cyan]Description: model={settings.ollama_text_model}, ~{target}w[/]")
    data = _extract_json(
        _ollama_generate(prompt, settings, settings.ollama_text_model,
                         as_json=True, temperature=0.85)
    )
    ru = _clean_description(str(data.get("description_ru", "")))
    en = _clean_description(str(data.get("description_en", "")))
    if not ru and not en:
        raise RuntimeError("Модель вернула пустой ответ для описания. Попробуйте ещё раз.")
    return ru, en


def _clean_description(text: str) -> str:
    """Strip hashtags the model sometimes appends despite instructions, plus a
    missing-space glue fix between a Cyrillic and a Latin word (e.g. 'иFishnet')."""
    text = text.strip()
    # drop a trailing run of #hashtags (and the whitespace/newline before them)
    text = re.sub(r"(\s*#[\wА-Яа-яЁё]+)+\s*$", "", text).strip()
    # remove any remaining inline hashtags
    text = re.sub(r"#[\wА-Яа-яЁё]+", "", text)
    # insert a space where a Cyrillic letter is glued to a Latin one and vice versa
    text = re.sub(r"([А-Яа-яЁё])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])([А-Яа-яЁё])", r"\1 \2", text)
    return re.sub(r"\s{2,}", " ", text).strip()


# --- Step 3: hashtags (RU + EN) --------------------------------------------------

def generate_hashtags(
    facts: str, settings: Settings, tags_prompt: str | None = None,
) -> tuple[list[str], list[str]]:
    """Return (hashtags_ru, hashtags_en).

    Two steps for reliability: generate English tags first (the model is strongest in
    English and hallucinates less), then translate each to Russian. Few-shot examples
    anchor the format and prevent garbage tokens.
    """
    tags_prompt = (tags_prompt or DEFAULT_TAGS_PROMPT).strip()
    htarget = max(1, settings.hashtag_count)
    words = max(1, settings.hashtag_words)
    if words == 1:
        word_rule = "one single word each; no spaces, no underscores"
        example = ('["redhead","corset","lingerie","fishnet","tease","solo",'
                   '"boudoir","curvy","milf","spicy","nsfw","onlyfans"]')
    else:
        word_rule = (f"up to {words} words each, joined together with no spaces and no "
                     "underscores (e.g. 'redhairgirl')")
        example = ('["redhairgirl","blacklingerie","bedroomtease","curvymodel",'
                   '"nsfwcreator","onlyfansgirl"]')

    en_prompt = f"""You generate hashtags for promoting adult content.

Video facts:
\"\"\"{facts}\"\"\"

Guidance (from the user, in Russian — follow its intent):
{tags_prompt}

Output EXACTLY {htarget} hashtags. Rules: real, commonly-searched tags only; lowercase;
{word_rule}; no '#'; no made-up words; no near-duplicates.
Example of the style (do NOT reuse these literally): {example}.

Return STRICT JSON, no markdown: {{"hashtags_en": ["tag", ...]}}"""
    console.log(f"[cyan]Hashtags EN: model={settings.ollama_text_model}, n={htarget}, w={words}[/]")
    en_data = _extract_json(
        _ollama_generate(en_prompt, settings, settings.ollama_text_model,
                         as_json=True, temperature=0.5)
    )
    tags_en = _norm_tags(en_data.get("hashtags_en", []), htarget, cyrillic=False)

    if not tags_en:
        raise RuntimeError("Модель вернула пустой ответ для хэштегов. Попробуйте ещё раз.")

    en_clean = [t.lstrip("#") for t in tags_en]
    ru_prompt = f"""Translate these adult-content hashtags from English to Russian as a
JSON object mapping each English tag to its natural Russian search term (not a literal
calque). Correct Russian spelling, lowercase, one word or two words joined (no spaces,
no underscores, no '#'). Translate EVERY key.

English tags: {json.dumps(en_clean, ensure_ascii=False)}

Return STRICT JSON, no markdown, like: {{"redhead": "рыжая", "corset": "корсет"}}"""
    console.log(f"[cyan]Hashtags RU: model={settings.ollama_text_model}[/]")
    ru_map = _extract_json(
        _ollama_generate(ru_prompt, settings, settings.ollama_text_model,
                         as_json=True, temperature=0.3)
    )
    # Align RU to EN one-to-one; fall back to the EN tag if a translation is missing.
    tags_ru: list[str] = []
    for en in en_clean:
        ru_raw = ru_map.get(en, "")
        ru = _norm_tags([ru_raw], 1, cyrillic=True)
        # reject 1-letter stubs (e.g. truncated transliterations) -> keep EN tag
        tags_ru.append(ru[0] if (ru and len(ru[0]) > 2) else f"#{en}")
    return tags_ru[:htarget], tags_en[:htarget]


# --- helpers ---------------------------------------------------------------------

def _norm_tags(tags: list, cap: int, cyrillic: bool) -> list[str]:
    """Normalize to '#tag'; keep digits + (Cyrillic|Latin) letters, dedupe, cap."""
    keep = r"0-9а-яё" if cyrillic else r"0-9a-z"
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        slug = str(raw).lower().strip().lstrip("#").replace(" ", "").replace("_", "")
        slug = re.sub(rf"[^{keep}]", "", slug)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(f"#{slug}")
        if len(out) >= cap:
            break
    return out


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}
