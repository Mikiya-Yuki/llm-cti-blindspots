#!/usr/bin/env python3
"""Run the Phase A3 extension prompts (a3-1.0) on Claude: A3 (standard access) and Phase B.

This is scripts/run_claude.py v1.0 (used for A1) with the changes needed for A3 only:
the templates come from prompts_a3.md (tasks T3, T4, T5), 108 prompts are built, the shuffle
seed base is 20261122, the default is 2 runs, every record carries "set": "A3", and preflight
and run refuse to start unless the rendered prompts match prompt_manifest_a3.tsv.

Usage (from the repository root, with the `anthropic` package installed):
  python3 -I scripts/run_claude_a3.py dry-run   --out DIR
  python3 -I scripts/run_claude_a3.py preflight --out DIR --workspace Default
  python3 -I scripts/run_claude_a3.py run       --out DIR --workspace Default
                                      [--runs 1,2] [--workers 2] [--max-cost-usd 60] [--limit N]

dry-run   renders all 108 prompts and writes prompt_manifest_a3.tsv (hashes only). No API call.
preflight counts input tokens for all 108 prompts (count_tokens; not billed). No message is sent.
run       sends the prompts. Already completed calls are skipped, so an interrupted run can be resumed.

Rendering rule (part of the frozen materials)
  For each `### <lang>` block under `## T3 ...`, `## T4 ...` and `## T5 ...` in prompts_a3.md, the template is the
  text between the opening and closing ``` fence lines, without the fence lines themselves.
  The literal string {DOCUMENT} is replaced by the full text of inputs/<case>_input.txt (UTF-8),
  unchanged. Nothing else is substituted. The rendered prompt is the only user message; there is
  no system prompt.

Request settings (prompts.md v1.0, "Decoding and API settings"; unchanged for A3)
  model claude-opus-5-5, max_tokens 16000, output_config.effort "medium", streamed.
  Not sent: system, thinking, temperature, top_p, top_k, fallbacks.
  A response that stops at max_tokens gets one logged rerun with max_tokens 32000.
  Transient errors (HTTP 429, 5xx, connection) are retried with the identical request.
  A refusal is a result, not an error: it is never retried and the prompt is never changed.

Order
  Runs are done in sequence (run 1 for all 108 prompts, then run 2). Within a run the
  108 prompts are shuffled with random.Random(20261122 + run); the order is saved with the outputs.

Secrets and privacy
  The API key is read from the macOS keychain (service "anthropic-cvp-pilot", account $USER).
  It is never printed or written to disk. Raw outputs are private (protocol §11): publish
  aggregate counts only, never item-level information about which inputs triggered safeguards.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
RERUN_MAX_TOKENS = 32000
EFFORT = "medium"
PROMPT_VERSION = "a3-1.0"
PROMPT_SET = "A3"
N_PROMPTS = 108
TASKS = ("T3", "T4", "T5")
LANGS = ("en", "zh-Hans", "zh-Hant")
KEYCHAIN_SERVICE = "anthropic-cvp-pilot"
PRICE_IN, PRICE_OUT = 4.0, 20.0          # USD per million tokens, Claude Opus 5.5
PRICE_CACHE_WRITE, PRICE_CACHE_READ = 5.0, 0.20
SEED_BASE = 20261122
TRANSIENT_WAITS = (30, 90, 180)          # seconds between retries after the SDK's own retries


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_templates():
    text = (BASE / "prompts_a3.md").read_text(encoding="utf-8")
    templates, task, lang, buf = {}, None, None, None
    for line in text.split("\n"):
        if buf is not None:
            if line.startswith("```"):
                templates[(task, lang)] = "\n".join(buf)
                buf, lang = None, None
            else:
                buf.append(line)
        elif line.startswith("## "):
            m = re.match(r"## (T[345])\b", line)
            task, lang = (m.group(1) if m else None), None
        elif line.startswith("### ") and task:
            lang = line[4:].strip()
        elif line.startswith("```") and task and lang:
            buf = []
    wanted = {(t, l) for t in TASKS for l in LANGS}
    if set(templates) != wanted:
        sys.exit(f"prompts_a3.md: expected templates {sorted(wanted)}, found {sorted(templates)}")
    for key, tpl in templates.items():
        if tpl.count("{DOCUMENT}") != 1:
            sys.exit(f"prompts_a3.md: template {key} must contain {{DOCUMENT}} exactly once")
    return templates


def load_input_hashes():
    hashes = {}
    for line in (BASE / "inputs" / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            hashes[name.strip()] = digest
    return hashes


def build_items():
    templates = load_templates()
    expected = load_input_hashes()
    items = []
    with open(BASE / "case_table.csv", encoding="utf-8", newline="") as f:
        cases = [(r["case_id"], r["group"].split(" ")[0], r["stratum"]) for r in csv.DictReader(f)]
    for case_id, group, stratum in cases:
        name = f"{case_id.lower()}_input.txt"
        raw = (BASE / "inputs" / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected.get(name) != digest:
            sys.exit(f"inputs/{name} does not match inputs/SHA256SUMS.txt")
        doc = raw.decode("utf-8")
        for task in TASKS:
            for lang in LANGS:
                tpl = templates[(task, lang)]
                prompt = tpl.replace("{DOCUMENT}", doc)
                items.append({
                    "item_id": f"{case_id}_{task}_{lang}", "case_id": case_id, "group": group,
                    "stratum": stratum, "task": task, "lang": lang,
                    "template_sha256": sha256_text(tpl), "input_sha256": digest,
                    "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt), "prompt": prompt,
                })
    if len(items) != N_PROMPTS:
        sys.exit(f"expected {N_PROMPTS} prompts, built {len(items)}")
    return items


def check_manifest(items):
    """Refuse to send anything unless every rendered prompt matches prompt_manifest_a3.tsv."""
    path = BASE / "prompt_manifest_a3.tsv"
    if not path.exists():
        sys.exit("prompt_manifest_a3.tsv not found; the frozen manifest is required before any call")
    with open(path, encoding="utf-8", newline="") as f:
        frozen = {r["item_id"]: r["prompt_sha256"] for r in csv.DictReader(f, delimiter="\t")}
    built = {it["item_id"]: it["prompt_sha256"] for it in items}
    if frozen != built:
        bad = sorted(k for k in set(frozen) | set(built) if frozen.get(k) != built.get(k))
        sys.exit(f"rendered prompts differ from prompt_manifest_a3.tsv ({len(bad)} items, "
                 f"e.g. {bad[:3]}); nothing was sent")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def get_api_key():
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(f'No API key found in the macOS keychain (service "{KEYCHAIN_SERVICE}").')
    key = out.stdout.strip()
    if not key:
        sys.exit("The keychain entry is empty.")
    return key


def make_client():
    import anthropic
    return anthropic.Anthropic(api_key=get_api_key(), max_retries=6, timeout=900.0)


def environment(workspace):
    import anthropic
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "rerun_max_tokens": RERUN_MAX_TOKENS,
            "output_config": {"effort": EFFORT}, "not_sent": ["system", "thinking", "temperature",
            "top_p", "top_k", "fallbacks"], "streaming": True, "prompt_set": PROMPT_SET,
            "prompt_version": PROMPT_VERSION,
            "workspace": workspace, "sdk": f"anthropic-python {anthropic.__version__}",
            "python": platform.python_version(), "platform": platform.platform()}


def cost_of(usage):
    if not usage:
        return 0.0
    return ((usage.get("input_tokens") or 0) * PRICE_IN
            + (usage.get("output_tokens") or 0) * PRICE_OUT
            + (usage.get("cache_creation_input_tokens") or 0) * PRICE_CACHE_WRITE
            + (usage.get("cache_read_input_tokens") or 0) * PRICE_CACHE_READ) / 1e6


def completed(path):
    if not path.exists():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if rec.get("error") is None and (rec.get("response") or {}).get("stop_reason"):
        return rec
    return None


def send(client, prompt, max_tokens):
    """One streamed request; returns a dict with timestamps, the message and response headers."""
    import anthropic
    attempt = 0
    while True:
        started = now()
        try:
            with client.messages.stream(model=MODEL, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": prompt}],
                                        output_config={"effort": EFFORT}) as stream:
                msg = stream.get_final_message()
                return {"started_at": started, "finished_at": now(),
                        "request_id": stream.request_id,
                        "workspace_id": stream.workspace_id,
                        "response": msg.model_dump(mode="json")}
        except (anthropic.RateLimitError, anthropic.InternalServerError,
                anthropic.RequestTimeoutError, anthropic.APIConnectionError) as e:
            if attempt >= len(TRANSIENT_WAITS):
                raise
            print(f"  transient error ({type(e).__name__}); retrying the identical request "
                  f"in {TRANSIENT_WAITS[attempt]} s", flush=True)
            time.sleep(TRANSIENT_WAITS[attempt])
            attempt += 1


def error_info(e):
    info = {"type": type(e).__name__, "message": str(e)[:2000]}
    for attr in ("status_code", "request_id"):
        if getattr(e, attr, None) is not None:
            info[attr] = getattr(e, attr)
    return info


class Budget:
    def __init__(self, cap):
        self.cap, self.spent, self.lock = cap, 0.0, threading.Lock()

    def add(self, usage):
        with self.lock:
            self.spent += cost_of(usage)
            return self.spent


def do_item(client, item, run, position, outdir, workspace, stop, budget):
    path = outdir / f"run{run}" / f"{item['item_id']}.json"
    if stop.is_set():
        return
    rec = completed(path)
    if rec is None:
        rec = {"schema": "claude-call-v1", "set": PROMPT_SET, "item_id": item["item_id"],
               "case_id": item["case_id"], "task": item["task"], "lang": item["lang"],
               "run": run, "position": position, "workspace": workspace,
               "model_requested": MODEL, "max_tokens": MAX_TOKENS,
               "prompt_version": PROMPT_VERSION, "template_sha256": item["template_sha256"],
               "input_sha256": item["input_sha256"], "prompt_sha256": item["prompt_sha256"]}
        try:
            rec.update(send(client, item["prompt"], MAX_TOKENS), error=None)
        except Exception as e:  # anything else stops the whole run; nothing is resent
            rec.update(started_at=now(), error=error_info(e))
            write_json(path.with_suffix(".error.json"), rec)
            print(f"  ERROR on {item['item_id']} run {run}: {rec['error']['type']} - stopping",
                  flush=True)
            stop.set()
            return
        write_json(path, rec)
        spent = budget.add(rec["response"].get("usage"))
        print(f"  run {run} #{position:02d} {item['item_id']}: "
              f"{rec['response'].get('stop_reason')} (~${spent:.2f} so far)", flush=True)
    if rec["response"].get("stop_reason") == "max_tokens":
        rerun_path = path.with_suffix(".rerun.json")
        if not completed(rerun_path):
            base = {k: v for k, v in rec.items()
                    if k not in ("response", "request_id", "workspace_id", "started_at",
                                 "finished_at", "error")}
            rec2 = dict(base, max_tokens=RERUN_MAX_TOKENS, rerun_of=path.name)
            try:
                rec2.update(send(client, item["prompt"], RERUN_MAX_TOKENS), error=None)
                write_json(rerun_path, rec2)
                budget.add(rec2["response"].get("usage"))
            except Exception as e:
                rec2.update(error=error_info(e))
                write_json(rerun_path.with_suffix(".error.json"), rec2)
                stop.set()
    if budget.spent > budget.cap:
        print(f"  cost cap ${budget.cap:.2f} reached - stopping after the calls in progress",
              flush=True)
        stop.set()


def cmd_dry_run(args):
    items = build_items()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "prompt_manifest_a3.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["item_id", "case_id", "task", "lang", "template_sha256", "input_sha256",
                    "prompt_sha256", "prompt_chars"])
        for it in items:
            w.writerow([it[k] for k in ("item_id", "case_id", "task", "lang", "template_sha256",
                                        "input_sha256", "prompt_sha256", "prompt_chars")])
    sizes = [it["prompt_chars"] for it in items]
    print(f"{len(items)} prompts rendered (9 templates x 12 inputs); "
          f"{min(sizes)}-{max(sizes)} characters; no API call made.")
    print(f"wrote {out / 'prompt_manifest_a3.tsv'}")


def cmd_preflight(args):
    items = build_items()
    check_manifest(items)
    client = make_client()
    out = Path(args.out)
    counts = {}
    for it in items:
        r = client.messages.count_tokens(model=MODEL,
                                         messages=[{"role": "user", "content": it["prompt"]}])
        counts[it["item_id"]] = r.input_tokens
    toks = list(counts.values())
    write_json(out / "preflight_count_tokens.json",
               {"at": now(), "workspace": args.workspace, "model": MODEL,
                "input_tokens": counts, "min": min(toks), "max": max(toks), "total": sum(toks)})
    print(f"input tokens per prompt: {min(toks)}-{max(toks)}; total for one run: {sum(toks)}")
    est = sum(toks) * 2 * PRICE_IN / 1e6
    print(f"input cost for 2 runs: about ${est:.2f} (output tokens, including thinking, "
          f"come on top)")


def cmd_run(args):
    if args.workspace not in ("Default", "CVP"):
        sys.exit("--workspace must be Default or CVP")
    items = build_items()
    check_manifest(items)
    runs = [int(x) for x in args.runs.split(",")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        "sessions": []}
    meta["settings"] = environment(args.workspace)
    meta["sessions"].append({"started_at": now(), "runs": runs, "workers": args.workers,
                             "max_cost_usd": args.max_cost_usd, "limit": args.limit})
    write_json(meta_path, meta)
    budget = Budget(args.max_cost_usd)
    for p in out.glob("run*/*.json"):
        rec = completed(p)
        if rec:
            budget.add(rec["response"].get("usage"))
    print(f"already spent according to saved outputs: ~${budget.spent:.2f}")
    client = make_client()
    stop = threading.Event()
    for run in runs:
        order = list(items)
        random.Random(SEED_BASE + run).shuffle(order)
        if args.limit:
            order = order[:args.limit]
        write_json(out / f"run{run}" / "order.json",
                   {"run": run, "seed": SEED_BASE + run, "order": [it["item_id"] for it in order]})
        print(f"run {run}: {len(order)} prompts", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(do_item, client, it, run, pos, out, args.workspace, stop,
                                   budget) for pos, it in enumerate(order, 1)]
        for fut in futures:
            if fut.exception() is not None:
                print(f"  internal error: {fut.exception()!r} - stopping", flush=True)
                stop.set()
        if stop.is_set():
            print("stopped; rerun the same command to resume.")
            break
    meta["sessions"][-1]["finished_at"] = now()
    meta["sessions"][-1]["spent_usd_estimate"] = round(budget.spent, 2)
    write_json(meta_path, meta)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["dry-run", "preflight", "run"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--runs", default="1,2")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-cost-usd", type=float, default=60.0)
    ap.add_argument("--limit", type=int, default=0, help="only the first N prompts of each run")
    args = ap.parse_args()
    if args.command != "dry-run" and not args.workspace:
        sys.exit("--workspace is required (Default or CVP)")
    {"dry-run": cmd_dry_run, "preflight": cmd_preflight, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    main()
