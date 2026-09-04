# DVIZH Social Hub v1

Social Hub keeps content work separate from ordinary tasks while reusing the same account, Telegram bot, weekly schedule and server state.

## Core flow

`idea → script → record → edit → scheduled → published`

A material stores its platform, format, title, fear level, courage step, minimum and normal outcome, planned publication time, reminder, notes, publication URL and post-publication reflection.

## Telegram

- `/social` opens the dashboard.
- `/idea <text>` captures an idea without demanding immediate production.
- “Next step” chooses one small action from the current pipeline stage.
- The courage ladder logs fear before and after a safe exposure step.

## Web

The Social Hub page supports creating and editing materials, moving them through the pipeline, scheduling publication, recording a link and reflection, and managing reaction-check windows.

## Week integration

A scheduled material creates one `social` schedule item and occurrence in the common weekly calendar. Completing that occurrence publishes the matching material. Archiving, deleting or unscheduling the material removes the pending calendar projection without erasing completed history.

## Defaults

- Weekly publication goal: 2.
- Courage level: 1 of 5.
- Reaction-check windows: 13:00 and 20:00.

All defaults are editable. Social Hub records workflow and exposure practice; it does not promise audience growth or replace moderation and personal safety decisions.
