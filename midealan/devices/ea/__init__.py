"""Midea lan EA device."""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDeviceInitKwargs, ToshibaDevice
from midealan.message import MessageRequest, ToshibaFrame

from .message import MessageEAResponse, MessageQuery

_LOGGER = logging.getLogger(__name__)
TOSHIBA_BASE_STATUS_LENGTH = 25
TOSHIBA_STATUS_COOKING = 0x0A
TOSHIBA_STATUS_KEEP_WARM = 0x07
TOSHIBA_BASE_FRAME_TYPES = frozenset((0x0003, 0x8003, 0x0004))
MINUTES_PER_HOUR = 60


class DeviceAttributes(StrEnum):
    """Midea EA device attributes."""

    cooking = "cooking"
    keep_warm = "keep_warm"
    mode = "mode"
    time_remaining = "time_remaining"
    keep_warm_time = "keep_warm_time"
    top_temperature = "top_temperature"
    bottom_temperature = "bottom_temperature"
    progress = "progress"


class MideaEADevice(ToshibaDevice):
    """Midea EA device."""

    TOSHIBA_RESPONSE_FRAME_TYPES = frozenset(
        TOSHIBA_BASE_FRAME_TYPES,
    )

    _toshiba_progress: ClassVar[dict[int, str]] = {
        0x01: "stop",
        0x02: "error",
        0x03: "reserved",
        0x04: "soak",
        0x05: "rice_cooking",
        0x06: "steam",
        0x07: "keep_warm",
        0x08: "heat_cleaning",
        0x0A: "cooking",
    }

    _mode_list: ClassVar[list[str]] = (
        [
            "smart",
            "reserve",
            "cook_rice",
            "fast_cook_rice",
            "standard_cook_rice",
            "gruel",
            "cook_congee",
            "stew_soup",
            "stewing",
            "heat_rice",
            "make_cake",
            "yoghourt",
            "soup_rice",
            "coarse_rice",
            "five_ceeals_rice",
            "eight_treasures_rice",
            "crispy_rice",
            "shelled_rice",
            "eight_treasures_congee",
            "infant_congee",
            "older_rice",
            "rice_soup",
            "rice_paste",
            "egg_custard",
            "warm_milk",
            "hot_spring_egg",
            "millet_congee",
            "firewood_rice",
            "few_rice",
            "red_potato",
            "corn",
            "quick_freeze_bun",
            "steam_ribs",
            "steam_egg",
            "coarse_congee",
            "steep_rice",
            "appetizing_congee",
            "corn_congee",
            "sprout_rice",
            "luscious_rice",
            "luscious_boiled",
            "fast_rice",
            "fast_boil",
            "bean_rice_congee",
            "fast_congee",
            "baby_congee",
            "cook_soup",
            "congee_coup",
            "steam_corn",
            "steam_red_potato",
            "boil_congee",
            "delicious_steam",
            "boil_egg",
            "rice_wine",
            "fruit_vegetable_paste",
            "vegetable_porridge",
            "pork_porridge",
            "fragrant_rice",
            "assorte_rice",
            "steame_fish",
            "baby_rice",
            "essence_rice",
            "fragrant_dense_congee",
            "one_two_cook",
            "original_steame",
            "hot_fast_rice",
            "online_celebrity_rice",
            "sushi_rice",
            "stone_bowl_rice",
            "no_water_treat",
            "keep_fresh",
            "low_sugar_rice",
            "black_buckwheat_rice",
            "resveratrol_rice",
            "yellow_wheat_rice",
            "green_buckwheat_rice",
            "roughage_rice",
            "millet_mixed_rice",
            "iron_pan_rice",
            "olla_pan_rice",
            "vegetable_rice",
            "baby_side",
            "regimen_congee",
            "earthen_pot_congee",
            "regimen_soup",
            "pottery_jar_soup",
            "canton_soup",
            "nutrition_stew",
            "northeast_stew",
            "uncap_boil",
            "trichromatic_coarse_grain",
            "four_color_vegetables",
            "egg",
            "chop",
        ]
        + ["unknown"] * 98
        + ["clean"]
        + ["unknown"] * 5
        + ["keep_warm"]
    )
    _progress: ClassVar[list[str]] = ["idle", "delay", "cooking", "keep_warm"]

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea EA device."""
        super().__init__(
            device_type=DeviceType.EA,
            **kwargs,
            attributes={
                DeviceAttributes.cooking: False,
                DeviceAttributes.keep_warm: False,
                DeviceAttributes.mode: 0,
                DeviceAttributes.time_remaining: None,
                DeviceAttributes.top_temperature: None,
                DeviceAttributes.bottom_temperature: None,
                DeviceAttributes.keep_warm_time: None,
                DeviceAttributes.progress: "unknown",
            },
        )

    def build_query(self) -> list[MessageRequest]:
        """Midea EA device build query."""
        if self.toshiba_protocol:
            return self.build_toshiba_query()
        return [MessageQuery(self._message_protocol_version)]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea EA device process message."""
        status = self.process_toshiba_message(msg)
        if status is not None:
            return status
        message = MessageEAResponse(msg)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                value = getattr(message, str(status))
                if status == DeviceAttributes.progress:
                    if value < len(MideaEADevice._progress):
                        self._attributes[status] = MideaEADevice._progress[value]
                    else:
                        self._attributes[status] = "unknown"
                elif status == DeviceAttributes.mode:
                    if value < len(MideaEADevice._mode_list):
                        self._attributes[status] = MideaEADevice._mode_list[value]
                    else:
                        self._attributes[status] = "cloud"
                else:
                    self._attributes[status] = value
                new_status[str(status)] = self._attributes[status]
        return new_status

    @staticmethod
    def _bcd(value: int) -> int:
        """Decode the packed-decimal time fields used by Toshiba rice cookers."""
        return value - (value // 0x10) * 6

    def process_toshiba_frame(self, frame: ToshibaFrame) -> dict[str, Any] | None:
        """Decode the common Toshiba rice-cooker status generations."""
        body = frame.body
        if len(body) < TOSHIBA_BASE_STATUS_LENGTH or body[0] != 0x00:
            return None
        cooking_state = body[23]
        course = body[16]
        progress = self._toshiba_progress.get(cooking_state, "stop")
        hours = self._bcd(body[22])
        minutes = self._bcd(body[21])
        values: dict[DeviceAttributes, Any] = {
            DeviceAttributes.cooking: cooking_state == TOSHIBA_STATUS_COOKING,
            DeviceAttributes.keep_warm: cooking_state == TOSHIBA_STATUS_KEEP_WARM,
            DeviceAttributes.mode: course,
            DeviceAttributes.time_remaining: hours * MINUTES_PER_HOUR + minutes,
            DeviceAttributes.progress: progress,
        }
        self._attributes.update(values)
        return {str(attr): value for attr, value in values.items()}

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea EA device set attribute."""
        del attr, value
        self.reject_toshiba_write()


class MideaAppliance(MideaEADevice):
    """Midea EA appliance."""
