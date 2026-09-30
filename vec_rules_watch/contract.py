"""Rule-based diffs of the machine-readable contract: panels/index.json with its gene lists, the phase endpoint and
the organisers' scorer on GitHub. Each change is a Message (rendered into English and Chinese from fixed
templates) plus zero or more "what this changes for your file" Messages.

The rules know the fields index.json and the phase endpoint have today (2026-09-30); a field they do not know is
still reported, as a generic "field X: old -> new" line, so a new field cannot slip through unnoticed.
"""
from __future__ import annotations

import hashlib
import json
import re

from .messages import Joined, Message
from .pages import excerpt

KNOWN_BOARD_FIELDS = {"label", "n_genes", "genes_file", "genes_sha256", "min_cells", "max_cells", "obsm_required",
                      "obs_required", "needs_coords", "anchors"}
PHASE_FLAGS = ("accepts_submissions", "shows_scores", "nominations_open", "data_open")
STAGE_RE = re.compile(r"\bE\d+(?:\.\d+)?\b")
MAX_NAMES = 10


def item(msg: Message, *impact) -> dict:
    return {"msg": msg, "impact": [m for m in impact if m is not None]}


def panel_sha256(genes) -> str:
    """index.json's genes_sha256 convention (same as vec_submit_check): sha256 of the newline-joined list, 16 hex."""
    return hashlib.sha256("\n".join(genes).encode("utf-8")).hexdigest()[:16]


def parse_genes(text: str) -> list:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _val(v):
    if isinstance(v, (dict, list)) and not (isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v)):
        return excerpt(json.dumps(v, sort_keys=True, ensure_ascii=False))
    if isinstance(v, str):
        return excerpt(v)
    return v


def _coords(spec: dict):
    keys = spec.get("obsm_required") or []
    if spec.get("needs_coords") or keys:
        return Message("coords.required", keys=keys or ["?"])
    return Message("coords.none")


def board_summary(board: str, spec: dict) -> Message:
    return Message("contract.board_summary", board=board, n_genes=spec.get("n_genes"),
                   genes_file=spec.get("genes_file"), genes_sha256=spec.get("genes_sha256"),
                   min_cells=spec.get("min_cells"), max_cells=spec.get("max_cells"), coords=_coords(spec))


def genes_check(board: str, spec: dict, genes) -> list:
    """index.json says genes_sha256 / n_genes; does the published list agree?"""
    if genes is None or not isinstance(spec, dict):
        return []
    got = panel_sha256(genes)
    exp = spec.get("genes_sha256")
    exp_n = spec.get("n_genes")
    if (exp is not None and got != exp) or (exp_n is not None and len(genes) != exp_n):
        return [item(Message("contract.sha_mismatch", board=board, genes_file=spec.get("genes_file"), expected=exp,
                             got=got, n=len(genes), expected_n=exp_n))]
    return []


def _genes_diff(board, old_spec, new_spec, old_genes, new_genes) -> list:
    out = []
    if old_spec.get("genes_file") != new_spec.get("genes_file"):
        out.append(item(Message("contract.genes_file_changed", board=board, old=old_spec.get("genes_file"),
                                new=new_spec.get("genes_file"))))
    same_list = old_genes is not None and new_genes is not None and old_genes == new_genes
    meta_changed = (old_spec.get("genes_sha256") != new_spec.get("genes_sha256")
                    or old_spec.get("n_genes") != new_spec.get("n_genes"))
    if same_list and not meta_changed:
        return out
    if old_genes is not None and new_genes is not None:
        if same_list:
            return out
        old_set, new_set = set(old_genes), set(new_genes)
        add = [g for g in new_genes if g not in old_set]
        rem = [g for g in old_genes if g not in new_set]
        kept_old = [g for g in old_genes if g in new_set]
        kept_new = [g for g in new_genes if g in old_set]
        order = Message("genes.order_changed") if kept_old != kept_new else Message("genes.order_same")
        out.append(item(
            Message("contract.genes_changed", board=board, old_n=len(old_genes), new_n=len(new_genes),
                    added=len(add), removed=len(rem), order_note=order, old_sha=old_spec.get("genes_sha256"),
                    new_sha=new_spec.get("genes_sha256")),
            Message("impact.genes_changed", board=board)))
        if add or rem:
            out.append(item(Message("contract.genes_examples", added_list=_names(add), removed_list=_names(rem))))
    elif meta_changed:
        out.append(item(
            Message("contract.genes_changed", board=board, old_n=old_spec.get("n_genes"),
                    new_n=new_spec.get("n_genes"), added="?", removed="?", order_note=Message("genes.order_same"),
                    old_sha=old_spec.get("genes_sha256"), new_sha=new_spec.get("genes_sha256")),
            Message("impact.genes_changed", board=board)))
    return out


