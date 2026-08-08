"""Single-Owner authentication and in-memory Session authority."""

from __future__ import annotations

import asyncio
import heapq
import secrets
import unicodedata
from dataclasses import dataclass, field

import anyio
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadData, URLSafeSerializer
from pydantic import ConfigDict, Field, field_validator, model_validator

from src.trading_kernel.application.owner_console.models import FrozenModel

_SERIALIZER_SALT = "brc-owner-console-session-v1"
_FAILURE_LIMIT = 5
_FAILURE_WINDOW_MS = 15 * 60_000
_COOLDOWN_MS = 15 * 60_000
_MAX_FAILURE_KEYS = 4096
_MAX_USERNAME_LENGTH = 256
_MAX_PASSWORD_HASH_LENGTH = 1024
_MAX_TOTP_SEED_LENGTH = 256
_MAX_SIGNING_KEY_LENGTH = 1024


class InvalidCredentials(Exception):
    """Generic failure for every invalid authentication factor."""

    def __init__(self) -> None:
        super().__init__("authentication failed")


class LoginThrottled(Exception):
    """Generic failure while a login identity is cooling down."""

    def __init__(self) -> None:
        super().__init__("authentication unavailable")


class OwnerAuthSettings(FrozenModel):
    """Fail-closed credentials and Session lifetime configuration."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    username: str = Field(
        min_length=1,
        max_length=_MAX_USERNAME_LENGTH,
        repr=False,
    )
    password_hash: str = Field(
        min_length=1,
        max_length=_MAX_PASSWORD_HASH_LENGTH,
        repr=False,
    )
    totp_seed: str = Field(
        min_length=1,
        max_length=_MAX_TOTP_SEED_LENGTH,
        repr=False,
    )
    session_signing_key: str = Field(
        min_length=1,
        max_length=_MAX_SIGNING_KEY_LENGTH,
        repr=False,
    )
    idle_timeout_ms: int = Field(default=30 * 60_000, gt=0)
    absolute_timeout_ms: int = Field(default=12 * 60 * 60_000, gt=0)

    @field_validator(
        "username",
        "password_hash",
        "totp_seed",
        "session_signing_key",
    )
    @classmethod
    def _require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("authentication setting must not be blank")
        return value

    @field_validator("password_hash")
    @classmethod
    def _require_argon2id_hash(cls, value: str) -> str:
        if not value.startswith("$argon2id$"):
            raise ValueError("password_hash must be a valid Argon2id hash")
        try:
            needs_rehash = _PASSWORD_HASHER.check_needs_rehash(value)
        except InvalidHashError as error:
            raise ValueError("password_hash must be a valid Argon2id hash") from error
        if needs_rehash:
            raise ValueError("password_hash must use the required Argon2id parameters")
        return value

    @field_validator("totp_seed")
    @classmethod
    def _require_valid_totp_seed(cls, value: str) -> str:
        try:
            pyotp.TOTP(value, interval=30).at(30)
        except (TypeError, ValueError) as error:
            raise ValueError("totp_seed must be valid Base32") from error
        return value

    @model_validator(mode="after")
    def _require_absolute_timeout_not_shorter_than_idle(self) -> OwnerAuthSettings:
        if self.absolute_timeout_ms < self.idle_timeout_ms:
            raise ValueError("absolute_timeout_ms must be at least idle_timeout_ms")
        return self


class LoginSession(FrozenModel):
    """Signed Session cookie returned only to the HTTP boundary."""

    cookie: str = Field(repr=False)


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """The sole process-local authenticated Session record."""

    session_id: str = field(repr=False)
    issued_at_ms: int
    last_seen_at_ms: int


@dataclass(frozen=True, slots=True)
class _FailureRecord:
    failure_times_ms: tuple[int, ...]
    expires_at_ms: int
    cooldown_until_ms: int | None = None


_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


class OwnerAuthService:
    """Race-safe single-Owner authentication with one in-memory Session."""

    def __init__(self, settings: OwnerAuthSettings) -> None:
        self._settings = settings
        self._totp = pyotp.TOTP(settings.totp_seed, interval=30)
        self._serializer = URLSafeSerializer(
            settings.session_signing_key,
            salt=_SERIALIZER_SALT,
        )
        self._lock = asyncio.Lock()
        self._session: SessionRecord | None = None
        self._failures: dict[tuple[str, str], _FailureRecord] = {}
        self._failure_expiries: list[tuple[int, tuple[str, str]]] = []

    async def login(
        self,
        *,
        username: str,
        password: str,
        totp_code: str,
        source_ip: str,
        now_ms: int,
    ) -> LoginSession:
        """Authenticate all factors and atomically replace the active Session."""

        _require_nonnegative_time(now_ms)
        throttle_key = (_normalize_throttle_username(username), source_ip)
        async with self._lock:
            self._purge_expired_failures_locked(now_ms=now_ms)
            if (
                throttle_key not in self._failures
                and len(self._failures) >= _MAX_FAILURE_KEYS
            ):
                raise LoginThrottled
            if self._is_throttled_locked(throttle_key, now_ms=now_ms):
                raise LoginThrottled

        password_valid = await anyio.to_thread.run_sync(
            _verify_password,
            self._settings.password_hash,
            password,
        )
        username_valid = secrets.compare_digest(
            username.encode("utf-8", errors="surrogatepass"),
            self._settings.username.encode("utf-8", errors="surrogatepass"),
        )
        totp_valid = self._verify_totp(totp_code, now_ms=now_ms)
        credentials_valid = password_valid & username_valid & totp_valid

        async with self._lock:
            if not credentials_valid:
                if (
                    throttle_key not in self._failures
                    and len(self._failures) >= _MAX_FAILURE_KEYS
                ):
                    raise LoginThrottled
                self._record_failure_locked(throttle_key, now_ms=now_ms)
                raise InvalidCredentials

            self._failures.pop(throttle_key, None)
            session_id = secrets.token_urlsafe(32)
            self._session = SessionRecord(
                session_id=session_id,
                issued_at_ms=now_ms,
                last_seen_at_ms=now_ms,
            )
            cookie = self._serializer.dumps(session_id)
            return LoginSession(cookie=cookie)

    async def validate_cookie(self, cookie: str | None, *, now_ms: int) -> bool:
        """Validate the signed cookie and slide the idle timeout when active."""

        _require_nonnegative_time(now_ms)
        session_id = self._deserialize_session_id(cookie)
        if session_id is None:
            return False

        async with self._lock:
            record = self._session
            if record is None or not secrets.compare_digest(
                record.session_id,
                session_id,
            ):
                return False
            if self._is_expired(record, now_ms=now_ms):
                self._session = None
                return False
            self._session = SessionRecord(
                session_id=record.session_id,
                issued_at_ms=record.issued_at_ms,
                last_seen_at_ms=max(record.last_seen_at_ms, now_ms),
            )
            return True

    async def logout(self, cookie: str | None) -> None:
        """Invalidate the matching Session; repeated or bad cookies are no-ops."""

        session_id = self._deserialize_session_id(cookie)
        if session_id is None:
            return

        async with self._lock:
            record = self._session
            if record is not None and secrets.compare_digest(
                record.session_id,
                session_id,
            ):
                self._session = None

    async def session_status(self, cookie: str | None, *, now_ms: int) -> bool:
        """Return only whether the supplied cookie owns the active Session."""

        return await self.validate_cookie(cookie, now_ms=now_ms)

    def _verify_totp(self, code: str, *, now_ms: int) -> bool:
        try:
            return self._totp.verify(
                code,
                for_time=now_ms / 1000,  # type: ignore[arg-type]
                valid_window=1,
            )
        except (TypeError, ValueError):
            return False

    def _deserialize_session_id(self, cookie: str | None) -> str | None:
        if not cookie:
            return None
        try:
            payload = self._serializer.loads(cookie)
        except (BadData, TypeError, ValueError):
            return None
        return payload if isinstance(payload, str) and payload else None

    def _is_expired(self, record: SessionRecord, *, now_ms: int) -> bool:
        return (
            now_ms - record.last_seen_at_ms >= self._settings.idle_timeout_ms
            or now_ms - record.issued_at_ms >= self._settings.absolute_timeout_ms
        )

    def _is_throttled_locked(
        self,
        key: tuple[str, str],
        *,
        now_ms: int,
    ) -> bool:
        record = self._failures.get(key)
        if record is None:
            return False
        if record.cooldown_until_ms is not None:
            if now_ms < record.cooldown_until_ms:
                return True
            self._failures.pop(key, None)
            return False

        current_failures = _current_failure_times(
            record.failure_times_ms,
            now_ms=now_ms,
        )
        if current_failures:
            if current_failures != record.failure_times_ms:
                self._failures[key] = _FailureRecord(
                    failure_times_ms=current_failures,
                    expires_at_ms=record.expires_at_ms,
                )
        else:
            self._failures.pop(key, None)
        return False

    def _record_failure_locked(
        self,
        key: tuple[str, str],
        *,
        now_ms: int,
    ) -> None:
        existing = self._failures.get(key)
        prior_times = () if existing is None else existing.failure_times_ms
        current_times = _current_failure_times(prior_times, now_ms=now_ms)
        new_times = (*current_times, now_ms)
        cooldown_until_ms = (
            now_ms + _COOLDOWN_MS if len(new_times) >= _FAILURE_LIMIT else None
        )
        expires_at_ms = cooldown_until_ms or now_ms + _FAILURE_WINDOW_MS
        record = _FailureRecord(
            failure_times_ms=new_times,
            expires_at_ms=expires_at_ms,
            cooldown_until_ms=cooldown_until_ms,
        )
        self._failures[key] = record
        heapq.heappush(self._failure_expiries, (record.expires_at_ms, key))

    def _purge_expired_failures_locked(self, *, now_ms: int) -> None:
        while self._failure_expiries and self._failure_expiries[0][0] <= now_ms:
            expires_at_ms, key = heapq.heappop(self._failure_expiries)
            record = self._failures.get(key)
            if record is not None and record.expires_at_ms == expires_at_ms:
                self._failures.pop(key, None)


def _verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def _normalize_throttle_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def _current_failure_times(
    failure_times_ms: tuple[int, ...],
    *,
    now_ms: int,
) -> tuple[int, ...]:
    return tuple(
        failure_time
        for failure_time in failure_times_ms
        if 0 <= now_ms - failure_time < _FAILURE_WINDOW_MS
    )


def _require_nonnegative_time(now_ms: int) -> None:
    if now_ms < 0:
        raise ValueError("now_ms must be nonnegative")
