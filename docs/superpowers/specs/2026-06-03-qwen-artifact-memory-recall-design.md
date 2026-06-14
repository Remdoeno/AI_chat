# Qwen Artifact Memory, Timeline, and Active Recall Design

## Scope
Improve the existing Qwen web app without merging the memory editor and artifacts pages. `/memory-admin` remains the long-term memory editor. `/artifacts` remains the idle-agent output page. Idle-agent作品 will also create concise long-term memories with an artifact/work label so the chat agent can remember its own creative work.

## Artifact Memories
When `save_idle_agent_artifact` stores an artifact, the backend creates or updates a concise curated memory labeled `artifact`. The memory contains series/title/type/progress summary, not full artifact text. This memory appears in memory lists and participates in normal retrieval.

## Serialized Hero Series
The idle-agent prompt includes a non-exclusive creative seed for a superhero serial featuring 闪光超人, BenMan, 绿手侠, Mr.H, Cora, and Discoman. The agent may continue this series during idle time but is not forced to write it every run. Artifacts can carry `series_title` and `episode_index` metadata for filtering and ordering.

## Timeline Memory
Curated memories gain timeline metadata: `timeline_at`, `supersedes_id`, and `confidence`. Memory prompts explicitly state that newer/confident memories should be preferred when older memories conflict. Memory-agent prompts ask the model to mark conflicts and avoid preserving duplicate stale facts.

## Active Recall
Before building the chat prompt, the backend detects explicit recall requests such as “回忆我们之间比较难忘的一件事”. These requests add an active-recall context built from recent curated memories, artifact memories, and timeline entries. This supplements embedding retrieval rather than replacing it.

## Testing
Add backend tests for artifact memory creation, hero seed prompt inclusion, timeline fields/listing, timeline-aware prompt formatting, and active recall trigger/context injection. Run full tests and restart service.
