"""meetings and agendas

create_all with checkfirst is safe on a database that already has the meetings table.
"""

from alembic import op
from app import models  # noqa: F401  (registers tables)
from app.db import Base

revision = "0001"
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    pass
