---
name: telegram-group-delivery-check
description: Verify whether Hermes can deliver messages into a specific Telegram group or topic, and diagnose failures like Chat not found.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Telegram, messaging, delivery, troubleshooting]
---

# Telegram group delivery check

Use this when a user wants Hermes to continue a conversation in a Telegram group, supergroup, or topic and you need to confirm whether delivery actually works.

## Goal

Determine whether Hermes can post into the requested Telegram destination, including plain non-reply messages.

## Preferred test method

Use a one-shot `cronjob` targeting the exact Telegram destination.

Why:
- `cronjob` records `last_delivery_error`
- you can inspect the delivery result afterward
- this is better than assuming a send worked just because job creation succeeded

## Target formats

- Group/supergroup: `telegram:-100...`
- Topic/thread inside a Telegram supergroup: `telegram:-100...:<thread_id>`

If the user gives a `t.me/c/.../...` link, the final path segment is often the topic or thread identifier to try as `:<thread_id>`.

## Workflow

1. Create a tiny one-shot cron job.
   - Use a plain final response like:
     `Hermes permission test: plain group message without mention.`
   - Explicitly avoid mentions/replies if that is what the user wants tested.

2. Run the cron job immediately.
   - Use `cronjob(action='run', job_id=...)`

3. Inspect the result.
   - Use `cronjob(action='list')`
   - Check:
     - `last_status`
     - `last_delivery_error`

4. If needed, try both forms:
   - chat only: `telegram:-100...`
   - chat + topic: `telegram:-100...:<thread_id>`

5. Clean up the test cron jobs.
   - Remove them after inspection.

## Interpreting failures

### `Telegram send failed: Chat not found`
Treat this as a hard access/reachability failure for the connected Telegram integration.

Most likely causes:
- the bot/account behind Hermes is not in the group
- it was removed from the group
- the chat ID is wrong for the connected integration
- a topic/thread target is wrong

Do not describe this as a mention/reply issue. If the chat is not found, Hermes cannot reach the destination at all.

## What to tell the user

If `Chat not found` occurs, explain that Hermes currently cannot post there yet, and ask the user to:
- add the Hermes/connected Telegram bot or account to the group
- confirm it has permission to post
- then message again from that group so you can retest

## Pitfalls

- Creating or manually triggering a cron job is not proof of successful delivery by itself.
- Always inspect `last_delivery_error` after the run.
- A thread/topic ID from a link may still be wrong for delivery; test both with and without the topic suffix when needed.
