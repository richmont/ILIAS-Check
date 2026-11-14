"""Validated local scope choices for pending-work classification."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class PolicyError(ValueError):
    """A safe configuration diagnostic without raw configuration values."""


@dataclass(frozen=True, slots=True)
class AlternativeSet:
    name: str
    members: tuple[str, ...]
    selected: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassificationPolicy:
    timezone: str | None = None
    excluded_exercises: tuple[str, ...] = ()
    alternative_sets: tuple[AlternativeSet, ...] = ()
    include_contextual: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> ClassificationPolicy:
        timezone = (values.get("ILIAS_TIMEZONE") or "").strip() or None
        if timezone:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise PolicyError("ILIAS_TIMEZONE must be a valid IANA timezone.") from None
        excluded_text = (values.get("ILIAS_PENDING_EXCLUDE_EXERCISES") or "").strip()
        excluded = tuple(dict.fromkeys(_identifier(x.strip()) for x in excluded_text.split(","))) if excluded_text else ()
        raw = values.get("ILIAS_PENDING_ALTERNATIVE_SETS") or "{}"
        try:
            declared = json.loads(raw, object_pairs_hook=_unique_keys)
        except (ValueError, TypeError):
            raise PolicyError("ILIAS_PENDING_ALTERNATIVE_SETS must be JSON without duplicate keys.") from None
        if not isinstance(declared, dict):
            raise PolicyError("ILIAS_PENDING_ALTERNATIVE_SETS must be a named object.")
        sets = []
        seen = set()
        for name, definition in declared.items():
            if not name.strip() or not isinstance(definition, dict) or set(definition) != {"members", "selected"}:
                raise PolicyError("Each alternative set requires members and selected lists.")
            members = _identifiers(definition["members"])
            selected = _identifiers(definition["selected"])
            if not members or not set(selected).issubset(members):
                raise PolicyError("Alternative selections must belong to a nonempty member set.")
            if seen.intersection(members):
                raise PolicyError("Alternative sets must not overlap.")
            seen.update(members)
            sets.append(AlternativeSet(name, members, selected))
        contextual = (values.get("ILIAS_PENDING_INCLUDE_CONTEXTUAL") or "false").strip().casefold()
        if contextual not in {"true", "false"}:
            raise PolicyError("ILIAS_PENDING_INCLUDE_CONTEXTUAL must be true or false.")
        return cls(timezone, excluded, tuple(sets), contextual == "true")

    def selection(self, exercise_id: str) -> str | None:
        if exercise_id in self.excluded_exercises:
            return "excluded"
        for alternative in self.alternative_sets:
            if exercise_id in alternative.members:
                return "selected" if exercise_id in alternative.selected else "unselected"
        return None

    @property
    def warnings(self) -> tuple[str, ...]:
        selected = {x for group in self.alternative_sets for x in group.selected}
        return ("selected_exercise_explicitly_excluded",) if selected.intersection(self.excluded_exercises) else ()


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise PolicyError("Exercise rules require positive numeric IDs as strings.")
    return value


def _identifiers(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PolicyError("Alternative members and selected must be lists of ID strings.")
    ids = tuple(_identifier(x) for x in value)
    if len(set(ids)) != len(ids):
        raise PolicyError("Alternative ID lists must not contain duplicates.")
    return ids


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result
