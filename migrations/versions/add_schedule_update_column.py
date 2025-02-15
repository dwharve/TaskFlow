"""add schedule update column

Revision ID: add_schedule_update_column
Revises: add_version_column
Create Date: 2024-02-15 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_schedule_update_column'
down_revision = 'add_version_column'
branch_labels = None
depends_on = None

def upgrade():
    # Add last_schedule_update column
    op.add_column('tasks', sa.Column('last_schedule_update', sa.DateTime(), nullable=True))
    
    # Initialize last_schedule_update for existing tasks with schedules
    op.execute("""
        UPDATE tasks 
        SET last_schedule_update = created_at 
        WHERE schedule IS NOT NULL AND schedule != ''
    """)

def downgrade():
    op.drop_column('tasks', 'last_schedule_update') 