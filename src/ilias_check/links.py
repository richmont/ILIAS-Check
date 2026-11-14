"""ILIAS repository-link recognition and token-free canonicalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from ilias_check.transport import _has_sensitive_url_material, _origin
from ilias_check.read_routes import passive_read_route


_TYPE_NAMES = {
    "fold": "folder",
    "folder": "folder",
    "file": "document",
    "exc": "exercise",
    "exercise": "exercise",
    "lm": "learning_module",
    "learningmodule": "learning_module",
    "seq": "learning_sequence",
    "lso": "learning_sequence",
    "sequence": "learning_sequence",
    "crs": "course",
    "course": "course",
    "cat": "category",
    "category": "category",
    "grp": "group",
    "group": "group",
    "wiki": "wiki",
    "webr": "web_resource",
    "tst": "test",
    "svy": "survey",
    "frm": "forum",
}
_READ_ONLY_BASE_CLASS_COMMANDS = {
    "ilrepositorygui": {"", "infoscreen"},
    "ilexercisehandlergui": {"infoscreen"},
}
_TARGET = re.compile(r"^(?P<type>[A-Za-z][A-Za-z0-9_-]*)_(?P<id>[0-9]+)$")
_GO_PATH = re.compile(r"(?:^|/)go/(?P<type>[A-Za-z][A-Za-z0-9_-]*)/(?P<id>[0-9]+)(?P<download>/download)?/?$")
_PATH_PAIR = re.compile(
    r"(?:^|/)goto\.php/(?P<type>[A-Za-z][A-Za-z0-9_-]*)/(?P<id>[0-9]+)(?:/|$)",
    re.IGNORECASE,
)
_PATH_COMBINED = re.compile(
    r"(?:^|/)goto\.php/(?P<type>[A-Za-z][A-Za-z0-9_-]*)_(?P<id>[0-9]+)(?:/|$)",
    re.IGNORECASE,
)
_MUTATION_QUERY_KEYS = {
    "action",
    "cmd",
    "delete",
    "finish",
    "complete",
    "join",
    "leave",
    "logout",
    "submit",
    "save",
    "unsubscribe",
    "step",
    "next",
    "previous",
    "lsocmd",
    "lsov",
    "lsoni",
    "lson",
    "lsop",
}


@dataclass(frozen=True, slots=True)
class ObjectRef:
    ref_id: str
    type_code: str
    object_type: str
    url: str
    read_url: str | None = None

    @property
    def key(self) -> str:
        return f"{self.type_code}:{self.ref_id}"


def canonical_object_url(
    base_url: str, client_id: str, type_code: str, ref_id: str
) -> str:
    """Build the session-free ILIAS goto URL for a recognized object reference."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", type_code):
        raise ValueError("Invalid ILIAS object type.")
    if not re.fullmatch(r"[1-9][0-9]*", str(ref_id)):
        raise ValueError("Invalid ILIAS reference ID.")
    return (
        f"{base_url.rstrip('/')}/goto.php?"
        f"target={type_code}_{ref_id}&client_id={client_id}"
    )


def object_ref_from_parts(
    base_url: str, client_id: str, type_code: str, ref_id: str
) -> ObjectRef | None:
    """Create a reference from explicit passive metadata such as data attributes."""
    normalized_type = type_code.strip().lower()
    normalized_id = str(ref_id).strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", normalized_type):
        return None
    if not re.fullmatch(r"[1-9][0-9]*", normalized_id):
        return None
    normalized_id = str(int(normalized_id))
    return ObjectRef(
        ref_id=normalized_id,
        type_code=normalized_type,
        object_type=_TYPE_NAMES.get(normalized_type, "unsupported"),
        url=canonical_object_url(base_url, client_id, normalized_type, normalized_id),
    )


