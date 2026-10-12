"""Local greetings share their vocabulary with the consumer UI; no model needed."""
import json
import re
from pathlib import Path

_CONFIG = json.loads((Path(__file__).resolve().parents[3] / 'shared/greetings.json').read_text())
_PHRASE = '(?:' + '|'.join(map(re.escape, _CONFIG['phrases'])) + ')(?: (?:' + '|'.join(map(re.escape, _CONFIG['addressees'])) + '))?'
_GREETING = re.compile('(?:' + _PHRASE + ')(?: ' + _PHRASE + ')*')


def greeting_reply(message: str) -> str | None:
    text = re.sub(r'[.,!?:;👋]', ' ', message.lower().replace("'", '').replace('’', ''))
    text = ' '.join(text.split())
    if (text and _GREETING.fullmatch(text)) or message.strip() == '👋':
        for rule in _CONFIG['replies']:
            if any(term in text for term in rule['contains']):
                return rule['message']
        return _CONFIG['default_reply']
    return None
