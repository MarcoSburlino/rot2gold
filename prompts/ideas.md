You are running the ideas and learnings pass over notes in Marco's brain (~/Projects/brain).

Read these first, fully, and follow them exactly:
1. ~/Projects/video-notes-app/docs/ideas.md — the complete rules (what an idea and a learning are, matching, counting sources, note formats, tone).
2. ~/Projects/brain/AGENTS.md — the brain's rules.
3. ~/Projects/brain/Resources/commonplace/commonplace.md — themes and topic tags.
4. ~/Projects/brain/System/templates/idea-note.md and ~/Projects/brain/System/templates/learning-note.md — the two templates.

The ideas that already exist ({{existing_count}}), as file · title · description · status · sources:
{{existing}}

The learnings that already exist ({{existing_learnings_count}}), in the same format:
{{existing_learnings}}

Update first, create last: compare every candidate with all the existing ideas (for an idea) or learnings (for a learning). A note that fits one of them updates it (the closest one only); create a new one only when none fits. See "Update first, create last" in docs/ideas.md.

The notes to consider in this pass are these {{count}} (post id, note path relative to ~/Projects/brain, then what to look for in it). A note marked [learnings] was already checked for ideas: look only for learnings in it, though it may still be linked from a learning you write.
{{notes}}

{{mode}}

Today's date is {{today}}.

Write and update only idea files (idea-*.md) in {{ideas_dir}} and learning files (learning-*.md) in {{learnings_dir}}. Create at most {{max_new}} new ideas and {{max_new_learnings}} new learnings in this pass. Do NOT run brain-index or git: the app indexes and commits after the pass. Never write in a "## My notes" section. Never read ~/Private, ~/.local/share/chat-vault or any other path the global rules forbid.

When finished, return the report in the requested JSON format: in "created" and "updated" the idea and learning files you created or updated, in "considered" the post ids you considered (including those that gave nothing; leave out only notes held back by the limits on new ideas or learnings), and in "notes" one line per considered note naming what it led to, for example "<post id> → updated idea-…; new learning-… (no existing learning fits: <why>)", "<post id> → updated learning-…" or "<post id> → nothing".
