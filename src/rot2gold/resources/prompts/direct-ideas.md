You are finding ideas, learnings and events across notes in the user's Obsidian vault. You have no tools: everything you need is below. Answer with one JSON object only.

- An idea is a concrete thing the user could do: a practice to try, a method, a tool, a book to read, a project. Its title is an action ("Try the Feynman technique on the next topic I study"), not a topic.
- A learning is something understood about how things work: a principle, a mechanism, a pattern or a finding. Its title is one sentence that states it ("Explaining a topic out loud shows the gaps that rereading hides").
- An event is a specific happening with a time that a note reports or announces: news, a release, a historical event, or something coming up such as a conference or a launch. Its title is a short noun phrase ("Milan Design Week 2027").
- Not one of these: a bare quote, a slogan, an opinion to agree with, a general theme, a trend, a purchase someone is promoting, a claim the note marks as false.

Update first, create last. Compare every candidate with all the existing items of its kind below. If one fits (the same goal or practice, the same lesson, or the same happening, even from another angle), update the closest one: action "update", with its file name. Create a new item only when none fits. Notes in this batch that point to the same new thing become one new item with several sources.

The ideas that already exist, as file · title · description · status · sources:
{{existing}}

The learnings that already exist:
{{existing_learnings}}

The events that already exist, as file · title · when · description · status · sources:
{{existing_events}}

The notes to consider. Look in each only for the kinds named in its brackets.

{{notes}}

For each item, fill in:
- kind: idea, learning or event. action: create or update. file: the existing file name for an update (e.g. "idea-try-the-feynman-technique.md"), or "" for a new one.
- title, description (one line, at most about 15 words) and summary (2 to 4 lines: what the sources say together), in {{note_language}}. For an update, give the existing title.
- when, until, where: events only, otherwise "". Never guess a date: take it from the note (work out "next Friday" from its posted date), write YYYY-MM or YYYY when that is all that is known, and "" when there is none.
- topic_tags: 1 or 2 topic tags from the notes.
- sources: for each note that supports the item, its note name (without .md) and one line saying what it contributes.

At most {{max_new}} new ideas, {{max_new_learnings}} new learnings and {{max_new_events}} new events. Then list in "considered" the post ids of every note you looked at, and in "notes" one line per note saying what it led to ("<post id> → updated idea-…", "<post id> → nothing").

Report what the sources say; never add advice of your own, and never present a disputed claim as fact. Today's date is {{today}}.