def _names(names) -> Joined:
    shown = list(names[:MAX_NAMES])
    if len(names) > MAX_NAMES:
        shown.append(f"... (+{len(names) - MAX_NAMES})")
    return Joined(shown)


def diff_board(board: str, old: dict, new: dict, old_genes=None, new_genes=None) -> list:
    out = []
    out += _genes_diff(board, old, new, old_genes, new_genes)
    if (old.get("min_cells"), old.get("max_cells")) != (new.get("min_cells"), new.get("max_cells")):
        out.append(item(Message("contract.cells_changed", board=board, old_min=old.get("min_cells"),
                                old_max=old.get("max_cells"), new_min=new.get("min_cells"),
                                new_max=new.get("max_cells")),
                        Message("impact.cells_changed", board=board, new_min=new.get("min_cells"),
                                new_max=new.get("max_cells"))))
    if (old.get("obsm_required") or []) != (new.get("obsm_required") or []):
        keys = new.get("obsm_required") or []
        out.append(item(Message("contract.obsm_changed", board=board, old=old.get("obsm_required") or [], new=keys),
                        Message("impact.obsm_required", board=board, keys=keys) if keys
                        else Message("impact.obsm_none", board=board)))
    if (old.get("obs_required") or []) != (new.get("obs_required") or []):
        out.append(item(Message("contract.obs_changed", board=board, old=old.get("obs_required") or [],
                                new=new.get("obs_required") or []),
                        Message("impact.obs_changed", board=board)))
    if bool(old.get("needs_coords")) != bool(new.get("needs_coords")):
        out.append(item(Message("contract.coords_changed", board=board, old=old.get("needs_coords"),
                                new=new.get("needs_coords")),
                        Message("impact.coords_on" if new.get("needs_coords") else "impact.coords_off", board=board)))
    out += _anchors_diff(board, old.get("anchors") or {}, new.get("anchors") or {})
    if old.get("label") != new.get("label"):
        so = STAGE_RE.findall(str(old.get("label") or ""))
        sn = STAGE_RE.findall(str(new.get("label") or ""))
        if so != sn:
            out.append(item(Message("contract.stage_changed", board=board, old=Joined(so), new=Joined(sn)),
                            Message("impact.stage_changed", board=board)))
        out.append(item(Message("contract.field_changed", board=board, field="label", old=_val(old.get("label")),
                                new=_val(new.get("label")))))
    for f in sorted((set(old) | set(new)) - KNOWN_BOARD_FIELDS):
        if f not in new:
            out.append(item(Message("contract.field_removed", board=board, field=f, old=_val(old[f]))))
        elif f not in old:
            out.append(item(Message("contract.field_added", board=board, field=f, new=_val(new[f]))))
        elif old[f] != new[f]:
            out.append(item(Message("contract.field_changed", board=board, field=f, old=_val(old[f]),
                                    new=_val(new[f]))))
    return out


def _anchors_diff(board, old: dict, new: dict) -> list:
    out = []
    set_changed = False
    for m in sorted(set(old) | set(new)):
        o, n = old.get(m), new.get(m)
        if o == n:
            continue
        if o is None:
            set_changed = True
            n = n if isinstance(n, dict) else {}
            out.append(item(Message("contract.anchor_added", board=board, metric=m, floor=n.get("floor"),
                                    ceiling=n.get("ceiling"))))
        elif n is None:
            set_changed = True
            out.append(item(Message("contract.anchor_removed", board=board, metric=m)))
        else:
            o = o if isinstance(o, dict) else {"floor": o}
            n = n if isinstance(n, dict) else {"floor": n}
            out.append(item(Message("contract.anchors_changed", board=board, metric=m, old_floor=o.get("floor"),
                                    new_floor=n.get("floor"), old_ceiling=o.get("ceiling"),
                                    new_ceiling=n.get("ceiling")),
                            Message("impact.anchors_changed", board=board, metric=m)))
    if set_changed:
        out.append(item(Message("impact.anchor_set", board=board)))
    return out


