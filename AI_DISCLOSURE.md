# AI disclosure

GraphHacks rule 11: "AI coding assistants are allowed, but their use must be disclosed."

## What the AI assistant did

I used **Claude (Anthropic)** throughout this project, in a chat session, on 16–17 October 2026 (after the hackathon opened).

- **Research:** a survey of existing agent-memory systems and open problems, used to choose the problem.
- **Design documents:** SETUP, Mem, EXT, TRU, AGT, SCN, API, MCP, TEN, EVL, DEP and SUB `.md` files, each with a design and an implementation plan.
- **Code:** the AI wrote **most of the code in this repository**, including the memory core and every Cypher query, extraction, trust and revocation, agents, the API and console, the MCP server, the benchmark, the evaluation, the deployment files and the tests. It ran the tests in its own sandbox against embedded FalkorDB.
- **Bugs:** it found and reported several bugs in its own earlier code, with tested fixes.

## What I did

<!-- Be specific and truthful. Judges may ask you to show or explain any of this.
     Delete lines that aren't true; add what is. Examples of the kind of thing to list:
     - chose the track, the problem and the scope after reviewing the research
     - decided which proposed fixes to apply and applied them myself (which ones)
     - ran the system with live Gemini and fixed what broke (what broke, how)
     - tuned the extraction prompt / aliases against real model output
     - wrote <feature or fix> myself (link the commit)
     - deployed it (which mode, what I had to change)
     - recorded the demo, wrote this README's narrative and the blog post -->

- TODO(you)

## Verification

<!-- What you personally ran and checked, e.g. "ran pytest locally: N passed", "ran smoke.py --full against the live URL", "reran the benchmark against FalkorDB 6.x: numbers in README". -->

- TODO(you)

## Understanding

I can explain the graph model, every query in the README, the architecture and the main technical decisions. <!-- Only keep this line once it's true: see SUB.md §3. -->
