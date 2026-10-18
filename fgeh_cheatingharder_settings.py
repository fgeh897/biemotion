import os


ENABLE_DEBUG_LOG = True
MAX_CHECK_IN_VISITORS = 3
# A completed visit adds a persistent directed relationship-bit cooldown.
CHECK_IN_COOLDOWN_SIM_MINUTES = 1440
CLAIM_CONFIRMATION_COOLDOWN_SIM_MINUTES = 1440
# Decisions recur while the directed claim exists.  A WAIT decision schedules
# the next evaluation instead of ending the route forever.
RELATIONSHIP_REEVALUATION_SIM_MINUTES = 360
RELATIONSHIP_RETRY_SIM_MINUTES = 60
# An unresolved breakup is a durable crisis, not a one-day silent cooldown.
# Each side gets a staggered first decision; later decisions remain paced so
# the director does not spam socials or dialogs every simulation tick.
RELATIONSHIP_CRISIS_FIRST_RESPONSE_SIM_MINUTES = 3
RELATIONSHIP_CRISIS_ROLE_STAGGER_SIM_MINUTES = 7
RELATIONSHIP_CRISIS_RESTORE_FIRST_SIM_MINUTES = 5
RELATIONSHIP_CRISIS_ACTION_COOLDOWN_SIM_MINUTES = 90
RELATIONSHIP_CRISIS_GIVE_SPACE_SIM_MINUTES = 180
RELATIONSHIP_CRISIS_REPEAT_DECISION_SIM_MINUTES = 90
AUTONOMOUS_BREAKUP_PROPOSAL_COOLDOWN_SIM_MINUTES = 1440
# Once the proposer confirms breakup after the recipient's response, retries
# are execution retries for the same decision, not new proposals.  Keep them
# short and bounded so a killed social mixer cannot leave the pair in a false
# permanent limbo.
CONFIRMED_BREAKUP_RETRY_SIM_MINUTES = 30
# Give the visible social one clean retry.  If it is killed again, the already
# confirmed decision is completed through the no-animation transaction path.
CONFIRMED_BREAKUP_MAX_RETRIES = 1
# A Sim who explicitly insisted on ending the relationship should not reverse
# that decision seconds later merely because their static five-D values remain
# affectionate.  The recent intent is temporary context, not a permanent ban.
RECONCILIATION_CONFIRMED_BREAKUP_COOLDOWN_SIM_MINUTES = 360
RESTORED_CLAIM_FIRST_EVALUATION_SIM_MINUTES = 5
CHECK_IN_DELAY_SIM_MINUTES = 30
CHECK_IN_VISIT_DURATION_SIM_MINUTES = 180
CHECK_IN_WARNING_ENABLED = True
# Emotional-expansion Beta authority rule.  Every Sim uses the same scored
# reaction pool; only the current active selectable Sim asks for player input.
# Closing that picker hands the exact decision back to the character brain.
BETRAYAL_PLAYER_DECISION_MODE = "active_sim"
CHEATING_WITNESS_RADIUS = 5.0
# EA may apply romantic-boundary knowledge after the interaction callback.
# Correlate only a short, bounded interval and refuse matches with >1 rival.
EA_AWARENESS_CORRELATION_SIM_MINUTES = 60
EA_AWARENESS_CORRELATION_CAPACITY = 64
EA_AWARENESS_PENDING_SIGNAL_CAPACITY = 32
EA_AWARENESS_PENDING_SIGNAL_SIM_MINUTES = 5
EA_AWARENESS_MIN_SATISFACTION_DROP = 1.0
EA_AWARENESS_EVIDENCE_RECEIPT_CAPACITY = 128
# EA's short-term romance warnings can help explain a nearby auto-breakup, but
# must not label an unrelated breakup days later.
EA_AUTO_BREAKUP_WARNING_WINDOW_SIM_MINUTES = 360
# RelationshipBitChange preserves Actor -> Target only until EA adds the
# bidirectional broken-up bit.  This short receipt joins those two callbacks.
EA_BREAKUP_DECLARATION_WINDOW_SIM_MINUTES = 5
EA_BREAKUP_TRANSITION_CAPACITY = 32
# After our model denies an EA relationship effect, concrete EA loots may keep
# arriving through sibling operations.  One short receipt joins that semantic
# transaction without blocking later, unrelated events.
EA_EFFECT_GATE_WINDOW_SIM_MINUTES = 5
EA_EFFECT_GATE_CAPACITY = 64
# Once the relationship model takes ownership of an EA-scripted breakup
# request, equivalent retries are suppressed for one Sim day.  The short
# effect gate above still joins concrete sibling loots from one transaction;
# this longer receipt prevents a persistent jealousy reaction from repeatedly
# creating new decisions, ledger entries, and Buff expressions.
EA_BREAKUP_TAKEOVER_COOLDOWN_SIM_MINUTES = 1440
EA_RELATIONSHIP_TAKEOVER_CAPACITY = 64
# One EA breakup transaction can surface through several resolver and root-bit
# callbacks.  Keep a bounded result cache so the pair negotiates only once.
BREAKUP_NEGOTIATION_CAPACITY = 64
# One jealousy/betrayal reaction can also surface first as a concrete EA
# interaction and then as a scheduled relationship-model tick.  Join those
# different request ids into one short pair-level reaction session so the
# second callback cannot redraw a contradictory breakup outcome.
BREAKUP_REACTION_SESSION_SIM_MINUTES = 5
# A player-confirmed second-stage decision must cover every sibling EA loot
# callback belonging to the same breakup transaction, then expire quickly.
BREAKUP_FINAL_AUTHORIZATION_SIM_MINUTES = 5
# A model-selected breakup may wait in the Sim's queue longer than the small
# lower-layer authorization window.  Keep the pair transaction alive so an EA
# jealousy reaction cannot start a second negotiation while that exact
# interaction is pending.
BREAKUP_PENDING_EXECUTION_SIM_MINUTES = 60
# A lower-layer EA jealousy/autonomy request may reuse only a recent upper-layer
# relationship decision.  Older interpretations remain history, not authority
# to end the current official relationship.
EA_BREAKUP_POLICY_DECISION_MAX_AGE_SIM_MINUTES = 360
# InteractionSource is only a queue-origin hint.  Player override is granted
# solely when PIE_MENU is paired with one of these explicit breakup
# affordances.  EA's base targeted "Break Up" mixer is 0x6614 (26132).
# Future project/pack/third-party manual breakup interactions should be added
# deliberately after their Actor -> Target semantics are verified.
EA_MANUAL_BREAKUP_AFFORDANCE_IDS = frozenset((0x6614,))
# EA's complete automatic breakup loot.  This is used only as the final
# transport fallback after our negotiation has already authorized a breakup
# and the visible social mixer repeatedly fails to complete.
EA_CONFIRMED_BREAKUP_FALLBACK_LOOT_ID = 387559
CHECK_IN_ARRIVAL_RETRY_MINUTES = 1
CHECK_IN_ARRIVAL_MAX_RETRIES = 15
MIN_ROMANTIC_INTERACTION_SCORE = 0

