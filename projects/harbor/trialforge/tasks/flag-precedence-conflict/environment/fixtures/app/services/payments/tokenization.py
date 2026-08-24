"""Card tokenization."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def tokenize(card, vault):
    if flags.get_bool("payments.card_tokenization_v2", default=False):
        return vault.token_v2(card.pan, card.expiry)
    return vault.token_v1(card.pan)


def detokenize(token, vault):
    return vault.resolve(token)
