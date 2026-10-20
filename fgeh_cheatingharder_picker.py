"""In-game picker for settings and asymmetric directed relationship values."""

import services
import sims4.resources

from event_testing.results import TestResult
from interactions.base.immediate_interaction import ImmediateSuperInteraction
from interactions.base.picker_interaction import PickerSuperInteraction
from sims.sim import Sim
from sims4.localization import LocalizationHelperTuning
from sims4.resources import Types
from sims4.utils import flexmethod
from ui.ui_dialog_picker import ObjectPickerRow

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_dimension_registry import DIMENSION_DEFINITIONS
from fgeh_cheatingharder_relationship import get_claim_records, get_sim_info


_PICKER_INSTALLED = False
_TOGGLE_WARNING_ID = 1
_SWITCH_DIRECTION_ID = 20
_BACK_TO_DIMENSIONS_ID = 21
_CUSTOM_VALUE_ID = 22
_EVALUATE_RELATIONSHIP_ID = 23
_CUSTOM_VALUE_INPUT = "relationship_value"


class _PickerChoice(object):
    __slots__ = ("id", "action", "dimension", "value")

    def __init__(self, choice_id, action, dimension=None, value=None):
        self.id = int(choice_id)
        self.action = str(action)
        self.dimension = dimension
        self.value = value


def _raw(text):
    return LocalizationHelperTuning.get_raw_text(str(text))


def _sim_name(sim_info):
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name and last_name:
        return "{} {}".format(first_name, last_name)
    return str(first_name or getattr(sim_info, "sim_id", "?"))


def _get_picker_interaction(interaction_id):
    try:
        key = sims4.resources.get_resource_key(
            interaction_id,
            Types.INTERACTION,
        )
        return services.affordance_manager().get(key)
    except Exception:
        log_exception(
            "picker interaction lookup failed id={}".format(
                interaction_id
            )
        )
        return None


def _base_pair_from_picker(inst, target, context):
    actor = get_sim_info(
        getattr(inst, "sim", None)
        if inst is not None
        else getattr(context, "sim", None)
    )
    partner = get_sim_info(
        getattr(inst, "target", None) if inst is not None else target
    )
    if (
        actor is None
        or partner is None
        or actor.sim_id == partner.sim_id
    ):
        return (None, None)
    return (actor, partner)


def _pair_from_picker(inst, target, context):
    actor, partner = _base_pair_from_picker(inst, target, context)
    if actor is None or partner is None:
        return (None, None)
    reversed_direction = bool(
        getattr(inst, "_fgeh_edit_reversed", False)
    )
    return (partner, actor) if reversed_direction else (actor, partner)


def _direction_text(observer, partner):
    return "{} \u2192 {}".format(_sim_name(observer), _sim_name(partner))


def _state_for(observer, partner):
    from fgeh_cheatingharder_state import get_directed_state

    return get_directed_state(observer, partner)


