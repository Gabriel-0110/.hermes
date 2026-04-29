# iMessage Delivery Failure — 2026-04-29

**Time:** 2026-04-29T02:37Z (approx)
**Task:** weekly-investor-report-delivery
**Report:** investor-weekly-latest.md

## What Happened

The weekly investor report was read successfully but iMessage delivery failed for both recipients:
- +19295997269
- +19297153656 (Gabe)

## Root Cause

Neither phone number is on the iMessage allowlist. The `claude --channels plugin:imessage` session confirmed both sends failed with the message:
> "Both sends failed — neither `+19295997269` nor `+19297153656` (Gabe) are on the iMessage allowlist."

## Fix Required

Run `/imessage:access` in the terminal to approve both numbers, then retry delivery.

The report is saved at:
- `/Users/openclaw/.hermes/shared/reports/investor-weekly-latest.md`
- `/tmp/hermes-weekly-report.txt` (temp copy ready to send)
