from enum import Enum


class EventStatus(str, Enum):
    NEW = "new"
    PUBLISHED = "published"
    REGISTRATION_CLOSED = "registration_closed"
    FINISHED = "finished"


class SyncStatus(str, Enum):
    NEVER = "never"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