# Permanent-devotion vertical slice: on the active lot only, a devoted Sim
# begins longing after four Sim hours without a meaningful successful social.
# The runtime samples every 30 Sim minutes and never interrupts player actions.
DEVOTION_LONGING_START_SIM_MINUTES = 240
DEVOTION_LONGING_FULL_INTENSITY_SIM_MINUTES = 720
DEVOTION_LONGING_CHECK_SIM_MINUTES = 30
DEVOTION_LONGING_FIRST_CHECK_SIM_MINUTES = 2
DEVOTION_SEEK_COOLDOWN_SIM_MINUTES = 60
DEVOTION_CONTACT_EVENT_MIN_INTERVAL_SIM_MINUTES = 15

# Memory-driven autonomy begins with one deliberately small active-lot slice:
# after betrayal, a selected seek_reassurance intent waits briefly for EA's
# jealousy reaction to finish, then queues one safe low-priority social.
AUTONOMOUS_ACTION_FIRST_ATTEMPT_SIM_MINUTES = 2
AUTONOMOUS_ACTION_RETRY_SIM_MINUTES = 1
AUTONOMOUS_ACTION_MAX_RETRIES = 10
AUTONOMOUS_ACTION_OUTCOME_TIMEOUT_SIM_MINUTES = 240
# EA can describe one visible betrayal through several callbacks (local
# witness, romantic-boundary discovery, jealousy completion).  Treat matching
# signals as one reaction episode so they add evidence without applying the
# five-dimensional injury or drawing a second primary behavior again.
BETRAYAL_REACTION_EPISODE_SIM_MINUTES = 30
SEEK_REASSURANCE_COOLDOWN_SIM_MINUTES = 180
CLING_TO_PARTNER_COOLDOWN_SIM_MINUTES = 180
CONFRONT_PARTNER_COOLDOWN_SIM_MINUTES = 180
CONFRONT_RIVAL_COOLDOWN_SIM_MINUTES = 180

