You are running the ideas pass over notes in Marco's brain (~/Projects/brain).

Read these first, fully, and follow them exactly:
1. ~/Projects/video-notes-app/docs/ideas.md — the complete rules (what an idea is, matching, counting sources, note format, tone).
2. ~/Projects/brain/AGENTS.md — the brain's rules.
3. ~/Projects/brain/Resources/commonplace/commonplace.md — themes and topic tags.
4. ~/Projects/brain/System/templates/idea-note.md — the idea note template.
5. Every idea note's front matter and title in ~/Projects/brain/Inbox/ideas/.

The notes to consider in this pass are these {{count}} (post id, then note path relative to ~/Projects/brain):
{{notes}}

{{mode}}

Today's date is {{today}}.

Write and update only files in {{ideas_dir}}. Create at most {{max_new}} new ideas in this pass. Do NOT run brain-index or git: the app indexes and commits after the pass. Never write in a "## My notes" section. Never read ~/Private, ~/.local/share/chat-vault or any other path the global rules forbid.

When finished, return the report in the requested JSON format: the idea files you created, the idea files you updated, and the post ids you considered (including those that gave no idea; leave out only notes held back by the {{max_new}}-new-ideas limit).
