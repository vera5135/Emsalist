"""add typed legal_issue_source_links table (P2.8A7)

Revision ID: 1a2b3c4d5e6f
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-15 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = '0a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legal_issue_source_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('source_record_id', sa.String(length=32), nullable=False),
        sa.Column('source_version_id', sa.String(length=32), nullable=False),
        sa.Column('source_paragraph_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_issue_source_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_issue_source_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issue_source_links_issue',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_record_id'],
            ['source_records.id'],
            name='fk_legal_issue_source_links_source_record',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_record_id', 'source_version_id'],
            ['source_versions.source_record_id', 'source_versions.id'],
            name='fk_legal_issue_source_links_source_version',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_version_id', 'source_paragraph_id'],
            ['source_paragraphs.source_version_id', 'source_paragraphs.id'],
            name='fk_legal_issue_source_links_source_paragraph',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "relation_type IN ('source_governs_issue')",
            name='ck_legal_issue_source_links_relation_type',
        ),
    )
    op.create_index(
        'ix_legal_issue_source_links_tenant_case',
        'legal_issue_source_links',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_legal_issue_source_links_issue',
        'legal_issue_source_links',
        ['case_id', 'issue_id'],
    )
    op.create_index(
        'ix_legal_issue_source_links_source_provenance',
        'legal_issue_source_links',
        ['source_record_id', 'source_version_id', 'source_paragraph_id'],
    )
    op.create_index(
        'uq_legal_issue_source_links_active_relation',
        'legal_issue_source_links',
        [
            'tenant_id', 'case_id', 'issue_id',
            'source_record_id', 'source_version_id', 'source_paragraph_id',
            'relation_type',
        ],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_legal_issue_source_links_active_relation', table_name='legal_issue_source_links')
    op.drop_index('ix_legal_issue_source_links_source_provenance', table_name='legal_issue_source_links')
    op.drop_index('ix_legal_issue_source_links_issue', table_name='legal_issue_source_links')
    op.drop_index('ix_legal_issue_source_links_tenant_case', table_name='legal_issue_source_links')
    op.drop_table('legal_issue_source_links')
