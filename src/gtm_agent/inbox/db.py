"""Postgres access for marketing.chat_inquiries (internal-db, `marketing`
schema -- migrations/0008_marketing_chat_inquiries.sql). Connects as the
scoped `marketing_app` role (internal-db/migrations/0007), never the
superuser -- same least-privilege pattern rag-01's PgVectorStore uses for
`rag_app`. psycopg is imported lazily so importing this module doesn't
require the `pg` extra unless it's actually used (mirrors rag-01/rag/store.py).
"""

from __future__ import annotations

from gtm_agent.inbox.models import ChatInquiry, ChatInquiryRecord


def insert_inquiry(dsn: str, inquiry: ChatInquiry) -> str:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO marketing.chat_inquiries
                    (message, contact_name, contact_email, source, page_path,
                     session_id, classification, classification_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    inquiry.message,
                    inquiry.contact_name,
                    inquiry.contact_email,
                    inquiry.source,
                    inquiry.page_path,
                    inquiry.session_id,
                    inquiry.classification.value,
                    inquiry.classification_reason,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row[0])


def list_inquiries(dsn: str, limit: int = 20, classification: str | None = None) -> list[ChatInquiryRecord]:
    import psycopg

    query = """
        SELECT id, created_at, message, contact_name, contact_email, source,
               page_path, session_id, classification, classification_reason
        FROM marketing.chat_inquiries
    """
    params: list[object] = []
    if classification:
        query += " WHERE classification = %s"
        params.append(classification)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        ChatInquiryRecord(
            id=str(r[0]),
            created_at=r[1],
            message=r[2],
            contact_name=r[3],
            contact_email=r[4],
            source=r[5],
            page_path=r[6],
            session_id=r[7],
            classification=r[8],
            classification_reason=r[9],
        )
        for r in rows
    ]
