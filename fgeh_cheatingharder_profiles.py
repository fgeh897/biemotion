"""Trait-specific extensions registered without coupling them to the core."""

from fgeh_cheatingharder_domain import IntentType


def possessive_devotion_score_modifier(candidate, opportunity, state, context):
    if candidate.intent_type != IntentType.VISIT_UNANNOUNCED:
        return ()
    observer = context.get("observer")
    if observer is None:
        return ()
    try:
        from fgeh_cheatingharder_relationship import is_enabled

        if is_enabled(observer):
            return (("possessive_devotion_profile", 18.0),)
    except Exception:
        return ()
    return ()
