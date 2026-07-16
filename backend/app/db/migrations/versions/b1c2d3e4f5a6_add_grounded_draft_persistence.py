"""add grounded draft persistence tables (P2.9A)

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-07-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'draft_documents',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('draft_type', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='draft'),
        sa.Column('supersedes_draft_id', sa.String(length=32), nullable=True),
        sa.Column('created_by', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'case_id', 'id', name='uq_draft_documents_tenant_case_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_draft_documents_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_draft_documents_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'supersedes_draft_id'],
            ['draft_documents.tenant_id', 'draft_documents.case_id', 'draft_documents.id'],
            name='fk_draft_documents_supersedes',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "status IN ('deleted', 'draft', 'finalized', 'reviewing', 'superseded')",
            name='ck_draft_documents_status',
        ),
        sa.CheckConstraint(
            "draft_type IN ('arabuluculuk_basvurusu', 'beyan', 'cevaba_cevap', "
            "'cevap_dilekcesi', 'dava_dilekcesi', 'delil_listesi', 'ihtarname', "
            "'ihtiyati_tedbir', 'ikinci_cevap', 'istinaf', 'itiraz', 'temyiz')",
            name='ck_draft_documents_draft_type',
        ),
    )
    op.create_index('ix_draft_documents_tenant_case', 'draft_documents', ['tenant_id', 'case_id'])
    op.create_index('ix_draft_documents_case_status', 'draft_documents', ['case_id', 'status'])

    op.create_table(
        'draft_paragraphs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_document_id', sa.String(length=32), nullable=False),
        sa.Column('paragraph_order', sa.Integer(), nullable=False),
        sa.Column('paragraph_type', sa.String(length=40), nullable=False, server_default='body'),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('verification_status', sa.String(length=30), nullable=False, server_default='pending_review'),
        sa.Column('generated_by', sa.String(length=20), nullable=False, server_default='user'),
        sa.Column('model_name', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'case_id', 'id', name='uq_draft_paragraphs_tenant_case_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_draft_paragraphs_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_draft_paragraphs_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_document_id'],
            ['draft_documents.tenant_id', 'draft_documents.case_id', 'draft_documents.id'],
            name='fk_draft_paragraphs_draft_document',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "paragraph_type IN ('body', 'deliller', 'ekler', 'hukuki_degerlendirme', "
            "'hukuki_nedenler', 'kisa_ozet', 'konu', 'merci', 'olaylar', "
            "'sonuc_ve_talep', 'taraflar')",
            name='ck_draft_paragraphs_paragraph_type',
        ),
        sa.CheckConstraint(
            "verification_status IN ('accepted', 'needs_review', 'pending_review')",
            name='ck_draft_paragraphs_verification_status',
        ),
        sa.CheckConstraint(
            "generated_by IN ('ai', 'user')",
            name='ck_draft_paragraphs_generated_by',
        ),
        sa.CheckConstraint('paragraph_order >= 1', name='ck_draft_paragraphs_order_min'),
    )
    op.create_index(
        'uq_draft_paragraphs_active_order',
        'draft_paragraphs',
        ['draft_document_id', 'paragraph_order'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )
    op.create_index('ix_draft_paragraphs_tenant_case', 'draft_paragraphs', ['tenant_id', 'case_id'])
    op.create_index('ix_draft_paragraphs_document_order', 'draft_paragraphs', ['draft_document_id', 'paragraph_order'])

    op.create_table(
        'draft_paragraph_issue_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('legal_issue_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False, server_default='issue_drafted_in_paragraph'),
        sa.Column('created_by', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_draft_paragraph_issue_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_draft_paragraph_issue_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_paragraph_id'],
            ['draft_paragraphs.tenant_id', 'draft_paragraphs.case_id', 'draft_paragraphs.id'],
            name='fk_draft_paragraph_issue_links_paragraph',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'legal_issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_draft_paragraph_issue_links_issue',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "relation_type IN ('issue_drafted_in_paragraph')",
            name='ck_draft_paragraph_issue_links_relation_type',
        ),
    )
    op.create_index(
        'uq_draft_paragraph_issue_links_active',
        'draft_paragraph_issue_links',
        ['tenant_id', 'case_id', 'draft_paragraph_id', 'legal_issue_id', 'relation_type'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )
    op.create_index('ix_draft_paragraph_issue_links_tenant_case', 'draft_paragraph_issue_links', ['tenant_id', 'case_id'])
    op.create_index('ix_draft_paragraph_issue_links_paragraph', 'draft_paragraph_issue_links', ['draft_paragraph_id'])
    op.create_index('ix_draft_paragraph_issue_links_issue', 'draft_paragraph_issue_links', ['legal_issue_id'])

    op.create_table(
        'draft_paragraph_source_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('source_record_id', sa.String(length=32), nullable=False),
        sa.Column('source_version_id', sa.String(length=32), nullable=False),
        sa.Column('source_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('usage_type', sa.String(length=30), nullable=False, server_default='citation'),
        sa.Column('quote_hash', sa.String(length=64), nullable=False),
        sa.Column('verification_status', sa.String(length=30), nullable=False, server_default='verified'),
        sa.Column('created_by', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_draft_paragraph_source_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_draft_paragraph_source_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_paragraph_id'],
            ['draft_paragraphs.tenant_id', 'draft_paragraphs.case_id', 'draft_paragraphs.id'],
            name='fk_draft_paragraph_source_links_paragraph',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_record_id'],
            ['source_records.id'],
            name='fk_draft_paragraph_source_links_source_record',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_record_id', 'source_version_id'],
            ['source_versions.source_record_id', 'source_versions.id'],
            name='fk_draft_paragraph_source_links_source_version',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_version_id', 'source_paragraph_id'],
            ['source_paragraphs.source_version_id', 'source_paragraphs.id'],
            name='fk_draft_paragraph_source_links_source_paragraph',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "usage_type IN ('citation', 'quotation', 'reference')",
            name='ck_draft_paragraph_source_links_usage_type',
        ),
        sa.CheckConstraint(
            "verification_status IN ('needs_review', 'verified')",
            name='ck_draft_paragraph_source_links_verification_status',
        ),
        sa.CheckConstraint('length(quote_hash) = 64', name='ck_draft_paragraph_source_links_quote_hash_len'),
    )
    op.create_index(
        'uq_draft_paragraph_source_links_active',
        'draft_paragraph_source_links',
        [
            'tenant_id', 'case_id', 'draft_paragraph_id',
            'source_record_id', 'source_version_id', 'source_paragraph_id',
        ],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )
    op.create_index('ix_draft_paragraph_source_links_tenant_case', 'draft_paragraph_source_links', ['tenant_id', 'case_id'])
    op.create_index('ix_draft_paragraph_source_links_paragraph', 'draft_paragraph_source_links', ['draft_paragraph_id'])
    op.create_index(
        'ix_draft_paragraph_source_links_provenance',
        'draft_paragraph_source_links',
        ['source_record_id', 'source_version_id', 'source_paragraph_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_draft_paragraph_source_links_provenance', table_name='draft_paragraph_source_links')
    op.drop_index('ix_draft_paragraph_source_links_paragraph', table_name='draft_paragraph_source_links')
    op.drop_index('ix_draft_paragraph_source_links_tenant_case', table_name='draft_paragraph_source_links')
    op.drop_index('uq_draft_paragraph_source_links_active', table_name='draft_paragraph_source_links')
    op.drop_table('draft_paragraph_source_links')
    op.drop_index('ix_draft_paragraph_issue_links_issue', table_name='draft_paragraph_issue_links')
    op.drop_index('ix_draft_paragraph_issue_links_paragraph', table_name='draft_paragraph_issue_links')
    op.drop_index('ix_draft_paragraph_issue_links_tenant_case', table_name='draft_paragraph_issue_links')
    op.drop_index('uq_draft_paragraph_issue_links_active', table_name='draft_paragraph_issue_links')
    op.drop_table('draft_paragraph_issue_links')
    op.drop_index('ix_draft_paragraphs_document_order', table_name='draft_paragraphs')
    op.drop_index('ix_draft_paragraphs_tenant_case', table_name='draft_paragraphs')
    op.drop_index('uq_draft_paragraphs_active_order', table_name='draft_paragraphs')
    op.drop_table('draft_paragraphs')
    op.drop_index('ix_draft_documents_case_status', table_name='draft_documents')
    op.drop_index('ix_draft_documents_tenant_case', table_name='draft_documents')
    op.drop_table('draft_documents')
