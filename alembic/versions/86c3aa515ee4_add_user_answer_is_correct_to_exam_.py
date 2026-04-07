"""add user_answer is_correct to exam_session_questions and extend paragraph_questions

Revision ID: 86c3aa515ee4
Revises: 88c7cd6e2b11
Create Date: 2026-04-07 14:11:27.564149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '86c3aa515ee4'
down_revision: Union[str, Sequence[str], None] = '88c7cd6e2b11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


paragraphtype = sa.Enum('reading_comprehension', 'case_study', 'data_interpretation', name='paragraphtype')


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('exam_session_questions', sa.Column('user_answer', sa.String(), nullable=True))
    op.add_column('exam_session_questions', sa.Column('is_correct', sa.Boolean(), nullable=True))
    op.alter_column('paragraph_questions', 'passage', new_column_name='content')
    op.add_column('paragraph_questions', sa.Column('title', sa.String(), nullable=True))
    paragraphtype.create(op.get_bind(), checkfirst=True)
    op.add_column('paragraph_questions', sa.Column('paragraph_type', sa.Enum('reading_comprehension', 'case_study', 'data_interpretation', name='paragraphtype', create_type=False), nullable=True))
    op.add_column('paragraph_questions', sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('paragraph_questions', sa.Column('difficulty', sa.Enum('easy', 'medium', 'hard', name='difficultylevel', create_type=False), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paragraph_questions', 'difficulty')
    op.drop_column('paragraph_questions', 'tags')
    op.drop_column('paragraph_questions', 'paragraph_type')
    paragraphtype.drop(op.get_bind(), checkfirst=True)
    op.drop_column('paragraph_questions', 'title')
    op.alter_column('paragraph_questions', 'content', new_column_name='passage')
    op.drop_column('exam_session_questions', 'is_correct')
    op.drop_column('exam_session_questions', 'user_answer')
