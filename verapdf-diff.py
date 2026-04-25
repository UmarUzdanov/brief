#!/usr/bin/env python3
"""
Compare veraPDF validation results between two folders of PDFs.

Usage:
  verapdf-diff.py <before_dir> <after_dir> [--profile PATH] [--output FILE]

Produces a single HTML report showing which files improved, regressed, or
stayed the same between the two runs. Matches files by basename.
"""

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path

PROFILES_DIR = "/Users/umar/projects/veraPDF-validation-profiles"
PROFILE_ALIASES = {
    "wcag":          "PDF_UA/WCAG-2-2-Complete.xml",
    "wcag-basic":    "PDF_UA/WCAG-2-2.xml",
    "wcag-pdf20":    "PDF_UA/WCAG-2-2-Complete-PDF20.xml",
    "wcag-machine":  "PDF_UA/WCAG-2-2-Machine.xml",
    "ua1":           "PDF_UA/PDFUA-1.xml",
    "ua2":           "PDF_UA/PDFUA-2.xml",
    "ua2-iso32005":  "PDF_UA/PDFUA-2-ISO32005.xml",
    "wtpdf-a":       "PDF_UA/WTPDF-1-0-Accessibility.xml",
    "wtpdf-r":       "PDF_UA/WTPDF-1-0-Reuse.xml",
}
DEFAULT_PROFILE = "wcag"


def resolve_profile(value: str) -> str:
    if value in PROFILE_ALIASES:
        return os.path.join(PROFILES_DIR, PROFILE_ALIASES[value])
    return value


