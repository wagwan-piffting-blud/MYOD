from __future__ import annotations

import json
import re
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


EAS_REGEX = re.compile(
    r"^ZCZC-([A-Z]{3})-([A-Z\?]{3})-((?:\d{6}(?:-?)){1,31})\+(\d{4})-(\d{7})-([A-Za-z0-9/ ]{1,8}?)-$",
    re.MULTILINE,
)
FIXED_TZ_OFFSET_REGEX = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
INVALID_HEADER_MESSAGE = "Invalid EAS header format"

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_ABBR_UPPER = [month.upper() for month in MONTH_ABBR]
WEEKDAY_ABBR = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

STATE_ABBREVIATIONS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
PROVINCE_ABBREVIATIONS = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}


@dataclass(frozen=True)
class EASDuration:
    hours: int
    minutes: int


@dataclass(frozen=True)
class ParsedEAS:
    originator: str
    event_code: str
    locations: list[str]
    duration: EASDuration
    start_time: datetime
    senderid: str

    @property
    def fips_codes(self) -> list[str]:
        return self.locations

    @property
    def sender_id(self) -> str:
        return self.senderid


@dataclass
class FIPSContext:
    codes: list[str]
    fips_text: list[str]
    fips_text_with_and: list[str]
    str_fips: str


def _include_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / "include" / filename


def _load_resource(filename: str) -> dict[str, Any]:
    with _include_path(filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


RESOURCE_MAP = {
    "sameUS": _load_resource("same-us.json"),
    "sameCA": _load_resource("same-ca.json"),
    "endecModes": _load_resource("endec-modes.json"),
}


def _lookup_resource(resource_key: str, section_key: str, item_key: str) -> Any:
    return RESOURCE_MAP.get(resource_key, {}).get(section_key, {}).get(item_key)


def _lookup_same(section_key: str, item_key: str, canadian_mode: bool = False) -> Any:
    return _lookup_resource("sameCA" if canadian_mode else "sameUS", section_key, item_key)


def _apply_mode_template(mode_key: str, replacements: dict[str, str]) -> str:
    template = _lookup_resource("endecModes", "TEMPLATES", mode_key)
    if not isinstance(template, str):
        return ""
    for key, value in replacements.items():
        template = template.replace(f"__{key}__", value if value is not None else "")
    return template


def _all_endec_modes() -> list[str]:
    templates = RESOURCE_MAP.get("endecModes", {}).get("TEMPLATES", {})
    if not isinstance(templates, dict):
        return []
    return sorted(mode for mode in templates.keys() if isinstance(mode, str))


def _parse_eas_time(time_str: str) -> datetime:
    day_of_year = int(time_str[:3])
    hours = int(time_str[3:5])
    minutes = int(time_str[5:7])
    year = datetime.now(timezone.utc).year
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=day_of_year - 1,
        hours=hours,
        minutes=minutes,
    )


def _parse_eas_duration(duration_str: str) -> EASDuration:
    return EASDuration(hours=int(duration_str[:2]), minutes=int(duration_str[2:4]))


def _parse_header(header: str) -> ParsedEAS:
    match = EAS_REGEX.match(header or "")
    if not match:
        raise ValueError(INVALID_HEADER_MESSAGE)

    originator, event_code, locations, duration, start_time, senderid = match.groups()
    return ParsedEAS(
        originator=originator,
        event_code=event_code,
        locations=locations.split("-"),
        duration=_parse_eas_duration(duration),
        start_time=_parse_eas_time(start_time),
        senderid=senderid,
    )


def _parsed_header_to_dict(parsed: ParsedEAS) -> dict[str, Any]:
    return {
        "originator": parsed.originator,
        "event_code": parsed.event_code,
        "fips_codes": list(parsed.fips_codes),
        "locations": list(parsed.locations),
        "duration_hours": parsed.duration.hours,
        "duration_minutes": parsed.duration.minutes,
        "start_time_utc": parsed.start_time.isoformat(),
        "sender_id": parsed.sender_id,
    }


