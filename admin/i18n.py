"""Lightweight i18n helper for Streamlit admin dashboard."""
import json
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED_LOCALES = ["en", "ja", "zh-TW", "zh-CN"]
DEFAULT_LOCALE = "en"


def load_translations(locale: str) -> dict[str, Any]:
    """Load translations for the given locale.
    
    Falls back to DEFAULT_LOCALE if the requested locale file doesn't exist.
    
    Args:
        locale: The locale code (e.g., "en", "ja", "zh-TW", "zh-CN")
    
    Returns:
        Dictionary of translations
    """
    path = LOCALES_DIR / f"{locale}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Fallback to default
    default_path = LOCALES_DIR / f"{DEFAULT_LOCALE}.json"
    return json.loads(default_path.read_text(encoding="utf-8"))


def t(translations: dict[str, Any], key: str, **kwargs: Any) -> str:
    """Translate a key using dot-notation lookup.
    
    Examples:
        t(tr, "health.title") -> translations["health"]["title"]
        t(tr, "health.fetchError", error="Connection failed") -> formatted string
    
    Args:
        translations: The translations dictionary
        key: Dot-separated key path (e.g., "health.title")
        **kwargs: Format parameters for the translation string
    
    Returns:
        The translated and formatted string, or the key itself if not found
    """
    value: Any = translations
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part, key)
        else:
            return key
    
    if isinstance(value, str) and kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, ValueError):
            return value
    
    return str(value) if not isinstance(value, dict) else key