TRAIT_INSTANCE_ID = 0x82C385E2
DEVOTION_TRAIT_INSTANCE_ID = 0x9C0503EF1B6FD35C
DEVOTION_LONGING_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD35D
DEVOTION_ANXIOUS_LONGING_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD360
DEVOTION_REUNION_RELIEF_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD361
DEVOTION_EXPRESSION_BUFF_INSTANCE_IDS = {
    "gentle_longing": DEVOTION_LONGING_BUFF_INSTANCE_ID,
    "anxious_longing": DEVOTION_ANXIOUS_LONGING_BUFF_INSTANCE_ID,
    "reunion_relief": DEVOTION_REUNION_RELIEF_BUFF_INSTANCE_ID,
}
BETRAYAL_PRESSURE_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD362
BETRAYAL_HURT_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD363
BETRAYAL_ANGER_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD364
REPAIR_REOPENING_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD366
REPAIR_WARY_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD367
REPAIR_INSUFFICIENT_BUFF_INSTANCE_ID = 0x9C0503EF1B6FD368
RELATIONSHIP_REACTION_BUFF_INSTANCE_IDS = {
    "betrayal_pressure": BETRAYAL_PRESSURE_BUFF_INSTANCE_ID,
    "betrayal_hurt": BETRAYAL_HURT_BUFF_INSTANCE_ID,
    "betrayal_anger": BETRAYAL_ANGER_BUFF_INSTANCE_ID,
    "repair_reopening": REPAIR_REOPENING_BUFF_INSTANCE_ID,
    "repair_wary": REPAIR_WARY_BUFF_INSTANCE_ID,
    "repair_insufficient": REPAIR_INSUFFICIENT_BUFF_INSTANCE_ID,
}
CLAIM_RELATIONSHIP_BIT_INSTANCE_ID = 0xE374C824
PICKER_INTERACTION_ID = 0x9C0503EF1B6FD340
RELATIONSHIP_EDIT_INTERACTION_ID = 0x9C0503EF1B6FD369
RELATIONSHIP_BROWSER_INTERACTION_ID = 0x9C0503EF1B6FD36A
ROMANTIC_JOURNAL_INTERACTION_ID = 0x9C0503EF1B6FD36B
DEVOTION_INTERACTION_ID = 0x9C0503EF1B6FD35B
RECONCILIATION_INTERACTION_ID = 0x9C0503EF1B6FD365
# EA's achievement EventData_RelationshipData stores added relationship-bit
# tuning IDs in a uint32 field.  Keep this whole persistent relationship
# family within 32 bits so anchors cannot make account saving fail.
STATE_TRACK_INSTANCE_IDS = {
    "attachment": 0x1B6FD350,
    "trust": 0x1B6FD351,
    "exclusivity": 0x1B6FD352,
    "commitment": 0x1B6FD353,
    "boundary": 0x1B6FD354,
}
CHECK_IN_COOLDOWN_BIT_INSTANCE_ID = 0x1B6FD355
# Visible, persisted UI projection of owner -> only-beloved.  This remains
# 32-bit because EA achievement relationship data serializes bit IDs as uint32.
DEVOTION_RELATIONSHIP_BIT_INSTANCE_ID = 0x1B6FD35E
# Visible observer -> rival projection created only after the observer has
# confirmed a betrayal event involving that rival.
BETRAYAL_RIVAL_RELATIONSHIP_BIT_INSTANCE_ID = 0x1B6FD35F

# EA/EP21 signals.  These are read-only adapters: the mod does not maintain a
# competing intelligence database and does not replace the game's notices.
EA_AFFAIR_SECRET_INSTANCE_ID = 479950
EA_REL_BIT_CHEATER_CAUGHT_BY_SIM = 306132
EA_REL_BIT_SIM_CAUGHT_CHEATER = 306133
EA_REL_BIT_ROMANTIC_CHEATED_WITH = 37265
EA_REL_BIT_ROMANTIC_BROKEN_UP = 15811
EA_REL_BIT_ROMANTIC_BROKEN_UP_ENGAGED = 15812
EA_REL_BIT_ROMANTIC_DIVORCED = 15815
EA_REL_BIT_ROMANTIC_SIGNIFICANT_OTHER = 15825
# Base-game targeted "Apologize" social.  EA supplies distinct SUCCESS and
# FAILURE outcomes; the repair adapter observes those results without
# replacing the interaction, animation, or EA relationship-track effects.
EA_INTERACTION_APOLOGIZE_TARGETED_FRIENDLY = 26006
EA_FORMER_ROMANTIC_RELATIONSHIP_BIT_IDS = frozenset((
    EA_REL_BIT_ROMANTIC_BROKEN_UP,
    EA_REL_BIT_ROMANTIC_BROKEN_UP_ENGAGED,
    EA_REL_BIT_ROMANTIC_DIVORCED,
))
# EA loot_SignificantOther_AddBoth.  This is the verified commit boundary for
# mutual reconciliation: it removes former-partner markers in both directions,
# restores romantic-Significant_Other, and runs EA's pack-safe follow-up loots.
EA_LOOT_SIGNIFICANT_OTHER_ADD_BOTH = 279989

LOG_FILE_NAME = "fgeh_cheatingharder_debug.log"


def get_mod_directory():
    """Return the directory containing the installed script module."""
    return os.path.dirname(os.path.abspath(__file__))


def get_log_path():
    return os.path.join(get_mod_directory(), LOG_FILE_NAME)


def is_check_in_warning_enabled():
    return bool(CHECK_IN_WARNING_ENABLED)


def set_check_in_warning_enabled(enabled):
    global CHECK_IN_WARNING_ENABLED
    CHECK_IN_WARNING_ENABLED = bool(enabled)
    return CHECK_IN_WARNING_ENABLED