def parse_header(header: str) -> ParsedEAS:
    return _parse_header(header)


def parse_header_json(header: str) -> str:
    parsed = _parse_header(header)
    return json.dumps(_parsed_header_to_dict(parsed), separators=(",", ":"))


def parse_header_pretty_json(header: str) -> str:
    parsed = _parse_header(header)
    return json.dumps(_parsed_header_to_dict(parsed), indent=2)


def _detect_user_local_timezone() -> tzinfo | None:
    try:
        return datetime.now().astimezone().tzinfo
    except Exception:
        return None


def _parse_fixed_offset_timezone(timezone_spec: str) -> tzinfo | None:
    match = FIXED_TZ_OFFSET_REGEX.match(timezone_spec)
    if not match:
        return None
    hours = int(match.group(2))
    minutes = int(match.group(3))
    if hours > 23 or minutes > 59:
        return None
    sign_char = match.group(1)
    sign = -1 if sign_char == "-" else 1
    offset = timedelta(hours=hours, minutes=minutes) * sign
    return timezone(offset, name=f"UTC{sign_char}{hours:02d}:{minutes:02d}")


def _parse_timezone_spec(timezone_spec: str) -> tzinfo | None:
    if not isinstance(timezone_spec, str):
        return None
    normalized = timezone_spec.strip()
    if not normalized:
        return None
    if normalized.lower() == "utc":
        return timezone.utc
    if normalized.lower() == "local":
        return _detect_user_local_timezone()

    fixed_offset = _parse_fixed_offset_timezone(normalized)
    if fixed_offset is not None:
        return fixed_offset

    try:
        return ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _resolve_output_timezone(timezone_override: str | None) -> tzinfo:
    override_text = timezone_override.strip() if isinstance(timezone_override, str) else ""
    candidates = [override_text, "local", "UTC"] if override_text else ["local", "UTC"]
    for candidate in candidates:
        parsed = _parse_timezone_spec(candidate)
        if parsed is not None:
            return parsed
    return timezone.utc


def _to_output_timezone(dt_utc: datetime, output_tz: tzinfo) -> datetime:
    return dt_utc.astimezone(output_tz)


def _zoned_parts(dt_utc: datetime, output_tz: tzinfo) -> dict[str, int | str]:
    zoned = _to_output_timezone(dt_utc, output_tz)
    weekday_sun_first = (zoned.weekday() + 1) % 7
    return {
        "year": zoned.year,
        "month": zoned.month,
        "month_index": zoned.month - 1,
        "day": zoned.day,
        "hour24": zoned.hour,
        "minute": zoned.minute,
        "weekday": weekday_sun_first,
        "date_key": f"{zoned.year:04d}-{zoned.month:02d}-{zoned.day:02d}",
    }


def _ordinal_day(day: int) -> str:
    mod_100 = day % 100
    if 11 <= mod_100 <= 13:
        return f"{day}th"
    if day % 10 == 1:
        return f"{day}st"
    if day % 10 == 2:
        return f"{day}nd"
    if day % 10 == 3:
        return f"{day}rd"
    return f"{day}th"


def _format_time12(
    dt_utc: datetime,
    output_tz: tzinfo,
    *,
    pad_hour: bool = True,
    lower_meridiem: bool = False,
) -> str:
    parts = _zoned_parts(dt_utc, output_tz)
    hour24 = int(parts["hour24"])
    hour12 = hour24 % 12 or 12
    hour = f"{hour12:02d}" if pad_hour else str(hour12)
    meridiem = "pm" if hour24 >= 12 else "am"
    if not lower_meridiem:
        meridiem = meridiem.upper()
    return f"{hour}:{int(parts['minute']):02d} {meridiem}"


