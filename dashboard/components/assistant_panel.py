from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from src.services.assistant_service import AssistantReply, answer_question, starter_prompts_for_page, submit_feedback
from src.utils.text_normalization import normalize_page_scope


SOURCE_LABELS = {
    "exact_cache": "Cached Answer",
    "semantic_cache": "Similar Answer",
    "knowledge": "Knowledge Base",
    "hybrid": "Hybrid",
    "llm": "AI Generated",
    "clarifying": "Clarification",
}


def _inject_assistant_css() -> None:
    st.markdown(
        """
        <style>
        .assistant-page-badge {
            display:inline-flex;
            align-items:center;
            gap:0.35rem;
            padding:0.32rem 0.58rem;
            border-radius:999px;
            border:1px solid rgba(255,255,255,0.10);
            background:rgba(255,255,255,0.04);
            color:#C4B5FD;
            font-size:10px;
            text-transform:uppercase;
            letter-spacing:0.08em;
            margin-bottom:0.55rem;
        }
        .assistant-thread {
            display:grid;
            gap:0.45rem;
            margin:0.6rem 0 0.7rem;
        }
        .assistant-bubble {
            border-radius:16px;
            padding:0.65rem 0.78rem;
            font-size:12px;
            line-height:1.5;
            border:1px solid rgba(255,255,255,0.08);
        }
        .assistant-bubble-user {
            background:rgba(255,255,255,0.04);
            color:#F7F8FC;
        }
        .assistant-bubble-assistant {
            background:linear-gradient(180deg, rgba(26,33,64,0.96) 0%, rgba(15,19,36,0.98) 100%);
            color:#E8ECF9;
        }
        .assistant-answer-card {
            border-radius:18px;
            border:1px solid rgba(255,255,255,0.08);
            background:linear-gradient(180deg, rgba(26,33,64,0.98) 0%, rgba(15,19,36,0.99) 100%);
            box-shadow:0 16px 36px rgba(3,6,20,0.34);
            padding:0.85rem 0.9rem;
            margin-top:0.5rem;
        }
        .assistant-answer-meta {
            display:flex;
            flex-wrap:wrap;
            gap:0.45rem;
            margin-bottom:0.6rem;
        }
        .assistant-badge {
            display:inline-flex;
            align-items:center;
            padding:0.22rem 0.52rem;
            border-radius:999px;
            background:rgba(139,92,246,0.12);
            border:1px solid rgba(196,181,253,0.16);
            color:#F7F8FC;
            font-size:10px;
            font-weight:700;
            letter-spacing:0.04em;
            text-transform:uppercase;
        }
        .assistant-badge-muted {
            background:rgba(255,255,255,0.04);
            border-color:rgba(255,255,255,0.08);
            color:#B8C1DA;
        }
        .assistant-answer-copy {
            color:#E8ECF9;
            font-size:12px;
            line-height:1.58;
        }
        .assistant-source-list {
            display:grid;
            gap:0.45rem;
            margin-top:0.45rem;
        }
        .assistant-source-item {
            border-radius:14px;
            border:1px solid rgba(255,255,255,0.07);
            background:rgba(255,255,255,0.03);
            padding:0.6rem 0.7rem;
        }
        .assistant-source-title {
            color:#F7F8FC;
            font-size:12px;
            font-weight:700;
            margin-bottom:0.12rem;
        }
        .assistant-source-label {
            color:#A5B4FC;
            font-size:10px;
            text-transform:uppercase;
            letter-spacing:0.08em;
            margin-bottom:0.28rem;
        }
        .assistant-source-excerpt {
            color:#B8C1DA;
            font-size:11px;
            line-height:1.45;
        }
        .assistant-notice {
            margin-top:0.55rem;
            font-size:11px;
            color:#B8C1DA;
            line-height:1.45;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _append_message(role: str, content: str) -> None:
    messages = list(st.session_state.get("assistant_messages", []))
    messages.append({"role": role, "content": content})
    st.session_state["assistant_messages"] = messages[-12:]


def _handle_question(question: str, page_scope: str) -> None:
    query = str(question or "").strip()
    if not query:
        return
    with st.spinner("Working on it..."):
        reply = answer_question(
            query,
            page_scope=page_scope,
            session_state=st.session_state,
            history=st.session_state.get("assistant_messages", []),
        )
    _append_message("user", query)
    _append_message("assistant", reply.answer_text)
    st.session_state["assistant_last_reply"] = reply
    st.session_state["assistant_last_page_scope"] = page_scope
    st.session_state["assistant_query_input"] = ""


def _render_thread() -> None:
    messages = st.session_state.get("assistant_messages", [])
    if not messages:
        return
    st.markdown("<div class='assistant-thread'>", unsafe_allow_html=True)
    for item in messages[-6:]:
        role = "assistant" if item.get("role") == "assistant" else "user"
        bubble_class = "assistant-bubble-assistant" if role == "assistant" else "assistant-bubble-user"
        st.markdown(
            f"<div class='assistant-bubble {bubble_class}'>{escape(str(item.get('content', '')))}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_related_questions(reply: AssistantReply, page_scope: str) -> None:
    if not reply.related_questions:
        return
    st.caption("Related Questions")
    columns = st.columns(1 if len(reply.related_questions) == 1 else 2)
    for index, prompt in enumerate(reply.related_questions):
        with columns[index % len(columns)]:
            if st.button(prompt, key=f"assistant_related_{reply.answer_id}_{index}", use_container_width=True):
                _handle_question(prompt, page_scope)
                st.rerun()


def _render_feedback(reply: AssistantReply, page_scope: str) -> None:
    if reply.answer_id is None:
        return
    feedback_cols = st.columns(2)
    with feedback_cols[0]:
        if st.button("Helpful", key=f"assistant_helpful_{reply.answer_id}", use_container_width=True):
            submit_feedback(reply.answer_id, "helpful", page_scope)
            st.session_state["assistant_feedback_note"] = "Thanks — I’ll prioritize answers like this one."
            st.rerun()
    with feedback_cols[1]:
        if st.button("Not Helpful", key=f"assistant_unhelpful_{reply.answer_id}", use_container_width=True):
            submit_feedback(reply.answer_id, "not_helpful", page_scope)
            st.session_state["assistant_feedback_note"] = "Thanks — I’ll avoid reusing this answer too aggressively."
            st.rerun()


def _render_answer(reply: AssistantReply, page_scope: str) -> None:
    safe_answer = escape(reply.answer_text).replace("\n", "<br/>")
    st.markdown("<div class='assistant-answer-card'>", unsafe_allow_html=True)
    source_label = SOURCE_LABELS.get(reply.source_type, "Assistant")
    st.markdown(
        (
            "<div class='assistant-answer-meta'>"
            f"<span class='assistant-badge'>{escape(source_label)}</span>"
            f"<span class='assistant-badge assistant-badge-muted'>{escape(reply.confidence_label)} Confidence</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='assistant-answer-copy'>{safe_answer}</div>", unsafe_allow_html=True)
    if reply.retrieval_only_notice:
        st.markdown(f"<div class='assistant-notice'>{escape(reply.retrieval_only_notice)}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    _render_feedback(reply, page_scope)
    _render_related_questions(reply, page_scope)

    if reply.source_refs:
        with st.expander("View Source Context", expanded=False):
            st.markdown("<div class='assistant-source-list'>", unsafe_allow_html=True)
            for item in reply.source_refs:
                st.markdown(
                    (
                        "<div class='assistant-source-item'>"
                        f"<div class='assistant-source-title'>{escape(item.get('title', ''))}</div>"
                        f"<div class='assistant-source-label'>{escape(item.get('source_label', ''))}</div>"
                        f"<div class='assistant-source-excerpt'>{escape(item.get('excerpt', ''))}</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)


def render_assistant_panel(page_name: str) -> None:
    _inject_assistant_css()
    page_scope = normalize_page_scope(page_name)
    expanded = page_scope in {"ytuber", "outlier_finder", "tools"}

    with st.expander("Assistant", expanded=expanded):
        st.markdown(
            f"<div class='assistant-page-badge'>Current Page: {escape(page_name)}</div>",
            unsafe_allow_html=True,
        )
        st.caption("Ask about product usage, creator workflow, metrics, or troubleshooting.")

        query = st.text_input(
            "What Are You Facing?",
            key="assistant_query_input",
            placeholder="Why did this scan return weak results?",
            label_visibility="visible",
        )
        ask_clicked = st.button("Ask Assistant", key="assistant_ask", use_container_width=True, type="primary")

        prompts = starter_prompts_for_page(page_scope)
        st.caption("Try A Starter Prompt")
        prompt_cols = st.columns(2)
        starter_clicked = None
        for index, prompt in enumerate(prompts[:4]):
            with prompt_cols[index % 2]:
                if st.button(prompt, key=f"assistant_starter_{page_scope}_{index}", use_container_width=True):
                    starter_clicked = prompt

        if starter_clicked:
            _handle_question(starter_clicked, page_scope)
            st.rerun()
        if ask_clicked and query.strip():
            _handle_question(query, page_scope)
            st.rerun()

        note = st.session_state.pop("assistant_feedback_note", "")
        if note:
            st.caption(note)

        _render_thread()

        last_reply: AssistantReply | None = st.session_state.get("assistant_last_reply")
        last_scope = st.session_state.get("assistant_last_page_scope")
        if last_reply is not None and (last_scope == page_scope or last_scope is None):
            _render_answer(last_reply, page_scope)
