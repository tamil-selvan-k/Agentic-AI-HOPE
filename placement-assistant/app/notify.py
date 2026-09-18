from dataclasses import dataclass, field


@dataclass
class OutboxNotifier:
    """Stand-in for SMS and email. Records what would have been sent. (Given.)"""
    sent: list[dict] = field(default_factory=list)

    def send(self, roll_no: str, message: str) -> str:
        notification_id = f"n_{len(self.sent) + 1}"
        self.sent.append({"id": notification_id, "roll_no": roll_no, "message": message})
        return notification_id