def run_verapdf(profile: str, folder: str) -> dict:
    print(f"Running veraPDF on {folder} ...", file=sys.stderr)
    result = subprocess.run(
        ["verapdf", "-p", profile, "-r", "--format", "json", folder],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print(result.stderr, file=sys.stderr)
        sys.exit(f"veraPDF produced no output for {folder}")
    return json.loads(result.stdout)


def index_by_basename(report: dict) -> dict:
    out = {}
    for job in report.get("report", {}).get("jobs", []):
        name = job.get("itemDetails", {}).get("name", "")
        if not name:
            continue
        base = os.path.basename(name).lower()
        vr = job.get("validationResult", [])
        if not vr:
            out[base] = {"parsed": False, "path": name}
            continue
        d = vr[0].get("details", {})
        failed_rules = {
            f"{r.get('clause')}-t{r.get('testNumber')}": {
                "description": r.get("description", ""),
                "failed_checks": r.get("failedChecks", 0),
                "clause": r.get("clause", ""),
                "test": r.get("testNumber", ""),
            }
            for r in d.get("ruleSummaries", [])
            if r.get("ruleStatus") == "FAILED"
        }
        out[base] = {
            "parsed": True,
            "path": name,
            "compliant": vr[0].get("profile") is not None and d.get("failedRules", 0) == 0,
            "passed_rules": d.get("passedRules", 0),
            "failed_rules": d.get("failedRules", 0),
            "passed_checks": d.get("passedChecks", 0),
            "failed_checks": d.get("failedChecks", 0),
            "failed_rule_ids": failed_rules,
        }
    return out


def classify(before: dict, after: dict) -> str:
    if not before or not before.get("parsed"):
        return "new"
    if not after or not after.get("parsed"):
        return "missing"
    b_fail = before["failed_rules"] > 0
    a_fail = after["failed_rules"] > 0
    if b_fail and not a_fail:
        return "fixed"
    if not b_fail and a_fail:
        return "regressed"
    if b_fail and a_fail:
        if after["failed_checks"] < before["failed_checks"]:
            return "improved"
        if after["failed_checks"] > before["failed_checks"]:
            return "worsened"
        return "still_failing"
    return "still_passing"


CATEGORY_LABELS = {
    "fixed": ("Fixed (fail &rarr; pass)", "green"),
    "improved": ("Improved (still failing, fewer issues)", "teal"),
    "still_passing": ("Unchanged (still passing)", "gray"),
    "still_failing": ("Unchanged (still failing)", "orange"),
    "worsened": ("Worsened (more issues)", "red"),
    "regressed": ("Regressed (pass &rarr; fail)", "red"),
    "new": ("New in 'after' folder", "blue"),
    "missing": ("Missing from 'after' folder", "gray"),
}

# Plain-language headline for each category — what to call it for a reader
# who does not know veraPDF jargon. The technical label from CATEGORY_LABELS
# is preserved as a subtitle so the original information is not lost.
CATEGORY_PLAIN = {
    "fixed":         ("Now passes",           "Was failing the standard before; passes all rules now."),
    "improved":      ("Improved but still failing", "Still doesn't pass, but has fewer violations than before."),
    "still_passing": ("Unchanged — passing",  "Passed before and still passes."),
    "still_failing": ("Unchanged — still failing", "Failed before, still fails the same number of issues."),
    "worsened":      ("Worsened",             "Was failing; now fails with even more violations."),
    "regressed":     ("Newly failing",        "Was passing the standard before. Now fails."),
    "new":           ("New file",             "Only present in the 'after' folder; nothing to compare to."),
    "missing":       ("Removed",              "Was in the 'before' folder; not in 'after'."),
}

# Section display order: bad news first, then good news, then ambiguous.
SECTION_ORDER = (
    "regressed", "worsened", "still_failing",
    "improved", "fixed", "still_passing",
    "new", "missing",
)

# Plain-English version of common veraPDF rule identifiers. Keys are the
# `{clause}-t{testNumber}` strings that index_by_basename builds. The short
# label is what appears as the headline of each rule; the explanation is one
# plain sentence describing what the rule actually catches in everyday terms
# (no spec quoting). For rules not in this table the original spec description
# is shown verbatim — better to show the unfamiliar than to invent meaning.
RULE_PLAIN = {
    "5-t1":         ("Missing PDF/UA marker",          "The PDF didn't declare itself as following the PDF/UA accessibility standard."),
    "7.1-t1":       ("Decoration mixed with content",  "Decorative artwork was incorrectly tagged as real content."),
    "7.1-t2":       ("Content mixed with decoration",  "Real content was incorrectly tagged as decoration."),
    "7.1-t3":       ("Untagged content",               "Visible text or graphics weren't labelled — invisible to screen readers."),
    "7.1-t5":       ("Non-standard tag without mapping","Custom structure tags were used without being mapped to a standard equivalent."),
    "7.1-t9":       ("Missing document title",         "The PDF had no human-readable title in its metadata."),
    "7.10-t1":      ("Layer config missing name",      "An optional-content (layer) configuration was missing its name."),
    "7.2-t20":      ("Malformed list item",            "A list item contained tags that aren't allowed inside a list item."),
    "7.5-t1":       ("Table headers without scope",    "Table-header cells didn't say whether they apply to a row or a column."),
    "7.9-t1":       ("Note tag missing ID",            "A footnote or note element was missing an identifier."),
    "7.18.1-t2":    ("Annotation without alt text",    "Clickable areas (links, form fields, etc.) had no description for screen-reader users."),
    "7.18.5-t1":    ("Untagged hyperlinks",            "Hyperlinks weren't marked up as links in the accessibility tree."),
    "7.18.5-t2":    ("Hyperlinks without description", "Hyperlinks had no accessible text describing where they go."),
    "7.21.3.1-t1":  ("Font subset names mismatched",   "Embedded font subsets used inconsistent identifying names."),
    "7.21.4.1-t1":  ("Font not embedded",              "A font used by the PDF wasn't embedded — it may render incorrectly on other systems."),
    "7.21.4.2-t1":  ("Font CharSet incomplete (Type 1)","An embedded Type-1 font's CharSet didn't list all glyphs in the font."),
    "7.21.4.2-t2":  ("Font CIDSet incomplete",         "An embedded CID font's CIDSet didn't list all character IDs in the font."),
    "7.21.5-t1":    ("Font glyph widths inconsistent", "A font's declared character widths didn't match what was in the embedded font file."),
    "7.21.6-t1":    ("Font encoding mismatched",       "A font's character-to-glyph mapping was inconsistent."),
    "7.6-t1":       ("Form field without name",        "A form field had no accessible name."),
    "7.6-t2":       ("Form field without TU",          "A form field had no user-facing label."),
}


def _rule_plain(rid: str, fallback_description: str):
    """Return (short_label, plain_explanation) for a rule id, or a single-
    sentence truncation of the spec description if we have no translation."""
    if rid in RULE_PLAIN:
        return RULE_PLAIN[rid]
    desc = (fallback_description or "").strip()
    short = desc.split(". ")[0]
    if len(short) > 80:
        short = short[:77] + "…"
    return (short or rid, desc)


# Plain-language version of each known veraPDF profile, looked up by the
# stem of the profile XML path so render_html() does not need a new param.
# The script already knows these alias names via PROFILE_ALIASES above.
PROFILE_PLAIN = {
    "WCAG-2-2-Complete":        ("WCAG 2.2 (full)",         "Web Content Accessibility Guidelines 2.2 combined with PDF/UA-1."),
    "WCAG-2-2":                 ("WCAG 2.2 (basic)",        "Web Content Accessibility Guidelines 2.2, baseline subset."),
    "WCAG-2-2-Complete-PDF20":  ("WCAG 2.2 + PDF 2.0",      "WCAG 2.2 combined with PDF 2.0 conformance."),
    "WCAG-2-2-Machine":         ("WCAG 2.2 (machine)",      "Machine-checkable subset of WCAG 2.2."),
    "PDFUA-1":                  ("PDF/UA-1 (ISO 14289-1)",  "The international standard for accessible PDFs. A passing PDF can be used by people who rely on screen readers."),
    "PDFUA-2":                  ("PDF/UA-2 (ISO 14289-2)",  "Updated international standard for accessible PDFs."),
    "PDFUA-2-ISO32005":         ("PDF/UA-2 + ISO 32005",    "PDF/UA-2 combined with ISO 32005 structured tagging."),
    "WTPDF-1-0-Accessibility":  ("WTPDF 1.0 (Accessibility)","Well-Tagged PDF, Accessibility profile."),
    "WTPDF-1-0-Reuse":          ("WTPDF 1.0 (Reuse)",       "Well-Tagged PDF, Reuse profile."),
}


def fmt_stat(before, after, key):
    b = before[key] if before and before.get("parsed") else "&mdash;"
    a = after[key] if after and after.get("parsed") else "&mdash;"
    return f"{b} &rarr; {a}"


def render_rule_diff(before, after):
    if not (before and before.get("parsed") and after and after.get("parsed")):
        return ""
    b_rules = before["failed_rule_ids"]
    a_rules = after["failed_rule_ids"]
    fixed = sorted(set(b_rules) - set(a_rules))
    new = sorted(set(a_rules) - set(b_rules))
    persist = sorted(set(a_rules) & set(b_rules))
    if not (fixed or new or persist):
        return ""

    def _entry(klass: str, sigil: str, status: str, rid: str, desc: str, count_html: str):
        short, plain = _rule_plain(rid, desc)
        return (
            f'<li class="{klass}">'
            f'<span class="rd-sigil" aria-hidden="true">{sigil}</span>'
            f'<div class="rd-body">'
            f'<div class="rd-headline">'
            f'<span class="rd-status">{status}</span>'
            f'<span class="rd-label">{html.escape(short)}</span>'
            f'<span class="rd-count">{count_html}</span>'
            f'</div>'
            f'<div class="rd-explain">{html.escape(plain)}</div>'
            f'<div class="rd-spec"><code>{html.escape(rid)}</code> '
            f'<span class="rd-spec-text">{html.escape(desc)}</span></div>'
            f'</div></li>'
        )

    parts = ['<details><summary>Rule-by-rule detail</summary><ul class="rd-list">']
    for rid in fixed:
        r = b_rules[rid]
        c = r["failed_checks"]
        parts.append(_entry("rd-fixed", "&#10003;", "Fixed", rid, r["description"],
                            f'{_fmt_int(c)} violation{"s" if c != 1 else ""} cleared'))
    for rid in new:
        r = a_rules[rid]
        c = r["failed_checks"]
        parts.append(_entry("rd-new", "&#x2717;", "Newly failing", rid, r["description"],
                            f'{_fmt_int(c)} violation{"s" if c != 1 else ""}'))
    for rid in persist:
        rb, ra = b_rules[rid], a_rules[rid]
        delta = ra["failed_checks"] - rb["failed_checks"]
        if delta == 0:
            cnt = f'{_fmt_int(rb["failed_checks"])} violation{"s" if rb["failed_checks"]!=1 else ""} (unchanged)'
        elif delta < 0:
            cnt = (f'{_fmt_int(rb["failed_checks"])} &rarr; {_fmt_int(ra["failed_checks"])} '
                   f'({_fmt_int(-delta)} fewer)')
        else:
            cnt = (f'{_fmt_int(rb["failed_checks"])} &rarr; {_fmt_int(ra["failed_checks"])} '
                   f'({_fmt_int(delta)} more)')
        parts.append(_entry("rd-persist", "&#9679;", "Still failing", rid, ra["description"], cnt))
    parts.append("</ul></details>")
    return "".join(parts)


def _profile_plain(profile_path: str):
    """Look up a human-readable name + 1-line description for the given
    veraPDF profile XML path. Falls back to the file stem if unknown."""
    stem = Path(profile_path).stem
    if stem in PROFILE_PLAIN:
        return PROFILE_PLAIN[stem]
    return (stem, "")


def _fmt_int(n) -> str:
    """Thousands-separated integer for big counts in the headline."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def render_html(before_dir, after_dir, profile, before_idx, after_idx) -> str:
    from collections import Counter

    all_names = sorted(set(before_idx) | set(after_idx))
    buckets = {k: [] for k in CATEGORY_LABELS}
    for name in all_names:
        b = before_idx.get(name)
        a = after_idx.get(name)
        cat = classify(b, a)
        buckets[cat].append((name, b, a))

    totals = {k: len(v) for k, v in buckets.items()}
    total = sum(totals.values())

    # ----------------------------------------------------------------------
    # Aggregate stats for the headline. All derived from data already in
    # before_idx / after_idx — no new helpers, no signature changes.
    # ----------------------------------------------------------------------
    pass_after = sum(1 for items in buckets.values() for _n, _b, a in items
                     if a and a.get("parsed") and a.get("failed_rules", 0) == 0)
    pass_before = sum(1 for items in buckets.values() for _n, b, _a in items
                      if b and b.get("parsed") and b.get("failed_rules", 0) == 0)
    fail_after = sum(1 for items in buckets.values() for _n, _b, a in items
                     if a and a.get("parsed") and a.get("failed_rules", 0) > 0)
    fail_before = sum(1 for items in buckets.values() for _n, b, _a in items
                      if b and b.get("parsed") and b.get("failed_rules", 0) > 0)
    violations_before = sum(b.get("failed_checks", 0)
                            for items in buckets.values()
                            for _n, b, _a in items
                            if b and b.get("parsed"))
    violations_after = sum(a.get("failed_checks", 0)
                           for items in buckets.values()
                           for _n, _b, a in items
                           if a and a.get("parsed"))

    profile_label, profile_blurb = _profile_plain(profile)
    needs_attention = totals["regressed"] + totals["worsened"] + totals["still_failing"]

    # ----------------------------------------------------------------------
    # Per-category top-rule aggregation: which underlying rules drive this
    # bucket, in plain-language terms (using the rule's own description from
    # the spec — no invented translations).
    # ----------------------------------------------------------------------
    def aggregate_rules(cat):
        files_per_rule: Counter = Counter()
        checks_per_rule: Counter = Counter()
        descriptions: dict = {}
        for _name, b, a in buckets[cat]:
            b_rules = b["failed_rule_ids"] if b and b.get("parsed") else {}
            a_rules = a["failed_rule_ids"] if a and a.get("parsed") else {}
            if cat in ("fixed", "improved"):
                # rules removed between before and after
                src = {r: info for r, info in b_rules.items() if r not in a_rules}
            elif cat == "regressed":
                src = a_rules
            elif cat == "worsened":
                src = {r: info for r, info in a_rules.items()
                       if r not in b_rules
                       or info["failed_checks"] > b_rules[r]["failed_checks"]}
            elif cat == "still_failing":
                src = a_rules
            elif cat == "new":
                src = a_rules
            elif cat == "missing":
                src = b_rules
            else:  # still_passing
                src = {}
            for rid, info in src.items():
                files_per_rule[rid] += 1
                checks_per_rule[rid] += info["failed_checks"]
                descriptions[rid] = info["description"]
        ranked = sorted(files_per_rule.items(),
                        key=lambda kv: (-kv[1], -checks_per_rule[kv[0]]))
        return [(rid, files_per_rule[rid], checks_per_rule[rid], descriptions[rid])
                for rid, _ in ranked]

    # ----------------------------------------------------------------------
    # Headline answer in plain English.
    # ----------------------------------------------------------------------
    if total == 0:
        headline_main = "No files to compare."
        headline_sub = "Both folders were empty (or had no PDFs)."
    elif fail_after == 0 and pass_after > 0 and totals["regressed"] == 0 and totals["worsened"] == 0:
        if pass_before == 0:
            headline_main = f"All {pass_after} PDF{'s' if pass_after != 1 else ''} now meet {profile_label}."
            headline_sub = "None passed before."
        else:
            headline_main = f"All {pass_after} PDF{'s' if pass_after != 1 else ''} meet {profile_label}."
            headline_sub = f"{pass_before} already did; {pass_after - pass_before} were repaired."
    elif totals["regressed"] > 0 or totals["worsened"] > 0:
        bad_bits = []
        if totals["regressed"]:
            bad_bits.append(f"{totals['regressed']} newly fail{'s' if totals['regressed']==1 else ''}")
        if totals["worsened"]:
            bad_bits.append(f"{totals['worsened']} got worse")
        headline_main = f"{pass_after} of {total} PDFs pass {profile_label}. {', '.join(bad_bits).capitalize()}."
        headline_sub = "See “Needs attention” below."
    else:
        headline_main = f"{pass_after} of {total} PDFs meet {profile_label}."
        if fail_after > 0:
            headline_main += f" {fail_after} still fail."
        headline_sub = ""

    # Two scoreboard tiles: PDFs passing (before → after) and total violations
    # (before → after). These are the proof, not the headline — they get the
    # biggest type on the page. Both the from and to numbers carry color so
    # the eye sees red→green (improvement) or green→red (regression) at a glance.
    def _from_to_classes(before_v: int, after_v: int, lower_is_better: bool):
        if before_v == after_v:
            return ("neutral", "neutral")
        better_after = (after_v < before_v) if lower_is_better else (after_v > before_v)
        return ("bad", "good") if better_after else ("good", "bad")

    def _delta_caption(before_v: int, after_v: int, lower_is_better: bool) -> str:
        if before_v == after_v:
            return "unchanged"
        d = after_v - before_v
        if lower_is_better:
            return f"{_fmt_int(-d)} fewer" if d < 0 else f"{_fmt_int(d)} more"
        return f"{_fmt_int(d)} more passing" if d > 0 else f"{_fmt_int(-d)} no longer passing"

    scoreboard_tiles = []
    fc, tc = _from_to_classes(pass_before, pass_after, lower_is_better=False)
    scoreboard_tiles.append({
        "label": "PDFs passing",
        "before": pass_before, "after": pass_after, "denom": total,
        "from_class": fc, "to_class": tc,
        "caption": _delta_caption(pass_before, pass_after, lower_is_better=False),
    })
    if violations_before or violations_after:
        fc, tc = _from_to_classes(violations_before, violations_after, lower_is_better=True)
        scoreboard_tiles.append({
            "label": "Rule violations",
            "before": violations_before, "after": violations_after, "denom": None,
            "from_class": fc, "to_class": tc,
            "caption": _delta_caption(violations_before, violations_after, lower_is_better=True),
        })

    # ----------------------------------------------------------------------
    # Sticky nav strip — minimal: one chip per populated section, plus a
    # "Before remediation" chip if there were any failing files in the
    # original folder (jumps to the #sec-before listing).
    # ----------------------------------------------------------------------
    before_failing_count = sum(
        1 for name in all_names
        if name in before_idx
        and before_idx[name].get("parsed")
        and before_idx[name].get("failed_rules", 0) > 0
    )
    before_chip = ""
    if before_failing_count > 0:
        before_chip = (
            f'<a class="navchip red" href="#sec-before">'
            f'<span class="nc-n">{before_failing_count}</span>'
            f'<span class="nc-l">Before remediation</span></a>'
        )
    nav_chips = before_chip + "".join(
        f'<a class="navchip {CATEGORY_LABELS[cat][1]}" href="#sec-{cat}">'
        f'<span class="nc-n">{totals[cat]}</span>'
        f'<span class="nc-l">{CATEGORY_PLAIN[cat][0]}</span></a>'
        for cat in SECTION_ORDER
        if totals[cat] > 0
    )
    nav_block = (f'<nav class="toc" aria-label="Sections">{nav_chips}</nav>'
                 if nav_chips else "")

    # ----------------------------------------------------------------------
    # Headline "what was wrong" panel: top rules across files that are now
    # passing (or, if nothing was fixed, top rules across files that need
    # attention — whichever is the more useful headline for THIS report).
    # ----------------------------------------------------------------------
    # Status word + meta-strong template per category, mirroring the per-file
    # row's "NOW PASSES / 2,515 violations cleared" pattern.
    rule_status_meta = {
        "fixed":         ("Fixed",         "violations cleared"),
        "improved":      ("Reduced",       "fewer violations"),
        "still_passing": ("Passes",        "violations"),
        "still_failing": ("Still failing", "violations"),
        "worsened":      ("Worse",         "more violations"),
        "regressed":     ("Newly failing", "new violations"),
        "new":           ("Failing",       "violations"),
        "missing":       ("Was failing",   "violations (file removed)"),
    }

    def render_top_rules(cat, limit=8, intro="", heading=""):
        rows = aggregate_rules(cat)[:limit]
        if not rows:
            return ""
        status_label, meta_unit = rule_status_meta.get(cat, ("", "violations"))
        color = CATEGORY_LABELS[cat][1]

        items = []
        for rid, files, checks, desc in rows:
            short, plain = _rule_plain(rid, desc)
            # Per-rule before/after totals across the files in this bucket.
            bf = af = bv = av = 0
            file_breakdown = []
            for nm, b_, a_ in buckets[cat]:
                br = b_["failed_rule_ids"] if b_ and b_.get("parsed") else {}
                ar = a_["failed_rule_ids"] if a_ and a_.get("parsed") else {}
                in_b = rid in br
                in_a = rid in ar
                if in_b:
                    bf += 1; bv += br[rid]["failed_checks"]
                if in_a:
                    af += 1; av += ar[rid]["failed_checks"]
                if in_b or in_a:
                    file_breakdown.append((nm,
                                           br[rid]["failed_checks"] if in_b else None,
                                           ar[rid]["failed_checks"] if in_a else None))

            # Summary sentence in the same shape as a per-file summary.
            if cat == "fixed":
                summary = f"Was failing in {bf} file{'s' if bf!=1 else ''} ({_fmt_int(bv)} violation{'s' if bv!=1 else ''}). All fixed."
                meta_strong = f"{_fmt_int(bv)} {meta_unit}"
            elif cat == "improved":
                summary = f"Was failing in {bf} file{'s' if bf!=1 else ''} ({_fmt_int(bv)} violation{'s' if bv!=1 else ''}). Now in {af} ({_fmt_int(av)})."
                meta_strong = f"{_fmt_int(bv-av)} {meta_unit}"
            elif cat == "regressed":
                summary = f"Was passing everywhere; now fails in {af} file{'s' if af!=1 else ''} ({_fmt_int(av)} violation{'s' if av!=1 else ''})."
                meta_strong = f"{_fmt_int(av)} {meta_unit}"
            elif cat == "worsened":
                summary = f"Was failing in {bf} file{'s' if bf!=1 else ''} ({_fmt_int(bv)} violation{'s' if bv!=1 else ''}); now {af} ({_fmt_int(av)})."
                meta_strong = f"{_fmt_int(av-bv)} {meta_unit}"
            elif cat == "still_failing":
                summary = f"Still fails in {af} file{'s' if af!=1 else ''} ({_fmt_int(av)} violation{'s' if av!=1 else ''})."
                meta_strong = f"{_fmt_int(av)} {meta_unit}"
            elif cat == "new":
                summary = f"Fails in {af} new file{'s' if af!=1 else ''} ({_fmt_int(av)} violation{'s' if av!=1 else ''})."
                meta_strong = f"{_fmt_int(av)} {meta_unit}"
            elif cat == "missing":
                summary = f"Was failing in {bf} removed file{'s' if bf!=1 else ''} ({_fmt_int(bv)} violation{'s' if bv!=1 else ''})."
                meta_strong = f"{_fmt_int(bv)} {meta_unit}"
            else:
                summary = ""
                meta_strong = ""

            stats_lines = (
                f'<span><span class="ri-stat-l">Files affected</span> {bf} &rarr; {af}</span>'
                f'<span><span class="ri-stat-l">Violations</span> {_fmt_int(bv)} &rarr; {_fmt_int(av)}</span>'
            )

            # Expandable per-file breakdown for this rule.
            breakdown_items = []
            for nm, b_count, a_count in file_breakdown:
                if b_count is not None and a_count is not None:
                    delta = f"{b_count} &rarr; {a_count}"
                    if a_count == 0:
                        klass = "rd-fixed"; sigil = "&#10003;"
                    elif a_count > b_count:
                        klass = "rd-new"; sigil = "&uarr;"
                    elif a_count < b_count:
                        klass = "rd-fixed"; sigil = "&darr;"
                    else:
                        klass = "rd-persist"; sigil = "&#9679;"
                elif b_count is not None:
                    delta = f"{b_count} &rarr; &mdash;"
                    klass = "rd-persist"; sigil = "&#9679;"
                else:
                    delta = f"&mdash; &rarr; {a_count}"
                    klass = "rd-new"; sigil = "&uarr;"
                breakdown_items.append(
                    f'<li class="{klass}">'
                    f'<span class="rd-sigil" aria-hidden="true">{sigil}</span>'
                    f'<div class="rd-body">'
                    f'<div class="rd-headline">'
                    f'<span class="rd-label rd-label-mono">{html.escape(nm)}</span>'
                    f'<span class="rd-count">{delta} violation{"s" if (b_count or 0)+(a_count or 0)!=1 else ""}</span>'
                    f'</div></div></li>'
                )
            breakdown_html = (
                f'<details><summary>Per-file breakdown ({len(file_breakdown)} file{"s" if len(file_breakdown)!=1 else ""})</summary>'
                f'<ul class="rd-list">{"".join(breakdown_items)}</ul>'
                f'</details>'
            ) if file_breakdown else ""

            items.append(
                f'<li class="rowitem">'
                f'  <div class="ri-count">'
                f'    <span class="ri-num">{files}</span>'
                f'    <span class="ri-num-sub">file{"s" if files!=1 else ""}</span>'
                f'  </div>'
                f'  <div class="ri-body">'
                f'    <div class="ri-label">{html.escape(short)}</div>'
                f'    <div class="ri-explain">{summary} <span class="ri-explain-aside">{html.escape(plain)}</span></div>'
                f'    <div class="ri-stats">{stats_lines}</div>'
                f'    <div class="ri-spec" title="Exact text from the standard">'
                f'      <code>{html.escape(rid)}</code> '
                f'      <span class="ri-spec-text">{html.escape(desc)}</span>'
                f'    </div>'
                f'    {breakdown_html}'
                f'  </div>'
                f'  <div class="ri-meta">'
                f'    <span class="badge {color}">{status_label}</span>'
                f'    <span class="ri-meta-strong">{meta_strong}</span>'
                f'  </div>'
                f'</li>'
            )
        intro_html = f'<p class="rule-intro">{intro}</p>' if intro else ""
        h = heading or f'What was {CATEGORY_PLAIN[cat][0].lower()}'
        return (f'<section class="rule-summary">'
                f'<h3>{h}</h3>'
                f'{intro_html}'
                f'<ol class="rowlist">{"".join(items)}</ol>'
                f'</section>')

    # No top-level rule aggregate — files are the only listing. The per-file
    # rows below carry the same information one file at a time.
    headline_rules_html = ""

    # ----------------------------------------------------------------------
    # "What was failing before" — per-file rows showing the ORIGINAL state.
    # Same layout as the per-file rows below; before-data only, no diff.
    # ----------------------------------------------------------------------
    def render_before_rule_list(failed_rule_ids: dict) -> str:
        if not failed_rule_ids:
            return ""
        items = []
        for rid in sorted(failed_rule_ids):
            info = failed_rule_ids[rid]
            short, plain = _rule_plain(rid, info["description"])
            c = info["failed_checks"]
            items.append(
                f'<li class="rd-new">'
                f'<span class="rd-sigil" aria-hidden="true">&#x2717;</span>'
                f'<div class="rd-body">'
                f'<div class="rd-headline">'
                f'<span class="rd-status">Failing</span>'
                f'<span class="rd-label">{html.escape(short)}</span>'
                f'<span class="rd-count">{_fmt_int(c)} violation{"s" if c != 1 else ""}</span>'
                f'</div>'
                f'<div class="rd-explain">{html.escape(plain)}</div>'
                f'<div class="rd-spec"><code>{html.escape(rid)}</code> '
                f'<span class="rd-spec-text">{html.escape(info["description"])}</span></div>'
                f'</div></li>'
            )
        return ('<details><summary>Rule-by-rule detail</summary>'
                f'<ul class="rd-list">{"".join(items)}</ul></details>')

    def render_before_row(name: str, b: dict) -> str:
        br = b["failed_rules"]; bc = b["failed_checks"]; pc = b["passed_checks"]
        summary = f"Was failing {br} rule{'s' if br != 1 else ''} ({_fmt_int(bc)} violation{'s' if bc != 1 else ''})."
        stats = (
            f'<span><span class="ri-stat-l">Rules</span> {br}</span>'
            f'<span><span class="ri-stat-l">Violations</span> {_fmt_int(bc)}</span>'
            f'<span><span class="ri-stat-l">Successful checks</span> {_fmt_int(pc)}</span>'
        )
        diff = render_before_rule_list(b.get("failed_rule_ids", {}))
        return (
            f'<article class="rowitem fileitem">'
            f'  <div class="ri-count">'
            f'    <span class="ri-num">{br}</span>'
            f'    <span class="ri-num-sub">rules failing</span>'
            f'  </div>'
            f'  <div class="ri-body">'
            f'    <div class="ri-label ri-label-mono">{html.escape(name)}</div>'
            f'    <div class="ri-explain">{summary}</div>'
            f'    <div class="ri-stats">{stats}</div>'
            f'    {diff}'
            f'  </div>'
            f'  <div class="ri-meta">'
            f'    <span class="badge red">Failing</span>'
            f'    <span class="ri-meta-strong">{_fmt_int(bc)} violation{"s" if bc != 1 else ""}</span>'
            f'  </div>'
            f'</article>'
        )

    before_failing = [(name, before_idx[name]) for name in all_names
                       if name in before_idx
                       and before_idx[name].get("parsed")
                       and before_idx[name].get("failed_rules", 0) > 0]
    before_section_html = ""
    if before_failing:
        before_rows_html = "".join(render_before_row(n, b) for n, b in before_failing)
        before_section_html = (
            f'<section class="bucket red" id="sec-before">'
            f'<header class="bucket-head">'
            f'<h2><span class="dot"></span>'
            f'<span class="bucket-title">What was failing before</span>'
            f'<span class="bucket-count">{len(before_failing)} file{"s" if len(before_failing) != 1 else ""}</span>'
            f'</h2>'
            f'<p class="bucket-blurb">Original state of the &lsquo;before&rsquo; folder &mdash; '
            f'{len(before_failing)} file{"s" if len(before_failing) != 1 else ""} were failing the standard. '
            f'What changed after remediation is in the sections that follow.</p>'
            f'</header>'
            f'<div class="files">{before_rows_html}</div>'
            f'</section>'
        )

    # ----------------------------------------------------------------------
    # Per-section render: human heading, plain explanation, then the file
    # table with rule-level diff visible-by-default behind a `<details>`.
    # ----------------------------------------------------------------------
    def render_status_badge(cat):
        return (f'<span class="badge {CATEGORY_LABELS[cat][1]}">'
                f'{CATEGORY_PLAIN[cat][0]}</span>')

    def render_file_row(cat, name, b, a):
        # Pick the headline number for the count column — the figure that
        # most directly answers "what changed for this file in this category".
        # All numbers stay visible elsewhere; this is just the lead.
        if cat == "fixed" and b and b.get("parsed"):
            count_num, count_sub = b["failed_rules"], "rules fixed"
            summary = (f"Was failing {b['failed_rules']} rule{'s' if b['failed_rules']!=1 else ''} "
                       f"({_fmt_int(b['failed_checks'])} violation{'s' if b['failed_checks']!=1 else ''}). All fixed.")
            meta_strong = f"{_fmt_int(b['failed_checks'])} violation{'s' if b['failed_checks']!=1 else ''} cleared"
        elif cat == "improved" and b and b.get("parsed") and a and a.get("parsed"):
            br, ar = b["failed_rules"], a["failed_rules"]
            bc, ac = b["failed_checks"], a["failed_checks"]
            fixed_n = max(br - ar, 0)
            count_num, count_sub = ar, "rules still failing"
            summary = (f"Still fails {ar} rule{'s' if ar!=1 else ''} ({_fmt_int(ac)} violation{'s' if ac!=1 else ''}). "
                       f"{fixed_n} rule type{'s' if fixed_n!=1 else ''} fixed; "
                       f"{_fmt_int(bc-ac)} fewer violations than before.")
            meta_strong = f"{_fmt_int(bc-ac)} violation{'s' if (bc-ac)!=1 else ''} cleared"
        elif cat == "still_passing":
            count_num, count_sub = 0, "issues"
            summary = "Passed before, still passes."
            meta_strong = "no violations"
        elif cat == "still_failing" and a and a.get("parsed"):
            ar, ac = a["failed_rules"], a["failed_checks"]
            count_num, count_sub = ar, "rules failing"
            summary = f"Still fails the same {ar} rule{'s' if ar!=1 else ''} ({_fmt_int(ac)} violation{'s' if ac!=1 else ''})."
            meta_strong = f"{_fmt_int(ac)} violation{'s' if ac!=1 else ''}"
        elif cat == "worsened" and b and b.get("parsed") and a and a.get("parsed"):
            br, ar = b["failed_rules"], a["failed_rules"]
            bc, ac = b["failed_checks"], a["failed_checks"]
            count_num, count_sub = ar, "rules failing"
            summary = (f"Now fails {ar} rule{'s' if ar!=1 else ''} ({_fmt_int(ac)} violation{'s' if ac!=1 else ''}); "
                       f"was {br} rule{'s' if br!=1 else ''} ({_fmt_int(bc)} violation{'s' if bc!=1 else ''}).")
            meta_strong = f"{_fmt_int(ac-bc)} more violations"
        elif cat == "regressed" and a and a.get("parsed"):
            ar, ac = a["failed_rules"], a["failed_checks"]
            count_num, count_sub = ar, "rules newly failing"
            summary = f"Used to pass. Now fails {ar} rule{'s' if ar!=1 else ''} ({_fmt_int(ac)} violation{'s' if ac!=1 else ''})."
            meta_strong = f"{_fmt_int(ac)} new violation{'s' if ac!=1 else ''}"
        elif cat == "new":
            if a and a.get("parsed"):
                ar, ac = a["failed_rules"], a["failed_checks"]
                count_num, count_sub = ar, "rules failing" if ar else "issues"
                if ar:
                    summary = f"Only in &lsquo;after&rsquo;. Fails {ar} rule{'s' if ar!=1 else ''} ({_fmt_int(ac)} violation{'s' if ac!=1 else ''})."
                    meta_strong = f"{_fmt_int(ac)} violation{'s' if ac!=1 else ''}"
                else:
                    summary = "Only in &lsquo;after&rsquo;. Passes."
                    meta_strong = "no violations"
            else:
                count_num, count_sub = "?", "unparsed"
                summary = "Only in &lsquo;after&rsquo;. veraPDF could not parse it."
                meta_strong = "unparsed"
        elif cat == "missing":
            if b and b.get("parsed"):
                br, bc = b["failed_rules"], b["failed_checks"]
                count_num, count_sub = br, "rules failed" if br else "issues"
                summary = f"Was failing {br} rule{'s' if br!=1 else ''} ({_fmt_int(bc)} violation{'s' if bc!=1 else ''}) before. Not in &lsquo;after&rsquo;."
                meta_strong = f"{_fmt_int(bc)} violation{'s' if bc!=1 else ''} (before)"
            else:
                count_num, count_sub = "—", "before"
                summary = "Not in &lsquo;after&rsquo;."
                meta_strong = "removed"
        else:
            count_num, count_sub = "?", ""
            summary = ""
            meta_strong = ""

        # Detail row beneath: full before→after triplet for anyone who needs it.
        def stat(label, b_val, a_val, fmt=lambda x: str(x)):
            bv = fmt(b_val) if b_val is not None else "—"
            av = fmt(a_val) if a_val is not None else "—"
            return f'<span><span class="ri-stat-l">{label}</span> {bv} &rarr; {av}</span>'
        bp = b.get("parsed") if b else False
        ap = a.get("parsed") if a else False
        stats_line = (
            stat("Rules",       b["failed_rules"]   if bp else None, a["failed_rules"]   if ap else None) +
            stat("Violations",  b["failed_checks"]  if bp else None, a["failed_checks"]  if ap else None, _fmt_int) +
            stat("Successful checks", b["passed_checks"] if bp else None, a["passed_checks"] if ap else None, _fmt_int)
        )

        diff = render_rule_diff(b, a)
        return (
            f'<article class="rowitem fileitem">'
            f'  <div class="ri-count">'
            f'    <span class="ri-num">{count_num}</span>'
            f'    <span class="ri-num-sub">{count_sub}</span>'
            f'  </div>'
            f'  <div class="ri-body">'
            f'    <div class="ri-label ri-label-mono">{html.escape(name)}</div>'
            f'    <div class="ri-explain">{summary}</div>'
            f'    <div class="ri-stats">{stats_line}</div>'
            f'    {diff}'
            f'  </div>'
            f'  <div class="ri-meta">'
            f'    {render_status_badge(cat)}'
            f'    <span class="ri-meta-strong">{meta_strong}</span>'
            f'  </div>'
            f'</article>'
        )

    sections_html_parts = []
    for cat in SECTION_ORDER:
        rows = buckets[cat]
        if not rows:
            continue
        legacy_label, color = CATEGORY_LABELS[cat]
        plain_head, plain_blurb = CATEGORY_PLAIN[cat]
        n = len(rows)
        # No per-section "most affected rules" chip row: the headline rule
        # list above already covers this category in the rich format.
        # Adding a second, cosmetically-different summary creates visual
        # noise without new information.
        files_html = "".join(render_file_row(cat, n_, b_, a_) for n_, b_, a_ in rows)
        sections_html_parts.append(
            f'<section class="bucket {color}" id="sec-{cat}">'
            f'<header class="bucket-head">'
            f'<h2><span class="dot"></span>'
            f'<span class="bucket-title">{plain_head}</span>'
            f'<span class="bucket-count">{n} file{"s" if n != 1 else ""}</span>'
            f'</h2>'
            f'<p class="bucket-blurb">{plain_blurb} '
            f'<span class="bucket-legacy" title="The veraPDF category this section corresponds to.">'
            f'(category: <em>{legacy_label}</em>)</span></p>'
            f'</header>'
            f'<div class="files">{files_html}</div>'
            f'</section>'
        )

    sections_html = "".join(sections_html_parts) or (
        '<section class="bucket gray"><header class="bucket-head"><h2>'
        '<span class="dot"></span><span class="bucket-title">Nothing to show</span></h2>'
        '<p class="bucket-blurb">No PDFs were found in either folder.</p></header></section>'
    )

    # ----------------------------------------------------------------------
    # Final HTML
    # ----------------------------------------------------------------------
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF accessibility check &mdash; {profile_label}</title>
<style>
  :root {{
    --nav-h: 52px;
    --paper:      #faf6ee;     /* warm cream page */
    --panel:      #fffdf6;     /* slightly lighter card */
    --ink:        #1a1916;
    --ink-soft:   #4d4942;
    --ink-mute:   #79746a;
    --rule:       #d9d3c4;     /* divider */
    --rule-soft:  #ebe5d4;
    --code-bg:    #f0eadb;
    --serif:      'Iowan Old Style','Palatino','Palatino Linotype','Book Antiqua','Georgia','Times New Roman',serif;
    --sans:       -apple-system, BlinkMacSystemFont, 'Segoe UI Variable Text', 'Segoe UI', system-ui, 'Helvetica Neue', sans-serif;
    --mono:       ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    --pass-fg:    #1d5b32;  --pass-bg: #e3eed8;  --pass-bd: #b1cda6;
    --warn-fg:    #7d5400;  --warn-bg: #f5e6c5;  --warn-bd: #d9bf7d;
    --fail-fg:    #8a2424;  --fail-bg: #f3dcd6;  --fail-bd: #d6a39a;
    --info-fg:    #1d3d8a;  --info-bg: #dde0ed;  --info-bd: #aab3d3;
    --neutral-fg: #4d4942;  --neutral-bg: #ede8db; --neutral-bd: #cdc6b4;
  }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: var(--sans);
    background: var(--paper);
    color: var(--ink);
    margin: 0; padding: 0 1.5em 5em;
    -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
    line-height: 1.55;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}

  /* --- editorial header --- */
  header.page {{
    padding: 2.6em 0 1.4em;
    border-bottom: 1px solid var(--rule);
    margin-bottom: 1.6em;
  }}
  .eyebrow {{
    font-family: var(--sans);
    font-size: .72rem; letter-spacing: .14em; text-transform: uppercase;
    color: var(--ink-mute); margin: 0 0 .8em;
  }}
  h1.title {{
    font-family: var(--serif);
    font-weight: 400; letter-spacing: -.012em;
    font-size: clamp(1.75rem, 4.2vw, 2.6rem); line-height: 1.05;
    margin: 0 0 .25em;
  }}
  .kicker {{
    font-family: var(--serif); font-weight: 400; font-style: italic;
    font-size: clamp(1rem, 1.8vw, 1.2rem); line-height: 1.4;
    color: var(--ink-soft); margin: 0 0 .85em; max-width: 56ch;
  }}
  .preamble {{
    max-width: 64ch;
    color: var(--ink-soft); font-size: .94rem; line-height: 1.55;
    margin: 0;
  }}
  .preamble strong {{ color: var(--ink); font-weight: 600; }}
  .meta-grid {{
    display: grid; grid-template-columns: max-content 1fr; gap: .15em 1.2em;
    margin: 1.4em 0 0; font-size: .88rem; color: var(--ink-soft);
  }}
  .meta-grid dt {{
    font-family: var(--sans); text-transform: uppercase; letter-spacing: .08em;
    font-size: .68rem; color: var(--ink-mute); padding-top: .25em;
  }}
  .meta-grid dd {{ margin: 0; font-family: var(--mono); font-size: .8rem; word-break: break-all; }}
  .meta-aside {{ color: var(--ink-mute); font-size: .82em; }}

  /* --- sticky section nav --- */
  nav.toc {{
    position: sticky; top: 0; z-index: 20;
    margin: 0 -1.5em; padding: .5em 1.5em;
    background: rgba(250, 246, 238, .94);
    -webkit-backdrop-filter: saturate(150%) blur(6px);
    backdrop-filter: saturate(150%) blur(6px);
    border-bottom: 1px solid var(--rule);
    display: flex; flex-wrap: wrap; gap: .35em .5em;
  }}
  .navchip {{
    display: inline-flex; align-items: baseline; gap: .45em;
    padding: .3em .75em; border-radius: 2px;
    font-size: .82rem; line-height: 1;
    text-decoration: none; color: var(--ink);
    background: var(--panel); border: 1px solid var(--rule);
  }}
  .navchip:hover {{ border-color: var(--ink-soft); }}
  .navchip .nc-n {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .navchip.green  {{ border-left: 3px solid var(--pass-bd); }}
  .navchip.teal   {{ border-left: 3px solid var(--info-bd); }}
  .navchip.gray   {{ border-left: 3px solid var(--neutral-bd); }}
  .navchip.orange {{ border-left: 3px solid var(--warn-bd); }}
  .navchip.red    {{ border-left: 3px solid var(--fail-bd); }}
  .navchip.blue   {{ border-left: 3px solid var(--info-bd); }}

  /* --- the headline answer: scoreboard first, caption second ---
     The proof (numbers + before→after) is the largest type on the page;
     the prose caption is secondary and clarifies what the numbers mean. */
  .answer {{
    margin: 2.2em 0 1.6em; padding: 1.8em 1.6em 1.4em;
    background: var(--panel); border-left: 4px solid var(--ink);
    border-radius: 0 4px 4px 0;
  }}
  .answer.pass {{ border-left-color: var(--pass-fg); }}
  .answer.fail {{ border-left-color: var(--fail-fg); }}
  .answer.warn {{ border-left-color: var(--warn-fg); }}

  .scoreboard {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.4em 2.2em;
    margin: 0 0 1.2em;
    padding-bottom: 1.2em;
    border-bottom: 1px solid var(--rule-soft);
  }}
  .score {{ display: flex; flex-direction: column; gap: .25em; }}
  .score-label {{
    font-family: var(--sans);
    font-size: .72rem; font-weight: 600; letter-spacing: .12em;
    text-transform: uppercase; color: var(--ink-mute);
  }}
  .score-pair {{
    display: flex; align-items: baseline; gap: .25em;
    font-family: var(--serif); font-weight: 400;
    font-variant-numeric: tabular-nums; line-height: 1;
    letter-spacing: -.018em;
  }}
  .score-from {{
    font-size: clamp(2.2rem, 6vw, 3.4rem);
    color: var(--ink-mute);
  }}
  .score-arrow {{
    font-size: clamp(1.6rem, 4vw, 2.4rem);
    color: var(--ink-mute);
    margin: 0 .15em;
  }}
  .score-to {{
    font-size: clamp(2.8rem, 8vw, 4.6rem);
    color: var(--ink); font-weight: 500;
  }}
  .score-of {{
    align-self: flex-end; padding-bottom: .3em;
    font-size: clamp(1rem, 2vw, 1.4rem);
    color: var(--ink-mute); margin-left: .2em;
  }}
  /* Both sides of the from→to pair carry color so red→green or green→red
     reads at a glance regardless of which side is "before" and which is "after". */
  .cls-good     {{ color: var(--pass-fg); }}
  .cls-bad      {{ color: var(--fail-fg); }}
  .cls-neutral  {{ color: var(--ink); }}
  .score-caption {{
    font-family: var(--sans); font-size: .92rem; color: var(--ink-soft);
    font-variant-numeric: tabular-nums;
    margin-top: .15em;
  }}
  .score-good .score-caption {{ color: var(--pass-fg); }}
  .score-bad  .score-caption {{ color: var(--fail-fg); }}

  .answer .what {{
    font-family: var(--serif);
    font-size: clamp(1.05rem, 1.8vw, 1.2rem); line-height: 1.45; font-weight: 400;
    margin: 0; letter-spacing: -.005em; color: var(--ink);
  }}
  .answer .what-sub {{ color: var(--ink-soft); }}
  .answer .what.pass-text {{ color: var(--pass-fg); }}
  .answer .what.fail-text {{ color: var(--fail-fg); }}
  .answer .what.warn-text {{ color: var(--warn-fg); }}

  /* attention callout */
  .attention {{
    margin: 1.6em 0; padding: 1em 1.2em;
    background: var(--fail-bg); border: 1px solid var(--fail-bd);
    border-radius: 4px; color: var(--fail-fg);
  }}
  .attention strong {{ font-weight: 600; }}
  .attention a {{ color: inherit; text-decoration: underline; }}

  /* --- top-rules summary --- */
  section.rule-summary {{ margin: 2em 0 2.2em; }}
  section.rule-summary > h3 {{
    font-family: var(--serif); font-weight: 400; font-size: 1.25rem;
    margin: 0 0 .35em; letter-spacing: -.005em;
  }}
  section.rule-summary .rule-intro {{
    color: var(--ink-soft); font-size: .92rem; margin: 0 0 1em;
  }}
  /* Shared row-item layout: used both by the top "what was wrong" rule
     list (rule-centric) and by the per-file articles (file-centric).
     Same grid, same number column, same body, same meta column —
     the only thing that varies is what the numbers count. */
  ol.rowlist {{
    list-style: none; padding: 0; margin: 0;
    border-top: 1px solid var(--rule);
  }}
  .rowitem {{
    display: grid;
    grid-template-columns: 5em 1fr 11em;
    gap: .2em 1.2em;
    padding: 1em .25em;
    border-bottom: 1px solid var(--rule-soft);
    align-items: start;
  }}
  .ri-count {{ display: flex; flex-direction: column; align-items: flex-start; }}
  .ri-num {{
    font-family: var(--serif); font-weight: 500; line-height: 1;
    font-size: clamp(1.8rem, 3vw, 2.4rem); font-variant-numeric: tabular-nums;
    color: var(--ink); letter-spacing: -.01em;
  }}
  .ri-num-sub {{
    font-family: var(--sans); font-size: .68rem; color: var(--ink-mute);
    letter-spacing: .08em; text-transform: uppercase; margin-top: 4px;
    line-height: 1.2;
  }}
  .ri-body {{ display: flex; flex-direction: column; gap: .25em; padding-top: .25em; min-width: 0; }}
  .ri-label {{
    font-family: var(--serif); font-weight: 500; font-size: 1.15rem;
    line-height: 1.25; color: var(--ink); letter-spacing: -.005em;
    overflow-wrap: anywhere;
  }}
  .ri-label-mono {{ font-family: var(--mono); font-size: 1rem; }}
  .ri-explain {{
    font-family: var(--sans); font-size: .92rem; line-height: 1.45;
    color: var(--ink-soft);
  }}
  .ri-explain-aside {{ color: var(--ink-mute); font-style: italic; }}
  .ri-spec {{
    font-size: .78rem; line-height: 1.5; color: var(--ink-mute);
    border-left: 2px solid var(--rule-soft); padding: .15em 0 .15em .65em;
    margin-top: .3em;
  }}
  .ri-spec-arrow {{
    font-family: var(--sans); text-transform: uppercase; font-size: .68rem;
    letter-spacing: .08em; margin-right: .35em;
  }}
  .ri-stats {{
    margin-top: .35em;
    display: flex; flex-wrap: wrap; gap: .25em 1.4em;
    font-family: var(--sans); font-size: .82rem; color: var(--ink-soft);
    font-variant-numeric: tabular-nums;
  }}
  .ri-stats .ri-stat-l {{
    font-weight: 500; color: var(--ink-mute); margin-right: .35em;
    text-transform: uppercase; font-size: .68rem; letter-spacing: .06em;
  }}
  .ri-meta {{
    text-align: right; padding-top: .35em;
    display: flex; flex-direction: column; gap: .35em; align-items: flex-end;
    font-family: var(--sans); font-size: .82rem; color: var(--ink-soft);
    font-variant-numeric: tabular-nums;
  }}
  .ri-meta-strong {{ font-weight: 500; color: var(--ink-soft); }}
  .ri-id {{
    background: var(--code-bg); padding: 1px 6px; border-radius: 2px;
    font-family: var(--mono); font-size: .74rem; color: var(--ink-mute);
  }}

  /* --- per-section --- */
  section.bucket {{
    margin-top: 2.4em;
    padding-top: 1em;
    border-top: 1px solid var(--rule);
    scroll-margin-top: calc(var(--nav-h) + .6em);
  }}
  section.bucket:target h2 {{
    box-shadow: -8px 0 0 -3px currentColor;
    transition: box-shadow .25s;
  }}
  .bucket-head {{ margin-bottom: 1.2em; }}
  .bucket h2 {{
    font-family: var(--serif); font-weight: 400;
    font-size: 1.4rem; margin: 0 0 .25em;
    display: flex; align-items: baseline; gap: .55em;
    letter-spacing: -.005em;
  }}
  .bucket h2 .dot {{
    width: .5em; height: .5em; border-radius: 999px; background: currentColor;
    display: inline-block; opacity: .55; align-self: center;
  }}
  .bucket h2 .bucket-count {{
    margin-left: auto;
    font-family: var(--sans); font-size: .75rem; font-weight: 500;
    color: var(--ink-mute); letter-spacing: .06em; text-transform: uppercase;
    font-variant-numeric: tabular-nums;
  }}
  .bucket-blurb {{
    color: var(--ink-soft); font-size: .92rem; margin: 0 0 1em;
    max-width: 60ch;
  }}
  .bucket-legacy {{ color: var(--ink-mute); font-size: .82rem; }}
  .bucket-legacy em {{ font-style: italic; }}
  .bucket.green   h2 {{ color: var(--pass-fg); }} .bucket.green   {{ --bucket-bd: var(--pass-bd); }}
  .bucket.teal    h2 {{ color: var(--info-fg); }} .bucket.teal    {{ --bucket-bd: var(--info-bd); }}
  .bucket.gray    h2 {{ color: var(--neutral-fg); }} .bucket.gray  {{ --bucket-bd: var(--neutral-bd); }}
  .bucket.orange  h2 {{ color: var(--warn-fg); }} .bucket.orange  {{ --bucket-bd: var(--warn-bd); }}
  .bucket.red     h2 {{ color: var(--fail-fg); }} .bucket.red     {{ --bucket-bd: var(--fail-bd); }}
  .bucket.blue    h2 {{ color: var(--info-fg); }} .bucket.blue    {{ --bucket-bd: var(--info-bd); }}

  /* per-section rule chips */
  .rchip-row {{
    display: flex; flex-wrap: wrap; gap: .45em; margin: .8em 0 .2em;
    align-items: center;
  }}
  .rchip-lead {{
    font-family: var(--sans); font-size: .72rem; letter-spacing: .08em;
    text-transform: uppercase; color: var(--ink-mute);
    margin-right: .25em;
  }}
  .rchip {{
    display: inline-flex; align-items: baseline; gap: .5em;
    padding: .35em .7em; border-radius: 3px;
    background: var(--panel); border: 1px solid var(--rule);
    font-size: .85rem;
  }}
  .rchip-n {{
    font-family: var(--serif); font-weight: 600; font-size: 1.05rem;
    line-height: 1; color: var(--ink); font-variant-numeric: tabular-nums;
  }}
  .rchip-text {{ color: var(--ink-soft); }}

  /* per-file article uses the same .rowitem grid as the rule list above.
     The whole bucket of files is a .rowlist for visual symmetry with the
     top "what was wrong" section. */
  .files {{ list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--rule); }}
  .badge {{
    font-family: var(--sans);
    font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em;
    padding: .25em .65em; border-radius: 2px;
    border: 1px solid currentColor;
    align-self: flex-end;
  }}
  .badge.green   {{ color: var(--pass-fg); background: var(--pass-bg); border-color: var(--pass-bd); }}
  .badge.teal    {{ color: var(--info-fg); background: var(--info-bg); border-color: var(--info-bd); }}
  .badge.gray    {{ color: var(--neutral-fg); background: var(--neutral-bg); border-color: var(--neutral-bd); }}
  .badge.orange  {{ color: var(--warn-fg); background: var(--warn-bg); border-color: var(--warn-bd); }}
  .badge.red     {{ color: var(--fail-fg); background: var(--fail-bg); border-color: var(--fail-bd); }}
  .badge.blue    {{ color: var(--info-fg); background: var(--info-bg); border-color: var(--info-bd); }}

  /* --- expandable rule-level diff (per file) --- */
  details {{
    margin-top: .6em; font-size: .9rem;
    border-top: 1px dashed var(--rule-soft); padding-top: .55em;
  }}
  details summary {{
    cursor: pointer; color: var(--ink-soft);
    font-weight: 500; outline: none; list-style: none;
    padding: 0;
  }}
  details summary::-webkit-details-marker {{ display: none; }}
  details summary::before {{
    content: "\\25B8"; display: inline-block;
    width: 1.2em; color: var(--ink-mute);
    transition: transform .15s;
  }}
  details[open] > summary::before {{ transform: rotate(90deg); }}
  ul.rd-list {{ list-style: none; padding: .55em 0 .15em; margin: 0; display: grid; gap: .55em; }}
  ul.rd-list li {{
    display: grid; grid-template-columns: 1.4em 1fr; gap: .15em .55em;
    padding: .55em .7em; border-radius: 3px;
    border-left: 3px solid var(--rule);
    background: var(--paper);
  }}
  .rd-sigil {{ font-family: var(--mono); font-size: 1rem; line-height: 1.3; }}
  .rd-body {{ display: flex; flex-direction: column; gap: .15em; min-width: 0; }}
  .rd-headline {{
    display: flex; flex-wrap: wrap; align-items: baseline; gap: .35em .7em;
  }}
  .rd-status {{
    font-family: var(--sans); font-size: .68rem; font-weight: 700;
    letter-spacing: .1em; text-transform: uppercase;
    padding: 1px 6px; border-radius: 2px;
  }}
  .rd-label {{
    font-family: var(--serif); font-weight: 500;
    font-size: 1.02rem; line-height: 1.3; color: var(--ink);
  }}
  .rd-count {{
    margin-left: auto;
    font-family: var(--sans); font-size: .8rem; color: var(--ink-soft);
    font-variant-numeric: tabular-nums;
  }}
  .rd-explain {{ font-family: var(--sans); font-size: .9rem; color: var(--ink-soft); line-height: 1.45; }}
  .rd-spec {{
    font-size: .76rem; line-height: 1.55; color: var(--ink-mute);
    margin-top: .15em;
  }}
  .rd-spec code {{
    font-family: var(--mono); font-size: .76rem;
    background: var(--code-bg); padding: 1px 5px; border-radius: 2px;
    color: var(--ink-soft); margin-right: .35em;
  }}
  .rd-spec-text {{ font-style: italic; }}
  .rd-fixed   {{ border-left-color: var(--pass-bd); }}
  .rd-fixed   .rd-status, .rd-fixed   .rd-sigil {{ color: var(--pass-fg); }}
  .rd-fixed   .rd-status {{ background: var(--pass-bg); }}
  .rd-new     {{ border-left-color: var(--fail-bd); }}
  .rd-new     .rd-status, .rd-new     .rd-sigil {{ color: var(--fail-fg); }}
  .rd-new     .rd-status {{ background: var(--fail-bg); }}
  .rd-persist {{ border-left-color: var(--neutral-bd); }}
  .rd-persist .rd-status, .rd-persist .rd-sigil {{ color: var(--ink-mute); }}
  .rd-persist .rd-status {{ background: var(--neutral-bg); }}

  /* --- footer / glossary --- */
  footer.glossary {{
    margin-top: 4em; padding-top: 1.6em;
    border-top: 1px solid var(--rule);
    font-size: .85rem; color: var(--ink-soft);
    max-width: 64ch;
  }}
  footer.glossary h4 {{
    font-family: var(--serif); font-weight: 400; font-size: 1.05rem;
    margin: 1.2em 0 .35em;
  }}
  footer.glossary p {{ margin: 0 0 .8em; line-height: 1.5; }}
  footer.glossary ol {{ margin: .2em 0 1em; padding-left: 1.4em; line-height: 1.55; }}
  footer.glossary li {{ margin: .35em 0; }}
  footer.glossary code {{
    font-family: var(--mono); background: var(--code-bg);
    padding: 1px 5px; border-radius: 2px; font-size: .82rem;
  }}

  /* narrow viewport */
  @media (max-width: 720px) {{
    body {{ padding: 0 .9em 4em; }}
    nav.toc {{ margin: 0 -.9em; padding: .5em .9em; }}
    .file-head {{ gap: .35em .8em; }}
    .badge {{ margin-left: 0; }}
    .scoreboard {{ gap: 1em; }}
    ol.top-rules li {{
      grid-template-columns: 3.2em 1fr;
    }}
    .tr-meta {{
      grid-column: 2 / 3; padding-top: .15em;
      flex-direction: row; align-items: baseline; align-self: start;
      text-align: left; gap: .8em;
    }}
    ul.rd-list li {{ grid-template-columns: 1.2em 1fr; }}
    .rd-headline {{ flex-wrap: wrap; }}
    .rd-count {{ margin-left: 0; flex-basis: 100%; }}
  }}
</style></head>
<body><div class="wrap">

<header class="page">
  <p class="eyebrow">Before vs after</p>
  <h1 class="title">PDF accessibility check</h1>
  <p class="kicker">PDFs before and after remediation. Click on each file to see what was failing and what was fixed.</p>
  <p class="preamble">Each PDF was checked against <strong>{html.escape(profile_label)}</strong> &mdash; {html.escape(profile_blurb) if profile_blurb else "a veraPDF accessibility profile."}
  &lsquo;Before&rsquo; is the original; &lsquo;after&rsquo; is what came out of the remediator.</p>
  <dl class="meta-grid">
    <dt>Before folder</dt><dd>{html.escape(before_dir)}</dd>
    <dt>After folder</dt><dd>{html.escape(after_dir)}</dd>
    <dt>Standard</dt><dd>{html.escape(profile_label)} <span class="meta-aside">({html.escape(profile)})</span></dd>
    <dt>Compared</dt><dd>{total} file{'' if total == 1 else 's'} (matched by basename)</dd>
  </dl>
</header>

{nav_block}

<div class="answer {('pass' if (fail_after == 0 and pass_after > 0 and totals['regressed'] == 0 and totals['worsened'] == 0) else ('fail' if (totals['regressed'] > 0 or totals['worsened'] > 0) else ('warn' if fail_after > 0 else '')))}">
  <div class="scoreboard">
    {''.join(
      f'<div class="score score-{t["to_class"]}">'
      f'  <div class="score-label">{html.escape(t["label"])}</div>'
      f'  <div class="score-pair">'
      f'    <span class="score-from cls-{t["from_class"]}" title="before">{_fmt_int(t["before"])}</span>'
      f'    <span class="score-arrow" aria-hidden="true">&rarr;</span>'
      f'    <span class="score-to cls-{t["to_class"]}" title="after">{_fmt_int(t["after"])}</span>'
      f'    {f"""<span class="score-of">/ {_fmt_int(t["denom"])}</span>""" if t.get("denom") else ""}'
      f'  </div>'
      f'  <div class="score-caption">{html.escape(t["caption"])}</div>'
      f'</div>'
      for t in scoreboard_tiles
    )}
  </div>
  <p class="what {('pass-text' if (fail_after == 0 and pass_after > 0 and totals['regressed'] == 0 and totals['worsened'] == 0) else ('fail-text' if (totals['regressed'] > 0 or totals['worsened'] > 0) else ('warn-text' if fail_after > 0 else '')))}">{headline_main}{f' <span class="what-sub">{headline_sub}</span>' if headline_sub else ''}</p>
</div>

{f'<aside class="attention"><strong>Needs attention:</strong> {needs_attention} file{"s" if needs_attention != 1 else ""} did not pass. Jump to the relevant section below.</aside>' if needs_attention > 0 else ''}

{headline_rules_html}

{before_section_html}

{sections_html}

<footer class="glossary">
  <h4>About this report</h4>
  <p>Each PDF was checked against the <strong>{html.escape(profile_label)}</strong> standard.
     A passing PDF meets the requirements that make it usable by people who rely on
     screen readers.</p>
  <h4>How remediation works</h4>
  <p>Each PDF goes through a seven-step pipeline that rebuilds the parts of the
     file screen readers depend on, without changing what the document looks like:</p>
  <ol>
    <li><strong>Pre-checks.</strong> Clean up technical obstacles that would block tagging:
        optional-content layer names, embedded-file specifications, legacy
        XFA-form data, and broken XObject references.</li>
    <li><strong>Fonts.</strong> Embed every font used by the document and make sure each
        font's character data is consistent &mdash; screen readers depend on this to
        translate glyphs back to text. Symbol fonts (Wingdings, ZapfDingbats, Symbol)
        get explicit Unicode mappings synthesised. Any font that can't be repaired
        aborts the pipeline rather than silently producing a non-conforming file.</li>
    <li><strong>Strip the slate.</strong> Remove all existing accessibility tags and
        marked-content operators. Existing tags are often partial, malformed, or use
        non-standard types; rebuilding from scratch is more reliable than patching
        an unknown tree.</li>
    <li><strong>Catalog metadata.</strong> Mark the document as tagged, set the
        document language, and tell PDF readers to display the document's title
        instead of the filename.</li>
    <li><strong>XMP metadata.</strong> Write a complete metadata stream declaring
        the file as following the accessibility standard, with a real title and a
        modification date.</li>
    <li><strong>Structure tree.</strong> Analyse the document's content semantically
        &mdash; headings, paragraphs, lists, tables, figures, reading order &mdash; and
        build a structure tree. Every visible element is labelled either as real
        content (with its semantic role) or as decoration to be skipped. The
        content streams are rewritten so the tags line up with what the renderer
        actually paints.</li>
    <li><strong>Annotations.</strong> Wire up links, form fields, and other
        clickable areas with descriptions that screen-reader users can hear.
        Printer-only annotations are removed. Tab order is set to follow the
        document structure.</li>
  </ol>
  <p>The accessibility check above runs on the original PDF and on the rebuilt
     PDF, then compares them rule by rule.</p>
</footer>

</div></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before_dir")
    ap.add_argument("after_dir")
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="profile alias (%s) or XML path (default: %s)"
                         % (", ".join(PROFILE_ALIASES), DEFAULT_PROFILE))
    ap.add_argument("--output", default=None,
                    help="output HTML path (default: ~/verapdf-diff-<profile>.html)")
    args = ap.parse_args()

    profile_label = args.profile if args.profile in PROFILE_ALIASES else Path(args.profile).stem
    args.profile = resolve_profile(args.profile)
    if args.output is None:
        args.output = str(Path.home() / f"verapdf-diff-{profile_label}.html")

    for p in [args.before_dir, args.after_dir, args.profile]:
        if not Path(p).exists():
            sys.exit(f"not found: {p}")

    before_report = run_verapdf(args.profile, args.before_dir)
    after_report = run_verapdf(args.profile, args.after_dir)

    before_idx = index_by_basename(before_report)
    after_idx = index_by_basename(after_report)

    html_out = render_html(args.before_dir, args.after_dir, args.profile,
                           before_idx, after_idx)
    Path(args.output).write_text(html_out)
    print(f"wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
