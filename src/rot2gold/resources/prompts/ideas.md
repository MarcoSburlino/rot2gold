You are running the ideas, learnings and events pass over the video notes in the user's Obsidian vault, for Rot2Gold.

Read these first, fully, and follow them exactly:
1. {{rules}}/ideas.md — the complete rules (what an idea, a learning and an event are, matching, counting sources, note formats, tone).
2. {{rules}}/vault-rules.md — the rules for writing in the vault.{{user_rules}}
3. The hub note — themes and topic tags.
4. idea-note.md, learning-note.md and event-note.md in the templates folder — the three templates.

{{where}}

Write in {{note_language}}; quotes from a source stay in their original language.

The ideas that already exist ({{existing_count}}), as file · title · description · status · sources:
{{existing}}

The learnings that already exist ({{existing_learnings_count}}), in the same format:
{{existing_learnings}}

The events that already exist ({{existing_events_count}}), as file · title · when · description · status · sources:
{{existing_events}}

Update first, create last: compare every candidate with all the existing items of its kind. A note that fits one of them updates it (the closest one only); create a new one only when none fits. For an event, it fits when it is the same happening (the same thing, at the same time and place), whatever name the video gives it. See "Update first, create last" in the rules.

The notes to consider in this pass are these {{count}} (post id, note path relative to the vault, then what to look for in it). Look in each note only for the kinds named in its brackets: the others were already checked. It may still be linked from an item you write.
{{notes}}

{{mode}}

Today's date is {{today}}.

Write and update only idea files (idea-*.md) in {{ideas_dir}}, learning files (learning-*.md) in {{learnings_dir}} and event files (event-*.md) in {{events_dir}}. Create at most {{max_new}} new ideas, {{max_new_learnings}} new learnings and {{max_new_events}} new events in this pass. Never guess an event's date: take it from the note (resolving "next Friday" from its `posted:` date), keep it partial (YYYY-MM or YYYY) when that is all that is known, and leave `when:` empty when there is none. Do NOT run git or any indexing command: the app does that after the pass. Never write in a "## My notes" section. Never read outside the vault and the folders named above.

When finished, return the report in the requested JSON format: in "created" and "updated" the idea, learning and event files you created or updated, in "considered" the post ids you considered (including those that gave nothing; leave out only notes held back by the limits on new items), and in "notes" one line per considered note naming what it led to, for example "<post id> → updated idea-…; new learning-… (no existing learning fits: <why>)", "<post id> → new event-… (2026-11-12, Milan)" or "<post id> → nothing".
