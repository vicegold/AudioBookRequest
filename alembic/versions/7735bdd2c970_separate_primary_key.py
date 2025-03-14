"""separate primary key

Revision ID: 7735bdd2c970
Revises: 845d93d41d01
Create Date: 2025-02-17 19:18:09.258150

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "7735bdd2c970"
down_revision: Union[str, None] = "845d93d41d01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("DELETE FROM bookrequest")
    with op.batch_alter_table("bookrequest", schema=None) as batch_op:
        batch_op.drop_column("asin")
        batch_op.add_column(
            sa.Column("asin", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        )
        batch_op.add_column(sa.Column("id", sa.Uuid(), nullable=False))
        batch_op.create_primary_key("pk_bookrequest", ["id"])

        batch_op.drop_constraint("user_user_username", type_="foreignkey")
        batch_op.create_foreign_key(
            "user_user_username",
            "user",
            ["user_username"],
            ["username"],
            ondelete="CASCADE",
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("bookrequest", schema=None) as batch_op:
        batch_op.drop_column("id")

        batch_op.drop_constraint("user_user_username", type_="foreignkey")
        batch_op.create_foreign_key(
            "user_user_username",
            "user",
            ["user_username"],
            ["username"],
            ondelete="SET NULL",
        )

    # ### end Alembic commands ###
