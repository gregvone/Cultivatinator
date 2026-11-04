"""Explicit backup authentication policy; shared with the stdlib host helper."""

from dataclasses import dataclass
import ipaddress
import re


def peer_address(value):
    address = ipaddress.ip_address(value)
    return (
        address.ipv4_mapped
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped
        else address
    )


@dataclass(frozen=True)
class BackupPolicy:
    mode: str = "password"
    networks: str = ""

    def __post_init__(self):
        if self.mode not in {"password", "trusted_lan"}:
            raise ValueError("Backup auth mode must be password or trusted_lan")
        if not isinstance(self.networks, str) or len(self.networks) > 4096:
            raise ValueError("Trusted networks must be comma-separated CIDRs")
        entries = [part.strip() for part in self.networks.split(",") if part.strip()]
        if len(entries) > 32:
            raise ValueError("At most 32 trusted networks are supported")
        try:
            parsed = tuple(ipaddress.ip_network(part, strict=True) for part in entries)
        except ValueError as exc:
            raise ValueError(
                "Trusted networks must contain valid, explicit CIDRs"
            ) from exc
        if any(network.prefixlen == 0 for network in parsed):
            raise ValueError("An unrestricted /0 is not a trusted LAN network")
        if self.mode == "trusted_lan" and not parsed:
            raise ValueError("trusted_lan requires explicit trusted networks")
        object.__setattr__(self, "allowed", parsed)

    @property
    def cidrs(self):
        return sorted({str(network) for network in self.allowed})

    def require_peer(self, value):
        try:
            address = peer_address(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "The connection address is not in a configured trusted network"
            ) from exc
        if not any(
            address.version == network.version and address in network
            for network in self.allowed
        ):
            raise ValueError(
                "The connection address is not in a configured trusted network"
            )
        return str(address)

    def allows_host(self, value):
        # Host/Origin equality alone is insufficient for a passwordless endpoint:
        # reject public DNS names to prevent DNS rebinding into the private app.
        host = (value or "").lower().rstrip(".")
        try:
            self.require_peer(host)
            return True
        except ValueError:
            pass
        if host == "localhost":
            try:
                self.require_peer("127.0.0.1")
                return True
            except ValueError:
                return False
        return bool(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.local)?", host)
        )