def diff_index(old, new: dict, old_genes: dict, new_genes: dict, panels_dir: str) -> list:
    """old/new: parsed index.json (old None = first run). old_genes/new_genes: {genes_file: [genes]}."""
    out = []
    if old is None:
        out.append(item(Message("contract.baseline", n=len(new))))
        for board in sorted(new):
            spec = new[board]
            if isinstance(spec, dict):
                out.append(item(board_summary(board, spec)))
                out += genes_check(board, spec, new_genes.get(spec.get("genes_file")))
        return out
    for board in sorted(set(old) | set(new)):
        o, n = old.get(board), new.get(board)
        if o == n and (not isinstance(n, dict)
                       or old_genes.get(n.get("genes_file")) == new_genes.get(n.get("genes_file"))):
            continue
        if not isinstance(o, dict) or not isinstance(n, dict):
            if o is None and isinstance(n, dict):
                out.append(item(
                    Message("contract.board_added", board=board, label=n.get("label"), task=n.get("task"),
                            split=n.get("split"), n_genes=n.get("n_genes"), genes_file=n.get("genes_file"),
                            min_cells=n.get("min_cells"), max_cells=n.get("max_cells"), coords=_coords(n)),
                    Message("impact.board_added", board=board, n_genes=n.get("n_genes"),
                            min_cells=n.get("min_cells"), max_cells=n.get("max_cells"), coords=_coords(n),
                            panels_dir=panels_dir)))
                out += genes_check(board, n, new_genes.get(n.get("genes_file")))
            elif n is None and isinstance(o, dict):
                out.append(item(Message("contract.board_removed", board=board, label=o.get("label")),
                                Message("impact.board_removed", board=board)))
            elif n is None:
                out.append(item(Message("contract.field_removed", board="index.json", field=board, old=_val(o))))
            elif o is None:
                out.append(item(Message("contract.field_added", board="index.json", field=board, new=_val(n))))
            else:
                out.append(item(Message("contract.field_changed", board="index.json", field=board, old=_val(o),
                                        new=_val(n))))
            continue
        changes = diff_board(board, o, n, old_genes.get(o.get("genes_file")), new_genes.get(n.get("genes_file")))
        out += changes
        if changes:
            out += genes_check(board, n, new_genes.get(n.get("genes_file")))
    return out


# -- phase endpoint --

def diff_phase(old, new: dict) -> list:
    if not isinstance(new, dict):
        return [item(Message("phase.field_changed", field="(body)", old=_val(old), new=_val(new)))]
    if old is None:
        return [item(Message("phase.baseline", phase=new.get("phase"), label=new.get("label"), board=new.get("board"),
                             split=new.get("split"), daily_quota=new.get("daily_quota"),
                             accepts_submissions=new.get("accepts_submissions"),
                             nominations_open=new.get("nominations_open")))]
    old = old if isinstance(old, dict) else {}
    out = []
    if old.get("phase") != new.get("phase"):
        out.append(item(Message("phase.phase_changed", old=old.get("phase"), new=new.get("phase"),
                                label=_val(new.get("label"))),
                        Message("impact.phase_changed")))
    elif old.get("label") != new.get("label"):
        out.append(item(Message("phase.label_changed", old=_val(old.get("label")), new=_val(new.get("label")))))
    if old.get("board") != new.get("board"):
        out.append(item(Message("phase.board_changed", old=old.get("board"), new=new.get("board")),
                        Message("impact.board_changed", new=new.get("board"))))
    if old.get("daily_quota") != new.get("daily_quota"):
        out.append(item(Message("phase.quota_changed", old=old.get("daily_quota"), new=new.get("daily_quota")),
                        Message("impact.quota_changed")))
    for flag in PHASE_FLAGS:
        if flag in new and old.get(flag) != new.get(flag) and isinstance(new.get(flag), bool):
            out.append(item(Message(f"phase.{flag}.{'true' if new[flag] else 'false'}")))
        elif old.get(flag) != new.get(flag):
            out.append(item(Message("phase.field_changed", field=flag, old=_val(old.get(flag)),
                                    new=_val(new.get(flag)))))
    if old.get("split") != new.get("split"):
        out.append(item(Message("phase.split_changed", old=old.get("split"), new=new.get("split"))))
    if old.get("note") != new.get("note"):
        if new.get("note"):
            out.append(item(Message("phase.note_changed", new=_val(new.get("note")))))
        else:
            out.append(item(Message("phase.field_changed", field="note", old=_val(old.get("note")),
                                    new=_val(new.get("note")))))
    known = {"phase", "label", "board", "daily_quota", "split", "note", *PHASE_FLAGS}
    for f in sorted((set(old) | set(new)) - known):
        if old.get(f) != new.get(f):
            out.append(item(Message("phase.field_changed", field=f, old=_val(old.get(f)), new=_val(new.get(f)))))
    return out


