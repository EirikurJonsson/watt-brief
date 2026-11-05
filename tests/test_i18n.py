"""The page's translations: same keys everywhere, every server error code covered, and every
suggested question gets through the input guard in its own language."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from watt_brief.api import MESSAGES
from watt_brief.brief import LANGUAGES
from watt_brief.entsoe import ZONES
from watt_brief.guards import MESSAGES as GUARD_MESSAGES
from watt_brief.guards import check_question

STATIC = Path(__file__).parent.parent / "src/watt_brief/static"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def load() -> dict:
    script = f'const m = require("{STATIC / "i18n.js"}"); console.log(JSON.stringify(m));'
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


I18N = load() if shutil.which("node") else {}
LANGS = ["en", "da", "de", "fr"]


def test_the_page_and_the_brief_offer_the_same_languages():
    assert sorted(LANGUAGES) == sorted(LANGS) == sorted(I18N["STRINGS"])


@pytest.mark.parametrize("lang", LANGS)
def test_every_language_has_every_key_and_the_same_placeholders(lang):
    en, other = I18N["STRINGS"]["en"], I18N["STRINGS"][lang]
    assert set(other) == set(en)
    holes = {
        key: (
            sorted(re.findall(r"\{(\w+)\}", en[key])),
            sorted(re.findall(r"\{(\w+)\}", other[key])),
        )
        for key in en
        if sorted(re.findall(r"\{(\w+)\}", en[key])) != sorted(re.findall(r"\{(\w+)\}", other[key]))
    }
    assert holes == {}
    assert all(text.strip() for text in other.values())


def test_every_error_the_server_can_send_has_a_page_translation():
    codes = (
        set(MESSAGES)
        | set(GUARD_MESSAGES)
        | {
            "no_data",
            "no_prices",
            "zone_unknown",
            "zone_unsupported",
            "denmark_ambiguous",
            "bad_query",
        }
    )
    for lang in LANGS:
        missing = [c for c in codes if f"err_{c}" not in I18N["STRINGS"][lang]]
        assert missing == [], (lang, missing)


def test_every_zone_has_a_name_in_every_language():
    assert set(I18N["ZONE_NAMES"]) == set(ZONES)
    for names in I18N["ZONE_NAMES"].values():
        assert set(names) == set(LANGS) and all(len(v) == 2 and all(v) for v in names.values())


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", ["chip1_q", "chip2_q", "chip3_q", "question_placeholder"])
def test_suggested_questions_pass_the_input_guard_in_their_language(lang, key):
    assert check_question(I18N["STRINGS"][lang][key])


def test_the_page_loads_the_translations_before_the_app_and_declares_each_language():
    html = (STATIC / "index.html").read_text()
    assert html.index("i18n.js") < html.index("app.js")
    for lang in LANGS:
        assert f'<option value="{lang}">' in html
