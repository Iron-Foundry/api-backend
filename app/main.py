import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from loguru import logger
from starlette.middleware.base import RequestResponseEndpoint
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from valkey.asyncio import Valkey

from app.db import create_engine, create_session_factory
from app.docs import (
    DESCRIPTION,
    SERVERS,
    TAGS_METADATA,
    install_openapi_customization,
    render_reference,
)
from app.routers import (
    assets,
    auth,
    badges,
    ccdispatch,
    clan,
    config,
    content,
    events,
    feedback,
    frenzy,
    ironclad,
    members,
    meta,
    metrics,
    music,
    osrs_cache,
    parties,
    ranking,
    reference,
    role_panels,
    runelite_configs,
    staff,
    surveys,
    ticket_config,
    tilerace,
)
from app.routers import (
    discord as discord_router,
)
from app.routers.config import _ALL_SERVICE_KEYS, get_service_toggles
from app.services.bulk_gains import BulkGainsService
from app.services.cc_dispatch import CcDispatchService
from app.services.ccingest_metrics import collector as ccingest_collector
from app.services.clan_stats import ClanStatsService
from app.services.competition_schedule import CompetitionScheduleService
from app.services.competition_snapshot import CompetitionSnapshotService
from app.services.connection_manager import connection_manager
from app.services.discord_chat import DiscordChatService
from app.services.efficiency_rates import EfficiencyRatesService
from app.services.endpoint_metrics import (
    EndpointMetricsCollector,
    EndpointMetricsService,
)
from app.services.http.wom_queue import init_wom_queue
from app.services.loot_tables import LootTablesService
from app.services.metric_compaction import MetricCompactionService
from app.services.music_live import MusicStateService
from app.services.music_stats import MusicStatsService
from app.services.name_change import WomNameChangeService
from app.services.outbound_metrics import _collector as _outbound_collector
from app.services.outbound_metrics.service import OutboundMetricsService
from app.services.party_expiry import PartyExpiryService
from app.services.ranking_service import RankingService
from app.services.websocket_metrics import WebSocketMetricsService
from app.services.wom_metrics import WomMetricsService
from app.services.ws_registry import WsRegistry
from app.version import VERSION

