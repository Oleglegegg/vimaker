"""User preferences with named prompt presets, persisted to JSON.

A preset bundles a description prompt + a hashtag prompt under a name, so the user can
keep several styles (e.g. "Флирт", "Дерзко", "Нейтрально") and switch between them in
the GUI. Stored in the app config dir so they survive across runs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .metadata import DEFAULT_DESC_PROMPT, DEFAULT_TAGS_PROMPT

PREFS_DIR = Path.home() / ".config" / "vimaker"
PREFS_PATH = PREFS_DIR / "prefs.json"

# Bump when the built-in default presets change so existing installs pick them up
# (custom user presets are preserved across the migration).
PRESETS_VERSION = 4


@dataclass
class Preset:
    name: str
    desc_prompt: str
    tags_prompt: str


def _default_presets() -> list[Preset]:
    return [
        Preset("Стандарт", DEFAULT_DESC_PROMPT, DEFAULT_TAGS_PROMPT),
        Preset(
            "Флирт и интрига",
            "Ты — топовый SMM-копирайтер adult-площадок (OnlyFans, Fansly). Напиши "
            "описание-подпись от первого лица в игриво-кокетливом тоне, словно героиня "
            "лично переписывается с подписчиком и дразнит его. "
            "Зацепи с первой строки интригой — вопросом, намёком или провокацией. "
            "Раскрывай образ, наряд и атмосферу через ощущения и флирт, а не списком. "
            "Намекни на эксклюзив — на то, что зритель получит, если останется. "
            "Заверши дразнящим призывом к действию (вопрос или приглашение посмотреть/"
            "подписаться) с лёгкой недосказанностью. "
            "Живой разговорный русский без канцелярита, уместные эмодзи. Без хэштегов "
            "и без вульгарщины.",
            "Подбери хэштеги для продвижения adult-контента в игривом, кокетливом ключе. "
            "Микс: (1) нишевые теги по видео (наряд, образ, обстановка); (2) флиртовые "
            "(flirt, tease, playful); (3) теги комьюнити и охвата (onlyfans, nsfwcreator). "
            "Только реальные ищущиеся теги, без опечаток и выдуманных слов; избегай "
            "заспамленных (porn). Без повторов по смыслу.",
        ),
        Preset(
            "Дерзко и откровенно",
            "Ты — топовый SMM-копирайтер adult-площадок. Напиши смелую, дерзкую, "
            "уверенную подпись от первого лица — провокационно, страстно и с напором, "
            "но без грубости, оскорблений и пошлой вульгарщины. "
            "Начни с хлёсткого уверенного крючка, задающего характер. Подай образ, "
            "движения и настроение сцены смело и чувственно, намекни на горячий эксклюзив. "
            "Заверши прямым, уверенным призывом к действию. "
            "Живой русский, уместные эмодзи. Без хэштегов.",
            "Подбери дерзкие, провокационные, но реальные хэштеги для продвижения "
            "adult-контента. Микс: (1) конкретика по видео; (2) дерзкие/трендовые "
            "(spicy, naughty, hot); (3) комьюнити и охват (nsfwcreator, onlyfans). "
            "Только реально ищущиеся теги, без опечаток и выдуманных слов; избегай "
            "заспамленных (porn). Без повторов по смыслу.",
        ),
        Preset(
            "Нежно и чувственно",
            "Ты — топовый SMM-копирайтер adult-площадок. Напиши нежную, чувственную, "
            "томную подпись от первого лица. "
            "Начни с мягкого, обволакивающего крючка, задающего интимное настроение. "
            "Раскрой образ, наряд и атмосферу через тепло, эстетику и приятные ощущения; "
            "мягко намекни на нечто сокровенное, что ждёт зрителя. "
            "Заверши тёплым, ласковым приглашением остаться рядом. "
            "Плавный живой русский, деликатные эмодзи. Без хэштегов и без грубости.",
            "Подбери эстетичные, чувственные и реальные хэштеги для продвижения "
            "adult-контента. Микс: (1) конкретика по видео (образ, наряд, атмосфера); "
            "(2) эстетичные (sensual, soft, aesthetic); (3) комьюнити и охват "
            "(onlyfans, contentcreator). Только реально ищущиеся теги, без опечаток "
            "и выдуманных слов; избегай заспамленных (porn). Без повторов по смыслу.",
        ),
        Preset(
            "Премиум / люкс",
            "Ты — топовый SMM-копирайтер премиум adult-контента. Напиши изысканную, "
            "статусную подпись от первого лица, создающую ощущение эксклюзивности и "
            "роскоши. "
            "Начни с элегантного крючка с нотой избранности. Подай образ, наряд и "
            "обстановку как дорогой, утончённый контент; ясно намекни на закрытый, "
            "премиальный эксклюзив для избранных. "
            "Заверши приглашением в приватный, премиальный мир героини. "
            "Изящный живой русский, минимум эмодзи. Без хэштегов и без вульгарности.",
            "Подбери премиальные, статусные и реальные хэштеги для продвижения "
            "adult-контента. Микс: (1) конкретика по видео; (2) роскошь и эксклюзив "
            "(luxury, premium, exclusive, vip); (3) комьюнити и охват (onlyfans, "
            "vipcontent). Только реально ищущиеся теги, без опечаток и выдуманных слов; "
            "избегай заспамленных (porn). Без повторов по смыслу.",
        ),
    ]


@dataclass
class Prefs:
    presets: list[Preset] = field(default_factory=_default_presets)
    active: str = "Стандарт"
    version: int = PRESETS_VERSION

    def get(self, name: str) -> Preset:
        for p in self.presets:
            if p.name == name:
                return p
        return self.presets[0]

    def active_preset(self) -> Preset:
        return self.get(self.active)

    def upsert(self, preset: Preset) -> None:
        for i, p in enumerate(self.presets):
            if p.name == preset.name:
                self.presets[i] = preset
                return
        self.presets.append(preset)

    def delete(self, name: str) -> None:
        self.presets = [p for p in self.presets if p.name != name] or _default_presets()
        if self.active not in {p.name for p in self.presets}:
            self.active = self.presets[0].name


def load_prefs() -> Prefs:
    try:
        data = json.loads(PREFS_PATH.read_text())
        presets = [Preset(**p) for p in data.get("presets", [])] or _default_presets()
        active = data.get("active") or presets[0].name
        version = int(data.get("version", 1))
        prefs = Prefs(presets=presets, active=active, version=version)
    except Exception:
        return Prefs()

    # Migrate: refresh built-in presets to the latest wording, keep custom ones.
    if prefs.version < PRESETS_VERSION:
        builtin = {p.name: p for p in _default_presets()}
        merged: list[Preset] = []
        seen: set[str] = set()
        for name, p in builtin.items():          # latest built-ins first, in order
            merged.append(p)
            seen.add(name)
        for p in prefs.presets:                  # then any user-created presets
            if p.name not in seen:
                merged.append(p)
                seen.add(p.name)
        prefs.presets = merged
        prefs.version = PRESETS_VERSION
        if prefs.active not in seen:
            prefs.active = prefs.presets[0].name
        save_prefs(prefs)
    return prefs


def save_prefs(prefs: Prefs) -> None:
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(
        json.dumps(
            {
                "presets": [asdict(p) for p in prefs.presets],
                "active": prefs.active,
                "version": prefs.version,
            },
            ensure_ascii=False, indent=2,
        )
    )