def _dimension_rows(inst, target, context):
    observer, partner = _pair_from_picker(inst, target, context)
    if observer is None or partner is None:
        return
    state = _state_for(observer, partner)
    direction = _direction_text(observer, partner)
    yield ObjectPickerRow(
        option_id=_SWITCH_DIRECTION_ID,
        object_id=_SWITCH_DIRECTION_ID,
        name=_raw(
            "\u5207\u6362\u65b9\u5411\uff5c\u5f53\u524d\uff1a{}".format(
                direction
            )
        ),
        row_description=_raw(
            "\u70b9\u51fb\u540e\u7acb\u5373\u5207\u6362\u4e3a\u53cd\u65b9\u5411\u3002"
            "\u4e24\u4e2a\u65b9\u5411\u7684\u6570\u503c\u5b8c\u5168\u72ec\u7acb\u3002"
        ),
        tag=_PickerChoice(_SWITCH_DIRECTION_ID, "switch_direction"),
        is_enable=True,
    )
    yield ObjectPickerRow(
        option_id=_EVALUATE_RELATIONSHIP_ID,
        object_id=_EVALUATE_RELATIONSHIP_ID,
        name=_raw(
            "测试当前方向的自主关系复评｜{}".format(direction)
        ),
        row_description=_raw(
            "立即让五维候选池计算一次：维持、修复或提出分手。"
            "这不是强制结果；若抽中分手，会排入正常分手互动并进入协商。"
        ),
        tag=_PickerChoice(
            _EVALUATE_RELATIONSHIP_ID,
            "evaluate_relationship",
        ),
        is_enable=True,
    )
    for index, definition in enumerate(
        DIMENSION_DEFINITIONS.definitions()
    ):
        value = 0.0 if state is None else state.get(definition.key)
        initialized = bool(
            state is not None
            and state.persisted.get(definition.key, False)
        )
        value_text = (
            "{:.0f}".format(value)
            if initialized
            else "\u672a\u521d\u59cb\u5316"
        )
        row_id = 100 + index
        yield ObjectPickerRow(
            option_id=row_id,
            object_id=row_id,
            name=_raw(
                "{}\uff5c{}\uff1a{}".format(
                    direction,
                    definition.display_name,
                    value_text,
                )
            ),
            row_description=_raw(
                "{}\n\u70b9\u51fb\u9009\u62e9 0\u2014100 \u7684\u6570\u503c\u3002".format(
                    definition.description
                )
            ),
            tag=_PickerChoice(
                row_id,
                "select_dimension",
                dimension=definition.key,
            ),
            is_selected=False,
            is_enable=True,
        )


def _value_rows(inst, target, context, dimension):
    observer, partner = _pair_from_picker(inst, target, context)
    definition = DIMENSION_DEFINITIONS.get(dimension)
    if observer is None or partner is None or definition is None:
        return
    state = _state_for(observer, partner)
    current = 0.0 if state is None else state.get(dimension)
    initialized = bool(
        state is not None
        and state.persisted.get(dimension, False)
    )
    direction = _direction_text(observer, partner)
    yield ObjectPickerRow(
        option_id=_BACK_TO_DIMENSIONS_ID,
        object_id=_BACK_TO_DIMENSIONS_ID,
        name=_raw(
            "\u8fd4\u56de\u4e94\u7ef4\uff5c{}".format(direction)
        ),
        row_description=_raw(
            "\u5f53\u524d\u7f16\u8f91\uff1a{}\uff0c{}".format(
                definition.display_name,
                (
                    "\u5f53\u524d\u503c {:.1f}".format(current)
                    if initialized
                    else "\u5c1a\u672a\u521d\u59cb\u5316"
                ),
            )
        ),
        tag=_PickerChoice(
            _BACK_TO_DIMENSIONS_ID,
            "back_to_dimensions",
        ),
        is_enable=True,
    )
    yield ObjectPickerRow(
        option_id=_CUSTOM_VALUE_ID,
        object_id=_CUSTOM_VALUE_ID,
        name=_raw(
            "\u81ea\u5b9a\u4e49\u6570\u503c\uff5c{} \u2192 {}\uff5c{}".format(
                _sim_name(observer),
                _sim_name(partner),
                definition.display_name,
            )
        ),
        row_description=_raw(
            "\u8f93\u5165 0\u2014100 \u4e4b\u95f4\u7684\u6570\u503c\u3002"
            "\u5f53\u524d\u503c\uff1a{:.1f}".format(current)
        ),
        tag=_PickerChoice(
            _CUSTOM_VALUE_ID,
            "custom_dimension",
            dimension=dimension,
        ),
        is_selected=False,
        is_enable=True,
    )
    for index, value in enumerate(definition.picker_values):
        row_id = 1000 + index
        current_suffix = (
            "\uff08\u5f53\u524d\uff09"
            if initialized and abs(current - value) < 0.01
            else ""
        )
        yield ObjectPickerRow(
            option_id=row_id,
            object_id=row_id,
            name=_raw(
                "{}\uff5c{}\uff1a{}{}".format(
                    direction,
                    definition.display_name,
                    value,
                    current_suffix,
                )
            ),
            row_description=_raw(definition.description),
            tag=_PickerChoice(
                row_id,
                "set_dimension",
                dimension=dimension,
                value=value,
            ),
            # Keep this a true single-select picker.  EA increases
            # max_selectable when any row is preselected, which turns the
            # dialog into a confirmation/multi-select flow and prevents the
            # one-click value callback expected here.
            is_selected=False,
            is_enable=True,
        )


