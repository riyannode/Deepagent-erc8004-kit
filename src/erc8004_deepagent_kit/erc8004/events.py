from __future__ import annotations

from dataclasses import dataclass

from eth_utils import event_abi_to_log_topic
from web3 import Web3

from .abi_identity import IDENTITY_REGISTRY_ABI

TRANSFER_EVENT_ABI = next(item for item in IDENTITY_REGISTRY_ABI if item.get("type") == "event" and item.get("name") == "Transfer")
TRANSFER_TOPIC = Web3.to_hex(event_abi_to_log_topic(TRANSFER_EVENT_ABI))
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def address_topic(address: str) -> str:
    checksum = Web3.to_checksum_address(address)
    return "0x" + "0" * 24 + checksum[2:].lower()


def int_from_topic(topic: str | bytes) -> int:
    if isinstance(topic, bytes):
        return int.from_bytes(topic, byteorder="big")
    return int(topic, 16)


@dataclass(frozen=True)
class MintEvent:
    agent_id: str
    owner: str
    tx_hash: str
    block_number: int
    log_index: int