def normalize_object_link(
    href: str,
    page_url: str,
    base_url: str,
    client_id: str,
) -> ObjectRef | None:
    """Resolve a recognized modern/legacy object link and remove session material."""
    if not href or href.startswith(("mailto:", "javascript:", "#")):
        return None
    absolute = urljoin(page_url, href)
    try:
        parsed = urlsplit(absolute)
        if _origin(absolute) != _origin(base_url):
            return None
    except ValueError:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if _has_sensitive_url_material(absolute):
        return None
    installation_path = urlsplit(base_url).path.rstrip("/")
    if installation_path and not parsed.path.startswith(installation_path + "/"):
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(set(values)) != 1 for values in query.values()):
        return None
    base_classes = [value.lower() for value in query.get("baseClass", [])]
    base_class = base_classes[0] if len(base_classes) == 1 else ""
    read_only_cmds = _READ_ONLY_BASE_CLASS_COMMANDS.get(base_class, set())
    # Download links are repository metadata. Canonicalize them to the file
    # object's page; the crawler never requests these byte-serving routes.
    file_download_link = (
        parsed.path.rsplit("/", 1)[-1].lower() == "ilias.php"
        and query.get("cmdClass") == ["ilObjFileGUI"]
        and query.get("cmd") == ["sendfile"]
        and len(query.get("ref_id", [])) == 1
        and re.fullmatch(r"[1-9][0-9]*", query["ref_id"][0]) is not None
    )
    if any(
        key.lower().split("[", 1)[0] in _MUTATION_QUERY_KEYS
        and not (
            parsed.path.rsplit("/", 1)[-1].lower() == "ilias.php"
            and key.lower() == "cmd"
            and len(values) == 1
            and (values[0].lower() in read_only_cmds or passive_read_route(absolute) or file_download_link)
        )
        for key, values in query.items()
    ):
        return None

    found: tuple[str, str] | None = None
    legacy_read_url: str | None = None
    match = _GO_PATH.search(parsed.path)
    if match and (not match.group("download") or match.group("type") == "file"):
        found = match.group("type"), match.group("id")
    if parsed.path.lower().endswith("/goto.php") or "/goto.php/" in parsed.path.lower():
        target = parse_qs(parsed.query).get("target", [])
        if target:
            raw_target = target[0]
            if re.fullmatch(r"file_[1-9][0-9]*_download", raw_target):
                raw_target = raw_target.removesuffix("_download")
            match = _TARGET.fullmatch(raw_target)
            if match:
                found = match.group("type"), match.group("id")
        if found is None:
            match = _PATH_PAIR.search(parsed.path) or _PATH_COMBINED.search(parsed.path)
            if match:
                found = match.group("type"), match.group("id")

    if found is None:
        target = (query.get("target") or [None])[0]
        if target:
            match = _TARGET.fullmatch(target)
            if match:
                found = match.group("type"), match.group("id")
        if found is None:
            ref_id = (query.get("ref_id") or [None])[0]
            if ref_id and re.fullmatch(r"[1-9][0-9]*", ref_id):
                base_class = (query.get("baseClass") or [""])[0]
                explicit_type = (
                    (query.get("obj_type") or query.get("type") or [None])[0]
                )
                controller = (query.get("cmdClass") or [""])[0].lower()
                controller_types = {
                    "ilobjexercisegui": "exc",
                    "ilexsubmissionfilegui": "exc",
                    "ilexsubmissionteamgui": "exc",
                    "ilobjcoursegui": "crs",
                    "ilobjfoldergui": "fold",
                    "ilobjcategorygui": "cat",
                    "ilobjgroupgui": "grp",
                    "ilobjfilegui": "file",
                }
                type_code = explicit_type or controller_types.get(controller) or _type_from_base_class(base_class)
                if type_code:
                    found = type_code, ref_id
                    normalized_base_class = base_class.lower()
                    if (
                        not explicit_type
                        and normalized_base_class
                        in _READ_ONLY_BASE_CLASS_COMMANDS
                    ):
                        read_query = {
                            "baseClass": (
                                "ilExerciseHandlerGUI"
                                if normalized_base_class == "ilexercisehandlergui"
                                else "ilRepositoryGUI"
                            ),
                            "ref_id": str(int(ref_id)),
                            "client_id": client_id,
                        }
                        commands = query.get("cmd", [])
                        if (
                            normalized_base_class == "ilexercisehandlergui"
                            and
                            len(commands) == 1
                            and commands[0].lower()
                            in _READ_ONLY_BASE_CLASS_COMMANDS[normalized_base_class]
                            and commands[0]
                        ):
                            read_query["cmd"] = "infoScreen"
                        if normalized_base_class == "ilrepositorygui" and commands == ["view"]:
                            read_query["cmd"] = "view"
                        legacy_read_url = urlunsplit(
                            (
                                parsed.scheme,
                                parsed.netloc,
                                parsed.path,
                                urlencode(read_query),
                                "",
                            )
                        )

    if found is None:
        return None
    type_code, raw_id = found
    ref_id = str(int(raw_id))
    if int(ref_id) <= 0:
        return None
    return ObjectRef(
        ref_id=ref_id,
        type_code=type_code.lower(),
        object_type=(
            "unresolved"
            if legacy_read_url is not None and type_code.lower() == "obj"
            else _TYPE_NAMES.get(type_code.lower(), "unsupported")
        ),
        url=canonical_object_url(base_url, client_id, type_code.lower(), ref_id),
        read_url=legacy_read_url,
    )


def _type_from_base_class(base_class: str) -> str | None:
    normalized = base_class.lower()
    if normalized == "illmpresentationgui":
        return "lm"
    if normalized == "ilexercisehandlergui":
        return "exc"
    if "repository" in normalized:
        return "obj"
    if "sequence" in normalized:
        return "seq"
    if "learningmodule" in normalized:
        return "lm"
    return None