def _settings_rows():
    enabled = settings.is_check_in_warning_enabled()
    yield ObjectPickerRow(
        option_id=_TOGGLE_WARNING_ID,
        object_id=_TOGGLE_WARNING_ID,
        name=_raw(
            "\u67e5\u5c97\u5373\u5c06\u5230\u6765\u63d0\u793a\uff1a{}".format(
                "\u5f00" if enabled else "\u5173",
            )
        ),
        row_description=_raw(
            "\u70b9\u51fb\u8fd9\u4e00\u9879\u5207\u6362\u67e5\u5c97\u63d0\u793a\u3002"
        ),
        tag=_PickerChoice(_TOGGLE_WARNING_ID, "toggle_warning"),
        is_selected=enabled,
        is_enable=True,
    )
    records = get_claim_records()
    if not records:
        yield ObjectPickerRow(
            option_id=2,
            object_id=2,
            name=_raw(
                "\u5f53\u524d\u6ca1\u6709\u5df2\u8bb0\u5f55\u7684\u552f\u4e00\u8ba4\u5b9a"
            ),
            row_description=_raw(
                "\u70b9\u51fb\u5176\u4ed6\u5c0f\u4eba\u53ef\u7f16\u8f91\u53cc\u65b9\u72ec\u7acb\u7684\u4e94\u7ef4\u5173\u7cfb\u6570\u503c\u3002"
            ),
            tag=_PickerChoice(2, "info"),
            is_enable=True,
        )
        return
    for index, record in enumerate(records):
        observer = record["observer"]
        target_sim = record["target"]
        row_id = 200 + index
        yield ObjectPickerRow(
            option_id=row_id,
            object_id=row_id,
            name=_raw(
                "{} \u2192 {}".format(
                    _sim_name(observer),
                    _sim_name(target_sim),
                )
            ),
            row_description=_raw(
                "{} \u5f53\u524d\u8ba4\u5b9a {} \u4e3a\u552f\u4e00\u4f34\u4fa3\u3002".format(
                    _sim_name(observer),
                    _sim_name(target_sim),
                )
            ),
            tag=_PickerChoice(row_id, "info"),
            is_enable=True,
        )


