"""allow ai_regeneration revision change type (P2.9C1B)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-17 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = (
    "change_type IN ('initial_generation', 'manual_creation', "
    "'restored_revision', 'user_edit')"
)
_NEW_CHECK = (
    "change_type IN ('ai_regeneration', 'initial_generation', "
    "'manual_creation', 'restored_revision', 'user_edit')"
)


def upgrade() -> None:
    with op.batch_alter_table('draft_paragraph_revisions') as batch_op:
        batch_op.drop_constraint('ck_draft_paragraph_revisions_change_type',
                                 type_='check')
        batch_op.create_check_constraint(
            'ck_draft_paragraph_revisions_change_type', _NEW_CHECK)


def downgrade() -> None:
    with op.batch_alter_table('draft_paragraph_revisions') as batch_op:
        batch_op.drop_constraint('ck_draft_paragraph_revisions_change_type',
                                 type_='check')
        batch_op.create_check_constraint(
            'ck_draft_paragraph_revisions_change_type', _OLD_CHECK)