DATABASE_URL = os.getenv("DATABASE_URL", "")
VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")
WOM_GROUP_ID = os.getenv("WOM_GROUP_ID")
WOM_GROUP_KEY = os.getenv("WOM_GROUP_KEY")
WOM_API_KEY = os.getenv("WOM_API_KEY")
WOM_CLAN_NAME = os.getenv("WOM_CLAN_NAME", "Iron Foundry")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
_ALLOWED_ORIGINS = [o.strip() for o in FRONTEND_URL.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DATABASE_URL:
        logger.info("Connecting to PostgreSQL...")
        engine = create_engine(DATABASE_URL)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
    else:
        logger.warning("DATABASE_URL not set - PostgreSQL disabled")
        app.state.engine = None
        app.state.session_factory = None

    wom_queue = init_wom_queue()
    await wom_queue.start()

    logger.info("Connecting to Valkey at {}...", VALKEY_URI)
    app.state.valkey = Valkey.from_url(VALKEY_URI)
    await frenzy.warm_osrs_caches(app.state.valkey)

    # Read toggle state from DB; fall back to all-enabled if DB unavailable
    if app.state.session_factory:
        try:
            async with app.state.session_factory() as _s:
                toggles = await get_service_toggles(_s)
        except Exception as exc:
            logger.warning(
                "Could not read service toggles ({}), defaulting all enabled", exc
            )
            toggles = dict.fromkeys(_ALL_SERVICE_KEYS, True)
    else:
        toggles = dict.fromkeys(_ALL_SERVICE_KEYS, True)

    # The connection census is correctness plumbing rather than a feature, so it
    # is not in the toggle registry - nothing should be able to switch it off.
    app.state.ws_registry = WsRegistry(app.state.valkey, connection_manager)
    await app.state.ws_registry.start()

    # Build all service instances
    cc_dispatch_svc = CcDispatchService(VALKEY_URI)
    discord_chat_svc = DiscordChatService(VALKEY_URI, app.state.session_factory)
    music_state_svc = MusicStateService(VALKEY_URI, app.state.valkey)
    music_stats_svc = MusicStatsService(VALKEY_URI, app.state.session_factory)
    party_expiry_svc = PartyExpiryService(app.state.session_factory)
    compaction_service = MetricCompactionService(app.state.session_factory)

    if WOM_GROUP_ID:
        wom_service: WomNameChangeService | None = WomNameChangeService(
            app.state.session_factory,
            int(WOM_GROUP_ID),
            WOM_GROUP_KEY,
            WOM_CLAN_NAME,
            api_key=WOM_API_KEY,
        )
        clan_stats_service: ClanStatsService | None = ClanStatsService(
            app.state.session_factory
        )
        ranking_service: RankingService | None = RankingService(
            app.state.session_factory,
            int(WOM_GROUP_ID),
            api_key=WOM_API_KEY,
        )
        snapshot_service: CompetitionSnapshotService | None = (
            CompetitionSnapshotService(app.state.session_factory, app.state.valkey)
        )
        efficiency_rates_service: EfficiencyRatesService | None = (
            EfficiencyRatesService(app.state.session_factory)
        )
        comp_schedule_service: CompetitionScheduleService | None = None
        if WOM_GROUP_KEY:
            comp_schedule_service = CompetitionScheduleService(
                app.state.session_factory,
                app.state.valkey,
                int(WOM_GROUP_ID),
                WOM_GROUP_KEY,
                api_key=WOM_API_KEY,
                discord_contact=os.getenv("WOM_DISCORD_CONTACT"),
            )
    else:
        logger.warning(
            "WOM_GROUP_ID not set - name change, clan stats, ranking and snapshot services disabled"
        )
        wom_service = None
        clan_stats_service = None
        ranking_service = None
        snapshot_service = None
        efficiency_rates_service = None
        comp_schedule_service = None

    loot_tables_service = (
        LootTablesService(app.state.session_factory)
        if app.state.session_factory
        else None
    )

    app.state.ranking_service = ranking_service
    app.state.bulk_gains_service = (
        BulkGainsService(app.state.session_factory)
        if app.state.session_factory
        else None
    )
    app.state.service_registry = {
        "cc_dispatch": cc_dispatch_svc,
        "discord_chat": discord_chat_svc,
        "music_state": music_state_svc,
        "music_stats": music_stats_svc,
        "party_expiry": party_expiry_svc,
        "metric_compaction": compaction_service,
        "wom_name_change": wom_service,
        "clan_stats": clan_stats_service,
        "ranking": ranking_service,
        "competition_snapshot": snapshot_service,
        "competition_schedule": comp_schedule_service,
        "efficiency_rates": efficiency_rates_service,
        "loot_tables": loot_tables_service,
    }

    # Start only enabled services
    for key, svc in app.state.service_registry.items():
        if svc is not None and toggles.get(key, True):
            await svc.start()
        elif svc is not None:
            logger.info("Service {} disabled by config - skipping start", key)

    endpoint_metrics_service = EndpointMetricsService(
        app.state.endpoint_metrics_collector, app.state.session_factory
    )
    await endpoint_metrics_service.start()
    ws_metrics_service = WebSocketMetricsService(
        connection_manager,
        app.state.session_factory,
        ccingest_collector,
        registry=app.state.ws_registry,
    )
    await ws_metrics_service.start()
    wom_metrics_service = WomMetricsService(app.state.session_factory)
    await wom_metrics_service.start()
    outbound_metrics_service = OutboundMetricsService(
        _outbound_collector, app.state.session_factory
    )
    await outbound_metrics_service.start()
    yield
    await outbound_metrics_service.stop()
    await wom_metrics_service.stop()
    await ws_metrics_service.stop()
    await endpoint_metrics_service.stop()
    for svc in app.state.service_registry.values():
        if svc is not None and svc.is_running:
            await svc.stop()
    await app.state.ws_registry.stop()
    await wom_queue.stop()
    if app.state.engine:
        logger.info("Closing PostgreSQL connection...")
        await app.state.engine.dispose()
    logger.info("Closing Valkey connection...")
    await app.state.valkey.aclose()


app = FastAPI(
    title="The Foundry API",
    version=VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    servers=SERVERS,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
install_openapi_customization(app)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

_collector = EndpointMetricsCollector()
app.state.endpoint_metrics_collector = _collector

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def _request_metrics_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    req_bytes = int(request.headers.get("content-length", 0))
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    resp_bytes = int(response.headers.get("content-length", 0))
    route = request.scope.get("route")
    path = route.path if route else request.url.path
    _collector.record(
        request.method, path, response.status_code, duration_ms, req_bytes, resp_bytes
    )
    return response


app.include_router(meta.router)
app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(clan.router)
app.include_router(metrics.router)
app.include_router(config.router)
app.include_router(discord_router.router)
app.include_router(events.router)
app.include_router(ccdispatch.router)
app.include_router(members.router)
app.include_router(music.router)
app.include_router(parties.router)
app.include_router(ranking.router)
app.include_router(reference.router)
app.include_router(role_panels.router)
app.include_router(runelite_configs.router)
app.include_router(staff.router)
app.include_router(surveys.router)
app.include_router(feedback.router)
app.include_router(badges.router)
app.include_router(content.router)
app.include_router(frenzy.router)
app.include_router(ironclad.router)
app.include_router(tilerace.router)
app.include_router(ticket_config.router)
app.include_router(osrs_cache.router)


@app.get("/docs", include_in_schema=False)
async def scalar_docs() -> HTMLResponse:
    return render_reference(app.openapi_url or "/openapi.json", app.title)