def _romantic_partner_infos(viewer):
    """Return ledger and EA-romance partners without creating relationships."""
    viewer = get_sim_info(viewer)
    if viewer is None:
        return ()
    viewer_id = int(viewer.sim_id)
    partner_ids = set()

    # The project ledger is authoritative for pairs that already own any
    # five-dimensional state, summary, devotion bond, or known event.
    try:
        from fgeh_cheatingharder_ui_adapter import (
            build_character_relationships_view,
        )

        relationship_view = build_character_relationships_view(viewer)
        for relationship in relationship_view.get("relationships", ()):
            pair = relationship.get("pair", {})
            partner = pair.get("sim_b", {})
            partner_id = partner.get("sim_id")
            if partner_id is not None and int(partner_id) != viewer_id:
                partner_ids.add(int(partner_id))
    except Exception:
        log_exception(
            "relationship browser ledger candidate collection failed"
        )

    # Also include EA romantic relationships that have not acquired a custom
    # five-dimensional state yet.  Every call below is read-only: add=False is
    # deliberate, because opening UI must never initialize relationship data.
    try:
        from relationships.relationship_track import RelationshipTrack

        tracker = viewer.relationship_tracker
        romance_track = RelationshipTrack.ROMANCE_TRACK
        threshold = float(
            RelationshipTrack.ROMANCE_TRACK_FILTER_THRESHOLD
        )
        romance_bits = tuple(
            RelationshipTrack.ROMANCE_TRACK_FILTER_BITS or ()
        )
        for partner_id in tracker.target_sim_gen():
            partner_id = int(partner_id)
            if partner_id == viewer_id:
                continue
            try:
                if tracker.is_hidden(partner_id):
                    continue
            except Exception:
                pass
            is_romantic = False
            try:
                track = tracker.get_relationship_track(
                    partner_id,
                    romance_track,
                    add=False,
                )
                is_romantic = bool(
                    track is not None
                    and float(track.get_value()) >= threshold
                )
            except Exception:
                pass
            if not is_romantic and romance_bits:
                try:
                    is_romantic = tracker.has_any_bits(
                        partner_id,
                        romance_bits,
                    )
                except Exception:
                    pass
            if is_romantic:
                partner_ids.add(partner_id)
    except Exception:
        log_exception("relationship browser EA candidate collection failed")

    manager = services.sim_info_manager()
    partners = []
    for partner_id in partner_ids:
        partner = manager.get(partner_id)
        if partner is not None:
            partners.append(partner)
    partners.sort(key=lambda value: (_sim_name(value).casefold(), value.sim_id))
    return tuple(partners)


