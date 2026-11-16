You are fact-checking a YouTube title/description draft against the video's own subtitles (Tanglish, romanized).
The subtitles are the ONLY source of truth. Flag anything in the draft that:
1. states a fact, claim, number, name, or technical detail that is not said in the subtitles (e.g. "root access" when the speaker only said they got access),
2. attributes something to the wrong system or party (e.g. calling a bug on a forum server a "ChatGPT RCE"),
3. uses a technical term incorrectly (e.g. "transient dependency" where "transitive dependency" is meant),
4. contradicts the subtitles, or
5. has a timestamp that does not match where that topic starts in the subtitles (allow +-10 s).
Also list anything the speaker explicitly promises will be in the description (e.g. "full names description-la potruken") that is missing from the draft.

Do not flag style, tone, keyword choices or clickbait unless it is factually wrong.
Return ONLY a JSON object:
{"issues": [{"quote": "exact text from the draft", "problem": "what is wrong", "fix": "suggested replacement"}],
 "missing_promises": ["..."]}

=== DRAFT ===
{DRAFT}

=== SUBTITLES ===
{SRT}
