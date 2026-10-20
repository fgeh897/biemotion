"""Pure interaction-name classification used by Sims-facing adapters."""


def is_ea_jealousy_awareness_reaction_name(interaction_name):
    """Return True only for EA reactions that establish romantic awareness."""
    name = str(interaction_name or "").strip().lower()
    return (
        "reaction" in name
        and "jealousy" in name
        and ("lovedone" in name or "cheat" in name)
    )


def outside_romance_journal_overrides(
    actor_has_other_romance,
    target_has_other_romance,
):
    """Promote a multi-relationship romance without inventing discovery.

    Both participants know an interaction they personally took part in, but an
    absent partner does not.  The objective event therefore remains
    ``romance_completed``; only its journal presentation becomes salient.
    """
    if not (actor_has_other_romance or target_has_other_romance):
        return {}
    return {
        "journal_visibility": "timeline",
        "semantic_tags": ("boundary", "rival"),
        "salience": 70,
        "outside_romance": True,
        "outside_romance_roles": tuple(
            role
            for role, has_other_romance in (
                ("actor", actor_has_other_romance),
                ("target", target_has_other_romance),
            )
            if has_other_romance
        ),
    }