class FgehCheatingHarderSettingsPickerInteraction(PickerSuperInteraction):
    """Self-click opens settings; another Sim opens the directed editor."""

    @classmethod
    def has_valid_choice(cls, target, context, **kwargs):
        return True

    @flexmethod
    def picker_rows_gen(cls, inst, target, context, **kwargs):
        observer, partner = _pair_from_picker(inst, target, context)
        if observer is None or partner is None:
            yield from _settings_rows()
            return
        selected_dimension = getattr(
            inst,
            "_fgeh_selected_dimension",
            None,
        )
        if selected_dimension is None:
            yield from _dimension_rows(inst, target, context)
        else:
            yield from _value_rows(
                inst,
                target,
                context,
                selected_dimension,
            )

    def _show_current_page(self):
        return self._show_picker_dialog(
            self.sim,
            target_sim=self.target,
            target=self.target,
        )

    def _set_dimension_value(self, dimension, value, reason):
        observer, partner = _pair_from_picker(
            self,
            self.target,
            self.context,
        )
        if observer is None or partner is None:
            return False
        try:
            from fgeh_cheatingharder_state import set_directed_dimension

            state = set_directed_dimension(
                observer,
                partner,
                dimension,
                value,
                reason=reason,
            )
            actual = (
                None
                if state is None
                else state.get(dimension)
            )
            log(
                "picker dimension set edge={}->{} dimension={} requested={} actual={} reason={}",
                observer.sim_id,
                partner.sim_id,
                dimension,
                value,
                actual,
                reason,
            )
            return state is not None
        except Exception:
            log_exception(
                "picker dimension set failed edge={}->{} dimension={}".format(
                    observer.sim_id,
                    partner.sim_id,
                    dimension,
                )
            )
            return False

    def _show_custom_value_dialog(self, dimension):
        observer, partner = _pair_from_picker(
            self,
            self.target,
            self.context,
        )
        definition = DIMENSION_DEFINITIONS.get(dimension)
        if observer is None or partner is None or definition is None:
            self._show_current_page()
            return
        try:
            import math
            from event_testing.resolver import SingleSimResolver
            from ui.ui_dialog_generic import UiDialogTextInputOkCancel

            owner = self.sim
            state = _state_for(observer, partner)
            current = 0.0 if state is None else state.get(dimension)
            direction = _direction_text(observer, partner)
            title = _raw(
                "\u81ea\u5b9a\u4e49{}\uff5c{}".format(
                    definition.display_name,
                    direction,
                )
            )
            text = _raw(
                "\u8bf7\u8f93\u5165 0\u2014100 \u4e4b\u95f4\u7684\u6570\u503c\u3002"
                "\u8fd9\u53ea\u4f1a\u4fee\u6539 {} \u7684{}\u3002".format(
                    direction,
                    definition.display_name,
                )
            )
            dialog_factory = UiDialogTextInputOkCancel.TunableFactory(
                text_inputs=(_CUSTOM_VALUE_INPUT,)
            ).default
            dialog = dialog_factory(
                owner,
                resolver=SingleSimResolver(owner.sim_info),
                title=lambda *args, **kwargs: title,
                text=lambda *args, **kwargs: text,
                text_ok=lambda *args, **kwargs: _raw("\u786e\u5b9a"),
                text_cancel=lambda *args, **kwargs: _raw("\u53d6\u6d88"),
                min_value=0,
                max_value=100,
            )
            text_input_overrides = {
                _CUSTOM_VALUE_INPUT: (
                    lambda *args, **kwargs: _raw(
                        "{:g}".format(current)
                    )
                )
            }

            def _on_response(response_dialog):
                try:
                    if response_dialog.accepted:
                        raw_value = response_dialog.text_input_responses.get(
                            _CUSTOM_VALUE_INPUT,
                            "",
                        )
                        value = float(str(raw_value).strip())
                        if (
                            not math.isfinite(value)
                            or value < 0
                            or value > 100
                        ):
                            raise ValueError("value outside 0-100")
                        self._set_dimension_value(
                            dimension,
                            value,
                            "player_picker_custom",
                        )
                except Exception:
                    log_exception(
                        "picker custom value rejected dimension={}".format(
                            dimension
                        )
                    )
                self._fgeh_selected_dimension = dimension
                self._show_current_page()

            dialog.show_dialog(
                on_response=_on_response,
                text_input_overrides=text_input_overrides,
            )
            log(
                "picker custom value dialog shown edge={}->{} dimension={} current={}",
                observer.sim_id,
                partner.sim_id,
                dimension,
                current,
            )
        except Exception:
            log_exception(
                "picker custom value dialog failed dimension={}".format(
                    dimension
                )
            )
            self._show_current_page()

    def _run_interaction_gen(self, timeline):
        del timeline
        self._fgeh_edit_reversed = False
        self._fgeh_selected_dimension = None
        observer, partner = _base_pair_from_picker(
            self,
            self.target,
            self.context,
        )
        if observer is not None and partner is not None:
            try:
                from fgeh_cheatingharder_relationship_panel import (
                    show_relationship_panel,
                )

                if show_relationship_panel(observer, partner):
                    return True
            except Exception:
                log_exception("relationship panel safe shell entry failed")
        # Self-click still opens settings.  Any shell-side Python failure also
        # falls back to the proven numeric picker.
        self._show_current_page()
        return True
        if False:
            yield None

    def _route_choice_selected(self, choice, **kwargs):
        if choice is None:
            return
        action = getattr(choice, "action", None)
        if action == "toggle_warning":
            enabled = settings.set_check_in_warning_enabled(
                not settings.is_check_in_warning_enabled()
            )
            log("picker toggled check-in warning enabled={}", enabled)
            return self._show_current_page()
        if action == "switch_direction":
            self._fgeh_edit_reversed = not self._fgeh_edit_reversed
            self._fgeh_selected_dimension = None
            log(
                "picker direction switched reversed={}",
                self._fgeh_edit_reversed,
            )
            return self._show_current_page()
        if action == "evaluate_relationship":
            observer, partner = _pair_from_picker(
                self,
                self.target,
                self.context,
            )
            if observer is None or partner is None:
                return
            from fgeh_cheatingharder_domain import EventType
            from fgeh_cheatingharder_event_center import (
                get_last_decision,
                get_last_execution,
                publish,
            )

            publish(
                EventType.RELATIONSHIP_REEVALUATION,
                source="player_picker_test",
                observer_id=observer.sim_id,
                partner_id=partner.sim_id,
                payload={
                    "scheduled_reason": "player_picker_test",
                    "debug_ignore_breakup_cooldown": True,
                },
            )
            try:
                from fgeh_cheatingharder_notification import (
                    show_relationship_evaluation_notification,
                )

                show_relationship_evaluation_notification(
                    observer,
                    partner,
                    get_last_decision(observer.sim_id, partner.sim_id),
                    get_last_execution(observer.sim_id, partner.sim_id),
                )
            except Exception:
                log_exception("picker relationship evaluation notification failed")
            log(
                "picker relationship reevaluation requested edge={}->{}",
                observer.sim_id,
                partner.sim_id,
            )
            return
        if action == "select_dimension":
            self._fgeh_selected_dimension = choice.dimension
            log(
                "picker dimension selected reversed={} dimension={}",
                self._fgeh_edit_reversed,
                choice.dimension,
            )
            return self._show_current_page()
        if action == "back_to_dimensions":
            self._fgeh_selected_dimension = None
            return self._show_current_page()
        if action == "custom_dimension":
            self._fgeh_selected_dimension = choice.dimension
            return self._show_custom_value_dialog(choice.dimension)
        if action != "set_dimension":
            return
        self._set_dimension_value(
            choice.dimension,
            choice.value,
            "player_picker",
        )
        self._fgeh_selected_dimension = choice.dimension
        return self._show_current_page()

    def on_choice_selected(self, choice, **kwargs):
        log(
            "picker choice received action={} dimension={} value={} reversed={}",
            getattr(choice, "action", None),
            getattr(choice, "dimension", None),
            getattr(choice, "value", None),
            getattr(self, "_fgeh_edit_reversed", False),
        )
        try:
            return self._route_choice_selected(choice, **kwargs)
        except Exception:
            log_exception(
                "picker choice routing failed action={}".format(
                    getattr(choice, "action", None)
                )
            )
            try:
                return self._show_current_page()
            except Exception:
                log_exception("picker choice recovery failed")
                return None


