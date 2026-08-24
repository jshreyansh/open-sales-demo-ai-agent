"""Regression tests for interruption granularity (production issue #1).

Background (real call 66da2724, 2026-08-24): the prospect talked over the
agent five separate times, and every single cutoff landed at a COMPLETE
sentence boundary — never mid-word, never even mid-clause. Traced the whole
interruption path (VAD config, our own broadcast_interruption() call,
Cartesia's own interruption handler, the output transport's audio-queue
reset, Pipecat's SystemFrame priority queue) and every layer is architected
for near-instant interruption. The one thing NOT fast is cancelling Cartesia
itself: that needs a round trip to Cartesia's own server, and for a short
sentence, Cartesia can finish generating and streaming the whole thing
before that cancel has a chance to land — so the interruption arrives with
nothing left to cancel.

Fix: hand TTS smaller pieces than a whole sentence (clause-level, split on
natural pause punctuation), so the same interrupt-check-between-pieces loop
that already existed for "between sentences" now also runs "between
clauses" — bounding the worst case to one clause, not one sentence.
Deliberately does not change what gets RECORDED as heard: a sentence stays
the unit of record for _spoken_parts/_cut_off_part (see
_amend_interrupted_turn's "repeat it whole rather than guess where inside
it the cut landed"), only the unit of DISPATCH to TTS got finer.
"""
from __future__ import annotations

import asyncio

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import AgentRuntimeProcessor, _split_speech_chunks


async def _events(*items):
    for item in items:
        yield item


# --- Unit tests on the splitter itself --------------------------------------


def test_split_speech_chunks_splits_on_natural_pauses():
    assert _split_speech_chunks(
        "That's a real pain — work getting misplaced between agency and in-house teams."
    ) == [
        "That's a real pain —",
        "work getting misplaced between agency and in-house teams.",
    ]


def test_split_speech_chunks_splits_on_commas_too():
    assert _split_speech_chunks("Yeah, that's a fair one, nobody wants that.") == [
        "Yeah,",
        "that's a fair one,",
        "nobody wants that.",
    ]


def test_split_speech_chunks_leaves_a_short_sentence_whole():
    assert _split_speech_chunks("Sure. Why not") == ["Sure. Why not"]


def test_split_speech_chunks_does_not_split_grouped_numbers():
    # A comma with no following space (digit grouping) must not split --
    # real prose punctuation is always followed by whitespace.
    assert _split_speech_chunks("We generated 1,284 assets this week.") == [
        "We generated 1,284 assets this week."
    ]


def test_split_speech_chunks_never_returns_empty():
    assert _split_speech_chunks("") == [""]
    assert _split_speech_chunks("   ") == ["   "]


# --- _speak_reply (non-streaming path) --------------------------------------


def test_speak_reply_dispatches_each_clause_as_its_own_speak_call():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-chunk-granularity")
        calls = []

        async def _speak(text, direction):
            calls.append(text)
            agent._speech_finished.set()

        agent._speak = _speak
        sentence = "That's a real pain — work getting misplaced between agency and in-house teams."
        await agent._speak_reply(sentence, FrameDirection.DOWNSTREAM)

        assert calls == [
            "That's a real pain —",
            "work getting misplaced between agency and in-house teams.",
        ], f"expected two smaller _speak() calls, got {calls}"
        # Bookkeeping stays sentence-granular even though dispatch is finer.
        assert agent._spoken_parts == [sentence]

    asyncio.run(_run())


def test_speak_reply_stops_within_the_sentence_not_after_the_whole_thing():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-chunk-interrupt")
        calls = []

        async def _speak(text, direction):
            calls.append(text)
            agent._speech_finished.set()
            if len(calls) == 1:
                # Simulate a barge-in landing right after the first clause.
                agent._interrupted_this_turn = True

        agent._speak = _speak
        sentence = "That's a real pain — work getting misplaced between agency and in-house teams."
        await agent._speak_reply(sentence, FrameDirection.DOWNSTREAM)

        assert calls == ["That's a real pain —"], (
            f"spoke past the interruption instead of stopping within the sentence: {calls}"
        )
        # Record-keeping is unchanged: the whole sentence is the cut-off unit.
        assert agent._cut_off_part == sentence
        assert agent._spoken_parts == []

    asyncio.run(_run())


def test_speak_reply_unaffected_for_a_sentence_with_no_natural_pauses():
    """A sentence with nothing to split on behaves exactly as before —
    single _speak() call, normal bookkeeping."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-chunk-no-split")
        calls = []

        async def _speak(text, direction):
            calls.append(text)
            agent._speech_finished.set()

        agent._speak = _speak
        await agent._speak_reply("Nobody wants another tool to learn.", FrameDirection.DOWNSTREAM)

        assert calls == ["Nobody wants another tool to learn."]
        assert agent._spoken_parts == ["Nobody wants another tool to learn."]

    asyncio.run(_run())


# --- _flush_ready_sentences (the real streaming path most turns take) ------


def test_streaming_reply_stops_within_the_sentence_not_after_the_whole_thing():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-stream-chunk-interrupt")
        calls = []

        async def _speak(text, direction):
            calls.append(text)
            agent._speech_finished.set()
            if len(calls) == 1:
                agent._interrupted_this_turn = True

        agent._speak = _speak
        sentence = "That's a real pain — work getting misplaced between agency and in-house teams."
        stream = _events(
            ("reply_delta", sentence + " "),
            ("done_streamed", {"reply": sentence, "action": None}),
        )
        await agent._consume_turn_stream(stream, FrameDirection.DOWNSTREAM)

        assert calls == ["That's a real pain —"], (
            f"spoke past the interruption instead of stopping within the sentence: {calls}"
        )
        assert agent._cut_off_part == sentence
        assert agent._spoken_parts == []

    asyncio.run(_run())


def test_streaming_reply_speaks_every_clause_when_not_interrupted():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-stream-chunk-clean")
        calls = []

        async def _speak(text, direction):
            calls.append(text)
            agent._speech_finished.set()

        agent._speak = _speak
        sentence = "Yeah, that's a fair one, nobody wants that."
        stream = _events(
            ("reply_delta", sentence + " "),
            ("done_streamed", {"reply": sentence, "action": None}),
        )
        await agent._consume_turn_stream(stream, FrameDirection.DOWNSTREAM)

        assert calls == ["Yeah,", "that's a fair one,", "nobody wants that."]
        assert agent._spoken_parts == [sentence]

    asyncio.run(_run())
