# Known Limitations

None of these are blockers; they are the rough edges to keep in mind when reading the numbers.

## Skills Token Counts Are Partial

The Skills route shows skill invocations when they appear as tool calls and can enrich them from local `SKILL.md` files under `~/.codex/skills` and `~/.codex/plugins`. If a skill is loaded through another mechanism or a slug cannot be matched to disk, invocation counts may still appear while `tokens_per_call` stays blank.

## Cost Is API-Equivalent

Codex is often used through a ChatGPT subscription or entitlement. The Overview cost number estimates what the same token volume would cost at API rates from `pricing.json`; it is not a statement that you were billed that amount.

## Internal Model Slugs Need Pricing Overrides

Codex may log internal or product-specific model IDs such as review models. If a model is not listed in `pricing.json`, the dashboard falls back to a broad tier inferred from the model name and marks the cost as estimated. Add exact rates to `pricing.json` when you need precise accounting.

## Some Server-Side Or Cloud Sessions May Be Invisible

The scanner reads local JSONL files under `~/.codex/sessions`. Work that does not write local rollout files cannot be shown.

## First Scan Can Be Slow

The first scan on a heavy machine can read many JSONL files. Subsequent scans are incremental using mtime and byte-offset tracking in the `files` table.

## Run One Dashboard Per DB

Two dashboard processes pointed at the same SQLite file can fight over writes. Run one server per DB. If you need access from another device, start one process with an intentional `HOST` override on a trusted network.