def _locale_helper(dt_utc: datetime, output_tz: tzinfo) -> str:
    parts = _zoned_parts(dt_utc, output_tz)
    month_index = int(parts["month_index"])
    day = int(parts["day"])
    year = int(parts["year"])

    if month_index == 11 and day == 31 and dt_utc.month == 1 and dt_utc.day == 1:
        month_index = 0
        day = 1
        year = dt_utc.year

    return f"{_format_time12(dt_utc, output_tz, pad_hour=False)} on {MONTH_NAMES[month_index]} {_ordinal_day(day)}, {year}"


def _format_mon_day_year(
    dt_utc: datetime,
    output_tz: tzinfo,
    *,
    upper_month: bool = False,
    short_month: bool = False,
    include_year: bool = True,
) -> str:
    parts = _zoned_parts(dt_utc, output_tz)
    month_index = int(parts["month_index"])
    day = int(parts["day"])
    year = int(parts["year"])

    if short_month:
        month_name = MONTH_ABBR_UPPER[month_index] if upper_month else MONTH_ABBR[month_index]
    else:
        month_name = MONTH_NAMES[month_index].upper() if upper_month else MONTH_NAMES[month_index]

    day_text = f"{day:02d}"
    return f"{month_name} {day_text}, {year}" if include_year else f"{month_name} {day_text}"


def _get_zoned_time_zone_name(dt_utc: datetime, output_tz: tzinfo) -> str:
    zoned = _to_output_timezone(dt_utc, output_tz)
    return zoned.tzname() or "UTC"


def _format_slash_utc(dt_utc: datetime, output_tz: tzinfo) -> str:
    parts = _zoned_parts(dt_utc, output_tz)
    year_short = int(parts["year"]) % 100
    return (
        f"{int(parts['month']):02d}/{int(parts['day']):02d}/{year_short:02d} "
        f"{int(parts['hour24']):02d}:{int(parts['minute']):02d}:00 {_get_zoned_time_zone_name(dt_utc, output_tz)}"
    )


def _is_same_local_day(start_time: datetime, end_time: datetime, output_tz: tzinfo) -> bool:
    return _zoned_parts(start_time, output_tz)["date_key"] == _zoned_parts(end_time, output_tz)["date_key"]


def _format_base_range_time_text(start_time: datetime, end_time: datetime, output_tz: tzinfo) -> dict[str, str]:
    start_parts = _zoned_parts(start_time, output_tz)
    end_parts = _zoned_parts(end_time, output_tz)

    if start_parts["date_key"] == end_parts["date_key"]:
        return {
            "start": _format_time12(start_time, output_tz),
            "end": _format_time12(end_time, output_tz),
        }
    if start_parts["year"] == end_parts["year"]:
        return {
            "start": f"{_format_time12(start_time, output_tz)} {_format_mon_day_year(start_time, output_tz, include_year=False)}",
            "end": f"{_format_time12(end_time, output_tz)} {_format_mon_day_year(end_time, output_tz, include_year=False)}",
        }
    return {
        "start": f"{_format_time12(start_time, output_tz)} {_format_mon_day_year(start_time, output_tz)}",
        "end": f"{_format_time12(end_time, output_tz)} {_format_mon_day_year(end_time, output_tz)}",
    }


def _expand_state_abbreviation(name: str) -> str:
    return re.sub(
        r"[A-Z]{2}$",
        lambda match: STATE_ABBREVIATIONS.get(match.group(0), match.group(0)),
        name,
    )


def _build_fips_context(location_codes: list[str], canadian_mode: bool = False) -> FIPSContext:
    unique_codes: list[str] = []
    for code in location_codes:
        if code not in unique_codes:
            unique_codes.append(code)

    fips_text: list[str] = []
    for code in unique_codes:
        subdiv = _lookup_resource("sameUS", "SUBDIV", code[:1]) or ""
        same_name = _lookup_same("SAME", code[1:6], canadian_mode) or f"FIPS Code {code}"
        fips_text.append(f"{f'{subdiv} ' if subdiv else ''}{same_name}")

    fips_text_with_and = list(fips_text)
    if len(fips_text_with_and) > 1:
        fips_text_with_and[-1] = f"and {fips_text_with_and[-1]}"

    return FIPSContext(
        codes=unique_codes,
        fips_text=fips_text,
        fips_text_with_and=fips_text_with_and,
        str_fips=f"{'; '.join(fips_text_with_and)};",
    )


