You are writing notes in Marco's brain (~/Projects/brain) for posts from his saved collections, processed by the pipeline in ~/Projects/video-notes-app.

Read these first, fully, and follow them exactly:
1. ~/Projects/video-notes-app/docs/note-writing.md — the complete instructions (note format, cleanup rules, references, hub and quotes updates, vn done/skip).
2. ~/Projects/brain/AGENTS.md — the brain's rules (especially "Writing notes" and "Commonplace").
3. ~/Projects/brain/Resources/commonplace/commonplace.md and quotes.md — current themes and topic tags.
4. Two finished example notes to match in tone, depth and format: ~/Projects/brain/Resources/commonplace/videos/video-anthropics-three-ai-scenarios-for-the-economy-by-2030.md and ~/Projects/brain/Resources/commonplace/videos/video-feeding-your-mind-the-big-truth.md

Your batch is exactly these {{count}} post ids. Process only these:
{{ids}}

Get each post's data with `vn pending --id <id>` (it prints OCR text with confidence, image paths and the transcript). Always open the video frame image with your Read tool, and slide images when the guide says so. Use WebSearch/WebFetch for the "Checked" claims and link only sources you actually opened. Today's date is {{today}}.

For each post, finish it completely before starting the next: write the note, update quotes.md and commonplace.md (themes and the topic tags list), then run `vn done <id> Resources/commonplace/videos/video-<slug>.md`, or `vn skip <id> "<reason>"` if the content is useless.

Do NOT write idea notes or touch ~/Projects/brain/Inbox: a separate ideas pass does that. Do NOT run brain-index or git: the app indexes and commits after your batch. Don't edit any other existing brain notes, and never write in a "## My notes" section.

When finished, return the report in the requested JSON format: for each id, the note path or the skip reason; topic tags you created; claims you rated "disputed" (one line each, with the note name); and problems (bad OCR, unclear audio, language issues, anything you could not do).