class FgehCheatingHarderEditPickerInteraction(
    FgehCheatingHarderSettingsPickerInteraction
):
    """Developer entry that opens the existing numeric editor directly."""

    @classmethod
    def has_valid_choice(cls, target, context, **kwargs):
        observer, partner = _base_pair_from_picker(None, target, context)
        return observer is not None and partner is not None

    def _run_interaction_gen(self, timeline):
        del timeline
        self._fgeh_edit_reversed = False
        self._fgeh_selected_dimension = None
        observer, partner = _base_pair_from_picker(
            self,
            self.target,
            self.context,
        )
        if observer is None or partner is None:
            log("relationship edit picker skipped: target is not another Sim")
            return False
        self._show_current_page()
        log(
            "relationship edit picker shown pair={}->{}",
            observer.sim_id,
            partner.sim_id,
        )
        return True
        if False:
            yield None


class FgehCheatingHarderRelationshipBrowserInteraction(
    ImmediateSuperInteraction
):
    """Immediately open a scalable EA Sim picker, then one selected pair."""

    @classmethod
    def _test(cls, target, context, **interaction_parameters):
        base_result = super()._test(
            target,
            context,
            **interaction_parameters
        )
        viewer = get_sim_info(getattr(context, "sim", None))
        if viewer is None:
            return TestResult(False, "A valid active Sim is required.")
        if not bool(getattr(viewer, "is_selectable", False)):
            return TestResult(False, "The relationship browser requires a selectable Sim.")
        # This interaction only opens UI and never asks the actor to route,
        # reserve the clicked Sim, or change posture.  A ChoiceMenu performs
        # the affordance test again when the player clicks the row.  During an
        # active social, EA's generic SuperInteraction test can change between
        # menu construction and that second test, silently swallowing the
        # click before _run_interaction_gen is reached.  Keep our own safety
        # checks above, but do not let transient posture/social state block a
        # purely immediate browser.
        if not base_result:
            log(
                "relationship browser transient base test bypassed "
                "viewer={} target={} reason={}",
                getattr(viewer, "sim_id", None),
                getattr(get_sim_info(target), "sim_id", None),
                base_result,
            )
        return TestResult.TRUE

    def _run_interaction_gen(self, timeline):
        del timeline
        log(
            "relationship browser interaction entered viewer={} target={}",
            getattr(get_sim_info(self.sim), "sim_id", None),
            getattr(get_sim_info(self.target), "sim_id", None),
        )
        try:
            from sims4.localization import LocalizationHelperTuning
            from ui.ui_dialog_picker import SimPickerRow, UiSimPicker

            viewer = get_sim_info(self.sim)
            if viewer is None:
                return False
            partners = _romantic_partner_infos(viewer)
            title = LocalizationHelperTuning.get_raw_text(
                "选择要查看的关系"
            )
            description = LocalizationHelperTuning.get_raw_text(
                (
                    "选择一名恋爱对象查看五维关系。"
                    if partners
                    else "暂时没有可显示的恋爱对象或五维关系记录。"
                )
            )
            dialog = UiSimPicker.TunableFactory().default(
                self.sim,
                title=lambda *args, **kwargs: title,
                text=lambda *args, **kwargs: description,
                min_selectable=1,
                max_selectable=1,
                column_count=4,
                should_show_names=True,
            )
            for partner in partners:
                dialog.add_row(
                    SimPickerRow(
                        sim_id=partner.sim_id,
                        select_default=False,
                        tag=partner.sim_id,
                    )
                )

            def _on_partner_selected(response_dialog):
                try:
                    if not response_dialog.accepted:
                        return
                    selected = tuple(
                        response_dialog.get_result_tags() or ()
                    )
                    if not selected:
                        return
                    partner = services.sim_info_manager().get(
                        int(selected[0])
                    )
                    if partner is None:
                        return
                    from fgeh_cheatingharder_relationship_panel import (
                        show_relationship_panel,
                    )

                    show_relationship_panel(viewer, partner)
                    log(
                        "relationship browser selected pair={}->{}",
                        viewer.sim_id,
                        partner.sim_id,
                    )
                except Exception:
                    log_exception(
                        "relationship browser selection callback failed"
                    )

            dialog.add_listener(_on_partner_selected)
            dialog.show_dialog()
            log(
                "relationship browser shown viewer={} candidate_count={}",
                viewer.sim_id,
                len(partners),
            )
            return True
        except Exception:
            log_exception("relationship browser show failed")
            return False
        if False:
            yield None


