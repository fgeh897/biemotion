class ReactionPlan(object):
    """Data-only result of personality and relationship interpretation."""

    def __init__(self):
        self.blame_partner = 0.25
        self.blame_rival = 1.0
        self.breakup_weight = 0.0
        self.reconcile_weight = 1.0
        self.refuse_breakup = True
        self.push_confrontation = True
        self.rival_friendship_penalty = 50
        self.preserve_claim_for_reconciliation = True


def resolve_default_possessive_devotion_plan(event):
    """First profile: blame the rival, preserve the partner relationship."""
    return ReactionPlan()


def resolve_reaction_plan(event):
    """Stable extension point for future personality-specific strategies."""
    return resolve_default_possessive_devotion_plan(event)
