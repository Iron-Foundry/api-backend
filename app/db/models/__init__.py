"""SQLAlchemy ORM models - canonical PostgreSQL schema definition.

These classes mirror the tables created by the Alembic migrations and act as
the single source of truth for alembic autogenerate.
"""

from .assets import Asset
from .badges import Badge, UserBadge
from .ballot_tokens import (
    BallotPollVote,
    BallotTokenAccount,
    BallotTokenTransaction,
)
from .base import Base
from .clan import ClanStats, WomClanRank
from .competition_schedule import CompetitionSchedule, ScheduledCompetitionRun
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
from .gains import BulkGainsBatch, PlayerBulkGains
from .goals import MemberGoals
from .music import (
    MusicCounter,
    MusicTrackPlay,
    Playlist,
    PlaylistTrack,
)
from .parties import (
    PartyChatMessageDB,
    PartyDB,
    PartyMemberDB,
    PartyNotificationPreferences,
)
from .ranking import CompetitionSnapshot, PlayerRanking, PlayerSnapshot
from .reference_data import EfficiencyRate, LootDrop, LootSource
from .runelite_configs import RuneLiteConfig
from .service_metrics import MetricRecord, MetricRecordCompact, ServiceStatus
from .surveys import SurveyActive, SurveyResponse, SurveyTemplate, WebSurveySubmission
from .tickets import Ticket, Transcript
from .tilerace import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
    TileRepositoryTile,
)
from .users import User, UserAccount

__all__ = [
    "Asset",
    "Badge",
    "BallotPollVote",
    "BallotTokenAccount",
    "BallotTokenTransaction",
    "Base",
    "BulkGainsBatch",
    "ClanStats",
    "CofferEvent",
    "CompetitionSchedule",
    "CompetitionSnapshot",
    "Config",
    "ContentCategory",
    "ContentCollaborator",
    "ContentEntry",
    "ContentEntryReaction",
    "ContentEntryVersion",
    "EfficiencyRate",
    "Event",
    "Feedback",
    "FeedbackReaction",
    "FeedbackReply",
    "FrenzyEvent",
    "FrenzySubmission",
    "FrenzyTeam",
    "FrenzyTemplate",
    "FrenzyTemplateVersion",
    "Leaderboard",
    "LootDrop",
    "LootSource",
    "MemberGoals",
    "MembershipEvent",
    "Metric",
    "MetricRecord",
    "MetricRecordCompact",
    "MusicCounter",
    "MusicTrackPlay",
    "PartyChatMessageDB",
    "PartyDB",
    "PartyMemberDB",
    "PartyNotificationPreferences",
    "PlayerBulkGains",
    "PlayerRanking",
    "PlayerSnapshot",
    "Playlist",
    "PlaylistTrack",
    "RolePanel",
    "RuneLiteConfig",
    "ScheduledCompetitionRun",
    "ServiceStatus",
    "SurveyActive",
    "SurveyResponse",
    "SurveyTemplate",
    "Ticket",
    "TileRaceCompletion",
    "TileRaceEvent",
    "TileRaceRoll",
    "TileRaceSignup",
    "TileRaceTeam",
    "TileRepositoryTile",
    "Transcript",
    "User",
    "UserAccount",
    "UserBadge",
    "WebSurveySubmission",
    "WomClanRank",
]
