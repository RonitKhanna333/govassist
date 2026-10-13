"""Phone calls: a third channel onto the same conversation as /chat.

The web UI and the phone agent ask the same questions, from the same
`scheme.md` rules, and the verdict comes from the same rule engine. What
differs is only who speaks: on a call, a third-party voice platform (Bland
AI) runs the audio, and this package tells it what to ask and reads back
what it heard.

Two rules make a phone channel safe for this project, and both are enforced
here rather than left to a prompt:

* The call collects answers and nothing else. It never tells the person
  whether they qualify -- `script.py` says so in the instructions, and the
  verdict is computed in `api/routers/voice.py` by `decide()` after the
  call, exactly as it is for the web UI.
* An answer is only recorded if our own deterministic parser recognises it
  (`api/rules/spoken.py`). A phone line is 8 kHz audio and mishearing
  "chalis" (40) as "chaalees"/14 would flip a verdict, so a value the
  parser cannot read is left unknown instead of guessed.
"""