def _split_location_state(text: str) -> tuple[str, str]:
    parts = [part for part in text.split(", ") if part]
    if len(parts) <= 1:
        return (parts[0] if parts else text, "")
    return (", ".join(parts[:-1]), parts[-1])


def _filter_trilithic_location(text: str) -> str:
    result = text
    if result.startswith("City of"):
        result = re.sub(r"^City of\s*", "", result) + " city"
    if result.startswith("State of"):
        result = re.sub(r"^State of", "All of", result)
    if result.startswith("District of"):
        result = re.sub(r"^District of", "All of District of", result)
    if " City of" in result:
        result = result.replace(" City of", "") + " city"
    if " State of" in result and "All of" not in result:
        result = result.replace(" State of", " All of")
    if " District of" in result and "All of" not in result:
        result = result.replace(" District of", " All of District of")
    if " County" in result:
        result = result.replace(" County", "")
    if result.startswith("and "):
        result = re.sub(r"^and\s+", "", result)
    return result


def _filter_holly_or_gorman_location(text: str, is_gorman: bool = False) -> str:
    result = text
    if result.startswith("City of"):
        result = re.sub(r"^City of\s*", "", result) + " CITY"
    if result.startswith("State of"):
        if is_gorman:
            result = re.sub(r"^State of", "ALL", result)
        else:
            result = re.sub(r"^State of", "", result)
    if " City of" in result:
        result = result.replace(" City of", "") + " CITY"
    if " State of" in result and "All of" not in result:
        result = result.replace(" State of", "")
    if " County" in result:
        result = result.replace(" County", "")
    if result.startswith("and "):
        result = re.sub(r"^and\s+", "AND ", result)
    return result


def _process_das_fips_string(str_fips: str, combine_same_state: bool = False) -> tuple[str, bool]:
    parts = [part.strip() for part in str_fips.split(";") if part.strip()]
    states: dict[str, list[str]] = {}
    result: list[str] = []
    only_parishes = False

    for part_raw in parts:
        part = re.sub(r"^and\s+", "", part_raw, flags=re.IGNORECASE)
        match = re.match(r"^(City of )?(.*?)( County| Parish)?, (\w{2})$", part)
        state_match = re.match(r"^State of (.+)$", part)

        if match:
            city_prefix, name, locality_type, state = match.groups()
            clean_name = name

            if locality_type == " Parish":
                pass
            elif city_prefix:
                clean_name += " (city)"
                only_parishes = False
            else:
                only_parishes = False

            if state not in states:
                states[state] = []
            states[state].append(clean_name)
        elif state_match:
            result.append(state_match.group(1))
        else:
            result.append(part)

    for state, entries in states.items():
        last_index = len(entries) - 1
        for index, name in enumerate(entries):
            if not combine_same_state or index == last_index:
                result.append(f"{name}, {state}")
            else:
                result.append(name)

    final_result = "; ".join(result).replace(" and ", " ")
    final_result = re.sub(r"City of (.*?)( \(city\))?,", r"\1 (city),", final_result)
    if final_result == "":
        final_result = "; ".join(re.sub(r"^and\s+", "", part, flags=re.IGNORECASE) for part in parts)

    return (f"{final_result};", only_parishes)


