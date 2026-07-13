"""SQLAlchemy ORM models - canonical PostgreSQL schema definition.

These classes mirror the tables created by the Alembic migrations and act as
the single source of truth for alembic autogenerate.
"""

from .assets import Asset
from .ballot_tokens import (
    BallotPollVote,
    BallotTokenAccount,
    BallotTokenTransaction,
)
from .competition_schedule import CompetitionSchedule, ScheduledCompetitionRun
from .badges import Badge, UserBadge
from .base import Base
from .clan import ClanStats, WomClanRank
from .goals import MemberGoals
from .config import Config
from .content import (
    ContentCategory,
    ContentCollaborator,
    ContentEntry,
    ContentEntryReaction,
    ContentEntryVersion,
)
from .discord import RolePanel
from .events import CofferEvent, Event, Leaderboard, MembershipEvent, Metric
from .feedback import Feedback, FeedbackReaction, FeedbackReply
from .frenzy import (
    FrenzyEvent,
    FrenzySubmission,
    FrenzyTeam,
    FrenzyTemplate,
    FrenzyTemplateVersion,
)
from .tilerace import (
    TileRepositoryTile,
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceTeam,
    TileRaceSignup,
)
from .parties import (
    PartyChatMessageDB,
    PartyDB,
    PartyMemberDB,
    PartyNotificationPreferences,
)
from .gains import BulkGainsBatch, PlayerBulkGains
from .map_tiles import MapTile
from .ranking import CompetitionSnapshot, PlayerRanking, PlayerSnapshot
from .runelite_configs import RuneLiteConfig
from .service_metrics import MetricRecord, MetricRecordCompact, ServiceStatus
from .surveys import SurveyActive, SurveyResponse, SurveyTemplate, WebSurveySubmission
from .tickets import Ticket, Transcript
from .users import User, UserAccount

__all__ = [
    "Asset",
    "BallotPollVote",
    "BallotTokenAccount",
    "BallotTokenTransaction",
    "BulkGainsBatch",
    "PlayerBulkGains",
    "CompetitionSchedule",
    "ScheduledCompetitionRun",
    "Badge",
    "Base",
    "ClanStats",
    "WomClanRank",
    "CofferEvent",
    "CompetitionSnapshot",
    "Config",
    "ContentCategory",
    "ContentCollaborator",
    "ContentEntry",
    "ContentEntryReaction",
    "ContentEntryVersion",
    "Event",
    "Feedback",
    "FeedbackReaction",
    "FeedbackReply",
    "FrenzyEvent",
    "FrenzySubmission",
    "FrenzyTeam",
    "FrenzyTemplate",
    "FrenzyTemplateVersion",
    "TileRepositoryTile",
    "TileRaceCompletion",
    "TileRaceEvent",
    "TileRaceTeam",
    "TileRaceSignup",
    "Leaderboard",
    "MapTile",
    "MemberGoals",
    "MembershipEvent",
    "Metric",
    "MetricRecord",
    "MetricRecordCompact",
    "PartyChatMessageDB",
    "PartyDB",
    "PartyMemberDB",
    "PartyNotificationPreferences",
    "PlayerRanking",
    "PlayerSnapshot",
    "RolePanel",
    "RuneLiteConfig",
    "ServiceStatus",
    "SurveyActive",
    "SurveyResponse",
    "SurveyTemplate",
    "Ticket",
    "Transcript",
    "User",
    "UserAccount",
    "UserBadge",
    "WebSurveySubmission",
]
