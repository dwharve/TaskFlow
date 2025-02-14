"""add version column to settings

Revision ID: add_version_column
Create Date: 2024-02-14 22:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_version_column'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add version column with default value of 1
    op.add_column('settings', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))

def downgrade():
    # Remove version column
    op.drop_column('settings', 'version') 