def install_picker_affordance():
    global _PICKER_INSTALLED
    if _PICKER_INSTALLED:
        return True
    try:
        @injector.inject(Sim, "pre_add", safe=True)
        def _add_picker_affordance(original, sim, manager, *args, **kwargs):
            result = original(sim, manager, *args, **kwargs)
            try:
                affordances = tuple(
                    getattr(sim, "_super_affordances", ()) or ()
                )
                additions = []
                for interaction_id in (
                    settings.PICKER_INTERACTION_ID,
                    settings.RELATIONSHIP_EDIT_INTERACTION_ID,
                    settings.RELATIONSHIP_BROWSER_INTERACTION_ID,
                    settings.ROMANTIC_JOURNAL_INTERACTION_ID,
                ):
                    interaction = _get_picker_interaction(interaction_id)
                    if (
                        interaction is not None
                        and interaction not in affordances
                        and interaction not in additions
                    ):
                        additions.append(interaction)
                if additions:
                    sim._super_affordances = affordances + tuple(additions)
                    log(
                        "picker affordances added sim={} count={}",
                        getattr(sim, "id", None),
                        len(additions),
                    )
            except Exception:
                log_exception("picker affordance add failed")
            return result

        _PICKER_INSTALLED = True
        log("picker affordance injector installed")
        return True
    except Exception:
        log_exception("picker affordance injector failed")
        return False