def _format_location(location_code: str, is_last_item: bool, total_locations: int) -> str:
    subdivision_code = location_code[:1]
    same_code = location_code[1:6]
    location_name = _lookup_same("SAME", same_code) or same_code
    subdivision_name = _lookup_resource("sameUS", "SUBDIV", subdivision_code)

    if subdivision_name:
        base_location = _expand_state_abbreviation(location_name) if is_last_item and total_locations > 1 else location_name
        described = f"{subdivision_name}ern {base_location}"
    elif "All of" in location_name or "State of" in location_name:
        described = location_name
    else:
        described = _expand_state_abbreviation(location_name)

    if is_last_item and total_locations > 1:
        return f"and {described}"
    return described


def _remove_county_word(text: str) -> str:
    return re.sub(r"\s*County\b", "", text)


def _normalize_tft_time_text(text: str) -> str:
    text = re.sub(r"([A-Z]{3}) 0(\d)", r"\1 \2", text)
    text = re.sub(r"0(\d:\d\d [AP]M)", r"\1", text, count=1)
    return text


def _humanize_eas(
    eas: ParsedEAS,
    endec_emulation_mode: str | None = None,
    canadian_mode: bool = False,
    timezone_override: str | None = None,
) -> str:
    sender = eas.senderid.strip()
    output_tz = _resolve_output_timezone(timezone_override)
    start_time = eas.start_time

    normal_originator = _lookup_same("ORGS", eas.originator, canadian_mode) or eas.originator
    normal_event_code = _lookup_same("EVENTS", eas.event_code, canadian_mode) or eas.event_code
    fips_context = _build_fips_context(eas.locations, canadian_mode)

    location_str = "; ".join(
        _format_location(loc, index == len(eas.locations) - 1, len(eas.locations))
        for index, loc in enumerate(eas.locations)
    )

    end_time = start_time + timedelta(hours=eas.duration.hours, minutes=eas.duration.minutes)
    start_time_str = _locale_helper(start_time, output_tz)
    end_time_str = _locale_helper(end_time, output_tz)
    base_range_time = _format_base_range_time_text(start_time, end_time, output_tz)
    mode = endec_emulation_mode.upper() if isinstance(endec_emulation_mode, str) else ""

    if mode == "ALL":
        lines = [
            f"{mode_name}: {_humanize_eas(eas, mode_name, canadian_mode, timezone_override)}"
            for mode_name in _all_endec_modes()
            if mode_name != "ALL"
        ]
        return "\n\n".join(lines)

    location_str = _remove_county_word(location_str)
    fips_context.fips_text = [_remove_county_word(value) for value in fips_context.fips_text]
    fips_context.fips_text_with_and = [_remove_county_word(value) for value in fips_context.fips_text_with_and]
    fips_context.str_fips = _remove_county_word(fips_context.str_fips)

    if canadian_mode and eas.originator == "WXR":
        normal_originator = "Environment Canada"

    if mode == "TFT":
        str_fips = (
            fips_context.str_fips[:-1]
            .replace(",", "")
            .replace(";", ",")
            .replace("FIPS Code", "AREA")
        )
        str_fips = re.sub(r"State of ", "", str_fips)
        str_fips = re.sub(r"All of The United States", "UNITED STATES", str_fips, flags=re.IGNORECASE)

        tft_start = f"{_format_time12(start_time, output_tz)} ON {_format_mon_day_year(start_time, output_tz, short_month=True, upper_month=True)}"
        if _is_same_local_day(start_time, end_time, output_tz):
            tft_end = _format_time12(end_time, output_tz)
        else:
            tft_end = f"{_format_time12(end_time, output_tz)} ON {_format_mon_day_year(end_time, output_tz, short_month=True, upper_month=True)}"

        if eas.originator == "EAS" or eas.event_code in {"NPT", "EAN"}:
            prefix = f"{normal_event_code} has been issued"
        else:
            prefix = f"{normal_originator} has issued {normal_event_code}"

        return _apply_mode_template(
            "TFT",
            {
                "PREFIX": prefix,
                "FIPS": str_fips,
                "START": _normalize_tft_time_text(tft_start),
                "END": _normalize_tft_time_text(tft_end),
                "SENDER": sender,
            },
        ).upper()

    if mode == "SAGE":
        org_text = normal_originator
        if eas.originator == "CIV":
            org_text = "The Civil Authorities"
        if eas.originator == "EAS":
            org_text = "An EAS Participant"

        same_day = _is_same_local_day(start_time, end_time, output_tz)
        start_parts = _zoned_parts(start_time, output_tz)
        end_parts = _zoned_parts(end_time, output_tz)

        sage_start = _format_time12(start_time, output_tz, lower_meridiem=True)
        if not same_day:
            sage_start = (
                f"{sage_start} {WEEKDAY_ABBR[int(start_parts['weekday'])]} "
                f"{MONTH_ABBR[int(start_parts['month_index'])]} {int(start_parts['day']):02d}"
            )

        sage_end = _format_time12(end_time, output_tz, lower_meridiem=True)
        if not same_day:
            sage_end = (
                f"{sage_end} {WEEKDAY_ABBR[int(end_parts['weekday'])]} "
                f"{MONTH_ABBR[int(end_parts['month_index'])]} {int(end_parts['day']):02d}"
            )

        str_fips = fips_context.str_fips[:-1].replace(";", ",")
        str_fips = re.sub(r"All of The United States", "all of the United States", str_fips, flags=re.IGNORECASE)
        str_fips = re.sub(r"City of (.*?), ([A-Z]{2})", r"\1 city, \2", str_fips, flags=re.IGNORECASE)
        str_fips = re.sub(r"State of (.*?)", r"all of \1", str_fips, flags=re.IGNORECASE)

        return _apply_mode_template(
            "SAGE",
            {
                "ORG": org_text,
                "HAVEHAS": "have" if eas.originator == "CIV" else "has",
                "EVENTCODE": normal_event_code,
                "FIPS": str_fips,
                "START": sage_start,
                "END": sage_end,
                "SENDER": sender,
            },
        )

    if mode in {"TRILITHIC6", "TRILITHIC8PLUS"}:
        org_text = normal_originator
        if eas.originator == "CIV":
            org_text = "Civil Authorities" if mode == "TRILITHIC6" else "The Civil Authorities"

        trilithic_locations = []
        for entry in fips_context.fips_text_with_and:
            location, state = _split_location_state(entry)
            clean = _filter_trilithic_location(location)
            trilithic_locations.append(f"{clean} {state}".strip() if state else clean)
        trilithic_text = " - ".join(trilithic_locations)

        fips_text = (
            "the United States"
            if "All of The United States" in trilithic_text
            else f"the following counties: {trilithic_text}"
        )

        replacements = {
            "ORG": org_text,
            "HAVEHAS": "have" if eas.originator == "CIV" else "has",
            "EVENTCODE": normal_event_code,
            "FIPS": fips_text,
            "END": _format_slash_utc(end_time, output_tz),
        }
        if mode == "TRILITHIC8PLUS":
            replacements["SENDER"] = sender

        output = _apply_mode_template(mode, replacements)
        return re.sub(r"[\(\),!]", " ", output)

    if mode == "BURK":
        org_text = normal_originator
        if eas.originator == "EAS":
            org_text = "A Broadcast station or cable system"
        elif eas.originator == "CIV":
            org_text = "The Civil Authorities"

        str_fips = fips_context.str_fips[:-1].replace(",", "").replace(";", ",")
        event_text = " ".join(normal_event_code.split(" ")[1:]).upper()
        burk_start = f"{_format_mon_day_year(start_time, output_tz, upper_month=True)} at {_format_time12(start_time, output_tz)}"
        burk_end = f"{_format_time12(end_time, output_tz)}, {_format_mon_day_year(end_time, output_tz, upper_month=True)}".upper()

        return _apply_mode_template(
            "BURK",
            {
                "ORG": org_text,
                "HAVEHAS": "have" if eas.originator == "CIV" else "has",
                "EVENTTEXT": event_text,
                "FIPS": "the United States"
                if "All of The United States" in str_fips
                else f"for the following counties/areas: {str_fips}",
                "START": burk_start,
                "END": burk_end,
            },
        )

    if mode == "DAS1":
        org_text = normal_originator
        if eas.originator == "EAS":
            org_text = "A broadcast or cable system"
        elif eas.originator == "CIV":
            org_text = "A civil authority"
        elif eas.originator == "PEP":
            org_text = "THE PRIMARY ENTRY POINT EAS SYSTEM"

        das_fips, _ = _process_das_fips_string(fips_context.str_fips, combine_same_state=False)
        das_fips = re.sub(r"All of the United States", "United States", das_fips, flags=re.IGNORECASE)

        das_start = f"{_format_time12(start_time, output_tz, pad_hour=False).upper()} ON {_format_mon_day_year(start_time, output_tz, short_month=True, upper_month=True)}"
        if _is_same_local_day(start_time, end_time, output_tz):
            das_end = _format_time12(end_time, output_tz, pad_hour=False).upper()
        else:
            das_end = f"{_format_time12(end_time, output_tz, pad_hour=False).upper()} {_format_mon_day_year(end_time, output_tz, short_month=True, upper_month=True)}"

        return _apply_mode_template(
            "DAS1",
            {
                "ORG": org_text.upper(),
                "EVENTCODE": normal_event_code.upper(),
                "FIPS": das_fips,
                "START": das_start,
                "END": das_end,
                "SENDER": sender.upper(),
            },
        ).upper()

    if mode == "DAS2PLUS":
        org_text = normal_originator
        if eas.originator == "EAS":
            org_text = "A broadcast or cable system"
        elif eas.originator == "CIV":
            org_text = "A civil authority"
        elif eas.originator == "PEP":
            org_text = "THE PRIMARY ENTRY POINT EAS SYSTEM"

        das_fips, _ = _process_das_fips_string(fips_context.str_fips, combine_same_state=True)
        das_fips = re.sub(r"All of the United States", "United States", das_fips, flags=re.IGNORECASE)
        das_start = f"{_format_time12(start_time, output_tz, pad_hour=False).upper()} on {_format_mon_day_year(start_time, output_tz, short_month=True, upper_month=True)}"
        if _is_same_local_day(start_time, end_time, output_tz):
            das_end = _format_time12(end_time, output_tz, pad_hour=False).upper()
        else:
            das_end = f"{_format_time12(end_time, output_tz, pad_hour=False).upper()} {_format_mon_day_year(end_time, output_tz, short_month=True, upper_month=True)}"

        return _apply_mode_template(
            "DAS2PLUS",
            {
                "ORG": org_text,
                "EVENTCODE": normal_event_code.upper(),
                "FIPS": das_fips,
                "START": re.sub(r"([A-Z]{3}) 0(\d)", r"\1 \2", das_start, count=1),
                "END": re.sub(r"([A-Z]{3}) 0(\d)", r"\1 \2", das_end, count=1),
                "SENDER": sender,
            },
        )

    if mode == "HOLLYANNE":
        org_text = normal_originator
        if eas.originator == "EAS":
            org_text = "THE CABLE/BROADCAST SYSTEM"
        elif eas.originator == "CIV":
            org_text = "THE AUTHORITIES"

        states = {
            _split_location_state(entry)[1]
            for entry in fips_context.fips_text_with_and
            if _split_location_state(entry)[1]
        }
        holly_locations = []
        for entry in fips_context.fips_text_with_and:
            location, state = _split_location_state(entry)
            clean = _filter_holly_or_gorman_location(location, False).upper()
            if state and len(states) != 1:
                holly_locations.append(f"{clean} {state.upper()}")
            else:
                holly_locations.append(clean.strip())
        holly_text = ", ".join(holly_locations).replace(", AND ", " AND ").strip()

        return _apply_mode_template(
            "HOLLYANNE",
            {
                "ORG": org_text,
                "EVENTCODE": normal_event_code.upper(),
                "FIPS": "For all of the United States"
                if re.search(r"All of the United States", holly_text, flags=re.IGNORECASE)
                else f"FOR THE FOLLOWING COUNTIES: {holly_text}",
                "START": base_range_time["start"].upper(),
                "END": base_range_time["end"].upper(),
                "SENDER": sender,
            },
        ).upper()

    if mode == "GORMAN":
        gorman_start = (
            f"{_format_time12(start_time, output_tz, pad_hour=False).upper()} ON "
            f"{_format_mon_day_year(start_time, output_tz, upper_month=True, short_month=True, include_year=True)}"
        )
        gorman_start = re.sub(r"([A-Z]{3}) 0(\d)", r"\1 \2", gorman_start, count=1)

        if _is_same_local_day(start_time, end_time, output_tz):
            gorman_end = _format_time12(end_time, output_tz, pad_hour=False).upper()
        else:
            gorman_end = (
                f"{_format_time12(end_time, output_tz, pad_hour=False).upper()} ON "
                f"{_format_mon_day_year(end_time, output_tz, upper_month=True, short_month=True, include_year=True)}"
            )
            gorman_end = re.sub(r"([A-Z]{3}) 0(\d)", r"\1 \2", gorman_end, count=1)

        gorman_locations = []
        for entry in fips_context.fips_text_with_and:
            location, state = _split_location_state(entry)
            clean = _filter_holly_or_gorman_location(location, True).upper()
            gorman_locations.append(f"{clean} {state.upper()}".strip() if state else clean)
        gorman_text = ", ".join(gorman_locations).replace(", AND ", " AND ").strip()

        return _apply_mode_template(
            "GORMAN",
            {
                "EVENTCODE": normal_event_code.upper(),
                "FIPS": "UNITED STATES"
                if re.search(r"All of the United States", gorman_text, flags=re.IGNORECASE)
                else gorman_text,
                "START": gorman_start,
                "END": gorman_end,
                "SENDER": sender,
            },
        ).upper()

    if mode == "JSON":
        return json.dumps(
            {
                "event_code": normal_event_code,
                "originator": normal_originator,
                "fips_codes": fips_context.codes,
                "start_time": int(start_time.timestamp()),
                "end_time": int(end_time.timestamp()),
                "sender": sender,
            },
            separators=(",", ":"),
        )

    locs = fips_context.str_fips[:-1]
    locsarr = re.findall(r"(.*?), ([A-Z]{2})", locs)
    if locsarr:
        names: list[str] = []
        abbr_map = PROVINCE_ABBREVIATIONS if canadian_mode else STATE_ABBREVIATIONS
        for location, state in locsarr:
            names.append(f"{location.split(',')[0].strip()}, {abbr_map.get(state.strip(), state.strip())}")
        locs = "".join(names)

    return (
        f"{normal_originator} has issued {normal_event_code} for {locs}; beginning at {start_time_str} "
        f"and ending at {end_time_str}. Message from {sender}."
    )


def E2T(
    header: str,
    endec_emulation_mode: str | None = None,
    canadian_mode: bool = False,
    timezone_override: str | None = None,
) -> str:
    parsed = _parse_header(header)
    return _humanize_eas(parsed, endec_emulation_mode, canadian_mode, timezone_override)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an EAS SAME header into human-readable text.")
    parser.add_argument("header", type=str, help="The EAS SAME header string to convert.")
    parser.add_argument("--mode", type=str, default=None, help="Optional emulation mode for specific output formatting.")
    parser.add_argument("--canadian", action="store_true", help="Enable Canadian mode for location name lookups and formatting.")
    parser.add_argument("--timezone", type=str, default=None, help="Optional timezone override for output times.")

    args = parser.parse_args()

    print(E2T(args.header, args.mode, canadian_mode=args.canadian, timezone_override=args.timezone))