# -- scorer (GitHub) --

def _short(sha) -> str:
    return (sha or "?")[:7]


def diff_scorer(old, new: dict, pinned: str) -> list:
    branch = new.get("default_branch")
    head = new.get("head") or {}
    if old is None:
        return [item(Message(
            "scorer.baseline", repo=new.get("repo"), branch=branch, sha=_short(head.get("sha")),
            date=head.get("date"), version=new.get("version"),
            tags=Joined(sorted(new.get("tags") or {})), releases=Joined(sorted(new.get("releases") or {})),
            branches=Joined(sorted(new.get("branches") or {}))))]
    out = []
    if old.get("default_branch") != branch:
        out.append(item(Message("scorer.default_branch_changed", old=old.get("default_branch"), new=branch)))
    old_head = old.get("head") or {}
    if old_head.get("sha") != head.get("sha"):
        out.append(item(Message("scorer.head_moved", branch=branch, old=_short(old_head.get("sha")),
                                new=_short(head.get("sha")), date=head.get("date"),
                                subject=excerpt(head.get("subject") or "")),
                        Message("impact.head_moved", pinned=pinned)))
    if old.get("version") != new.get("version"):
        out.append(item(Message("scorer.version_changed", branch=branch, old=old.get("version"),
                                new=new.get("version"))))
    ot, nt = old.get("tags") or {}, new.get("tags") or {}
    for t in sorted(set(ot) | set(nt)):
        if t not in ot:
            out.append(item(Message("scorer.tag_added", tag=t, sha=_short(nt[t]))))
        elif t not in nt:
            out.append(item(Message("scorer.tag_removed", tag=t, sha=_short(ot[t]))))
        elif ot[t] != nt[t]:
            out.append(item(Message("scorer.tag_moved", tag=t, old=_short(ot[t]), new=_short(nt[t]))))
    orl, nrl = old.get("releases") or {}, new.get("releases") or {}
    for t in sorted(set(orl) | set(nrl)):
        if t not in orl:
            r = nrl[t]
            out.append(item(Message("scorer.release_added", tag=t, name=excerpt(r.get("name") or t),
                                    published=r.get("published"),
                                    pre=Message("word.prerelease") if r.get("prerelease") else "")))
        elif t not in nrl:
            out.append(item(Message("scorer.release_removed", tag=t)))
    ob, nb = old.get("branches") or {}, new.get("branches") or {}
    for b in sorted(set(ob) | set(nb)):
        if b == branch and b in ob:
            continue                                 # the default branch head is reported above
        if b not in ob:
            out.append(item(Message("scorer.branch_added", branch=b, sha=_short(nb[b]))))
        elif b not in nb:
            out.append(item(Message("scorer.branch_removed", branch=b, sha=_short(ob[b]))))
        elif ob[b] != nb[b]:
            out.append(item(Message("scorer.branch_moved", branch=b, old=_short(ob[b]), new=_short(nb[b]))))
    return out
