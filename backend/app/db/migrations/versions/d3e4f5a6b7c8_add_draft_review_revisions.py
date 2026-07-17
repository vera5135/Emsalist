"""add draft paragraph revisions and review events (P2.9C1)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-17 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'draft_paragraph_revisions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_document_id', sa.String(length=32), nullable=False),
        sa.Column('draft_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('base_paragraph_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('text_hash', sa.String(length=64), nullable=False),
        sa.Column('change_type', sa.String(length=30), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('draft_paragraph_id', 'revision_number',
                            name='uq_draft_paragraph_revisions_number'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_draft_paragraph_revisions_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'],
                                name='fk_draft_paragraph_revisions_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_document_id'],
            ['draft_documents.tenant_id', 'draft_documents.case_id', 'draft_documents.id'],
            name='fk_draft_paragraph_revisions_draft_document',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_paragraph_id'],
            ['draft_paragraphs.tenant_id', 'draft_paragraphs.case_id', 'draft_paragraphs.id'],
            name='fk_draft_paragraph_revisions_paragraph',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "change_type IN ('initial_generation', 'manual_creation', "
            "'restored_revision', 'user_edit')",
            name='ck_draft_paragraph_revisions_change_type',
        ),
        sa.CheckConstraint('revision_number >= 1',
                           name='ck_draft_paragraph_revisions_number_min'),
        sa.CheckConstraint('length(text_hash) = 64',
                           name='ck_draft_paragraph_revisions_text_hash_len'),
    )
    op.create_index('ix_draft_paragraph_revisions_paragraph', 'draft_paragraph_revisions',
                    ['draft_paragraph_id', 'revision_number'])
    op.create_index('ix_draft_paragraph_revisions_tenant_case', 'draft_paragraph_revisions',
                    ['tenant_id', 'case_id'])

    op.create_table(
        'draft_paragraph_review_events',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_document_id', sa.String(length=32), nullable=False),
        sa.Column('draft_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('paragraph_revision_id', sa.String(length=32), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reason_code', sa.String(length=50), nullable=True),
        sa.Column('reviewer_user_id', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('paragraph_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_draft_paragraph_review_events_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'],
                                name='fk_draft_paragraph_review_events_case'),
        sa.ForeignKeyConstraint(['paragraph_revision_id'], ['draft_paragraph_revisions.id'],
                                name='fk_draft_paragraph_review_events_revision',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_document_id'],
            ['draft_documents.tenant_id', 'draft_documents.case_id', 'draft_documents.id'],
            name='fk_draft_paragraph_review_events_draft_document',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_paragraph_id'],
            ['draft_paragraphs.tenant_id', 'draft_paragraphs.case_id', 'draft_paragraphs.id'],
            name='fk_draft_paragraph_review_events_paragraph',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "decision IN ('accepted', 'changes_requested')",
            name='ck_draft_paragraph_review_events_decision',
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ("
            "'chronology_revision_required', 'citation_revision_required', "
            "'factual_correction_required', 'formatting_revision_required', "
            "'language_revision_required', 'legal_reasoning_revision_required', "
            "'other_review_required', 'source_support_insufficient')",
            name='ck_draft_paragraph_review_events_reason_code',
        ),
    )
    op.create_index('ix_draft_paragraph_review_events_paragraph',
                    'draft_paragraph_review_events',
                    ['draft_paragraph_id', 'created_at'])
    op.create_index('ix_draft_paragraph_review_events_tenant_case',
                    'draft_paragraph_review_events', ['tenant_id', 'case_id'])


def downgrade() -> None:
    op.drop_index('ix_draft_paragraph_review_events_tenant_case',
                  table_name='draft_paragraph_review_events')
    op.drop_index('ix_draft_paragraph_review_events_paragraph',
                  table_name='draft_paragraph_review_events')
    op.drop_table('draft_paragraph_review_events')
    op.drop_index('ix_draft_paragraph_revisions_tenant_case',
                  table_name='draft_paragraph_revisions')
    op.drop_index('ix_draft_paragraph_revisions_paragraph',
                  table_name='draft_paragraph_revisions')
    op.drop_table('draft_paragraph_revisions')
