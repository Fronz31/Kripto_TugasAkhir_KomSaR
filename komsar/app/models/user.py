from datetime import datetime, timezone

from ..extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(16), unique=True, nullable=False, index=True)   # mis. B001
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)  # mis. budi01
    full_name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(60), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        """Tanpa password_hash."""
        return {"id": self.id, "user_id": self.user_id, "username": self.username,
                "full_name": self.full_name, "unit": self.unit,
                "is_admin": self.is_admin, "is_active": self.is_active}
